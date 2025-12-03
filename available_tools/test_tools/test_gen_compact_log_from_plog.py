#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Generate a compact Intellian periodic log by selecting a subset of columns.

The script:
1) Parses a periodic log (P-log) and stores the filtered rows in a structured form.
2) Recreates the log file but only keeps the requested columns, keeping the metadata lines intact.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from dev_common import *
from unit_tests.acu_log_tests.periodic_log_constants import (
    LAST_RTK_COMPASS_STATUS_COLUMN,
    LAST_VELOCITY_COLUMN,
    TIME_COLUMN,
)
from unit_tests.acu_log_tests.periodic_log_helper import (
    PLogData,
    build_time_series,
    compute_time_bounds,
    find_header_and_rows,
    select_columns,
)


DEFAULT_TIME_WINDOW_HOURS = 0.1  # 6 minutes
DEFAULT_COLUMNS: List[str] = [TIME_COLUMN, LAST_VELOCITY_COLUMN, LAST_RTK_COMPASS_STATUS_COLUMN]
DEFAULT_OUTPUT_PATH = TEMP_FOLDER_PATH / "compact_plog.tsv"

ARG_PLOG_PATH = f"{ARGUMENT_LONG_PREFIX}plog_path"
ARG_COLUMNS = f"{ARGUMENT_LONG_PREFIX}columns"
ARG_TIME_WINDOW = f"{ARGUMENT_LONG_PREFIX}hours"
ARG_OUTPUT_PATH = f"{ARGUMENT_LONG_PREFIX}output"


@dataclass
class CompactPlogRow:
    """Holds selected column values for a single P-log row."""

    values: Dict[str, str]

    def to_tsv_values(self, order: Sequence[str]) -> List[str]:
        """Return the values ordered for TSV output."""
        return [self.values.get(column, "") for column in order]


def get_tool_templates() -> List[ToolTemplate]:
    """
    Provide a single template pointing to the local ACU log folder so users can edit paths quickly.
    """
    sample_log_path = ACU_LOG_PATH / "192.168.101.79" / "P_YYYYMMDD_000000.txt"
    return [
        ToolTemplate(
            name="Compact P-log (Time/Velocity/RTK)",
            extra_description="Keeps Time/Velocity/RTK Compass columns and saves TSV under temp/.",
            args={
                ARG_PLOG_PATH: str(sample_log_path),
                ARG_OUTPUT_PATH: str(DEFAULT_OUTPUT_PATH),
                ARG_COLUMNS: DEFAULT_COLUMNS,
                ARG_TIME_WINDOW: DEFAULT_TIME_WINDOW_HOURS,
            },
            search_root=ACU_LOG_PATH,
            usage_note="Update --plog_path to reference the fetched P-log you want to shrink.",
            is_use_win_python=True
        ),
    ]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter Intellian P-log files down to a compact TSV with selected columns.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    parser.add_argument(
        ARG_PLOG_PATH,
        required=True,
        type=Path,
        help="Path to the periodic log file (P_*).",
    )
    parser.add_argument(
        ARG_COLUMNS,
        nargs="+",
        default=None,
        metavar="COLUMN",
        help="Space-separated list of column names to keep (default: Time/Velocity/RTK Compass).",
    )
    parser.add_argument(
        ARG_TIME_WINDOW,
        type=float,
        default=DEFAULT_TIME_WINDOW_HOURS,
        help=f"Time window in hours to keep from the tail of the log (default: {DEFAULT_TIME_WINDOW_HOURS}).",
    )
    parser.add_argument(
        ARG_OUTPUT_PATH,
        type=Path,
        default=Path(DEFAULT_OUTPUT_PATH),
        help=f"Destination file for the compact log (default: {DEFAULT_OUTPUT_PATH}).",
    )

    return parser.parse_args(argv)


def _normalize_columns(columns: Sequence[str]) -> List[str]:
    """Strip blanks, remove duplicates, and keep Time column first."""
    cleaned: List[str] = []
    seen = set()
    for column in columns:
        candidate = column.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        cleaned.append(candidate)

    if not cleaned:
        raise ValueError("Please provide at least one valid column name.")

    if TIME_COLUMN in cleaned:
        cleaned = [TIME_COLUMN] + [col for col in cleaned if col != TIME_COLUMN]

    return cleaned


