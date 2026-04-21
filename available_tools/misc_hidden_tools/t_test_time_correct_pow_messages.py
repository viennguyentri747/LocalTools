#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
import bisect
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

from dev.dev_common import *

POWGPS_MESSAGE_TYPE = "POWGPS"
POWTLV_MESSAGE_TYPE = "POWTLV"
DEFAULT_REFERENCE_TYPES = ["GNZDA", "GXZDA", "GPZDA"]
DEFAULT_POW_LOG_PATH = WSL_PERSISTENT_TEMP_PATH / "live_logs" / "ttymxc0_56.log"

DEFAULT_EXPECTED_POWGPS_SEC = 1.0
DEFAULT_EXPECTED_POWTLV_SEC = 0.2
DEFAULT_MAX_POW_DELTA_DRIFT_SEC = 1e-6
DEFAULT_MAX_HOST_DELTA_DRIFT_SEC = 0.15
DEFAULT_MAX_HOST_OFFSET_JITTER_SEC = 0.20
DEFAULT_MAX_POWGPS_REF_UTC_DRIFT_SEC = 1e-6
DEFAULT_MAX_POWGPS_REF_HOST_DELTA_SEC = 0.12

ARG_LOG_PATHS = f"{ARGUMENT_LONG_PREFIX}log_paths"
ARG_REFERENCE_TYPES = f"{ARGUMENT_LONG_PREFIX}reference_types"
ARG_EXPECTED_POWGPS_SEC = f"{ARGUMENT_LONG_PREFIX}expected_powgps_sec"
ARG_EXPECTED_POWTLV_SEC = f"{ARGUMENT_LONG_PREFIX}expected_powtlv_sec"
ARG_MAX_POW_DELTA_DRIFT_SEC = f"{ARGUMENT_LONG_PREFIX}max_pow_delta_drift_sec"
ARG_MAX_HOST_DELTA_DRIFT_SEC = f"{ARGUMENT_LONG_PREFIX}max_host_delta_drift_sec"
ARG_MAX_HOST_OFFSET_JITTER_SEC = f"{ARGUMENT_LONG_PREFIX}max_host_offset_jitter_sec"
ARG_MAX_POWGPS_REF_UTC_DRIFT_SEC = f"{ARGUMENT_LONG_PREFIX}max_powgps_ref_utc_drift_sec"
ARG_MAX_POWGPS_REF_HOST_DELTA_SEC = f"{ARGUMENT_LONG_PREFIX}max_powgps_ref_host_delta_sec"

LINE_TIMESTAMP_PATTERN = re.compile(r"^\[(?P<ts>[^\]]+)\]\s*(?P<payload>.*)$")
GPS_EPOCH_UTC_SECONDS = datetime(1980, 1, 6, tzinfo=timezone.utc).timestamp()


@dataclass
class ParsedLine:
    line_number: int
    source_path: Path
    host_time_seconds: Optional[float]
    message_type: str
    parts: List[str]
    raw_payload: str


@dataclass
class PowMessage:
    line_number: int
    source_path: Path
    host_time_seconds: Optional[float]
    message_type: str
    gps_quality: Optional[int]
    gps_week: Optional[int]
    gps_tow_us: Optional[int]
    leap_valid: Optional[int]
    leap_seconds: Optional[int]
    holdover: Optional[int]
    raw_payload: str

    @property
    def utc_seconds(self) -> Optional[float]:
        # Convert GPS week/TOW plus leap-second offset into UTC epoch seconds.
        if self.gps_week is None or self.gps_tow_us is None or self.leap_seconds is None:
            return None
        return GPS_EPOCH_UTC_SECONDS + (self.gps_week * 7 * 86400) + (self.gps_tow_us / 1_000_000.0) - self.leap_seconds


@dataclass
class ReferenceMessage:
    line_number: int
    source_path: Path
    host_time_seconds: Optional[float]
    message_type: str
    utc_seconds: Optional[float]
    raw_payload: str


