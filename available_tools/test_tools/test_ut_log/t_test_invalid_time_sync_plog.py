#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, List, Optional, Sequence

from available_tools.test_tools.test_ut_log.log_test_interface import EUtLogType, TestLogInterface, normalize_log_paths_map
from available_tools.test_tools.test_ut_log.t_get_acu_logs import ACU_LOG_PATH
from dev.dev_common import *
from unit_tests.acu_log_tests.periodic_log_constants import LAST_TIME_SYNC_COLUMN, TIME_COLUMN
from unit_tests.acu_log_tests.periodic_log_helper import PLogData
from available_tools.test_tools.test_ut_log.t_test_process_plog_local import process_plog_files, _validate_plog_file, _get_compact_log_str, ARG_PLOG_PATHS, ARG_TIME_WINDOW, ARG_OUTPUT_PATH


use_posix_paths()

DEFAULT_COLUMNS: List[str] = [TIME_COLUMN, LAST_TIME_SYNC_COLUMN]
# Max allowed absolute drift between (Time delta) and (LAST_TIME_SYNC delta), in seconds.
DEFAULT_MAX_DRIFT_TOLERANCE_SECS = 0.2
DRIFT_RECOVERY_GRACE_ROWS = 3
DRIFT_KIND_SYNC_LAG = "sync_lag"
DRIFT_KIND_SYNC_LEAD = "sync_lead"
DEFAULT_OUTPUT_PATH = get_temp_path(ETargetPlatform.WINDOWS) / "time_sync_plog.tsv"

ARG_PLOG_PATHS = ARG_PLOG_PATHS
ARG_TIME_WINDOW = ARG_TIME_WINDOW
ARG_OUTPUT_PATH = ARG_OUTPUT_PATH
# Keep CLI arg name for backward compatibility, but internally this is drift tolerance, not sync period.
ARG_MAX_DRIFT_TOLERANCE_SECS = f"{ARGUMENT_LONG_PREFIX}max_secs_per_sync"
DRIFT_VS_SYSTEM_TIME_ISSUE_NAME = "DRIFT VS SYSTEM TIME"
SYNC_ZERO_ISSUE_NAME = "SYNC_ZERO"
SYNC_ABNORMALITY_ISSUE_NAME = "SYNC ANOMALY"
EXPECTED_SECOND_BETWEEN_TIME_SYNC = 1
ALL_TIME_SYNC_ISSUES: List[str] = [DRIFT_VS_SYSTEM_TIME_ISSUE_NAME, SYNC_ZERO_ISSUE_NAME, SYNC_ABNORMALITY_ISSUE_NAME]
WIN_CMD_INVOCATION = get_win_python_runner_cmd_invocation("available_tools.test_tools.test_ut_log.t_test_invalid_time_sync_plog")
TEST_NAME = "time_sync_plog"


@dataclass
class DriftSample:
    row_index: int
    time_label: str
    sync_value: int
    drift: float
    real_time_delta: float
    sync_delta: int
    baseline_time_label: Optional[str]
    baseline_sync: Optional[int]
    kind: str

    def to_message(self) -> str:
        return (
            f"row={self.row_index}, time={self.time_label}, {LAST_TIME_SYNC_COLUMN}={self.sync_value}, "
            f"baseline_time={self.baseline_time_label}, baseline_sync={self.baseline_sync}, "
            f"kind={self.kind}, drift={self.drift:.3f}s, real_delta={self.real_time_delta:.3f}s, sync_delta={self.sync_delta}s"
        )


