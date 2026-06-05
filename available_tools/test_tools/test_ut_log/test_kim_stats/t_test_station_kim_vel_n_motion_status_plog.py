#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from available_tools.test_tools.test_ut_log.log_test_interface import EUtLogType, TestLogInterface, normalize_log_paths_map
from available_tools.test_tools.test_ut_log.t_get_acu_logs import ACU_LOG_PATH
from available_tools.test_tools.test_ut_log.t_test_process_plog_local import ARG_OUTPUT_PATH, ARG_PLOG_PATHS, ARG_TIME_WINDOW, _get_compact_log_str, _validate_plog_file, process_plog_files
from available_tools.test_tools.test_ut_log.test_kim_stats.common import DEFAULT_EXPECTED_MOTION_STATUSES, DEFAULT_IMX_REV_STR, DEFAULT_MIN_BASELINE_SINR, DeviationColumnConfig, DeviationSample, ImxSpecs, append_issue_row_context, build_grouped_deviation_issues, check_baseline_spread, compact_issues_by_prefix, find_baseline_rows, get_baseline_stats_by_column, get_imx_specs, get_issue_row_context, get_row_number, get_time_value, get_numeric_value, is_ignored_deviation_value, log_baseline_summary, log_ignored_deviation_value_counts, log_imx_spec, parse_int, record_ignored_deviation_value_count, require_columns, SUPPORTED_IMX_REV_STRS
from dev.dev_common import *
from unit_tests.acu_log_tests.periodic_log_constants import LAST_AVG_SINR_COLUMN, LAST_MOTION_STATUS_COLUMN, LAST_VELOCITY_COLUMN, TIME_COLUMN

use_posix_paths()

WIN_CMD_INVOCATION = get_win_python_runner_cmd_invocation("available_tools.test_tools.test_ut_log.test_kim_stats.t_test_station_kim_vel_n_motion_status_plog")
DEFAULT_OUTPUT_PATH = get_temp_path(ETargetPlatform.WINDOWS) / "stationary_kim_velocity_motion_status_plog.tsv"
DEFAULT_COLUMNS: List[str] = [TIME_COLUMN, LAST_AVG_SINR_COLUMN, LAST_VELOCITY_COLUMN, LAST_MOTION_STATUS_COLUMN]
ARG_MIN_BASELINE_SINR = f"{ARGUMENT_LONG_PREFIX}min_baseline_sinr"
ARG_MAX_VELOCITY = f"{ARGUMENT_LONG_PREFIX}max_velocity"
ARG_EXPECTED_MOTION_STATUS = f"{ARGUMENT_LONG_PREFIX}expected_motion_status"
ARG_IMX_REV = f"{ARGUMENT_LONG_PREFIX}imx_rev"
TEST_NAME = "stationary_kim_velocity_motion_status_plog"