def get_tool_templates() -> List[ToolTemplate]:
    # Define reusable CLI template metadata for this validation tool.
    return [
        ToolTemplate(
            name="Comprehensive POW timing + GNZDA correlation check",
            extra_description="Validate POW cadence, POWGPS/POWTLV coherence, host offset stability, and reference UTC alignment.",
            args={
                ARG_LOG_PATHS: [str(DEFAULT_POW_LOG_PATH)],
                ARG_REFERENCE_TYPES: list(DEFAULT_REFERENCE_TYPES),
                ARG_EXPECTED_POWGPS_SEC: DEFAULT_EXPECTED_POWGPS_SEC,
                ARG_EXPECTED_POWTLV_SEC: DEFAULT_EXPECTED_POWTLV_SEC,
                ARG_MAX_POW_DELTA_DRIFT_SEC: DEFAULT_MAX_POW_DELTA_DRIFT_SEC,
                ARG_MAX_HOST_DELTA_DRIFT_SEC: DEFAULT_MAX_HOST_DELTA_DRIFT_SEC,
                ARG_MAX_HOST_OFFSET_JITTER_SEC: DEFAULT_MAX_HOST_OFFSET_JITTER_SEC,
                ARG_MAX_POWGPS_REF_UTC_DRIFT_SEC: DEFAULT_MAX_POWGPS_REF_UTC_DRIFT_SEC,
                ARG_MAX_POWGPS_REF_HOST_DELTA_SEC: DEFAULT_MAX_POWGPS_REF_HOST_DELTA_SEC,
            },
            search_root=WSL_PERSISTENT_TEMP_PATH / "live_logs",
            usage_note="Use --reference_types GNZDA when GNZDA is present in the same log.",
        ),
    ]