class DriftIssueBlock:
    first: DriftSample
    last: DriftSample
    max_abs: DriftSample
    total_count: int

    def __init__(self, first: DriftSample) -> None:
        self.first = first
        self.last = first
        self.max_abs = first
        self.total_count = 1

    def update(self, sample: DriftSample) -> None:
        self.last = sample
        self.total_count += 1
        if abs(sample.drift) > abs(self.max_abs.drift):
            self.max_abs = sample

    def to_message(self, plog_file: Path, drift_tolerance_secs: float) -> str:
        display_plog_file = format_path_for_display(plog_file)
        row_label = f"Row {self.first.row_index}" if self.first.row_index == self.last.row_index else f"Rows {self.first.row_index}-{self.last.row_index}"
        prefix = f"{DRIFT_VS_SYSTEM_TIME_ISSUE_NAME}, total_count={self.total_count}, {row_label} in {display_plog_file} (threshold={drift_tolerance_secs:.3f}s)"
        if self.total_count == 1:
            return f"{prefix}, sample=[{self.first.to_message()}]"
        if self.max_abs.row_index == self.first.row_index:
            max_abs_msg = "first"
        elif self.max_abs.row_index == self.last.row_index:
            max_abs_msg = "last"
        else:
            max_abs_msg = f"[{self.max_abs.to_message()}]"
        return f"{prefix}, first=[{self.first.to_message()}], last=[{self.last.to_message()}], max_abs={max_abs_msg}"


@dataclass
class TimeSyncRunInfo:
    # Anchor for the current contiguous LAST_TIME_SYNC run.
    sync_value: Optional[int] = None
    run_start_time_float: Optional[float] = None
    run_start_time_label: Optional[str] = None
    run_start_sync_int: Optional[int] = None

    def start_new_run(self, sync_value: int, time_float: float, time_label: str) -> None:
        self.sync_value = sync_value
        self.run_start_time_float = time_float
        self.run_start_time_label = time_label
        self.run_start_sync_int = sync_value


def getToolData() -> ToolData:
    sample_log_path_1 = ACU_LOG_PATH / "192.168.100.61" / "P_20260216_000000.txt"
    args = {
        ARG_PLOG_PATHS: [str(sample_log_path_1)],
        ARG_OUTPUT_PATH: str(DEFAULT_OUTPUT_PATH),
        ARG_MAX_DRIFT_TOLERANCE_SECS: DEFAULT_MAX_DRIFT_TOLERANCE_SECS,
    }
    
    
    tool_templates = [
        ToolTemplate(
            name="Check P-log time sync",
            extra_description="Validate LAST_TIME_SYNC increments and export a compact Time/LAST_TIME_SYNC log.",
            args=args,
            search_root=ACU_LOG_PATH,
            override_cmd_invocation=WIN_CMD_INVOCATION,
        ),
    ]
    return ToolData(tool_templates=tool_templates, tool_priority=EToolPriority.Level10_Last, hidden=False)



def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check LAST_TIME_SYNC increments and write a compact Time/LAST_TIME_SYNC log.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))

    parser.add_argument( ARG_PLOG_PATHS, required=True, nargs="+", type=Path, help="One or more periodic log file paths (P_*.txt/P_*.log).", )
    parser.add_argument(ARG_TIME_WINDOW, type=float, default=None,
                        help="Time window in hours to keep from the tail of the log (default: all rows).", )
    parser.add_argument(ARG_OUTPUT_PATH, type=Path, default=Path(DEFAULT_OUTPUT_PATH),
                        help=f"Destination file for the compact log (default: {DEFAULT_OUTPUT_PATH}).", )
    parser.add_argument(ARG_MAX_DRIFT_TOLERANCE_SECS, type=float, default=DEFAULT_MAX_DRIFT_TOLERANCE_SECS,
                        help=f"Max allowed drift (seconds) between LAST_TIME_SYNC delta and Time delta; also used as max wait before the first LAST_TIME_SYNC tick (default: {DEFAULT_MAX_DRIFT_TOLERANCE_SECS}).", )

    return parser.parse_args(argv)


def _parse_time_seconds(value: str) -> Optional[float]:
    value = value.strip()
    if not value:
        return None
    try:
        if "." in value:
            time_part, frac = value.split(".", 1)
            hours, minutes, seconds = time_part.split(":")
            return int(hours) * 3600 + int(minutes) * 60 + float(f"{seconds}.{frac}")
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return None