def getToolData() -> ToolData:
    sample_log_path = ACU_LOG_PATH / "192.168.100.57" / "P_20260216_000000.txt"
    args = {ARG_PLOG_PATHS: [str(sample_log_path)], ARG_OUTPUT_PATH: str(DEFAULT_OUTPUT_PATH), ARG_IMX_REV: DEFAULT_IMX_REV_STR}
    return ToolData(tool_templates=[ToolTemplate(name="Check stationary KIM velocity/motion P-log", extra_description="Use high-SINR P-log rows as stationary baseline and flag velocity or motion-status movement.", args=args, search_root=ACU_LOG_PATH, override_cmd_invocation=WIN_CMD_INVOCATION)], tool_priority=EToolPriority.Level10_Last, hidden=False)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check stationary KIM velocity and motion status against high-SINR baseline rows.", formatter_class=argparse.RawTextHelpFormatter)
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))
    parser.add_argument(ARG_PLOG_PATHS, required=True, nargs="+", type=Path, help="One or more periodic log file paths (P_*.txt/P_*.log).")
    parser.add_argument(ARG_TIME_WINDOW, type=float, default=None, help="Time window in hours to keep from the tail of the log (default: all rows).")
    parser.add_argument(ARG_OUTPUT_PATH, type=Path, default=Path(DEFAULT_OUTPUT_PATH), help=f"Destination file for compact log output (default: {DEFAULT_OUTPUT_PATH}).")
    parser.add_argument(ARG_MIN_BASELINE_SINR, type=float, default=DEFAULT_MIN_BASELINE_SINR, help=f"Rows with {LAST_AVG_SINR_COLUMN} >= this value are baseline rows (default: {DEFAULT_MIN_BASELINE_SINR}).")
    parser.add_argument(ARG_IMX_REV, default=DEFAULT_IMX_REV_STR, choices=SUPPORTED_IMX_REV_STRS, help=f"IMX revision spec to use for default thresholds (default: {DEFAULT_IMX_REV_STR}).")
    parser.add_argument(ARG_MAX_VELOCITY, type=float, default=None, help="Max allowed absolute LAST_VELOCITY for stationary rows (default: selected IMX velocity accuracy).")
    parser.add_argument(ARG_EXPECTED_MOTION_STATUS, nargs="+", type=int, default=sorted(DEFAULT_EXPECTED_MOTION_STATUSES), help="Expected integer motion-status values for stationary rows (default: 0).")
    return parser.parse_args(argv)


def _write_metadata_file(output_path: Path, input_paths: Sequence[Path], time_window: Optional[float], min_baseline_sinr: float,
                         velocity_config: DeviationColumnConfig, expected_motion_statuses: Set[int], imx_spec: ImxSpecs, issues: Sequence[str]) -> Path:
    metadata_path = output_path.parent / f"stationary_kim_velocity_motion_plog_metadata_{get_file_timestamp()}.json"
    metadata = {
        "generated_at_utc": get_iso_timestamp(),
        "arguments": {
            "input_paths": [str(path) for path in input_paths],
            "time_window_hours": time_window,
            "output_path": str(output_path),
            "imx_rev": imx_spec.imx_rev_str,
            "imx_spec": imx_spec.to_message(),
            "min_baseline_sinr": min_baseline_sinr,
            "max_velocity": velocity_config.max_deviation,
            "ignored_velocity_values": velocity_config.ignored_deviation_values,
            "expected_motion_statuses": sorted(expected_motion_statuses),
        },
        "issue_counts_by_name": compact_issues_by_prefix(issues),
        "issues_total": len(issues),
        "issues_sample": list(issues[:200]),
        "status": "fail" if issues else "pass",
    }
    write_to_file(str(metadata_path), json.dumps(metadata, indent=2), mode=WriteMode.OVERWRITE)
    return metadata_path


def _log_baseline_motion_statuses(file_data, baseline_positions: Sequence[int], expected_motion_statuses: Set[int]) -> None:
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    status_idx = name_to_idx.get(LAST_MOTION_STATUS_COLUMN)
    if status_idx is None:
        return
    counts: Dict[str, int] = {}
    for row_position in baseline_positions:
        row = file_data.raw_data_rows[row_position]
        value = row[status_idx].strip() if status_idx < len(row) else ""
        counts[value] = counts.get(value, 0) + 1
    LOG(f"{LOG_PREFIX_MSG_INFO} baseline {LAST_MOTION_STATUS_COLUMN}: expected={sorted(expected_motion_statuses)}, counts={counts}")