def getToolData() -> ToolData:
    # Expose tool metadata in the common wrapper format.
    return ToolData(tool_template=get_tool_templates())


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    # Parse and validate command-line arguments for thresholds and inputs.
    parser = argparse.ArgumentParser(
        description="Run comprehensive POW timing validation and optional correlation with reference ZDA sentences.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_LOG_PATHS, nargs="+", type=Path, required=True, help="One or more local log files to scan.")
    parser.add_argument(ARG_REFERENCE_TYPES, nargs="+", default=list(DEFAULT_REFERENCE_TYPES),
                        help="Reference sentence types for UTC correlation (e.g. GNZDA GXZDA).")
    parser.add_argument(ARG_EXPECTED_POWGPS_SEC, type=float, default=DEFAULT_EXPECTED_POWGPS_SEC,
                        help="Expected POWGPS interval in seconds.")
    parser.add_argument(ARG_EXPECTED_POWTLV_SEC, type=float, default=DEFAULT_EXPECTED_POWTLV_SEC,
                        help="Expected POWTLV interval in seconds.")
    parser.add_argument(ARG_MAX_POW_DELTA_DRIFT_SEC, type=float, default=DEFAULT_MAX_POW_DELTA_DRIFT_SEC,
                        help="Allowed absolute drift in internal POW timestamp delta.")
    parser.add_argument(ARG_MAX_HOST_DELTA_DRIFT_SEC, type=float, default=DEFAULT_MAX_HOST_DELTA_DRIFT_SEC,
                        help="Allowed absolute drift in host timestamp delta from expected cadence.")
    parser.add_argument(ARG_MAX_HOST_OFFSET_JITTER_SEC, type=float, default=DEFAULT_MAX_HOST_OFFSET_JITTER_SEC,
                        help="Allowed spread (max-min) for host_time - pow_utc offset per message type.")
    parser.add_argument(ARG_MAX_POWGPS_REF_UTC_DRIFT_SEC, type=float, default=DEFAULT_MAX_POWGPS_REF_UTC_DRIFT_SEC,
                        help="Allowed UTC drift between POWGPS and nearest reference sentence.")
    parser.add_argument(ARG_MAX_POWGPS_REF_HOST_DELTA_SEC, type=float, default=DEFAULT_MAX_POWGPS_REF_HOST_DELTA_SEC,
                        help="Allowed absolute host timestamp gap between POWGPS and nearest reference sentence.")
    return parser.parse_args(argv)


def _normalize_message_type(token: str) -> str:
    # Strip NMEA-style prefix/surrounding spaces to normalize message IDs.
    return token.lstrip("$").strip()


def _parse_line(raw_line: str, line_number: int, source_path: Path) -> Optional[ParsedLine]:
    # Parse one raw log line into timestamped payload parts used downstream.
    stripped = raw_line.strip()
    if not stripped:
        return None
    host_ts: Optional[float] = None
    payload = stripped
    match = LINE_TIMESTAMP_PATTERN.match(stripped)
    if match:
        payload = match.group("payload").strip()
        try:
            host_ts = datetime.strptime(match.group("ts").strip(), "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            host_ts = None
    if not payload:
        return None
    no_checksum = payload.split("*", 1)[0]
    parts = [part.strip() for part in no_checksum.split(",")]
    if not parts or not parts[0]:
        return None
    return ParsedLine(line_number=line_number, source_path=source_path, host_time_seconds=host_ts,
                      message_type=_normalize_message_type(parts[0]), parts=parts, raw_payload=payload)


def _to_int(raw: str) -> Optional[int]:
    # Safely parse a signed integer field, returning None for invalid values.
    value = raw.strip()
    if value.startswith("-"):
        return int(value) if value[1:].isdigit() else None
    return int(value) if value.isdigit() else None


def _parse_pow_message(line: ParsedLine) -> Optional[PowMessage]:
    # Convert a parsed CSV-like line into a POWGPS/POWTLV structured message.
    if line.message_type not in {POWGPS_MESSAGE_TYPE, POWTLV_MESSAGE_TYPE}:
        return None
    if len(line.parts) < 7:
        return None
    return PowMessage(
        line_number=line.line_number, source_path=line.source_path, host_time_seconds=line.host_time_seconds,
        message_type=line.message_type, gps_quality=_to_int(line.parts[1]), gps_week=_to_int(line.parts[2]),
        gps_tow_us=_to_int(line.parts[3]), leap_valid=_to_int(line.parts[4]), leap_seconds=_to_int(line.parts[5]),
        holdover=_to_int(line.parts[6]), raw_payload=line.raw_payload,
    )


def _parse_reference_message(line: ParsedLine, reference_types: Sequence[str]) -> Optional[ReferenceMessage]:
    # Convert a reference sentence (e.g., ZDA) into a UTC timestamped record.
    if line.message_type not in set(reference_types):
        return None
    if len(line.parts) < 5:
        return None
    hhmmss = line.parts[1].split(".", 1)[0]
    day = _to_int(line.parts[2])
    month = _to_int(line.parts[3])
    year = _to_int(line.parts[4])
    utc_seconds: Optional[float] = None
    if len(hhmmss) == 6 and hhmmss.isdigit() and day is not None and month is not None and year is not None:
        try:
            utc_seconds = datetime(year, month, day, int(hhmmss[0:2]), int(hhmmss[2:4]), int(hhmmss[4:6]),
                                   tzinfo=timezone.utc).timestamp()
        except ValueError:
            utc_seconds = None
    return ReferenceMessage(line_number=line.line_number, source_path=line.source_path, host_time_seconds=line.host_time_seconds,
                            message_type=line.message_type, utc_seconds=utc_seconds, raw_payload=line.raw_payload)


def _scan_messages(log_paths: Sequence[Path], reference_types: Sequence[str]) -> Tuple[Dict[str, List[PowMessage]], List[ReferenceMessage]]:
    # Read all logs and split recognized POW and reference messages into lists.
    pow_by_type: Dict[str, List[PowMessage]] = {POWGPS_MESSAGE_TYPE: [], POWTLV_MESSAGE_TYPE: []}
    refs: List[ReferenceMessage] = []
    normalized_refs = [_normalize_message_type(t) for t in reference_types]
    for log_path in log_paths:
        if not log_path.exists():
            LOG_EXCEPTION(ValueError(f"Log path not found: {log_path}"), exit=True)
        if not log_path.is_file():
            LOG_EXCEPTION(ValueError(f"Log path must be a file: {log_path}"), exit=True)
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                parsed = _parse_line(raw_line, line_number=line_number, source_path=log_path)
                if parsed is None:
                    continue
                pow_msg = _parse_pow_message(parsed)
                if pow_msg is not None:
                    pow_by_type[pow_msg.message_type].append(pow_msg)
                ref_msg = _parse_reference_message(parsed, normalized_refs)
                if ref_msg is not None:
                    refs.append(ref_msg)
    return pow_by_type, refs


def _format_msg(msg: PowMessage | ReferenceMessage) -> str:
    # Build a compact source/location label for diagnostics.
    return f"{msg.source_path}:{msg.line_number} {msg.message_type}"


def _calc_delta_with_week_rollover(previous: PowMessage, current: PowMessage) -> Optional[float]:
    # Compute elapsed GPS seconds between two messages using week+TOW fields.
    if previous.gps_week is None or current.gps_week is None or previous.gps_tow_us is None or current.gps_tow_us is None:
        return None
    prev_total = (previous.gps_week * 7 * 86400) + (previous.gps_tow_us / 1_000_000.0)
    cur_total = (current.gps_week * 7 * 86400) + (current.gps_tow_us / 1_000_000.0)
    return cur_total - prev_total


def _check_cadence(entries: Sequence[PowMessage], expected_delta: float, max_pow_delta_drift: float,
                   max_host_delta_drift: float) -> List[str]:
    # Validate message interval consistency in both embedded POW time and host time.
    issues: List[str] = []
    if len(entries) < 2:
        return issues
    previous = entries[0]
    for current in entries[1:]:
        pow_delta = _calc_delta_with_week_rollover(previous, current)
        if pow_delta is not None and abs(pow_delta - expected_delta) > max_pow_delta_drift:
            issues.append(f"Internal POW delta mismatch {pow_delta:.6f}s (expected {expected_delta:.6f}s +- {max_pow_delta_drift:.6f}s) "
                          f"between {_format_msg(previous)} -> {_format_msg(current)}")
        if previous.host_time_seconds is not None and current.host_time_seconds is not None:
            host_delta = current.host_time_seconds - previous.host_time_seconds
            if abs(host_delta - expected_delta) > max_host_delta_drift:
                issues.append(f"Host delta mismatch {host_delta:.6f}s (expected {expected_delta:.6f}s +- {max_host_delta_drift:.6f}s) "
                              f"between {_format_msg(previous)} -> {_format_msg(current)}")
        previous = current
    return issues


def _check_pow_header_consistency(entries: Sequence[PowMessage], message_type: str) -> List[str]:
    # Ensure status/header fields stay in expected healthy values across captures.
    issues: List[str] = []
    if not entries:
        return issues
    leap_values = sorted({entry.leap_seconds for entry in entries if entry.leap_seconds is not None})
    if len(leap_values) > 1:
        issues.append(f"{message_type} leap second changed within log: {leap_values}")
    bad_quality = [entry for entry in entries if entry.gps_quality not in {1}]
    if bad_quality:
        sample = bad_quality[0]
        issues.append(f"{message_type} contains invalid GPS quality at {_format_msg(sample)} value={sample.gps_quality}")
    bad_leap_valid = [entry for entry in entries if entry.leap_valid not in {1}]
    if bad_leap_valid:
        sample = bad_leap_valid[0]
        issues.append(f"{message_type} contains invalid leap-valid flag at {_format_msg(sample)} value={sample.leap_valid}")
    bad_holdover = [entry for entry in entries if entry.holdover not in {0}]
    if bad_holdover:
        sample = bad_holdover[0]
        issues.append(f"{message_type} entered holdover at {_format_msg(sample)} value={sample.holdover}")
    return issues


def _check_host_offset_stability(entries: Sequence[PowMessage], message_type: str, max_offset_jitter: float) -> List[str]:
    # Check spread of host_time minus POW UTC offset for jitter anomalies.
    offsets = [entry.host_time_seconds - entry.utc_seconds for entry in entries
               if entry.host_time_seconds is not None and entry.utc_seconds is not None]
    if not offsets:
        return []
    spread = max(offsets) - min(offsets)
    issues: List[str] = []
    if spread > max_offset_jitter:
        issues.append(f"{message_type} host-vs-POW-UTC offset spread too large: {spread:.6f}s > {max_offset_jitter:.6f}s "
                      f"(min={min(offsets):.6f}s max={max(offsets):.6f}s avg={mean(offsets):.6f}s)")
    return issues


def _check_powgps_powtlv_pairing(powgps_entries: Sequence[PowMessage], powtlv_entries: Sequence[PowMessage]) -> List[str]:
    # Verify POWTLV stream coheres with POWGPS in timestamp pairing and density.
    issues: List[str] = []
    if not powgps_entries or not powtlv_entries:
        return issues
    # Index TLV by exact TOW(us) so each 1Hz POWGPS message can be verified against its matching
    # TLV emitted at the same absolute GPS time (typically one TLV at that exact TOW and more at +200ms steps).
    tlv_by_tow: Dict[int, List[PowMessage]] = {}
    for tlv in powtlv_entries:
        if tlv.gps_tow_us is None:
            continue
        tlv_by_tow.setdefault(tlv.gps_tow_us, []).append(tlv)
    missing_tows: List[str] = []
    lag_values: List[float] = []
    tlv_count_per_second: Dict[int, int] = {}
    for tlv in powtlv_entries:
        if tlv.gps_tow_us is not None:
            sec_key = tlv.gps_tow_us // 1_000_000
            tlv_count_per_second[sec_key] = tlv_count_per_second.get(sec_key, 0) + 1
    # Build the observed 1Hz POWGPS-second timeline; used to validate TLV density per second.
    gps_seconds = sorted({gps.gps_tow_us // 1_000_000 for gps in powgps_entries if gps.gps_tow_us is not None})
    for gps in powgps_entries:
        if gps.gps_tow_us is None:
            continue
        paired = tlv_by_tow.get(gps.gps_tow_us, [])
        if not paired:
            missing_tows.append(f"{_format_msg(gps)} tow={gps.gps_tow_us}")
            continue
        if gps.host_time_seconds is not None:
            for tlv in paired:
                if tlv.host_time_seconds is not None:
                    # Positive lag means TLV was logged after POWGPS on host side.
                    lag_values.append(tlv.host_time_seconds - gps.host_time_seconds)
    if missing_tows:
        issues.append(f"Missing POWTLV entry matching POWGPS tow on {len(missing_tows)} case(s). Sample: {missing_tows[:3]}")
    if lag_values:
        min_lag, max_lag, avg_lag = min(lag_values), max(lag_values), mean(lag_values)
        if min_lag < -0.020 or max_lag > 0.300:
            issues.append(f"POWTLV arrival lag vs POWGPS out of range: min={min_lag:.6f}s max={max_lag:.6f}s avg={avg_lag:.6f}s (expected near 0..0.25s)")
    if gps_seconds:
        # Ignore partial leading/trailing capture windows: first/last second may be clipped by log start/end.
        complete_seconds = gps_seconds[1:-1] if len(gps_seconds) > 2 else gps_seconds
        counts = [tlv_count_per_second.get(sec, 0) for sec in complete_seconds]
        if min(counts) < 4 or max(counts) > 6:
            issues.append(f"Unexpected POWTLV count per POW second: min={min(counts)} max={max(counts)} (expected around 5)")
    return issues


def _check_powgps_reference_alignment(powgps_entries: Sequence[PowMessage], references: Sequence[ReferenceMessage],
                                      max_ref_utc_drift: float, max_ref_host_delta: float) -> List[str]:
    # Compare each POWGPS UTC+host timing to the nearest external UTC reference (like ZDA).
    issues: List[str] = []
    valid_refs = [ref for ref in references if ref.utc_seconds is not None]
    valid_powgps = [msg for msg in powgps_entries if msg.utc_seconds is not None]
    if not valid_refs or not valid_powgps:
        return issues
    # Reference list is already in log order; UTC is monotonic in normal captures.
    # We use bisect to find the nearest reference UTC in O(logN) per POWGPS sample.
    ref_utc_values = [ref.utc_seconds for ref in valid_refs if ref.utc_seconds is not None]
    utc_drifts: List[float] = []
    host_deltas: List[float] = []
    bad_utc: List[str] = []
    bad_host: List[str] = []
    for gps in valid_powgps:
        gps_utc = gps.utc_seconds
        if gps_utc is None:
            continue
        idx = bisect.bisect_left(ref_utc_values, gps_utc)
        candidates: List[ReferenceMessage] = []
        if idx < len(valid_refs):
            candidates.append(valid_refs[idx])
        if idx > 0:
            candidates.append(valid_refs[idx - 1])
        if not candidates:
            continue
        # Only two candidates are needed: nearest on the right and nearest on the left.
        nearest_ref = min(candidates, key=lambda ref: abs((ref.utc_seconds or 0.0) - gps_utc))
        drift = abs((nearest_ref.utc_seconds or 0.0) - gps_utc)
        utc_drifts.append(drift)
        if drift > max_ref_utc_drift:
            bad_utc.append(f"{_format_msg(gps)} vs {_format_msg(nearest_ref)} utc_drift={drift:.6f}s")
        if gps.host_time_seconds is not None and nearest_ref.host_time_seconds is not None:
            # Host delta is the queue/phase difference seen by the logger for equivalent UTC epochs.
            host_delta = abs(gps.host_time_seconds - nearest_ref.host_time_seconds)
            host_deltas.append(host_delta)
            if host_delta > max_ref_host_delta:
                bad_host.append(f"{_format_msg(gps)} vs {_format_msg(nearest_ref)} host_delta={host_delta:.6f}s")
    if bad_utc:
        issues.append(f"POWGPS vs reference UTC mismatch count={len(bad_utc)}; sample={bad_utc[:3]}")
    if bad_host:
        issues.append(f"POWGPS vs reference host timestamp gap too large count={len(bad_host)}; sample={bad_host[:3]}")
    if utc_drifts:
        LOG(f"{LOG_PREFIX_MSG_INFO} POWGPS->REF UTC drift stats (sec): min={min(utc_drifts):.6f}, max={max(utc_drifts):.6f}, avg={mean(utc_drifts):.6f}")
    if host_deltas:
        LOG(f"{LOG_PREFIX_MSG_INFO} POWGPS->REF host delta stats (sec): min={min(host_deltas):.6f}, max={max(host_deltas):.6f}, avg={mean(host_deltas):.6f}")
    return issues


def _log_basic_stats(pow_by_type: Dict[str, List[PowMessage]], references: Sequence[ReferenceMessage]) -> None:
    # Emit summary counts and host-vs-UTC offset stats for quick operator context.
    for message_type in [POWGPS_MESSAGE_TYPE, POWTLV_MESSAGE_TYPE]:
        entries = pow_by_type.get(message_type, [])
        if not entries:
            LOG(f"{LOG_PREFIX_MSG_WARNING} No {message_type} entries found.")
            continue
        offsets = [entry.host_time_seconds - entry.utc_seconds for entry in entries
                   if entry.host_time_seconds is not None and entry.utc_seconds is not None]
        if offsets:
            LOG(f"{LOG_PREFIX_MSG_INFO} {message_type} count={len(entries)} host_minus_pow_utc sec: min={min(offsets):.6f}, max={max(offsets):.6f}, avg={mean(offsets):.6f}")
        else:
            LOG(f"{LOG_PREFIX_MSG_INFO} {message_type} count={len(entries)}")
    if references:
        ref_offsets = [ref.host_time_seconds - ref.utc_seconds for ref in references
                       if ref.host_time_seconds is not None and ref.utc_seconds is not None]
        if ref_offsets:
            LOG(f"{LOG_PREFIX_MSG_INFO} Reference count={len(references)} host_minus_ref_utc sec: min={min(ref_offsets):.6f}, max={max(ref_offsets):.6f}, avg={mean(ref_offsets):.6f}")
        else:
            LOG(f"{LOG_PREFIX_MSG_INFO} Reference count={len(references)}")


def main(argv: Optional[Sequence[str]] = None) -> None:
    # Run end-to-end log scan, validation checks, reporting, and exit status.
    args = parse_args(argv)
    log_paths = [Path(path).expanduser() for path in get_arg_value(args, ARG_LOG_PATHS)]
    reference_types = [_normalize_message_type(t) for t in get_arg_value(args, ARG_REFERENCE_TYPES)]
    expected_powgps_sec = float(get_arg_value(args, ARG_EXPECTED_POWGPS_SEC))
    expected_powtlv_sec = float(get_arg_value(args, ARG_EXPECTED_POWTLV_SEC))
    max_pow_delta_drift = float(get_arg_value(args, ARG_MAX_POW_DELTA_DRIFT_SEC))
    max_host_delta_drift = float(get_arg_value(args, ARG_MAX_HOST_DELTA_DRIFT_SEC))
    max_host_offset_jitter = float(get_arg_value(args, ARG_MAX_HOST_OFFSET_JITTER_SEC))
    max_powgps_ref_utc_drift = float(get_arg_value(args, ARG_MAX_POWGPS_REF_UTC_DRIFT_SEC))
    max_powgps_ref_host_delta = float(get_arg_value(args, ARG_MAX_POWGPS_REF_HOST_DELTA_SEC))

    pow_by_type, references = _scan_messages(log_paths=log_paths, reference_types=reference_types)
    powgps_entries = pow_by_type.get(POWGPS_MESSAGE_TYPE, [])
    powtlv_entries = pow_by_type.get(POWTLV_MESSAGE_TYPE, [])
    if not powgps_entries and not powtlv_entries:
        LOG(f"{LOG_PREFIX_MSG_ERROR} No POWGPS/POWTLV entries found in selected logs.")
        raise SystemExit(1)

    _log_basic_stats(pow_by_type=pow_by_type, references=references)

    issues: List[str] = []
    issues.extend(_check_cadence(powgps_entries, expected_delta=expected_powgps_sec,
                                 max_pow_delta_drift=max_pow_delta_drift, max_host_delta_drift=max_host_delta_drift))
    issues.extend(_check_cadence(powtlv_entries, expected_delta=expected_powtlv_sec,
                                 max_pow_delta_drift=max_pow_delta_drift, max_host_delta_drift=max_host_delta_drift))
    issues.extend(_check_pow_header_consistency(powgps_entries, POWGPS_MESSAGE_TYPE))
    issues.extend(_check_pow_header_consistency(powtlv_entries, POWTLV_MESSAGE_TYPE))
    issues.extend(_check_host_offset_stability(powgps_entries, POWGPS_MESSAGE_TYPE, max_offset_jitter=max_host_offset_jitter))
    issues.extend(_check_host_offset_stability(powtlv_entries, POWTLV_MESSAGE_TYPE, max_offset_jitter=max_host_offset_jitter))
    issues.extend(_check_powgps_powtlv_pairing(powgps_entries=powgps_entries, powtlv_entries=powtlv_entries))
    if references:
        issues.extend(_check_powgps_reference_alignment(
            powgps_entries=powgps_entries, references=references, max_ref_utc_drift=max_powgps_ref_utc_drift,
            max_ref_host_delta=max_powgps_ref_host_delta))
    else:
        LOG(f"{LOG_PREFIX_MSG_WARNING} No reference sentences found for types: {', '.join(reference_types)}")

    if issues:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Found {len(issues)} issue(s) in comprehensive POW timing checks.")
        for issue in issues:
            LOG(issue)
        raise SystemExit(1)

    LOG(f"{LOG_PREFIX_MSG_INFO} Comprehensive POW timing checks passed.")


if __name__ == "__main__":
    main()