def _parse_int(value: str) -> Optional[int]:
    value = value.strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _record_issue(issues: List[str], plog_file: Path, row_index: int, time_value: str, sync_value: str,
                  message: str, drift: Optional[float] = None, drift_time_now: Optional[float] = None,
                  drift_time_start: Optional[float] = None, drift_sync_now: Optional[int] = None,
                  drift_sync_start: Optional[int] = None, drift_time_now_label: Optional[str] = None,
                  drift_time_start_label: Optional[str] = None) -> None:
    display_plog_file = format_path_for_display(plog_file)
    if drift is not None:
        if drift_time_now_label and drift_time_start_label and drift_sync_now is not None and drift_sync_start is not None:
            drift_note = (f"DRIFT={drift:.3f}s, curr_time={drift_time_now_label} vs start_time={drift_time_start_label}, "
                          f"current_sync={drift_sync_now} vs start_sync={drift_sync_start}")
        elif None not in (drift_time_now, drift_time_start, drift_sync_now, drift_sync_start):
            drift_note = (f"DRIFT={drift:.3f}s, curr_time={drift_time_now:.3f}s vs start_time={drift_time_start:.3f}s, "
                          f"current_sync={drift_sync_now} vs start_sync={drift_sync_start}")
        else:
            drift_note = f"DRIFT={drift:.3f}s"
        issues.append(f"{drift_note}, Row {row_index} in {display_plog_file}:{row_index} :time={time_value}, {LAST_TIME_SYNC_COLUMN} ({message})")
        return
    issues.append(f"Row {row_index} in {display_plog_file}: time={time_value}, {LAST_TIME_SYNC_COLUMN}={sync_value} ({message})")


