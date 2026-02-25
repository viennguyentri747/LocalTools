#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from available_tools.test_tools.log_test_tools import t_test_process_plog_local
from dev.dev_common import *
from unit_tests.acu_log_tests.periodic_log_constants import LAST_TIME_SYNC_COLUMN, TIME_COLUMN
from unit_tests.acu_log_tests.periodic_log_helper import PLogData
from available_tools.test_tools.log_test_tools.t_test_process_plog_local import process_plog_files, _validate_plog_file, _get_compact_log_str, ARG_PLOG_PATHS, ARG_TIME_WINDOW, ARG_OUTPUT_PATH


use_posix_paths()

DEFAULT_COLUMNS: List[str] = [TIME_COLUMN, LAST_TIME_SYNC_COLUMN]
DEFAULT_MAX_SECS_PER_SYNC = 0.999
DEFAULT_OUTPUT_PATH = PERSISTENT_TEMP_PATH / "time_sync_plog.tsv"

ARG_PLOG_PATHS = ARG_PLOG_PATHS
ARG_TIME_WINDOW = ARG_TIME_WINDOW
ARG_OUTPUT_PATH = ARG_OUTPUT_PATH
ARG_MAX_SECS_PER_SYNC = f"{ARGUMENT_LONG_PREFIX}max_secs_per_sync"
DRIFT_ISSUE_NAME = "DRIFT"
SYNC_ZERO_ISSUE_NAME = "SYNC_ZERO"
ALL_TIME_SYNC_ISSUES: List[str] = [DRIFT_ISSUE_NAME, SYNC_ZERO_ISSUE_NAME]
#Note: need to make win python's pip to install local_tools package first by: cd ~/local_tools && <win_python_wsl_path> -m pip install -e .; otherwise the win_cmd_invocation won't work as it can't find the module to run.
WIN_CMD_INVOCATION = get_win_cmd_invocation("available_tools.test_tools.log_test_tools.t_test_time_sync_plog")

def get_tool_templates() -> List[ToolTemplate]:
    sample_log_path_1 = ACU_LOG_PATH / "192.168.100.61" / "P_20260216_000000.txt"
    #sample_log_path_2 = ACU_LOG_PATH / "192.168.100.61" / "P_20260217_000000.txt"
    args = {
        ARG_PLOG_PATHS: [str(sample_log_path_1)],
        ARG_OUTPUT_PATH: str(DEFAULT_OUTPUT_PATH),
        ARG_MAX_SECS_PER_SYNC: DEFAULT_MAX_SECS_PER_SYNC,
        # ARG_TIME_WINDOW: DEFAULT_TIME_WINDOW_HOURS,
    }
    
    return [
        ToolTemplate(
            name="Check P-log time sync",
            extra_description="Validate LAST_TIME_SYNC increments and export a compact Time/LAST_TIME_SYNC log.",
            args=args,
            search_root=ACU_LOG_PATH,
            override_cmd_invocation=WIN_CMD_INVOCATION,
        ),
    ]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check LAST_TIME_SYNC increments and write a compact Time/LAST_TIME_SYNC log.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))

    parser.add_argument( ARG_PLOG_PATHS, required=True, nargs="+", type=Path, help="One or more periodic log file paths (P_*.txt/P_*.log).", )
    parser.add_argument(ARG_TIME_WINDOW, type=float, default=None,
                        help="Time window in hours to keep from the tail of the log (default: all rows).", )
    parser.add_argument(ARG_OUTPUT_PATH, type=Path, default=Path(DEFAULT_OUTPUT_PATH),
                        help=f"Destination file for the compact log (default: {DEFAULT_OUTPUT_PATH}).", )
    parser.add_argument(ARG_MAX_SECS_PER_SYNC, type=float, default=DEFAULT_MAX_SECS_PER_SYNC,
                        help=f"Max allowed drift (seconds) between LAST_TIME_SYNC delta and Time delta; also used as max wait before the first LAST_TIME_SYNC tick (default: {DEFAULT_MAX_SECS_PER_SYNC}).", )

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
    if drift is not None:
        if drift_time_now_label and drift_time_start_label and drift_sync_now is not None and drift_sync_start is not None:
            drift_note = (f"DRIFT={drift:.3f}s, curr_time={drift_time_now_label} vs start_time={drift_time_start_label}, "
                          f"current_sync={drift_sync_now} vs start_sync={drift_sync_start}")
        elif None not in (drift_time_now, drift_time_start, drift_sync_now, drift_sync_start):
            drift_note = (f"DRIFT={drift:.3f}s, curr_time={drift_time_now:.3f}s vs start_time={drift_time_start:.3f}s, "
                          f"current_sync={drift_sync_now} vs start_sync={drift_sync_start}")
        else:
            drift_note = f"DRIFT={drift:.3f}s"
        issues.append(f"{drift_note}, Row {row_index} in {plog_file}:{row_index} :time={time_value}, {LAST_TIME_SYNC_COLUMN} ({message})")
        return
    issues.append(f"Row {row_index} in {plog_file}: time={time_value}, {LAST_TIME_SYNC_COLUMN}={sync_value} ({message})")


