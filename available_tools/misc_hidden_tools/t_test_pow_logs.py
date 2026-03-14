#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
import re
from datetime import datetime
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
DEFAULT_MAX_DRIFT_BETWEEN_MSG_SEC = 1e-6
DEFAULT_CHECK_TIMESTAMP = True
DEFAULT_MAX_DRIFT_BETWEEN_MSG_SECONDS = 0.05

ARG_LOG_PATHS = f"{ARGUMENT_LONG_PREFIX}log_paths"
ARG_MESSAGE_TYPES = f"{ARGUMENT_LONG_PREFIX}message_types"
ARG_SECONDS_PER_MESSAGE = f"{ARGUMENT_LONG_PREFIX}secs_per_message"
ARG_MAX_DRIFT_BETWEEN_MSG = f"{ARGUMENT_LONG_PREFIX}between_msg_drift"
ARG_CHECK_TIMESTAMP = f"{ARGUMENT_LONG_PREFIX}check_timestamp"
ARG_MAX_DRIFT_BETWEEN_MSG_TIME = f"{ARGUMENT_LONG_PREFIX}max_drift_between_msg_time"

LINE_TIMESTAMP_PATTERN = re.compile(r"^\[(?P<ts>[^\]]+)\]\s*(?P<payload>.*)$")


@dataclass
class PowEntry:
    message_type: str
    timestamp_token: str
    total_seconds: float
    line_number: int
    raw_line: str
    source_path: Path
    line_timestamp_seconds: Optional[float] = None


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name=f"Check {POWTLV_MESSAGE_TYPE} timing",
            extra_description="Verify POW sentence timestamps advance at a fixed interval.",
            args={
                ARG_LOG_PATHS: [str(DEFAULT_POW_LOG_PATH)],
                ARG_MESSAGE_TYPES: list(DEFAULT_POW_MESSAGE_TYPES),
                ARG_SECONDS_PER_MESSAGE: DEFAULT_SECONDS_PER_MESSAGE,
                ARG_MAX_DRIFT_BETWEEN_MSG: DEFAULT_MAX_DRIFT_BETWEEN_MSG_SEC,
                ARG_CHECK_TIMESTAMP: DEFAULT_CHECK_TIMESTAMP,
                ARG_MAX_DRIFT_BETWEEN_MSG_TIME: DEFAULT_MAX_DRIFT_BETWEEN_MSG_SECONDS,
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
                ARG_MAX_DRIFT_BETWEEN_MSG: DEFAULT_MAX_DRIFT_BETWEEN_MSG_SEC,
                ARG_CHECK_TIMESTAMP: DEFAULT_CHECK_TIMESTAMP,
                ARG_MAX_DRIFT_BETWEEN_MSG_TIME: DEFAULT_MAX_DRIFT_BETWEEN_MSG_SECONDS,
            },
            search_root=PERSISTENT_TEMP_PATH / "live_logs",
            usage_note="Point --log_paths at one or more captured live-log files.",
        ),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def _parse_bool_arg(raw_value: str | bool) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    return str(raw_value).strip().lower() in {"1", "true", "yes", "y", "on"}


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
    parser.add_argument(ARG_MAX_DRIFT_BETWEEN_MSG, type=float, default=DEFAULT_MAX_DRIFT_BETWEEN_MSG_SEC,
                        help="Allowed absolute drift in seconds between consecutive POW message timestamps.")
    parser.add_argument(ARG_CHECK_TIMESTAMP, nargs="?", const=True, type=_parse_bool_arg, default=DEFAULT_CHECK_TIMESTAMP,
                        help="Also validate host log line timestamps (true or false). Defaults to true.")
    parser.add_argument(ARG_MAX_DRIFT_BETWEEN_MSG_TIME, type=float, default=DEFAULT_MAX_DRIFT_BETWEEN_MSG_SECONDS,
                        help="Allowed +/- drift in seconds around --secs_per_message for line timestamp checks.")
    return parser.parse_args(argv)


def _normalize_message_type(raw_prefix: str) -> str:
    return raw_prefix.lstrip("$").strip()


def _parse_pow_timestamp(timestamp_token: str) -> float:
    if len(timestamp_token) < 6 or not timestamp_token.isdigit():
        raise ValueError(f"Invalid POW timestamp token: {timestamp_token}")
    # POW logs use a scalar timestamp token where the last 6 digits are fractional seconds.
    return int(timestamp_token) / 1_000_000.0


