#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from available_tools.test_tools.test_ut_log.log_test_interface import EUtLogType, TestLogInterface, normalize_log_paths_map
from available_tools.test_tools.test_ut_log.t_get_acu_logs import ACU_LOG_PATH
from available_tools.test_tools.test_ut_log.t_test_process_plog_local import ARG_OUTPUT_PATH, ARG_PLOG_PATHS, ARG_TIME_WINDOW, _get_compact_log_str, _validate_plog_file, process_plog_files
from available_tools.test_tools.test_ut_log.test_kim_stats.common import DEFAULT_IMX_REV_STR, DEFAULT_MIN_BASELINE_SINR, DeviationColumnConfig, ImxSpecs, check_baseline_spread, check_deviation_from_baseline, compact_issues_by_prefix, find_baseline_rows, get_baseline_stats_by_column, get_imx_specs, get_ignored_deviation_values_by_column, get_max_deviation_by_column, log_baseline_summary, log_imx_spec, require_columns, SUPPORTED_IMX_REV_STRS
from dev.dev_common import *
from unit_tests.acu_log_tests.periodic_log_constants import LAST_AVG_SINR_COLUMN, LAST_PITCH_P_COLUMN, LAST_ROLL_P_COLUMN, LAST_YAW_P_COLUMN, TIME_COLUMN

use_posix_paths()

WIN_CMD_INVOCATION = get_win_python_runner_cmd_invocation("available_tools.test_tools.test_ut_log.test_kim_stats.t_test_station_kim_rpy_plog")
DEFAULT_OUTPUT_PATH = get_temp_path(ETargetPlatform.WINDOWS) / "kim_rpy_stationary_plog.tsv"
DEFAULT_COLUMNS: List[str] = [TIME_COLUMN, LAST_AVG_SINR_COLUMN, LAST_ROLL_P_COLUMN, LAST_PITCH_P_COLUMN, LAST_YAW_P_COLUMN]
ARG_MIN_BASELINE_SINR = f"{ARGUMENT_LONG_PREFIX}min_baseline_sinr"
ARG_MAX_ROLL_DEVIATION = f"{ARGUMENT_LONG_PREFIX}max_roll_deviation"
ARG_MAX_PITCH_DEVIATION = f"{ARGUMENT_LONG_PREFIX}max_pitch_deviation"
ARG_MAX_YAW_DEVIATION = f"{ARGUMENT_LONG_PREFIX}max_yaw_deviation"
ARG_IMX_REV = f"{ARGUMENT_LONG_PREFIX}imx_rev"
TEST_NAME = "kim_rpy_stationary_plog"


def getToolData() -> ToolData:
    sample_log_path = ACU_LOG_PATH / "192.168.100.57" / "P_20260216_000000.txt"
    args = {ARG_PLOG_PATHS: [str(sample_log_path)], ARG_OUTPUT_PATH: str(DEFAULT_OUTPUT_PATH), ARG_MIN_BASELINE_SINR: DEFAULT_MIN_BASELINE_SINR, ARG_IMX_REV: DEFAULT_IMX_REV_STR}
    return ToolData(tool_templates=[ToolTemplate(name="Check stationary KIM RPY", extra_description="Use high-SINR rows as stationary baseline and flag roll/pitch/yaw movement outside tolerance.", args=args, search_root=ACU_LOG_PATH, override_cmd_invocation=WIN_CMD_INVOCATION)], tool_priority=EToolPriority.Level10_Last, hidden=False)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check stationary KIM roll/pitch/yaw against high-SINR baseline rows.", formatter_class=argparse.RawTextHelpFormatter)
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))
    parser.add_argument(ARG_PLOG_PATHS, required=True, nargs="+", type=Path, help="One or more periodic log file paths (P_*.txt/P_*.log).")
    parser.add_argument(ARG_TIME_WINDOW, type=float, default=None, help="Time window in hours to keep from the tail of the log (default: all rows).")
    parser.add_argument(ARG_OUTPUT_PATH, type=Path, default=Path(DEFAULT_OUTPUT_PATH), help=f"Destination file for compact log output (default: {DEFAULT_OUTPUT_PATH}).")
    parser.add_argument(ARG_MIN_BASELINE_SINR, type=float, default=DEFAULT_MIN_BASELINE_SINR, help=f"Rows with {LAST_AVG_SINR_COLUMN} >= this value are baseline rows (default: {DEFAULT_MIN_BASELINE_SINR}).")
    parser.add_argument(ARG_IMX_REV, default=DEFAULT_IMX_REV_STR, choices=SUPPORTED_IMX_REV_STRS, help=f"IMX revision spec to use for default thresholds (default: {DEFAULT_IMX_REV_STR}).")
    parser.add_argument(ARG_MAX_ROLL_DEVIATION, type=float, default=None, help="Max roll deviation from baseline average (default: selected IMX static roll RMS).")
    parser.add_argument(ARG_MAX_PITCH_DEVIATION, type=float, default=None, help="Max pitch deviation from baseline average (default: selected IMX static pitch RMS).")
    parser.add_argument(ARG_MAX_YAW_DEVIATION, type=float, default=None, help="Max yaw deviation from baseline average (default: selected IMX static heading RMS with dual compass).")
    return parser.parse_args(argv)


