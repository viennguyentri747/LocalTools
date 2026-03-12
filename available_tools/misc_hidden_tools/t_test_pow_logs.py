#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from dev.dev_common import *

POWGPS_MESSAGE_TYPE = "POWGPS"
POWTLV_MESSAGE_TYPE = "POWTLV"
DEFAULT_POW_LOG_PATH = PERSISTENT_TEMP_PATH / "live_logs" / "ttymxc0_56.log"
DEFAULT_POW_MESSAGE_TYPES = [POWTLV_MESSAGE_TYPE]
DEFAULT_SECONDS_PER_MESSAGE = 0.2
DEFAULT_POWGPS_SECONDS_PER_MESSAGE = 1.0
DEFAULT_TIME_TOLERANCE_SEC = 1e-6

ARG_LOG_PATHS = f"{ARGUMENT_LONG_PREFIX}log_paths"
ARG_MESSAGE_TYPES = f"{ARGUMENT_LONG_PREFIX}message_types"
ARG_SECONDS_PER_MESSAGE = f"{ARGUMENT_LONG_PREFIX}secs_per_message"
ARG_TOLERANCE = f"{ARGUMENT_LONG_PREFIX}tolerance"


@dataclass
class PowEntry:
    message_type: str
    timestamp_token: str
    total_seconds: float
    line_number: int
    raw_line: str
    source_path: Path


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name=f"Check {POWTLV_MESSAGE_TYPE} timing",
            extra_description="Verify POW sentence timestamps advance at a fixed interval.",
            args={
                ARG_LOG_PATHS: [str(DEFAULT_POW_LOG_PATH)],
                ARG_MESSAGE_TYPES: list(DEFAULT_POW_MESSAGE_TYPES),
                ARG_SECONDS_PER_MESSAGE: DEFAULT_SECONDS_PER_MESSAGE,
            },
            search_root=PERSISTENT_TEMP_PATH / "live_logs",
            usage_note="Point --log_paths at one or more captured live-log files.",
        ),
        ToolTemplate(
            name=f"Check {POWGPS_MESSAGE_TYPE} timing",
            extra_description="Verify POWGPS sentence timestamps advance at a fixed interval.",
            args={
                ARG_LOG_PATHS: [str(DEFAULT_POW_LOG_PATH)],
                ARG_MESSAGE_TYPES: [POWGPS_MESSAGE_TYPE],
                ARG_SECONDS_PER_MESSAGE: DEFAULT_POWGPS_SECONDS_PER_MESSAGE,
            },
            search_root=PERSISTENT_TEMP_PATH / "live_logs",
            usage_note="Point --log_paths at one or more captured live-log files.",
        ),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether POW sentence timestamps increase at the expected cadence.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_LOG_PATHS, nargs="+", type=Path, required=True, help="One or more local log files to scan.")
    parser.add_argument(ARG_MESSAGE_TYPES, nargs="+", default=list(DEFAULT_POW_MESSAGE_TYPES),
                        help=f"POW sentence types to validate, e.g. {POWTLV_MESSAGE_TYPE} {POWGPS_MESSAGE_TYPE}.")
    parser.add_argument(ARG_SECONDS_PER_MESSAGE, type=float, default=DEFAULT_SECONDS_PER_MESSAGE,
                        help="Expected timestamp delta in seconds between consecutive messages of the same type.")
    parser.add_argument(ARG_TOLERANCE, type=float, default=DEFAULT_TIME_TOLERANCE_SEC,
                        help="Allowed absolute error in seconds when comparing time deltas.")
    return parser.parse_args(argv)


def _normalize_message_type(raw_prefix: str) -> str:
    return raw_prefix.lstrip("$").strip()


def _parse_pow_timestamp(timestamp_token: str) -> float:
    if len(timestamp_token) < 6 or not timestamp_token.isdigit():
        raise ValueError(f"Invalid POW timestamp token: {timestamp_token}")
    # POW logs use a scalar timestamp token where the last 6 digits are fractional seconds.
    return int(timestamp_token) / 1_000_000.0