def _check_time_sync_drift_vs_system_time(file_data: PLogData, drift_tolerance_secs: float) -> List[str]:
    # Wait for the first time sync tick, then baseline there and summarize continuous drift episodes.
    # Note: drift_tolerance_secs is also used as the startup wait budget before the first sync tick appears.
    issues: List[str] = []
    plog_file = file_data.plog_file or Path("<unknown plog file>")
    display_plog_file = format_path_for_display(plog_file)
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    time_idx = name_to_idx.get(TIME_COLUMN)
    sync_idx = name_to_idx.get(LAST_TIME_SYNC_COLUMN)
    if time_idx is None or sync_idx is None:
        issues.append(f"Row 1 in {display_plog_file}: missing required columns ({TIME_COLUMN}, {LAST_TIME_SYNC_COLUMN})")
        return issues
    start_time_float: Optional[float] = None
    start_time_label: Optional[str] = None
    start_sync_int: Optional[int] = None
    baseline_ready = False
    baseline_start_time: Optional[float] = None
    baseline_wait_reported = False
    prev_time_of_day: Optional[float] = None
    prev_sync: Optional[int] = None
    curr_day_offset: float = 0.0
    # Track the current contiguous run so re-baselining can use the oldest row in that run.
    sync_run_info = TimeSyncRunInfo()
    drift_issue_block: Optional[DriftIssueBlock] = None
    drift_recovery_row_count = 0

    def flush_drift_issue_block() -> None:
        nonlocal drift_issue_block, drift_recovery_row_count
        if drift_issue_block is None:
            return
        # Close the current over-threshold span as one issue instead of logging every row.
        issues.append(drift_issue_block.to_message(plog_file, drift_tolerance_secs))
        drift_issue_block = None
        drift_recovery_row_count = 0

    for idx, row in enumerate(file_data.raw_data_rows):
        row_index = file_data.plog_data_row_indices[idx] if idx < len(file_data.plog_data_row_indices) else idx + 1
        curr_time_value = (row[time_idx] if time_idx < len(row) else "").strip()
        curr_sync_value = (row[sync_idx] if sync_idx < len(row) else "").strip()
        curr_time_secs_float = _parse_time_seconds(curr_time_value)
        curr_time_sync_int = _parse_int(curr_sync_value)

        if curr_time_secs_float is None or curr_time_sync_int is None:
            # If Time or LAST_TIME_SYNC cannot be parsed, this row SHOULD NOT extend the current drift span.
            flush_drift_issue_block()
            _record_issue(issues, plog_file, row_index, curr_time_value or "?", curr_sync_value or "?", "missing/invalid time sync data")
            continue

        if prev_time_of_day is not None and curr_time_secs_float < prev_time_of_day:
            curr_day_offset += 24 * 3600
        curr_adj_time_secs_float = curr_time_secs_float + curr_day_offset  # adjust for day rollover

        if prev_sync is None:
            prev_sync = curr_time_sync_int
            prev_time_of_day = curr_time_secs_float
            baseline_start_time = curr_adj_time_secs_float
            # First valid row initializes the first sync run anchor.
            sync_run_info.start_new_run(curr_time_sync_int, curr_adj_time_secs_float, curr_time_value)
            continue

        if sync_run_info.sync_value != curr_time_sync_int:
            # Sync value changed: start a new contiguous run anchor at this row.
            sync_run_info.start_new_run(curr_time_sync_int, curr_adj_time_secs_float, curr_time_value)

        if not baseline_ready:
            if curr_time_sync_int < prev_sync:
                _record_issue(issues, plog_file, row_index, curr_time_value, curr_sync_value, "LAST_TIME_SYNC decreased")
            if curr_time_sync_int > prev_sync:
                start_time_float = curr_adj_time_secs_float
                start_time_label = curr_time_value
                start_sync_int = curr_time_sync_int
                baseline_ready = True
                LOG(
                    f"{LOG_PREFIX_MSG_INFO} Baseline ready: {display_plog_file} row {row_index}: "
                    f"time={curr_time_value}, {LAST_TIME_SYNC_COLUMN}={curr_sync_value}, "
                    f"adjusted_time={curr_adj_time_secs_float:.3f}, start_sync={start_sync_int}"
                )
            elif not baseline_wait_reported and baseline_start_time is not None:
                wait_secs = curr_adj_time_secs_float - baseline_start_time
                if wait_secs > drift_tolerance_secs:
                    _record_issue(issues, plog_file, row_index, curr_time_value, curr_sync_value,
                                  f"LAST_TIME_SYNC not advanced within {drift_tolerance_secs:.3f}s")
                    baseline_wait_reported = True
            prev_time_of_day = curr_time_secs_float
            prev_sync = curr_time_sync_int
            continue

        # LAST_TIME_SYNC=0 after a valid non-zero baseline means the sync source was reset/lost, not a normal drift delta.
        # Report that interval through the SYNC_ZERO checker and start waiting for a fresh non-zero baseline afterward.
        if start_sync_int is not None and start_sync_int > 0 and curr_time_sync_int == 0:
            # Close any drift span before reset so the pre-zero drift and sync-zero interval stay separate.
            flush_drift_issue_block()
            # Reset baseline state; following non-zero rows will establish a new drift comparison anchor.
            baseline_ready = False
            baseline_start_time = None
            baseline_wait_reported = False
            start_time_float = None
            start_time_label = None
            start_sync_int = None
            prev_time_of_day = curr_time_secs_float
            prev_sync = curr_time_sync_int
            continue

        if curr_time_sync_int < prev_sync:
            _record_issue(issues, plog_file, row_index, curr_time_value, curr_sync_value,
                          "LAST_TIME_SYNC decreased")
        if start_time_float is None or start_sync_int is None:
            prev_time_of_day = curr_time_secs_float
            prev_sync = curr_time_sync_int
            continue
        real_time_delta_secs_float = curr_adj_time_secs_float - start_time_float
        sync_delta_secs_int = curr_time_sync_int - start_sync_int
        drift = real_time_delta_secs_float - sync_delta_secs_int
        # This checker validates accumulated drift against sync counter increments.
        # Example: 1.004s elapsed with sync_delta=1 => drift=0.004s, so it is below a 0.9999s drift threshold.
        if abs(drift) > drift_tolerance_secs:
            drift_kind = DRIFT_KIND_SYNC_LAG if drift > 0 else DRIFT_KIND_SYNC_LEAD
            drift_sample = DriftSample(
                row_index=row_index, time_label=curr_time_value, sync_value=curr_time_sync_int, drift=drift,
                real_time_delta=real_time_delta_secs_float, sync_delta=sync_delta_secs_int,
                baseline_time_label=start_time_label, baseline_sync=start_sync_int, kind=drift_kind,
            )
            if drift_issue_block is None:
                # Start a new block for the first over-threshold row after recovery/reset/file start.
                drift_issue_block = DriftIssueBlock(drift_sample)
            else:
                drift_issue_block.update(drift_sample)
            drift_recovery_row_count = 0
            # Re-anchor baseline to the oldest row in the current contiguous run with matching sync value.
            # Example: 1 1 1 1 2 1 1 1 -> at the rightmost 1s, baseline is the first 1 after 2.
            if sync_run_info.run_start_time_float is not None and sync_run_info.run_start_sync_int is not None:
                start_time_float = sync_run_info.run_start_time_float
                start_time_label = sync_run_info.run_start_time_label
                start_sync_int = sync_run_info.run_start_sync_int
            else:
                start_time_float = curr_adj_time_secs_float
                start_time_label = curr_time_value
                start_sync_int = curr_time_sync_int
        else:
            if drift_issue_block is not None:
                # Avoid splitting one borderline drift event when a few rows (<= DRIFT_RECOVERY_GRACE_ROWS) briefly fall back under the threshold.
                drift_recovery_row_count += 1
                if drift_recovery_row_count > DRIFT_RECOVERY_GRACE_ROWS:
                    flush_drift_issue_block()

        prev_time_of_day = curr_time_secs_float
        prev_sync = curr_time_sync_int

    # End of file can leave a drift span open; close it so the last block is reported.
    flush_drift_issue_block()
    return issues