def _write_metadata_file(output_path: Path, input_paths: Sequence[Path], time_window: Optional[float], min_baseline_sinr: float,
                         deviation_configs: Sequence[DeviationColumnConfig], imx_spec: ImxSpecs, issues: Sequence[str]) -> Path:
    max_deviation_by_column = get_max_deviation_by_column(deviation_configs)
    metadata_path = output_path.parent / f"kim_rpy_stationary_metadata_{get_file_timestamp()}.json"
    metadata = {
        "generated_at_utc": get_iso_timestamp(),
        "arguments": {
            "input_paths": [str(path) for path in input_paths],
            "time_window_hours": time_window,
            "output_path": str(output_path),
            "imx_rev": imx_spec.imx_rev_str,
            "imx_spec": imx_spec.to_message(),
            "min_baseline_sinr": min_baseline_sinr,
            "max_deviation_by_column": max_deviation_by_column,
            "baseline_spread_threshold_by_column": max_deviation_by_column,
            "ignored_deviation_values_by_column": get_ignored_deviation_values_by_column(deviation_configs),
        },
        "issue_counts_by_name": compact_issues_by_prefix(issues),
        "issues_total": len(issues),
        "issues_sample": list(issues[:200]),
        "status": "fail" if issues else "pass",
    }
    write_to_file(str(metadata_path), json.dumps(metadata, indent=2), mode=WriteMode.OVERWRITE)
    return metadata_path


def check_rpy_file(file_data, min_baseline_sinr: float, deviation_configs: Sequence[DeviationColumnConfig]) -> List[str]:
    issues = require_columns(file_data, DEFAULT_COLUMNS)
    if issues:
        return issues
    baseline_rows = find_baseline_rows(file_data, min_baseline_sinr)
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    if baseline_rows is None:
        return [f"BASELINE_MISSING, no rows with {LAST_AVG_SINR_COLUMN} >= {min_baseline_sinr:.3f} in {display_file}"]
    baseline_stats = get_baseline_stats_by_column(file_data, baseline_rows, deviation_configs)
    log_baseline_summary(file_data, baseline_rows, baseline_stats)
    issues.extend(check_baseline_spread(file_data, baseline_stats, deviation_configs))
    issues.extend(check_deviation_from_baseline(file_data, baseline_stats, deviation_configs, skip_row_positions=set(baseline_rows.row_positions), issue_name="RPY_DEVIATION"))
    return issues


def run_kim_rpy_stationary_test(input_paths: Sequence[Path], output_path: Path, time_window: Optional[float], min_baseline_sinr: float,
                                deviation_configs: Sequence[DeviationColumnConfig], imx_spec: ImxSpecs) -> None:
    input_paths = [Path(get_normalized_path(Path(path), target_platform=ETargetPlatform.CURRENT, log_label="P-log input path")) for path in input_paths]
    output_path = Path(get_normalized_path(Path(output_path), target_platform=ETargetPlatform.CURRENT, log_label="output path"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plog_files = sorted({_validate_plog_file(input_path) for input_path in input_paths})
    LOG(f"{LOG_PREFIX_MSG_INFO} Found {len(plog_files)} unique P-log file(s) for stationary KIM RPY analysis.")
    log_imx_spec(imx_spec)
    max_deviation_by_column = get_max_deviation_by_column(deviation_configs)
    LOG(f"{LOG_PREFIX_MSG_INFO} RPY deviation-from-baseline-average thresholds: {max_deviation_by_column}")
    LOG(f"{LOG_PREFIX_MSG_INFO} RPY baseline max-min spread thresholds: {max_deviation_by_column}")
    LOG(f"{LOG_PREFIX_MSG_INFO} RPY ignored deviation values: {get_ignored_deviation_values_by_column(deviation_configs)}")
    processed_data = process_plog_files(plog_files, DEFAULT_COLUMNS, time_window)
    rows_written = sum(len(file_data.raw_data_rows) for file_data in processed_data)
    if rows_written == 0:
        LOG_ISSUE(f"No rows found across {len(plog_files)} file(s); nothing to write.")
        return
    write_to_file(str(output_path), _get_compact_log_str(processed_data, DEFAULT_COLUMNS), mode=WriteMode.OVERWRITE)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} KIM RPY compact log created: {format_path_for_display(output_path)}")
    issues: List[str] = []
    for file_data in processed_data:
        issues.extend(check_rpy_file(file_data, min_baseline_sinr, deviation_configs))
    metadata_path = _write_metadata_file(output_path, input_paths, time_window, min_baseline_sinr, deviation_configs, imx_spec, issues)
    LOG(f"{LOG_PREFIX_MSG_INFO} Metadata saved: {format_path_for_display(metadata_path)}")
    open_path_in_explorer(output_path)
    if issues:
        LOG_LINE_SEPARATOR()
        LOG(f"{LOG_PREFIX_MSG_ERROR} Found {len(issues)} stationary KIM RPY issue(s).")
        for issue in issues:
            LOG(f"  - {issue}", show_time=False)
        raise SystemExit(1)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} No stationary KIM RPY issues found across {len(processed_data)} file(s).")


