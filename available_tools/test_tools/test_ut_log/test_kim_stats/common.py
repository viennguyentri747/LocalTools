#!/usr/local/bin/local_python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from dev.dev_common import *
from unit_tests.acu_log_tests.periodic_log_constants import LAST_AVG_SINR_COLUMN, LAST_GPS1_CNO_COLUMN, LAST_GPS2_CNO_COLUMN, LAST_INS_STATUS_COLUMN, TIME_COLUMN
from unit_tests.acu_log_tests.periodic_log_helper import PLogData


IMX5_REV_STR = "IMX5"
IMX6_REV_STR = "IMX6"
KIM_SPEC_KEY = "Kim"
DEFAULT_IMX_REV_STR = IMX5_REV_STR
DEFAULT_MIN_BASELINE_SINR = 8.0 #Note that this is x10 scale. e.g. value = 80 mean 8db in reality
DEFAULT_EXPECTED_MOTION_STATUSES: Set[int] = {0}
ISSUE_CONTEXT_COLUMNS: List[str] = [LAST_GPS1_CNO_COLUMN, LAST_GPS2_CNO_COLUMN, LAST_INS_STATUS_COLUMN]


@dataclass
class NumericStats:
    count: int
    avg: float
    min_value: float
    max_value: float
    min_row_number: Optional[int] = None
    min_time_value: Optional[str] = None
    min_row_context: str = ""
    max_row_number: Optional[int] = None
    max_time_value: Optional[str] = None
    max_row_context: str = ""

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


@dataclass
class DeviationSample:
    row_number: int
    time_value: str
    column: str
    value: float
    baseline_value: Optional[float]
    deviation: float
    threshold: float
    display_file: str
    row_context: str = ""

    def to_row_message(self) -> str:
        baseline_msg = "" if self.baseline_value is None else f", baseline_avg={self.baseline_value:.6f}"
        context_msg = "" if not self.row_context else f", {self.row_context}"
        return (
            f"row={self.row_number}, time={self.time_value}, {self.column}={self.value:.6f}"
            f"{baseline_msg}, deviation={self.deviation:.6f} > threshold={self.threshold:.6f}{context_msg}"
        )