def _check_time_sync_sync_zero(file_data: PLogData) -> List[str]:
    issues: List[str] = []
    plog_file = file_data.plog_file or Path("<unknown plog file>")
    display_plog_file = format_path_for_display(plog_file)
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    time_idx = name_to_idx.get(TIME_COLUMN)
    sync_idx = name_to_idx.get(LAST_TIME_SYNC_COLUMN)
    if time_idx is None or sync_idx is None:
        return [f"Row 1 in {display_plog_file}: missing required columns ({TIME_COLUMN}, {LAST_TIME_SYNC_COLUMN})"]
    start_sync_int: Optional[int] = None
    start_time_label: Optional[str] = None
    in_zero_block = False
    zero_start_time_label: Optional[str] = None
    zero_start_row: Optional[int] = None
    zero_end_time_label: Optional[str] = None
    zero_end_row: Optional[int] = None
    zero_count = 0
    for idx, row in enumerate(file_data.raw_data_rows):
        row_num = file_data.plog_data_row_indices[idx] if idx < len(file_data.plog_data_row_indices) else idx + 1
        curr_time_value = (row[time_idx] if time_idx < len(row) else "").strip()
        curr_sync_value = (row[sync_idx] if sync_idx < len(row) else "").strip()
        curr_time_secs_float = _parse_time_seconds(curr_time_value)
        curr_time_sync_int = _parse_int(curr_sync_value)
        if curr_time_secs_float is None or curr_time_sync_int is None:
            continue
        if start_sync_int is None and curr_time_sync_int > 0:
            start_sync_int = curr_time_sync_int
            start_time_label = curr_time_value
            continue
        if start_sync_int is None:
            continue
        if curr_time_sync_int == 0:
            if not in_zero_block:
                in_zero_block = True
                zero_start_time_label = curr_time_value
                zero_start_row = row_num
                zero_count = 0
            zero_end_time_label = curr_time_value
            zero_end_row = row_num
            zero_count += 1
            continue
        if in_zero_block:
            issues.append(
                f"{SYNC_ZERO_ISSUE_NAME}, start={zero_start_time_label} (row {zero_start_row}), "
                f"end={zero_end_time_label} (row {zero_end_row}), total_count={zero_count}, "
                f"Rows {zero_start_row}-{zero_end_row} in {display_plog_file} "
                f"(start_sync={start_sync_int}, start_time={start_time_label})"
            )
            in_zero_block = False
    if in_zero_block:
        issues.append(
            f"{SYNC_ZERO_ISSUE_NAME}, start={zero_start_time_label} (row {zero_start_row}), "
            f"end={zero_end_time_label} (row {zero_end_row}), total_count={zero_count}, "
            f"Rows {zero_start_row}-{zero_end_row} in {display_plog_file} "
            f"(start_sync={start_sync_int}, start_time={start_time_label})"
        )
    return issues


