#!/usr/local/bin/local_python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from dev.dev_common import *
from unit_tests.acu_log_tests.periodic_log_constants import LAST_AVG_SINR_COLUMN, TIME_COLUMN
from unit_tests.acu_log_tests.periodic_log_helper import PLogData


IMX5_REV_STR = "IMX5"
IMX6_REV_STR = "IMX6"
KIM_SPEC_KEY = "Kim"
DEFAULT_IMX_REV_STR = IMX5_REV_STR
DEFAULT_MIN_BASELINE_SINR = 8.0 #Note that this is x10 scale. e.g. value = 80 mean 8db in reality
DEFAULT_BASELINE_MAX_DEVIATION = 0.05
DEFAULT_EXPECTED_MOTION_STATUSES: Set[int] = {0}


@dataclass
class NumericStats:
    count: int
    avg: float
    min_value: float
    max_value: float

    @property
    def max_deviation(self) -> float:
        return self.max_value - self.min_value

    def to_message(self, label: str) -> str:
        return f"{label}: count={self.count}, avg={self.avg:.6f}, min={self.min_value:.6f}, max={self.max_value:.6f}, max_dev={self.max_deviation:.6f}"


@dataclass
class BaselineRows:
    row_positions: List[int]
    row_numbers: List[int]
    sinr_stats: NumericStats


@dataclass(frozen=True)
class ImxSpecs:
    imx_rev_str: str
    device_name: str
    static_roll_rms_deg: float
    static_pitch_rms_deg: float
    static_heading_dual_compass_rms_deg: float
    static_heading_magnetometer_rms_deg: float
    velocity_accuracy_mps: float
    dynamic_roll_pitch_rms_deg: float
    dynamic_heading_rms_deg: float
    angular_resolution_deg: float

    def get_roll_max_deviation(self) -> float:
        return self.static_roll_rms_deg

    def get_pitch_max_deviation(self) -> float:
        return self.static_pitch_rms_deg

    def get_yaw_max_deviation(self) -> float:
        return self.static_heading_dual_compass_rms_deg

    def get_static_velocity_max_deviation(self) -> float:
        return self.velocity_accuracy_mps

    def get_static_rpy_max_deviation(self) -> float:
        return max(self.get_roll_max_deviation(), self.get_pitch_max_deviation(), self.get_yaw_max_deviation())

    def to_message(self) -> str:
        return (
            f"imx_rev={self.imx_rev_str}, device={self.device_name}, "
            f"static_roll={self.static_roll_rms_deg:.3f}deg RMS, static_pitch={self.static_pitch_rms_deg:.3f}deg RMS, "
            f"static_heading_dual_compass={self.static_heading_dual_compass_rms_deg:.3f}deg RMS, "
            f"velocity_accuracy={self.velocity_accuracy_mps:.3f}m/s"
        )


IMX_SPECS_BY_REV_AND_DEVICE: Dict[str, Dict[str, ImxSpecs]] = {
    IMX5_REV_STR: {
        KIM_SPEC_KEY: ImxSpecs(
            imx_rev_str=IMX5_REV_STR, device_name=KIM_SPEC_KEY,
            static_roll_rms_deg=0.1, static_pitch_rms_deg=0.1,
            static_heading_dual_compass_rms_deg=0.4, static_heading_magnetometer_rms_deg=1.0,
            velocity_accuracy_mps=0.03, dynamic_roll_pitch_rms_deg=0.04,
            dynamic_heading_rms_deg=0.13, angular_resolution_deg=0.05,
        ),
    },
    IMX6_REV_STR: {
        KIM_SPEC_KEY: ImxSpecs(
            imx_rev_str=IMX6_REV_STR, device_name=KIM_SPEC_KEY,
            static_roll_rms_deg=0.09, static_pitch_rms_deg=0.09,
            static_heading_dual_compass_rms_deg=0.4, static_heading_magnetometer_rms_deg=1.0,
            velocity_accuracy_mps=0.02, dynamic_roll_pitch_rms_deg=0.03,
            dynamic_heading_rms_deg=0.09, angular_resolution_deg=0.05,
        ),
    },
}
# Backward-compatible name matching the existing task wording.
imxSpecs = IMX_SPECS_BY_REV_AND_DEVICE
SUPPORTED_IMX_REV_STRS: List[str] = sorted(IMX_SPECS_BY_REV_AND_DEVICE.keys())


def normalize_imx_rev_str(imx_rev_str: str) -> str:
    normalized = imx_rev_str.strip().upper().replace("-", "")
    if normalized not in IMX_SPECS_BY_REV_AND_DEVICE:
        raise ValueError(f"Unsupported IMX rev '{imx_rev_str}'. Expected one of: {', '.join(SUPPORTED_IMX_REV_STRS)}")
    return normalized


def get_imx_specs(imx_rev_str: str = DEFAULT_IMX_REV_STR, device_name: str = KIM_SPEC_KEY) -> ImxSpecs:
    normalized_rev = normalize_imx_rev_str(imx_rev_str)
    device_specs = IMX_SPECS_BY_REV_AND_DEVICE.get(normalized_rev, {})
    spec = device_specs.get(device_name)
    if spec is None:
        raise ValueError(f"Unsupported IMX spec device '{device_name}' for rev '{normalized_rev}'. Expected one of: {', '.join(sorted(device_specs.keys()))}")
    return spec


def log_imx_spec(spec: ImxSpecs) -> None:
    LOG(f"{LOG_PREFIX_MSG_INFO} Using IMX spec: {spec.to_message()}")


def parse_float(value: str) -> Optional[float]:
    try:
        return float(value.strip())
    except (AttributeError, ValueError):
        return None