def _scan_pow_entries(log_path: Path, message_types: Sequence[str]) -> Dict[str, List[PowEntry]]:
    normalized_types = {_normalize_message_type(message_type) for message_type in message_types}
    results: Dict[str, List[PowEntry]] = {message_type: [] for message_type in normalized_types}
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            payload = stripped.split("*", 1)[0]
            parts = payload.split(",")
            if len(parts) < 4:
                continue
            message_type = _normalize_message_type(parts[0])
            if message_type not in normalized_types:
                continue
            timestamp_token = parts[3].strip()
            try:
                total_seconds = _parse_pow_timestamp(timestamp_token)
            except ValueError:
                LOG(f"{LOG_PREFIX_MSG_WARNING} Skipping malformed {message_type} timestamp '{timestamp_token}' at {log_path}:{line_number}")
                continue
            results[message_type].append(PowEntry(message_type=message_type, timestamp_token=timestamp_token, total_seconds=total_seconds,
                                                  line_number=line_number, raw_line=stripped, source_path=log_path))
    return results


def _calc_delta_seconds(previous_seconds: float, current_seconds: float) -> float:
    delta = current_seconds - previous_seconds
    if delta < -43200:
        return delta + 86400
    return delta


def _format_entry(entry: PowEntry) -> str:
    return f"{entry.source_path}:{entry.line_number} {entry.message_type} {entry.timestamp_token}"


def analyze_pow_entries(entries: Sequence[PowEntry], expected_seconds_per_message: float, tolerance: float) -> List[str]:
    issues: List[str] = []
    if len(entries) < 2:
        return issues
    previous = entries[0]
    for current in entries[1:]:
        delta = _calc_delta_seconds(previous.total_seconds, current.total_seconds)
        if abs(delta - expected_seconds_per_message) > tolerance:
            issues.append(f"Unexpected delta {delta:.6f}s (expected {expected_seconds_per_message:.6f}s) between {_format_entry(previous)} -> {_format_entry(current)}")
        previous = current
    return issues


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    log_paths = [Path(path).expanduser() for path in get_arg_value(args, ARG_LOG_PATHS)]
    message_types = [_normalize_message_type(message_type) for message_type in get_arg_value(args, ARG_MESSAGE_TYPES)]
    expected_seconds_per_message = float(get_arg_value(args, ARG_SECONDS_PER_MESSAGE))
    tolerance = float(get_arg_value(args, ARG_TOLERANCE))

    all_entries_by_type: Dict[str, List[PowEntry]] = {message_type: [] for message_type in message_types}
    for log_path in log_paths:
        if not log_path.exists():
            LOG_EXCEPTION(ValueError(f"Log path not found: {log_path}"), exit=True)
        if not log_path.is_file():
            LOG_EXCEPTION(ValueError(f"Log path must be a file: {log_path}"), exit=True)
        scanned = _scan_pow_entries(log_path, message_types)
        for message_type in message_types:
            all_entries_by_type[message_type].extend(scanned.get(message_type, []))

    total_matches = sum(len(entries) for entries in all_entries_by_type.values())
    if total_matches == 0:
        LOG(f"{LOG_PREFIX_MSG_WARNING} No matching POW messages found for types: {', '.join(message_types)}")
        raise SystemExit(1)

    has_issue = False
    for message_type in message_types:
        entries = all_entries_by_type[message_type]
        if not entries:
            LOG(f"{LOG_PREFIX_MSG_WARNING} No entries found for {message_type}.")
            continue
        issues = analyze_pow_entries(entries, expected_seconds_per_message=expected_seconds_per_message, tolerance=tolerance)
        if issues:
            has_issue = True
            LOG(f"{LOG_PREFIX_MSG_ERROR} {message_type}: found {len(issues)} timing issue(s) across {len(entries)} entries.")
            for issue in issues:
                LOG(issue)
        else:
            LOG(f"{LOG_PREFIX_MSG_INFO} {message_type}: {len(entries)} entries checked, all deltas matched {expected_seconds_per_message:.6f}s.")

    if has_issue:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