def _check_time_sync_drift(file_data: PLogData, max_secs_per_sync: float) -> List[str]:
    #  Wait for the first time sync tick, then baseline there and check deltas vs LAST_TIME_SYNC.
    issues: List[str] = []
    plog_file = file_data.plog_file or Path("<unknown plog file>")
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    time_idx = name_to_idx.get(TIME_COLUMN)
    sync_idx = name_to_idx.get(LAST_TIME_SYNC_COLUMN)
    if time_idx is None or sync_idx is None:
        issues.append(f"Row 1 in {plog_file}: missing required columns ({TIME_COLUMN}, {LAST_TIME_SYNC_COLUMN})")
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

    for idx, row in enumerate(file_data.raw_data_rows):
        row_index = file_data.plog_data_row_indices[idx] if idx < len(file_data.plog_data_row_indices) else idx + 1
        curr_time_value = (row[time_idx] if time_idx < len(row) else "").strip()
        curr_sync_value = (row[sync_idx] if sync_idx < len(row) else "").strip()
        curr_time_secs_float = _parse_time_seconds(curr_time_value)
        curr_time_sync_int = _parse_int(curr_sync_value)

        if curr_time_secs_float is None or curr_time_sync_int is None:
            _record_issue(issues, plog_file, row_index, curr_time_value or "?", curr_sync_value or "?",
                          "missing/invalid time sync data")
            continue

        if prev_time_of_day is not None and curr_time_secs_float < prev_time_of_day:
            curr_day_offset += 24 * 3600
        curr_adj_time_secs_float = curr_time_secs_float + curr_day_offset  # adjust for day rollover

        if prev_sync is None:
            prev_sync = curr_time_sync_int
            prev_time_of_day = curr_time_secs_float
            baseline_start_time = curr_adj_time_secs_float
            continue

        if not baseline_ready:
            if curr_time_sync_int < prev_sync:
                _record_issue(issues, plog_file, row_index, curr_time_value, curr_sync_value, "LAST_TIME_SYNC decreased")
            if curr_time_sync_int > prev_sync:
                start_time_float = curr_adj_time_secs_float
                start_time_label = curr_time_value
                start_sync_int = curr_time_sync_int
                baseline_ready = True
                LOG(
                    f"{LOG_PREFIX_MSG_INFO} Baseline ready: {plog_file} row {row_index}: "
                    f"time={curr_time_value}, {LAST_TIME_SYNC_COLUMN}={curr_sync_value}, "
                    f"adjusted_time={curr_adj_time_secs_float:.3f}, start_sync={start_sync_int}"
                )
            elif not baseline_wait_reported and baseline_start_time is not None:
                wait_secs = curr_adj_time_secs_float - baseline_start_time
                if wait_secs > max_secs_per_sync:
                    _record_issue(issues, plog_file, row_index, curr_time_value, curr_sync_value,
                                  f"LAST_TIME_SYNC not advanced within {max_secs_per_sync:.3f}s")
                    baseline_wait_reported = True
            prev_time_of_day = curr_time_secs_float
            prev_sync = curr_time_sync_int
            continue

        # Ignore drift while sync value is zero after having had a non-zero baseline; this is handled by SYNC_ZERO checks.
        if start_sync_int is not None and start_sync_int > 0 and curr_time_sync_int == 0:
            # Reset variables
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
        real_time_delta_secs_float = curr_adj_time_secs_float - start_time_float
        sync_delta_secs_int = curr_time_sync_int - start_sync_int
        drift = real_time_delta_secs_float - sync_delta_secs_int
        if abs(drift) > max_secs_per_sync:
            _record_issue(issues, plog_file, row_index, curr_time_value, curr_sync_value,
                          f"drift = {drift:.3f}s > {max_secs_per_sync:.3f}s", drift=drift,
                          drift_time_now=curr_adj_time_secs_float, drift_time_start=start_time_float,
                          drift_sync_now=curr_time_sync_int, drift_sync_start=start_sync_int,
                          drift_time_now_label=curr_time_value, drift_time_start_label=start_time_label)

        prev_time_of_day = curr_time_secs_float
        prev_sync = curr_time_sync_int

    return issues