def check_velocity_motion_file(file_data, min_baseline_sinr: float, velocity_config: DeviationColumnConfig, expected_motion_statuses: Set[int]) -> List[str]:
    issues = require_columns(file_data, DEFAULT_COLUMNS)
    if issues:
        return issues
    baseline_rows = find_baseline_rows(file_data, min_baseline_sinr)
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    if baseline_rows is None:
        return [f"BASELINE_MISSING, no rows with {LAST_AVG_SINR_COLUMN} >= {min_baseline_sinr:.3f} in {display_file}"]
    baseline_stats = get_baseline_stats_by_column(file_data, baseline_rows, [velocity_config])
    log_baseline_summary(file_data, baseline_rows, baseline_stats)
    _log_baseline_motion_statuses(file_data, baseline_rows.row_positions, expected_motion_statuses)
    issues.extend(check_baseline_spread(file_data, baseline_stats, [velocity_config]))

    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    status_idx = name_to_idx.get(LAST_MOTION_STATUS_COLUMN)
    velocity_samples: List[DeviationSample] = []
    ignored_counts_by_column_value: Dict[str, Dict[float, int]] = {}
    for row_position, row in enumerate(file_data.raw_data_rows):
        row_num = get_row_number(file_data, row_position)
        time_value = get_time_value(file_data, row, name_to_idx)
        velocity = get_numeric_value(row, name_to_idx, velocity_config.column)
        if velocity is None:
            issues.append(append_issue_row_context(f"VELOCITY_INVALID, row={row_num}, time={time_value}, {velocity_config.column}=<invalid>", row, name_to_idx) + f" in {display_file}")
        elif is_ignored_deviation_value(velocity, velocity_config.ignored_deviation_values):
            record_ignored_deviation_value_count(ignored_counts_by_column_value, velocity_config.column, velocity)
        elif abs(velocity) > velocity_config.max_deviation:
            velocity_samples.append(
                DeviationSample(row_number=row_num, time_value=time_value, column=velocity_config.column, value=velocity,
                                baseline_value=None, deviation=abs(velocity), threshold=velocity_config.max_deviation,
                                display_file=display_file, row_context=get_issue_row_context(row, name_to_idx))
            )
        motion_status_raw = row[status_idx].strip() if status_idx is not None and status_idx < len(row) else ""
        motion_status = parse_int(motion_status_raw)
        if motion_status is None:
            issues.append(append_issue_row_context(f"MOTION_STATUS_INVALID, row={row_num}, time={time_value}, {LAST_MOTION_STATUS_COLUMN}={motion_status_raw or '<blank>'}", row, name_to_idx) + f" in {display_file}")
        elif motion_status not in expected_motion_statuses:
            issues.append(append_issue_row_context(f"MOTION_STATUS_UNEXPECTED, row={row_num}, time={time_value}, {LAST_MOTION_STATUS_COLUMN}={motion_status}, expected={sorted(expected_motion_statuses)}", row, name_to_idx) + f" in {display_file}")
    log_ignored_deviation_value_counts(file_data, ignored_counts_by_column_value)
    issues.extend(build_grouped_deviation_issues("VELOCITY_OUT_OF_RANGE", {velocity_config.column: velocity_samples}))
    return issues


