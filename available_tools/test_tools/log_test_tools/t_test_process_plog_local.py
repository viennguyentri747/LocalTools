#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from dev.dev_common import *
from unit_tests.acu_log_tests.periodic_log_constants import *
from unit_tests.acu_log_tests.periodic_log_helper import (
    PLogData,
    build_time_series,
    compute_time_bounds,
    find_header_and_rows,
    select_columns,
)

use_posix_paths()

#Note: need to make win python's pip to install local_tools package first by: cd ~/local_tools && <win_python_wsl_path> -m pip install -e .; otherwise the win_cmd_invocation won't work as it can't find the module to run.
WIN_CMD_INVOCATION = get_win_cmd_invocation("available_tools.test_tools.log_test_tools.t_test_process_plog_local")
DEFAULT_TIME_WINDOW_HOURS: float = 1.5  # 1.5 hours = 90 minutes
DEFAULT_COLUMNS: List[str] = [TIME_COLUMN, LAST_TIME_SYNC_COLUMN, LAST_VELOCITY_COLUMN, LAST_RTK_COMPASS_STATUS_COLUMN]
DEFAULT_OUTPUT_PATH = PERSISTENT_TEMP_PATH / "compact_plog.tsv"
ARG_PLOG_PATHS = f"{ARGUMENT_LONG_PREFIX}plog_paths"
ARG_COLUMNS = f"{ARGUMENT_LONG_PREFIX}columns"
ARG_TIME_WINDOW = f"{ARGUMENT_LONG_PREFIX}hours"
ARG_OUTPUT_PATH = f"{ARGUMENT_LONG_PREFIX}output"

def get_tool_templates() -> List[ToolTemplate]:
    """
    Provide a single template pointing to sample local ACU log files.
    """
    sample_log_path_1 = ACU_LOG_PATH / "192.168.100.61" / "P_20260216_000000.txt"
    #sample_log_path_2 = ACU_LOG_PATH / "192.168.100.61" / "P_20260217_000000.txt"
    args = {
        ARG_PLOG_PATHS: [str(sample_log_path_1)],
        ARG_OUTPUT_PATH: str(DEFAULT_OUTPUT_PATH),
        ARG_COLUMNS: DEFAULT_COLUMNS,
        ARG_TIME_WINDOW: DEFAULT_TIME_WINDOW_HOURS,
    }
   
    return [
        ToolTemplate(
            name="Compact P-log (Time/Velocity/RTK)",
            extra_description="Keeps Time/Velocity/RTK Compass columns and saves TSV under temp/.",
            args=args,
            search_root=ACU_LOG_PATH,
            usage_note="Update --plog_paths with one or more P-log file paths you want to shrink.",
            override_cmd_invocation=WIN_CMD_INVOCATION,
        ),
    ]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter Intellian P-log files down to a compact TSV with selected columns.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))

    parser.add_argument(ARG_PLOG_PATHS, required=True, nargs="+", type=Path, help="One or more periodic log file paths (P_*.txt/P_*.log).")
    parser.add_argument( ARG_COLUMNS, nargs="+", default=None, help="Space-separated list of column names to keep (default: Time/Velocity/RTK Compass).", )
    parser.add_argument( ARG_TIME_WINDOW, type=float, default=DEFAULT_TIME_WINDOW_HOURS, help="Time window in hours to keep from the tail of the log (default: all rows).", )
    parser.add_argument( ARG_OUTPUT_PATH, type=Path, default=Path(DEFAULT_OUTPUT_PATH), help=f"Destination file for the compact log (default: {DEFAULT_OUTPUT_PATH}).", )

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