def _check_time_sync_sync_zero(file_data: PLogData) -> List[str]:
    issues: List[str] = []
    plog_file = file_data.plog_file or Path("<unknown plog file>")
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    time_idx = name_to_idx.get(TIME_COLUMN)
    sync_idx = name_to_idx.get(LAST_TIME_SYNC_COLUMN)
    if time_idx is None or sync_idx is None:
        return [f"Row 1 in {plog_file}: missing required columns ({TIME_COLUMN}, {LAST_TIME_SYNC_COLUMN})"]
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
                f"Rows {zero_start_row}-{zero_end_row} in {plog_file} "
                f"(start_sync={start_sync_int}, start_time={start_time_label})"
            )
            in_zero_block = False
    if in_zero_block:
        issues.append(
            f"{SYNC_ZERO_ISSUE_NAME}, start={zero_start_time_label} (row {zero_start_row}), "
            f"end={zero_end_time_label} (row {zero_end_row}), total_count={zero_count}, "
            f"Rows {zero_start_row}-{zero_end_row} in {plog_file} "
            f"(start_sync={start_sync_int}, start_time={start_time_label})"
        )
    return issues


def _check_time_sync(file_data: PLogData, max_secs_per_sync: float) -> Dict[str, List[str]]:
    drift_issues = _check_time_sync_drift(file_data, max_secs_per_sync)
    sync_zero_issues = _check_time_sync_sync_zero(file_data)
    return {DRIFT_ISSUE_NAME: drift_issues, SYNC_ZERO_ISSUE_NAME: sync_zero_issues}