def _check_time_sync_abnormality(file_data: PLogData) -> List[str]:
    issues: List[str] = []
    plog_file = file_data.plog_file or Path("<unknown plog file>")
    display_plog_file = format_path_for_display(plog_file)
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    time_idx = name_to_idx.get(TIME_COLUMN)
    sync_idx = name_to_idx.get(LAST_TIME_SYNC_COLUMN)
    if time_idx is None or sync_idx is None:
        return [f"Row 1 in {display_plog_file}: missing required columns ({TIME_COLUMN}, {LAST_TIME_SYNC_COLUMN})"]

    prev_sync: Optional[int] = None
    prev_time_value: Optional[str] = None
    for idx, row in enumerate(file_data.raw_data_rows):
        row_num = file_data.plog_data_row_indices[idx] if idx < len(file_data.plog_data_row_indices) else idx + 1
        curr_time_value = (row[time_idx] if time_idx < len(row) else "").strip()
        curr_sync_value = (row[sync_idx] if sync_idx < len(row) else "").strip()
        curr_time_sync_int = _parse_int(curr_sync_value)
        if curr_time_sync_int is None:
            continue
        if prev_sync is None:
            prev_sync = curr_time_sync_int
            prev_time_value = curr_time_value
            continue

        sync_delta = curr_time_sync_int - prev_sync
        if prev_sync == 0 or curr_time_sync_int == 0:
            # Temporary rule: ignore any transition that touches zero (X->0 or 0->X).
            # These reset/loss windows are handled by SYNC_ZERO checker.
            prev_sync = curr_time_sync_int
            prev_time_value = curr_time_value
            continue
        if sync_delta != 0 and sync_delta != EXPECTED_SECOND_BETWEEN_TIME_SYNC:
                issues.append(
                    f"{SYNC_ABNORMALITY_ISSUE_NAME}, row={row_num}, "
                    f"prev(time={prev_time_value}, {LAST_TIME_SYNC_COLUMN}={prev_sync}) -> "
                    f"curr(time={curr_time_value}, {LAST_TIME_SYNC_COLUMN}={curr_time_sync_int}), "
                    f"delta={sync_delta}s (expected delta={EXPECTED_SECOND_BETWEEN_TIME_SYNC}s or 0 when unchanged) in {display_plog_file}"
                )
        prev_sync = curr_time_sync_int
        prev_time_value = curr_time_value
    return issues