def run_stationary_kim_velocity_motion_plog_test(input_paths: Sequence[Path], output_path: Path, time_window: Optional[float], min_baseline_sinr: float,
                                                 max_velocity: float, expected_motion_statuses: Set[int], imx_spec: ImxSpecs) -> None:
    input_paths = [Path(get_normalized_path(Path(path), target_platform=ETargetPlatform.CURRENT, log_label="P-log input path")) for path in input_paths]
    output_path = Path(get_normalized_path(Path(output_path), target_platform=ETargetPlatform.CURRENT, log_label="output path"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plog_files = sorted({_validate_plog_file(input_path) for input_path in input_paths})
    LOG(f"{LOG_PREFIX_MSG_INFO} Found {len(plog_files)} unique P-log file(s) for stationary KIM velocity/motion-status analysis.")
    log_imx_spec(imx_spec)
    velocity_config = DeviationColumnConfig(LAST_VELOCITY_COLUMN, max_velocity, imx_spec.get_static_velocity_ignored_deviation_values())
    LOG(f"{LOG_PREFIX_MSG_INFO} Velocity max threshold: {velocity_config.max_deviation:.6f} m/s")
    LOG(f"{LOG_PREFIX_MSG_INFO} Velocity ignored deviation values: {velocity_config.ignored_deviation_values}")
    processed_data = process_plog_files(plog_files, DEFAULT_COLUMNS, time_window)
    rows_written = sum(len(file_data.raw_data_rows) for file_data in processed_data)
    if rows_written == 0:
        LOG_ISSUE(f"No rows found across {len(plog_files)} file(s); nothing to write.")
        return
    write_to_file(str(output_path), _get_compact_log_str(processed_data, DEFAULT_COLUMNS), mode=WriteMode.OVERWRITE)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} KIM velocity/motion compact log created: {format_path_for_display(output_path)}")
    issues: List[str] = []
    for file_data in processed_data:
        issues.extend(check_velocity_motion_file(file_data, min_baseline_sinr, velocity_config, expected_motion_statuses))
    metadata_path = _write_metadata_file(output_path, input_paths, time_window, min_baseline_sinr, velocity_config, expected_motion_statuses, imx_spec, issues)
    LOG(f"{LOG_PREFIX_MSG_INFO} Metadata saved: {format_path_for_display(metadata_path)}")
    open_path_in_explorer(output_path)
    if issues:
        LOG_LINE_SEPARATOR()
        LOG(f"{LOG_PREFIX_MSG_ERROR} Found {len(issues)} stationary KIM velocity/motion-status issue(s).")
        for issue in issues:
            LOG(f"  - {issue}", show_time=False)
        raise SystemExit(1)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} No stationary KIM velocity/motion-status issues found across {len(processed_data)} file(s).")


class StationaryKimVelocityMotionStatusPlogTest(TestLogInterface):
    TEST_NAME = TEST_NAME

    @classmethod
    def get_target_log_types(cls) -> List[EUtLogType]:
        return [EUtLogType.PLOG]

    @classmethod
    def run_test(cls, log_paths_by_type: Dict[EUtLogType, List[Path]]) -> None:
        normalized_map = normalize_log_paths_map(log_paths_by_type)
        plog_paths = normalized_map.get(EUtLogType.PLOG, [])
        if not plog_paths:
            LOG_EXCEPTION(ValueError("No P-log files found for stationary KIM velocity/motion-status test."), exit=True)
        imx_spec = get_imx_specs(DEFAULT_IMX_REV_STR)
        run_stationary_kim_velocity_motion_plog_test(plog_paths, Path(DEFAULT_OUTPUT_PATH), None, DEFAULT_MIN_BASELINE_SINR,
                                                     imx_spec.get_static_velocity_max_deviation(), set(DEFAULT_EXPECTED_MOTION_STATUSES), imx_spec)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    time_window_raw = get_arg_value(args, ARG_TIME_WINDOW)
    imx_spec = get_imx_specs(str(get_arg_value(args, ARG_IMX_REV) or DEFAULT_IMX_REV_STR))
    max_velocity_raw = get_arg_value(args, ARG_MAX_VELOCITY)
    run_stationary_kim_velocity_motion_plog_test(
        input_paths=get_arg_value(args, ARG_PLOG_PATHS) or [],
        output_path=Path(get_arg_value(args, ARG_OUTPUT_PATH)),
        time_window=float(time_window_raw) if time_window_raw is not None else None,
        min_baseline_sinr=float(get_arg_value(args, ARG_MIN_BASELINE_SINR)),
        max_velocity=float(max_velocity_raw) if max_velocity_raw is not None else imx_spec.get_static_velocity_max_deviation(),
        expected_motion_statuses=set(get_arg_value(args, ARG_EXPECTED_MOTION_STATUS) or sorted(DEFAULT_EXPECTED_MOTION_STATUSES)),
        imx_spec=imx_spec,
    )


if __name__ == "__main__":
    main()