@dataclass(frozen=True)
class DeviationColumnConfig:
    column: str
    max_deviation: float
    ignored_deviation_values: Sequence[float] = field(default_factory=list)


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
    #Custom multiplier via testing
    roll_max_deviation_multiplier: float = 1.4
    pitch_max_deviation_multiplier: float = 1.4
    yaw_max_deviation_multiplier: float = 1.5
    static_velocity_max_deviation_multiplier: float = 1.2
    roll_ignored_deviation_values: List[float] = field(default_factory=lambda: [0.0])
    pitch_ignored_deviation_values: List[float] = field(default_factory=lambda: [0.0])
    yaw_ignored_deviation_values: List[float] = field(default_factory=lambda: [0.0])
    static_velocity_ignored_deviation_values: List[float] = field(default_factory=lambda: [0.0])

    def get_roll_max_deviation(self) -> float:
        return self.static_roll_rms_deg * self.roll_max_deviation_multiplier

    def get_pitch_max_deviation(self) -> float:
        return self.static_pitch_rms_deg * self.pitch_max_deviation_multiplier

    def get_yaw_max_deviation(self) -> float:
        return self.static_heading_dual_compass_rms_deg * self.yaw_max_deviation_multiplier

    def get_static_velocity_max_deviation(self) -> float:
        return self.velocity_accuracy_mps * self.static_velocity_max_deviation_multiplier

    def get_roll_ignored_deviation_values(self) -> List[float]:
        return self.roll_ignored_deviation_values

    def get_pitch_ignored_deviation_values(self) -> List[float]:
        return self.pitch_ignored_deviation_values

    def get_yaw_ignored_deviation_values(self) -> List[float]:
        return self.yaw_ignored_deviation_values

    def get_static_velocity_ignored_deviation_values(self) -> List[float]:
        return self.static_velocity_ignored_deviation_values

    def to_message(self) -> str:
        return (
            f"imx_rev={self.imx_rev_str}, device={self.device_name}, "
            f"static_roll={self.static_roll_rms_deg:.3f} deg RMS, static_pitch={self.static_pitch_rms_deg:.3f} deg RMS, "
            f"static_heading_dual_compass={self.static_heading_dual_compass_rms_deg:.3f} deg RMS, "
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


def get_issue_row_context(row: Sequence[str], name_to_idx: Dict[str, int], columns: Sequence[str] = ISSUE_CONTEXT_COLUMNS) -> str:
    parts: List[str] = []
    for column in columns:
        idx = name_to_idx.get(column)
        if idx is None:
            continue
        value = row[idx].strip() if idx < len(row) else ""
        parts.append(f"{column}={value or '<blank>'}")
    return ", ".join(parts)


def append_issue_row_context(message: str, row: Sequence[str], name_to_idx: Dict[str, int]) -> str:
    context = get_issue_row_context(row, name_to_idx)
    return message if not context else f"{message}, {context}"


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


def get_max_deviation_by_column(deviation_configs: Sequence[DeviationColumnConfig]) -> Dict[str, float]:
    return {config.column: config.max_deviation for config in deviation_configs}


def get_ignored_deviation_values_by_column(deviation_configs: Sequence[DeviationColumnConfig]) -> Dict[str, Sequence[float]]:
    return {config.column: config.ignored_deviation_values for config in deviation_configs}


def is_ignored_deviation_value(value: float, ignored_values: Sequence[float]) -> bool:
    return value in ignored_values


def record_ignored_deviation_value_count(counts_by_column_value: Dict[str, Dict[float, int]], column: str, value: float) -> None:
    value_counts = counts_by_column_value.setdefault(column, {})
    value_counts[value] = value_counts.get(value, 0) + 1


def log_ignored_deviation_value_counts(file_data: PLogData, counts_by_column_value: Dict[str, Dict[float, int]]) -> None:
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    for column in sorted(counts_by_column_value.keys()):
        value_counts = counts_by_column_value[column]
        if not value_counts:
            continue
        total_count = sum(value_counts.values())
        values_msg = ", ".join(f"{value:.6f}={value_counts[value]}" for value in sorted(value_counts.keys()))
        LOG(f"{LOG_PREFIX_MSG_INFO} ignored_deviation_values, column={column}, total_lines={total_count}, values={values_msg} in {display_file}")


def get_baseline_stats_by_column(file_data: PLogData, baseline_rows: BaselineRows, deviation_configs: Sequence[DeviationColumnConfig]) -> Dict[str, NumericStats]:
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    stats_by_column: Dict[str, NumericStats] = {}
    for config in deviation_configs:
        values: List[float] = []
        row_positions: List[int] = []
        for row_position in baseline_rows.row_positions:
            value = get_numeric_value(file_data.raw_data_rows[row_position], name_to_idx, config.column)
            if value is None or is_ignored_deviation_value(value, config.ignored_deviation_values):
                continue
            values.append(value)
            row_positions.append(row_position)
        stats = calculate_stats(values)
        if stats is not None:
            min_value_position = values.index(stats.min_value)
            max_value_position = values.index(stats.max_value)
            min_row_position = row_positions[min_value_position]
            max_row_position = row_positions[max_value_position]
            min_row = file_data.raw_data_rows[min_row_position]
            max_row = file_data.raw_data_rows[max_row_position]
            stats.min_row_number = get_row_number(file_data, min_row_position)
            stats.min_time_value = get_time_value(file_data, min_row, name_to_idx)
            stats.min_row_context = get_issue_row_context(min_row, name_to_idx)
            stats.max_row_number = get_row_number(file_data, max_row_position)
            stats.max_time_value = get_time_value(file_data, max_row, name_to_idx)
            stats.max_row_context = get_issue_row_context(max_row, name_to_idx)
            stats_by_column[config.column] = stats
    return stats_by_column


def log_baseline_summary(file_data: PLogData, baseline_rows: BaselineRows, stats_by_column: Dict[str, NumericStats]) -> None:
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    row_span = f"{baseline_rows.row_numbers[0]}-{baseline_rows.row_numbers[-1]}" if baseline_rows.row_numbers else "none"
    LOG(f"{LOG_PREFIX_MSG_INFO} Baseline rows in {display_file}: count={len(baseline_rows.row_positions)}, source_rows={row_span}, min_{LAST_AVG_SINR_COLUMN}={baseline_rows.sinr_stats.min_value:.3f}")
    LOG(f"{LOG_PREFIX_MSG_INFO} {baseline_rows.sinr_stats.to_message('baseline ' + LAST_AVG_SINR_COLUMN)}")
    for column, stats in stats_by_column.items():
        LOG(f"{LOG_PREFIX_MSG_INFO} {stats.to_message('baseline ' + column)}")


def check_baseline_spread(file_data: PLogData, stats_by_column: Dict[str, NumericStats], deviation_configs: Sequence[DeviationColumnConfig]) -> List[str]:
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    issues: List[str] = []
    for config in deviation_configs:
        stats = stats_by_column.get(config.column)
        if stats is None:
            issues.append(f"BASELINE_MISSING_VALUE, {config.column}: no parseable baseline values in {display_file}")
            continue
        if stats.max_deviation > config.max_deviation:
            min_context = "" if not stats.min_row_context else f", {stats.min_row_context}"
            max_context = "" if not stats.max_row_context else f", {stats.max_row_context}"
            issues.append(
                f"BASELINE_SPREAD, {config.column}: max_dev={stats.max_deviation:.6f} > baseline_spread_threshold={config.max_deviation:.6f}, "
                f"avg={stats.avg:.6f}, min_sample=[row={stats.min_row_number}, time={stats.min_time_value}, {config.column}={stats.min_value:.6f}{min_context}], "
                f"max_sample=[row={stats.max_row_number}, time={stats.max_time_value}, {config.column}={stats.max_value:.6f}{max_context}] in {display_file}"
            )
    return issues


def check_deviation_from_baseline(file_data: PLogData, baseline_stats_by_column: Dict[str, NumericStats], deviation_configs: Sequence[DeviationColumnConfig],
                                  skip_row_positions: Optional[Set[int]] = None, issue_name: str = "DEVIATION") -> List[str]:
    display_file = format_path_for_display(file_data.plog_file or Path("<unknown plog file>"))
    name_to_idx = {name: idx for idx, name in enumerate(file_data.header)}
    skip_row_positions = skip_row_positions or set()
    samples_by_column: Dict[str, List[DeviationSample]] = {}
    ignored_counts_by_column_value: Dict[str, Dict[float, int]] = {}
    for row_position, row in enumerate(file_data.raw_data_rows):
        for config in deviation_configs:
            value = get_numeric_value(row, name_to_idx, config.column)
            if value is not None and is_ignored_deviation_value(value, config.ignored_deviation_values):
                record_ignored_deviation_value_count(ignored_counts_by_column_value, config.column, value)
        if row_position in skip_row_positions:
            continue
        row_num = get_row_number(file_data, row_position)
        time_value = get_time_value(file_data, row, name_to_idx)
        for config in deviation_configs:
            stats = baseline_stats_by_column.get(config.column)
            value = get_numeric_value(row, name_to_idx, config.column)
            if stats is None or value is None:
                continue
            if is_ignored_deviation_value(value, config.ignored_deviation_values):
                continue
            deviation = abs(value - stats.avg)
            if deviation > config.max_deviation:
                samples_by_column.setdefault(config.column, []).append( DeviationSample(row_number=row_num, time_value=time_value, column=config.column, value=value, baseline_value=stats.avg, deviation=deviation, threshold=config.max_deviation, display_file=display_file, row_context=get_issue_row_context(row, name_to_idx)) )
    log_ignored_deviation_value_counts(file_data, ignored_counts_by_column_value)
    return build_grouped_deviation_issues(issue_name, samples_by_column)


def build_grouped_deviation_issues(issue_name: str, samples_by_column: Dict[str, List[DeviationSample]]) -> List[str]:
    issues: List[str] = []
    for column in sorted(samples_by_column.keys()):
        samples = sorted(samples_by_column[column], key=lambda sample: sample.row_number)
        if not samples:
            continue
        current_group: List[DeviationSample] = [samples[0]]
        for sample in samples[1:]:
            # A group is 1 consecutive set of issue rows for the same column; any non-issue row breaks the group.
            # Check if this issue row immediately follow the previous issue row
            if sample.row_number == current_group[-1].row_number + 1:
                current_group.append(sample)
                continue
            issues.append(_format_deviation_group(issue_name, current_group))
            current_group = [sample]
        issues.append(_format_deviation_group(issue_name, current_group))
    return issues


def _format_deviation_group(issue_name: str, samples: Sequence[DeviationSample]) -> str:
    max_sample = max(samples, key=lambda sample: sample.deviation)
    min_sample = min(samples, key=lambda sample: sample.deviation)
    avg_deviation = sum(sample.deviation for sample in samples) / len(samples)
    first = samples[0]
    last = samples[-1]
    baseline_msg = "" if first.baseline_value is None else f", baseline_avg={first.baseline_value:.6f}"
    if max_sample.deviation == min_sample.deviation and max_sample.deviation == avg_deviation:
        deviation_msg = f"deviation_max=deviation_min=avg_deviation={max_sample.deviation:.6f}"
    elif max_sample.deviation == min_sample.deviation:
        deviation_msg = f"deviation_max=deviation_min={max_sample.deviation:.6f}, avg_deviation={avg_deviation:.6f}"
    else:
        deviation_msg = f"deviation_max={max_sample.deviation:.6f}, deviation_min={min_sample.deviation:.6f}, avg_deviation={avg_deviation:.6f}"
    sample_msg = (
        f"min_sample=max_sample=[{max_sample.to_row_message()}]"
        if max_sample.row_number == min_sample.row_number and max_sample.column == min_sample.column and max_sample.deviation == min_sample.deviation
        else f"max_sample=[{max_sample.to_row_message()}], min_sample=[{min_sample.to_row_message()}]"
    )
    return (
        f"{issue_name}, rows={first.row_number}-{last.row_number}, column={first.column}, total_count={len(samples)}, "
        f"{deviation_msg}, threshold={first.threshold:.6f}{baseline_msg}, {sample_msg} in {first.display_file}"
    )


def compact_issues_by_prefix(issues: Sequence[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for issue in issues:
        issue_name = issue.split(",", 1)[0]
        counts[issue_name] = counts.get(issue_name, 0) + 1
    return counts