def _write_metadata_file(output_plog_path: Path, input_paths: Sequence[Path], time_window: Optional[float], target_columns: Sequence[str],
                         processed_files: Sequence[Path], rows_written: int, max_secs_per_sync: float, issue_counts_by_name: Dict[str, int],
                         issues: Sequence[str]) -> Path:
    """Persist metadata as JSON next to the compact log artifact."""
    now_utc = datetime.now(timezone.utc)
    timestamp = now_utc.strftime("%Y%m%d_%H%M%S")
    metadata_path = output_plog_path.parent / f"time_sync_metadata_{timestamp}.json"
    issues_reported = len(issues)
    metadata = {
        "generated_at_utc": now_utc.isoformat(),
        "arguments": {
            "input_paths": [str(path) for path in input_paths],
            "time_window_hours": time_window,
            "columns": list(target_columns),
            "output_plog_path": str(output_plog_path),
            "max_secs_per_sync": max_secs_per_sync,
            "checked_issue_names": ALL_TIME_SYNC_ISSUES,
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



def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())

def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    input_paths_raw = get_arg_value(args, ARG_PLOG_PATHS) or []
    input_paths = [Path(path).expanduser() for path in input_paths_raw]
    output_path = Path(get_arg_value(args, ARG_OUTPUT_PATH)).expanduser()
    time_window: Optional[str] = get_arg_value(args, ARG_TIME_WINDOW)
    if time_window is not None:
        time_window = float(time_window)
    max_secs_per_sync = float(get_arg_value(args, ARG_MAX_SECS_PER_SYNC))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plog_files = sorted({_validate_plog_file(input_path) for input_path in input_paths})
    LOG(f"{LOG_PREFIX_MSG_INFO} Found {len(plog_files)} unique P-log file(s) to analyze from {len(input_paths)} input path(s).")
    LOG(f"{LOG_PREFIX_MSG_INFO} Checking time sync issues: {', '.join(ALL_TIME_SYNC_ISSUES)}")

    processed_data = process_plog_files(plog_files, DEFAULT_COLUMNS, time_window)
    processed_files = [file_data.plog_file for file_data in processed_data if file_data.plog_file is not None]
    rows_written = sum(len(file_data.raw_data_rows) for file_data in processed_data)
    if rows_written == 0:
        LOG(f"{LOG_PREFIX_MSG_WARNING} No rows found across {len(plog_files)} file(s); nothing to write.")
        return

    LOG(f"{LOG_PREFIX_MSG_INFO} Writing {rows_written} row(s) with {len(DEFAULT_COLUMNS)} column(s) to {output_path}")
    compact_content = _get_compact_log_str(processed_data, DEFAULT_COLUMNS)
    write_to_file(str(output_path), compact_content, mode=WriteMode.OVERWRITE)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Time sync compact log created: {output_path}")

    issues: List[str] = []
    issue_counts_by_name: Dict[str, int] = {issue_name: 0 for issue_name in ALL_TIME_SYNC_ISSUES}
    separator: str = "SEPARATOR"
    for file_data in processed_data:
        issues_by_name = _check_time_sync(file_data, max_secs_per_sync)
        for issue_name, group_issues in issues_by_name.items():
            issue_counts_by_name[issue_name] += len(group_issues)
            issues.extend(group_issues)
            issues.append(separator)

    metadata_path = _write_metadata_file(
        output_plog_path=output_path,
        input_paths=input_paths,
        time_window=time_window,
        target_columns=DEFAULT_COLUMNS,
        processed_files=processed_files,
        rows_written=rows_written,
        max_secs_per_sync=max_secs_per_sync,
        issue_counts_by_name=issue_counts_by_name,
        issues=issues,
    )
    LOG(f"{LOG_PREFIX_MSG_INFO} Metadata saved: {metadata_path}")

    if issues:
        issue_counts_msg = ", ".join(f"{issue_name}={issue_counts_by_name[issue_name]}" for issue_name in ALL_TIME_SYNC_ISSUES)
        LOG_LINE_SEPARATOR()
        LOG(f"{LOG_PREFIX_MSG_ERROR} Found {len(issues)} time sync issue(s) across {len(processed_data)} file(s). [{issue_counts_msg}]")
        for issue in issues:
            if separator in issue:
                LOG(show_time=False)
            else:
                LOG(f"  - {issue}", show_time=False)

        raise SystemExit(1)

    LOG(
        f"{LOG_PREFIX_MSG_SUCCESS} No time sync issues found (checked: {', '.join(ALL_TIME_SYNC_ISSUES)}) "
        f"across {len(processed_data)} file(s)."
    )


if __name__ == "__main__":
    main()