def _check_time_sync(file_data: PLogData, drift_tolerance_secs: float, target_issues: Sequence[str]) -> Dict[str, List[str]]:
    issues_by_name: Dict[str, List[str]] = {}
    if DRIFT_VS_SYSTEM_TIME_ISSUE_NAME in target_issues:
        issues_by_name[DRIFT_VS_SYSTEM_TIME_ISSUE_NAME] = _check_time_sync_drift_vs_system_time(file_data, drift_tolerance_secs)
    if SYNC_ZERO_ISSUE_NAME in target_issues:
        issues_by_name[SYNC_ZERO_ISSUE_NAME] = _check_time_sync_sync_zero(file_data)
    if SYNC_ABNORMALITY_ISSUE_NAME in target_issues:
        issues_by_name[SYNC_ABNORMALITY_ISSUE_NAME] = _check_time_sync_abnormality(file_data)
    return issues_by_name


def _write_metadata_file(output_plog_path: Path, input_paths: Sequence[Path], time_window: Optional[float], target_columns: Sequence[str],
                         processed_files: Sequence[Path], rows_written: int, drift_tolerance_secs: float, issue_counts_by_name: Dict[str, int],
                         issues: Sequence[str], target_issues: Sequence[str], ignored_issues: Sequence[str]) -> Path:
    """Persist metadata as JSON next to the compact log artifact."""
    metadata_path = output_plog_path.parent / f"time_sync_metadata_{get_file_timestamp()}.json"
    issues_reported = len(issues)
    metadata = {
        "generated_at_utc": get_iso_timestamp(),
        "arguments": {
            "input_paths": [str(path) for path in input_paths],
            "time_window_hours": time_window,
            "columns": list(target_columns),
            "output_plog_path": str(output_plog_path),
            "drift_tolerance_secs": drift_tolerance_secs,
            "max_secs_per_sync": drift_tolerance_secs,  # backward-compatible alias for older consumers
            "checked_issue_names": list(target_issues),
            "ignored_issue_names": list(ignored_issues),
        },
        "issue_counts_by_name": issue_counts_by_name,
        "plog_files": [str(path) for path in processed_files],
        "rows_written": rows_written,
        "issues_total": len(issues),
        "issues_reported": issues_reported,
        "issues_sample": list(issues[:issues_reported]),
        "status": "fail" if issues else "pass",
    }
    write_to_file(str(metadata_path), json.dumps(metadata, indent=2), mode=WriteMode.OVERWRITE)
    return metadata_path