def _extract_line_timestamp_and_payload(raw_line: str) -> tuple[Optional[float], str]:
    stripped = raw_line.strip()
    if not stripped:
        return None, ""
    match = LINE_TIMESTAMP_PATTERN.match(stripped)
    if not match:
        return None, stripped
    timestamp_text = match.group("ts").strip()
    payload = match.group("payload").strip()
    try:
        parsed = datetime.strptime(timestamp_text, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return None, payload
    return parsed.timestamp(), payload


def _scan_pow_entries(log_path: Path, message_types: Sequence[str]) -> Dict[str, List[PowEntry]]:
    normalized_types = {_normalize_message_type(message_type) for message_type in message_types}
    results: Dict[str, List[PowEntry]] = {message_type: [] for message_type in normalized_types}
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line_timestamp_seconds, payload_line = _extract_line_timestamp_and_payload(raw_line)
            if not payload_line:
                continue
            payload = payload_line.split("*", 1)[0]
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
                                                  line_number=line_number, raw_line=payload_line, source_path=log_path,
                                                  line_timestamp_seconds=line_timestamp_seconds))
    return results


def _calc_delta_seconds(previous_seconds: float, current_seconds: float) -> float:
    delta = current_seconds - previous_seconds
    if delta < -43200:
        return delta + 86400
    return delta


def _format_entry(entry: PowEntry) -> str:
    return f"{entry.source_path}:{entry.line_number} {entry.message_type} {entry.timestamp_token}"


def analyze_pow_entries(entries: Sequence[PowEntry], expected_seconds_per_message: float,
                        max_drift_between_msg: float) -> List[str]:
    issues: List[str] = []
    if len(entries) < 2:
        return issues
    previous = entries[0]
    for current in entries[1:]:
        delta = _calc_delta_seconds(previous.total_seconds, current.total_seconds)
        if abs(delta - expected_seconds_per_message) > max_drift_between_msg:
            issues.append(f"Unexpected delta BETWEEN MSG {delta:.6f}s (expected {expected_seconds_per_message:.6f}s +- {max_drift_between_msg:.6f}s) between {_format_entry(previous)} -> {_format_entry(current)}")
        previous = current
    return issues


def analyze_log_timestamp_drift(entries: Sequence[PowEntry], expected_seconds_per_message: float,
                                max_drift_between_msg_time: float) -> List[str]:
    issues: List[str] = []
    if len(entries) < 2:
        return issues
    lower_bound, upper_bound = (expected_seconds_per_message - max_drift_between_msg_time,
                                expected_seconds_per_message + max_drift_between_msg_time)
    previous = entries[0]
    for current in entries[1:]:
        if previous.line_timestamp_seconds is None or current.line_timestamp_seconds is None:
            previous = current
            continue
        delta = current.line_timestamp_seconds - previous.line_timestamp_seconds
        if delta < lower_bound or delta > upper_bound:
            issues.append(f"Unexpected delta BETWEEN LINE TIMESTAMP {delta:.6f}s out of [{lower_bound:.6f}s, {upper_bound:.6f}s] between {_format_entry(previous)} -> {_format_entry(current)}")
        previous = current
    return issues


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    log_paths = [Path(path).expanduser() for path in get_arg_value(args, ARG_LOG_PATHS)]
    message_types = [_normalize_message_type(message_type) for message_type in get_arg_value(args, ARG_MESSAGE_TYPES)]
    expected_seconds_per_message = float(get_arg_value(args, ARG_SECONDS_PER_MESSAGE))
    max_drift_between_msg = float(get_arg_value(args, ARG_MAX_DRIFT_BETWEEN_MSG))
    check_timestamp = bool(get_arg_value(args, ARG_CHECK_TIMESTAMP))
    max_drift_between_msg_time = float(get_arg_value(args, ARG_MAX_DRIFT_BETWEEN_MSG_TIME))

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
        issues = analyze_pow_entries(entries, expected_seconds_per_message=expected_seconds_per_message,
                                     max_drift_between_msg=max_drift_between_msg)
        if check_timestamp:
            issues.extend(analyze_log_timestamp_drift(entries, expected_seconds_per_message=expected_seconds_per_message,
                                                      max_drift_between_msg_time=max_drift_between_msg_time))
        if issues:
            has_issue = True
            LOG(f"{LOG_PREFIX_MSG_ERROR} {message_type}: found {len(issues)} timing issue(s) across {len(entries)} entries of type {message_type}.")
            for issue in issues:
                LOG(issue)
        else:
            LOG(f"{LOG_PREFIX_MSG_INFO} {message_type}: {len(entries)} entries checked, all deltas matched {expected_seconds_per_message:.6f}s.")

    if has_issue:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