def _parse_plog_text(log_text: str, target_columns: List[str], max_time_capture: float) -> PLogData:
    """Replicates parse_periodic_log but works with already-loaded text so we only read once."""
    header, all_rows = find_header_and_rows(log_text)
    if not header or TIME_COLUMN not in header:
        raise ValueError("Log file does not contain a valid header starting with the Time column.")

    time_idx = header.index(TIME_COLUMN)
    base_time, parsed_times = build_time_series(all_rows, time_idx)
    if base_time is None:
        raise ValueError("Unable to determine the base time from the P-log.")

    found_target_columns, missing = select_columns(header, target_columns)
    if missing:
        raise ValueError(f"Missing target columns: {missing}")

    valid_rows: List[List[str]] = []
    valid_times: List[datetime] = []
    for row, timestamp in zip(all_rows, parsed_times):
        if timestamp is None:
            continue
        valid_rows.append(row)
        valid_times.append(timestamp)

    start, end = compute_time_bounds(valid_times, max_time_capture)
    filtered_rows: List[List[str]] = []
    filtered_times: List[datetime] = []
    if start is not None and end is not None:
        for row, timestamp in zip(valid_rows, valid_times):
            if start <= timestamp <= end:
                filtered_rows.append(row)
                filtered_times.append(timestamp)
    else:
        filtered_rows = valid_rows
        filtered_times = valid_times

    return PLogData(
        header=header,
        rows=filtered_rows,
        target_columns=found_target_columns,
        base_time=base_time,
        timestamps=filtered_times,
    )


def _extract_metadata_lines(log_text: str) -> List[str]:
    """
    Return the lines prior to the header so the compact log preserves metadata like version/date.
    """
    metadata: List[str] = []
    for line in log_text.splitlines():
        if line.startswith(f"{TIME_COLUMN}\t"):
            break
        metadata.append(line)
    return metadata


def _build_compact_rows(plog_data: PLogData) -> List[CompactPlogRow]:
    """Convert PLogData rows into CompactPlogRow objects keyed by column name."""
    name_to_idx: Dict[str, int] = {name: idx for idx, name in enumerate(plog_data.header)}
    compact_rows: List[CompactPlogRow] = []

    for raw_row in plog_data.raw_rows:
        row_values: Dict[str, str] = {}
        for column in plog_data.target_columns:
            idx = name_to_idx.get(column)
            if idx is None or idx >= len(raw_row):
                row_values[column] = ""
            else:
                row_values[column] = raw_row[idx]
        compact_rows.append(CompactPlogRow(row_values=row_values))

    return compact_rows


def _render_compact_log(metadata_lines: Sequence[str], columns: Sequence[str], rows: Sequence[CompactPlogRow]) -> str:
    """Build the final TSV content, reusing metadata lines and the filtered rows."""
    lines: List[str] = []
    lines.extend(line for line in metadata_lines if line is not None)
    lines.append("\t".join(columns))
    for row in rows:
        lines.append("\t".join(row.to_tsv_values(columns)))
    lines.append("")  # Ensure the file ends with a newline
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    log_path = Path(get_arg_value(args, ARG_PLOG_PATH)).expanduser()
    output_path = Path(get_arg_value(args, ARG_OUTPUT_PATH)).expanduser()
    time_window = float(get_arg_value(args, ARG_TIME_WINDOW))
    requested_columns = get_arg_value(args, ARG_COLUMNS) or list(DEFAULT_COLUMNS)
    target_columns = _normalize_columns(requested_columns)

    if not log_path.exists():
        LOG_EXCEPTION(ValueError(f"P-log not found: {log_path}"), exit=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    LOG(f"{LOG_PREFIX_MSG_INFO} Reading P-log: {log_path}")
    log_text = read_file_content(log_path, encoding="utf-8", errors="replace")
    metadata_lines = _extract_metadata_lines(log_text)

    LOG(f"{LOG_PREFIX_MSG_INFO} Parsing and filtering last {time_window} hour(s) for columns: {target_columns}")
    plog_data = _parse_plog_text(log_text, target_columns, time_window)

    compact_rows = _build_compact_rows(plog_data)
    if not compact_rows:
        LOG(f"{LOG_PREFIX_MSG_WARNING} No rows found inside the requested time window; nothing to write.")
        return

    LOG(f"{LOG_PREFIX_MSG_INFO} Writing {len(compact_rows)} row(s) with {len(target_columns)} column(s) to {output_path}")
    compact_content = _render_compact_log(metadata_lines, target_columns, compact_rows)
    write_to_file(str(output_path), compact_content, mode=WriteMode.OVERWRITE)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Compact log created: {output_path}")


if __name__ == "__main__":
    main()