class KimRpyStationaryPlogTest(TestLogInterface):
    TEST_NAME = TEST_NAME

    @classmethod
    def get_target_log_types(cls) -> List[EUtLogType]:
        return [EUtLogType.PLOG]

    @classmethod
    def run_test(cls, log_paths_by_type: Dict[EUtLogType, List[Path]]) -> None:
        normalized_map = normalize_log_paths_map(log_paths_by_type)
        plog_paths = normalized_map.get(EUtLogType.PLOG, [])
        if not plog_paths:
            LOG_EXCEPTION(ValueError("No P-log files found for stationary KIM RPY test."), exit=True)
        imx_spec = get_imx_specs(DEFAULT_IMX_REV_STR)
        deviation_configs = [
            DeviationColumnConfig(LAST_ROLL_P_COLUMN, imx_spec.get_roll_max_deviation(), imx_spec.get_roll_ignored_deviation_values()),
            DeviationColumnConfig(LAST_PITCH_P_COLUMN, imx_spec.get_pitch_max_deviation(), imx_spec.get_pitch_ignored_deviation_values()),
            DeviationColumnConfig(LAST_YAW_P_COLUMN, imx_spec.get_yaw_max_deviation(), imx_spec.get_yaw_ignored_deviation_values()),
        ]
        run_kim_rpy_stationary_test(plog_paths, Path(DEFAULT_OUTPUT_PATH), None, DEFAULT_MIN_BASELINE_SINR, deviation_configs, imx_spec)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    imx_spec = get_imx_specs(str(get_arg_value(args, ARG_IMX_REV) or DEFAULT_IMX_REV_STR))
    roll_deviation_raw = get_arg_value(args, ARG_MAX_ROLL_DEVIATION)
    pitch_deviation_raw = get_arg_value(args, ARG_MAX_PITCH_DEVIATION)
    yaw_deviation_raw = get_arg_value(args, ARG_MAX_YAW_DEVIATION)
    deviation_configs = [
        DeviationColumnConfig(LAST_ROLL_P_COLUMN, float(roll_deviation_raw) if roll_deviation_raw is not None else imx_spec.get_roll_max_deviation(), imx_spec.get_roll_ignored_deviation_values()),
        DeviationColumnConfig(LAST_PITCH_P_COLUMN, float(pitch_deviation_raw) if pitch_deviation_raw is not None else imx_spec.get_pitch_max_deviation(), imx_spec.get_pitch_ignored_deviation_values()),
        DeviationColumnConfig(LAST_YAW_P_COLUMN, float(yaw_deviation_raw) if yaw_deviation_raw is not None else imx_spec.get_yaw_max_deviation(), imx_spec.get_yaw_ignored_deviation_values()),
    ]
    time_window_raw = get_arg_value(args, ARG_TIME_WINDOW)
    run_kim_rpy_stationary_test(
        input_paths=get_arg_value(args, ARG_PLOG_PATHS) or [],
        output_path=Path(get_arg_value(args, ARG_OUTPUT_PATH)),
        time_window=float(time_window_raw) if time_window_raw is not None else None,
        min_baseline_sinr=float(get_arg_value(args, ARG_MIN_BASELINE_SINR)),
        deviation_configs=deviation_configs,
        imx_spec=imx_spec,
    )


if __name__ == "__main__":
    main()