def parse_int(value: str) -> Optional[int]:
    parsed = parse_float(value)
    return None if parsed is None else int(parsed)


def get_row_number(file_data: PLogData, row_position: int) -> int:
    return file_data.plog_data_row_indices[row_position] if row_position < len(file_data.plog_data_row_indices) else row_position + 1


def get_time_value(file_data: PLogData, row: Sequence[str], name_to_idx: Dict[str, int]) -> str:
    time_idx = name_to_idx.get(TIME_COLUMN)
    return row[time_idx].strip() if time_idx is not None and time_idx < len(row) else "?"


def require_columns(file_data: PLogData, columns: Sequence[str]) -> List[str]:
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    missing = [column for column in columns if column not in file_data.header]
    return [] if not missing else [f"Row 1 in {display_file}: missing required columns: {', '.join(missing)}"]


def get_numeric_value(row: Sequence[str], name_to_idx: Dict[str, int], column: str) -> Optional[float]:
    idx = name_to_idx.get(column)
    if idx is None or idx >= len(row):
        return None
    return parse_float(row[idx])


def calculate_stats(values: Sequence[float]) -> Optional[NumericStats]:
    if not values:
        return None
    return NumericStats(count=len(values), avg=sum(values) / len(values), min_value=min(values), max_value=max(values))


def find_baseline_rows(file_data: PLogData, min_sinr: float) -> Optional[BaselineRows]:
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    sinr_idx = name_to_idx.get(LAST_AVG_SINR_COLUMN)
    if sinr_idx is None:
        return None
    row_positions: List[int] = []
    row_numbers: List[int] = []
    sinr_values: List[float] = []
    for row_position, row in enumerate(file_data.raw_data_rows):
        if sinr_idx >= len(row):
            continue
        sinr = parse_float(row[sinr_idx])
        if sinr is None or sinr < min_sinr:
            continue
        row_positions.append(row_position)
        row_numbers.append(get_row_number(file_data, row_position))
        sinr_values.append(sinr)
    stats = calculate_stats(sinr_values)
    return None if stats is None else BaselineRows(row_positions=row_positions, row_numbers=row_numbers, sinr_stats=stats)


def get_baseline_stats_by_column(file_data: PLogData, baseline_rows: BaselineRows, columns: Sequence[str]) -> Dict[str, NumericStats]:
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    stats_by_column: Dict[str, NumericStats] = {}
    for column in columns:
        values = [value for row_position in baseline_rows.row_positions if (value := get_numeric_value(file_data.raw_data_rows[row_position], name_to_idx, column)) is not None]
        stats = calculate_stats(values)
        if stats is not None:
            stats_by_column[column] = stats
    return stats_by_column


def log_baseline_summary(file_data: PLogData, baseline_rows: BaselineRows, stats_by_column: Dict[str, NumericStats]) -> None:
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    row_span = f"{baseline_rows.row_numbers[0]}-{baseline_rows.row_numbers[-1]}" if baseline_rows.row_numbers else "none"
    LOG(f"{LOG_PREFIX_MSG_INFO} Baseline rows in {display_file}: count={len(baseline_rows.row_positions)}, source_rows={row_span}, min_{LAST_AVG_SINR_COLUMN}={baseline_rows.sinr_stats.min_value:.3f}")
    LOG(f"{LOG_PREFIX_MSG_INFO} {baseline_rows.sinr_stats.to_message('baseline ' + LAST_AVG_SINR_COLUMN)}")
    for column, stats in stats_by_column.items():
        LOG(f"{LOG_PREFIX_MSG_INFO} {stats.to_message('baseline ' + column)}")


def check_baseline_spread(file_data: PLogData, stats_by_column: Dict[str, NumericStats], max_deviation_by_column: Dict[str, float]) -> List[str]:
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    issues: List[str] = []
    for column, max_deviation in max_deviation_by_column.items():
        stats = stats_by_column.get(column)
        if stats is None:
            issues.append(f"BASELINE_MISSING_VALUE, {column}: no parseable baseline values in {display_file}")
            continue
        if stats.max_deviation > max_deviation:
            issues.append(f"BASELINE_SPREAD, {column}: max_dev={stats.max_deviation:.6f} > threshold={max_deviation:.6f}, avg={stats.avg:.6f}, min={stats.min_value:.6f}, max={stats.max_value:.6f} in {display_file}")
    return issues


def check_deviation_from_baseline(file_data: PLogData, baseline_stats_by_column: Dict[str, NumericStats], max_deviation_by_column: Dict[str, float],
                                  skip_row_positions: Optional[Set[int]] = None) -> List[str]:
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    skip_row_positions = skip_row_positions or set()
    issues: List[str] = []
    for row_position, row in enumerate(file_data.raw_data_rows):
        if row_position in skip_row_positions:
            continue
        row_num = get_row_number(file_data, row_position)
        time_value = get_time_value(file_data, row, name_to_idx)
        for column, max_deviation in max_deviation_by_column.items():
            stats = baseline_stats_by_column.get(column)
            value = get_numeric_value(row, name_to_idx, column)
            if stats is None or value is None:
                continue
            deviation = abs(value - stats.avg)
            if deviation > max_deviation:
                issues.append(f"RPY_DEVIATION, row={row_num}, time={time_value}, {column}={value:.6f}, baseline_avg={stats.avg:.6f}, deviation={deviation:.6f} > threshold={max_deviation:.6f} in {display_file}")
    return issues


def compact_issues_by_prefix(issues: Sequence[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for issue in issues:
        issue_name = issue.split(",", 1)[0]
        counts[issue_name] = counts.get(issue_name, 0) + 1
    return counts