def run_time_sync_test(input_paths: Sequence[Path], output_path: Path, time_window: Optional[float], drift_tolerance_secs: float) -> None:
    LOG(f"{LOG_PREFIX_MSG_INFO} Time-sync runtime python: sys.executable={format_path_for_display(sys.executable)}, argv0={format_path_for_display(sys.argv[0])}")
    input_paths = [get_normalized_path(Path(path), target_platform=ETargetPlatform.CURRENT, log_label="P-log input path") for path in input_paths]
    output_path = get_normalized_path(Path(output_path), target_platform=ETargetPlatform.CURRENT, log_label="output path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plog_files = sorted({_validate_plog_file(input_path) for input_path in input_paths})
    list_ignore_issues = [SYNC_ZERO_ISSUE_NAME]
    target_issues = [issue for issue in ALL_TIME_SYNC_ISSUES if issue not in list_ignore_issues]
    LOG(f"{LOG_PREFIX_MSG_INFO} Found {len(plog_files)} unique P-log file(s) to analyze from {len(input_paths)} input path(s).")
    LOG(f"{LOG_PREFIX_MSG_INFO} Checking time sync issues: {', '.join(target_issues)}")
    if list_ignore_issues:
        LOG(f"{LOG_PREFIX_MSG_INFO} Ignoring time sync issues: {', '.join(list_ignore_issues)}")

    processed_data = process_plog_files(plog_files, DEFAULT_COLUMNS, time_window)
    processed_files = [file_data.plog_file for file_data in processed_data if file_data.plog_file is not None]
    rows_written = sum(len(file_data.raw_data_rows) for file_data in processed_data)
    if rows_written == 0:
        LOG(f"{LOG_PREFIX_MSG_WARNING} No rows found across {len(plog_files)} file(s); nothing to write.")
        return

    LOG(f"{LOG_PREFIX_MSG_INFO} Writing {rows_written} row(s) with {len(DEFAULT_COLUMNS)} column(s) to {format_path_for_display(output_path)}")
    compact_content = _get_compact_log_str(processed_data, DEFAULT_COLUMNS)
    write_to_file(str(output_path), compact_content, mode=WriteMode.OVERWRITE)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Time sync compact log created: {format_path_for_display(output_path)}")

    issues: List[str] = []
    issue_counts_by_name: Dict[str, int] = {issue_name: 0 for issue_name in target_issues}
    for file_data in processed_data:
        issues_by_name = _check_time_sync(file_data, drift_tolerance_secs, target_issues)
        for issue_name, group_issues in issues_by_name.items():
            issue_counts_by_name[issue_name] += len(group_issues)
            issues.extend(group_issues)

    metadata_path = _write_metadata_file(
        output_plog_path=output_path,
        input_paths=input_paths,
        time_window=time_window,
        target_columns=DEFAULT_COLUMNS,
        processed_files=processed_files,
        rows_written=rows_written,
        drift_tolerance_secs=drift_tolerance_secs,
        issue_counts_by_name=issue_counts_by_name,
        issues=issues,
        target_issues=target_issues,
        ignored_issues=list_ignore_issues,
    )
    LOG(f"{LOG_PREFIX_MSG_INFO} Metadata saved: {format_path_for_display(metadata_path)}")

    if issues:
        issue_counts_msg = ", ".join(f"{issue_name}={issue_counts_by_name[issue_name]}" for issue_name in target_issues)
        LOG_LINE_SEPARATOR()
        LOG(f"{LOG_PREFIX_MSG_ERROR} Found {len(issues)} time sync issue(s) across {len(processed_data)} file(s). [{issue_counts_msg}]")
        for issue in issues:
            LOG(f"  - {issue}", show_time=False)

        raise SystemExit(1)

    LOG(
        f"{LOG_PREFIX_MSG_SUCCESS} No time sync issues found (checked: {', '.join(target_issues)}) "
        f"across {len(processed_data)} file(s)."
    )


class TimeSyncPlogTest(TestLogInterface):
    TEST_NAME = "time_sync_plog"

    @classmethod
    def get_target_log_types(cls) -> List[EUtLogType]:
        return [EUtLogType.PLOG]

    @classmethod
    def run_test(cls, log_paths_by_type: Dict[EUtLogType, List[Path]]) -> None:
        normalized_map = normalize_log_paths_map(log_paths_by_type)
        plog_paths = normalized_map.get(EUtLogType.PLOG, [])
        if not plog_paths:
            LOG_EXCEPTION(ValueError("No P-log files found for time sync test."), exit=True)
        run_time_sync_test(
            input_paths=plog_paths,
            output_path=Path(DEFAULT_OUTPUT_PATH),
            time_window=None,
            drift_tolerance_secs=DEFAULT_MAX_DRIFT_TOLERANCE_SECS,
        )


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    input_paths_raw = get_arg_value(args, ARG_PLOG_PATHS) or []
    input_paths = [get_normalized_path(Path(path), target_platform=ETargetPlatform.CURRENT, log_label="P-log input path") for path in input_paths_raw]
    output_path = get_normalized_path(Path(get_arg_value(args, ARG_OUTPUT_PATH)), target_platform=ETargetPlatform.CURRENT, log_label="output path")
    time_window_raw = get_arg_value(args, ARG_TIME_WINDOW)
    time_window = float(time_window_raw) if time_window_raw is not None else None
    drift_tolerance_secs = float(get_arg_value(args, ARG_MAX_DRIFT_TOLERANCE_SECS))
    run_time_sync_test(input_paths=input_paths, output_path=output_path, time_window=time_window, drift_tolerance_secs=drift_tolerance_secs)


if __name__ == "__main__":
    main()