def _parse_plog_text(log_text: str, target_columns: List[str], max_time_capture: Optional[float] = None) -> PLogData:
    """Replicates parse_periodic_log but works with already-loaded text so we only read once."""
    LOG(f"{LOG_PREFIX_MSG_INFO} Parsing plog with columns: {target_columns}{f' (max time capture: {max_time_capture} hours)' if max_time_capture is not None else ''}")
   
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
    valid_row_indices: List[int] = []
    for row_idx, (row, timestamp) in enumerate(zip(all_rows, parsed_times), start=1):
        if timestamp is None:
            continue
        valid_rows.append(row)
        valid_times.append(timestamp)
        valid_row_indices.append(row_idx)

    filtered_rows: List[List[str]] = []
    filtered_times: List[datetime] = []
    filtered_row_indices: List[int] = []
    if max_time_capture is None:
        filtered_rows = valid_rows
        filtered_times = valid_times
        filtered_row_indices = valid_row_indices
    else:
        start, end = compute_time_bounds(valid_times, max_time_capture)
        if start is not None and end is not None:
            for row, timestamp, row_idx in zip(valid_rows, valid_times, valid_row_indices):
                if start <= timestamp <= end:
                    filtered_rows.append(row)
                    filtered_times.append(timestamp)
                    filtered_row_indices.append(row_idx)
        else:
            filtered_rows = valid_rows
            filtered_times = valid_times
            filtered_row_indices = valid_row_indices

    LOG(f"Finished parsing P-log, filtered {len(filtered_rows)} rows.")
    return PLogData(
        header=header,
        data_rows=filtered_rows,
        target_columns=found_target_columns,
        base_time=base_time,
        timestamps=filtered_times,
        plog_data_row_indices=filtered_row_indices,
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


def process_plog_files(plog_files: Sequence[Path], target_columns: Sequence[str], time_window: Optional[float]) -> List[PLogData]:
    processed: List[PLogData] = []
    for plog_file in plog_files:
        LOG(f"{LOG_PREFIX_MSG_INFO} Reading P-log: {plog_file}")
        log_text = read_file_content(plog_file, encoding="utf-8", errors="replace")
        file_metadata_lines = _extract_metadata_lines(log_text)
        file_metadata_line = "\n".join(file_metadata_lines) if file_metadata_lines else None
        plog_data: PLogData = _parse_plog_text(log_text, list(target_columns), time_window)
        plog_data.plog_file = plog_file
        plog_data.file_metadata_line = file_metadata_line
        if not plog_data.raw_data_rows:
            if time_window is None:
                LOG(f"{LOG_PREFIX_MSG_WARNING} No rows found in {plog_file}; skipping.")
            else:
                LOG(f"{LOG_PREFIX_MSG_WARNING} No rows found inside the requested time window for {plog_file}; skipping.")
        processed.append(plog_data)
    return processed


def _get_compact_log_str(processed_data: Sequence[PLogData], columns: Sequence[str]) -> str:
    """Build the final TSV content from processed files and selected columns."""
    metadata_lines: List[str] = []
    for file_data in processed_data:
        if file_data.file_metadata_line:
            metadata_lines = file_data.file_metadata_line.split("\n")
            break
    lines: List[str] = []
    lines.extend(line for line in metadata_lines if line is not None)
    row_values: List[List[str]] = []
    for file_data in processed_data:
        name_to_idx: Dict[str, int] = {name: idx for idx, name in enumerate(file_data.header)}
        for raw_row in file_data.raw_data_rows:
            values: List[str] = []
            for column in columns:
                idx = name_to_idx.get(column)
                values.append(raw_row[idx] if idx is not None and idx < len(raw_row) else "")
            row_values.append(values)
    widths = [len(column) for column in columns]
    for values in row_values:
        for idx, value in enumerate(values):
            if len(value) > widths[idx]:
                widths[idx] = len(value)
    separator = "  "
    lines.append(separator.join(column.ljust(widths[idx]) for idx, column in enumerate(columns)))
    for values in row_values:
        lines.append(separator.join(value.ljust(widths[idx]) for idx, value in enumerate(values)))
    lines.append("")  # Ensure the file ends with a newline
    return "\n".join(lines)


def _is_plog_file(candidate: Path) -> bool:
    """Return True if the path resembles a periodic log file."""
    if not candidate.is_file():
        return False
    if not candidate.name.lower().startswith("p_"):
        return False
    return candidate.suffix.lower() in {".txt", ".log"}


def _validate_plog_file(plog_path: Path) -> Path:
    """Validate that input path is an existing P-log file path."""
    if not plog_path.exists():
        LOG_EXCEPTION(ValueError(f"P-log path not found: {plog_path}"), exit=True)
    if not plog_path.is_file():
        LOG_EXCEPTION(ValueError(f"P-log path must be a file, not a directory: {plog_path}"), exit=True)
    if not _is_plog_file(plog_path):
        LOG_EXCEPTION(ValueError(f"Invalid P-log file name/type: {plog_path}. Expected P_*.txt or P_*.log"), exit=True)
    return plog_path


def _write_metadata_file(output_plog_path: Path, input_paths: Sequence[Path], time_window: Optional[float], target_columns: Sequence[str], processed_files: Sequence[Path], rows_written: int) -> Path:
    """Persist metadata as JSON next to the compact log artifact."""
    now_utc = datetime.now(timezone.utc)
    timestamp = now_utc.strftime("%Y%m%d_%H%M%S")
    metadata_path = output_plog_path.parent / f"compact_plog_metadata_{timestamp}.json"
    metadata = {
        "generated_at_utc": now_utc.isoformat(),
        "arguments": {
            "input_paths": [str(path) for path in input_paths],
            "time_window_hours": time_window,
            "columns": list(target_columns),
            "output_plog_path": str(output_plog_path),
        },
        # "plog_file_count": len(processed_files),
        "plog_files": [str(path) for path in processed_files],
        "rows_written": rows_written,
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
    time_window = get_arg_value(args, ARG_TIME_WINDOW)
    if time_window is not None:
        time_window = float(time_window)
    requested_columns = get_arg_value(args, ARG_COLUMNS) or list(DEFAULT_COLUMNS)
    target_columns = _normalize_columns(requested_columns)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plog_files = sorted({_validate_plog_file(input_path) for input_path in input_paths})
    LOG(f"{LOG_PREFIX_MSG_INFO} Found {len(plog_files)} unique P-log file(s) to analyze from {len(input_paths)} input path(s).")

    processed_data: List[PLogData] = process_plog_files(plog_files, target_columns, time_window)
    processed_files = [file_data.plog_file for file_data in processed_data if file_data.plog_file is not None]
    rows_written = sum(len(file_data.raw_data_rows) for file_data in processed_data)
    if rows_written == 0:
        LOG(f"{LOG_PREFIX_MSG_WARNING} No rows found across {len(plog_files)} file(s); nothing to write.")
        return

    LOG(
        f"{LOG_PREFIX_MSG_INFO} Writing {rows_written} row(s) with {len(target_columns)} column(s) to {output_path}"
    )
    compact_content = _get_compact_log_str(processed_data, target_columns)
    write_to_file(str(output_path), compact_content, mode=WriteMode.OVERWRITE)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Compact log created: {output_path}")

    metadata_path = _write_metadata_file(
        output_plog_path=output_path,
        input_paths=input_paths,
        time_window=time_window,
        target_columns=target_columns,
        processed_files=processed_files,
        rows_written=rows_written,
    )
    LOG(f"{LOG_PREFIX_MSG_INFO} Metadata saved: {metadata_path}")


if __name__ == "__main__":
    main()
