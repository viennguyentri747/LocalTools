#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Parse "Intellian Periodic Log" (tab-delimited) and print:
  1) All available column names
  2) Validation of user-specified target columns
  3) A pretty table of those target columns within a time window (hours)
  4) Interactive graphs for numeric columns

Improvements:
- Uses tabulate library for better table formatting
- Encapsulates parsed data in PLogData class
- Separated parsing logic into dedicated function
- Added matplotlib graph generation with scrollable/zoomable interface

Usage:
  python parse_periodic_log.py --log /path/to/log.txt --hours 1.0 --columns Time LAST_AVG_SINR LAST_VELOCITY
  python parse_periodic_log.py --log /path/to/log.txt --hours 1.0 --columns Time LAST_AVG_SINR LAST_VELOCITY --graph LAST_AVG_SINR LAST_VELOCITY
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import re
from typing import List, Tuple, Optional, Dict, Any
from tabulate import tabulate
from dev_common import *

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure

from unit_tests.acu_log_tests.periodic_log_constants import *

class PLogData:
    """
    Encapsulates parsed periodic log data.

    Attributes:
        header: List of all column names from the log
        filtered_rows: Rows within the time window
        target_columns: Valid target columns to display
        base_time: First timestamp used as reference
        timestamps: List of datetime objects for each row
    """

    def __init__(self, header: List[str], rows: List[List[str]], target_columns: List[str], 
                 base_time: Optional[dt.datetime] = None, timestamps: Optional[List[dt.datetime]] = None):
        self.header = header
        self.raw_rows = rows
        self.target_columns = target_columns
        self.base_time = base_time
        self.timestamps = timestamps or []

    def to_table_string(self, tablefmt: str = "grid") -> str:
        """
        Generate formatted table string using tabulate.
        Args:
            tablefmt: Format style for tabulate (grid, simple, fancy_grid, etc.)
        Returns:
            Formatted table string
        """
        if not self.raw_rows:
            return f"{LOG_PREFIX_MSG_INFO} No rows within the specified window."

        table_data = self._get_filtered_rows()
        return tabulate(table_data, headers=self.target_columns, tablefmt=tablefmt)

    def _get_filtered_rows(self) -> List[List[str]]:
        """
        Extract data for target columns from filtered rows.
        Returns list of rows, each row is a list of values.
        """
        if not self.target_columns or not self.raw_rows:
            return []

        name_to_idx: Dict[str, int] = {name: i for i, name in enumerate(self.header)}
        indices = [name_to_idx[name] for name in self.target_columns]

        filtered_rows: List[List[str]] = []
        for row in self.raw_rows:
            row_data: List[str] = [row[idx] if idx < len(row) else "" for idx in indices]
            filtered_rows.append(row_data)

        return filtered_rows

    def get_numeric_columns(self, column_names: List[str]) -> Dict[str, Tuple[List[dt.datetime], List[float]]]:
        """
        Extract numeric data for specified columns.
        
        Args:
            column_names: List of column names to extract
            
        Returns:
            Dictionary mapping column names to (timestamps, values) tuples
        """
        if not self.raw_rows or not self.timestamps:
            return {}

        name_to_idx: Dict[str, int] = {name: i for i, name in enumerate(self.header)}
        result: Dict[str, Tuple[List[dt.datetime], List[float]]] = {}

        for col_name in column_names:
            if col_name not in name_to_idx:
                continue
            
            col_idx = name_to_idx[col_name]
            times: List[dt.datetime] = []
            values: List[float] = []
            
            for row, timestamp in zip(self.raw_rows, self.timestamps):
                if col_idx >= len(row):
                    continue
                    
                try:
                    value = float(row[col_idx])
                    times.append(timestamp)
                    values.append(value)
                except (ValueError, TypeError):
                    # Skip non-numeric values
                    continue
            
            if times and values:
                result[col_name] = (times, values)
        
        return result

    def plot_columns(self, column_names: List[str], output_path: Optional[str] = None, 
                     show_interactive: bool = True, figsize: Tuple[int, int] = (12, 6)) -> Optional[Figure]:
        """
        Create interactive plots for specified numeric columns.
        
        Args:
            column_names: List of column names to plot
            output_path: Optional path to save the figure
            show: Whether to display the plot interactively
            figsize: Figure size as (width, height)
            
        Returns:
            The matplotlib Figure object, or None if plotting failed
        """
        numeric_data = self.get_numeric_columns(column_names)
        
        if not numeric_data:
            print(f"[WARNING] No numeric data found for columns: {column_names}", file=sys.stderr)
            return None
        
        # Create subplots - one for each column
        n_plots = len(numeric_data)
        fig, axes = plt.subplots(n_plots, 1, figsize=figsize, squeeze=False)
        axes = axes.flatten()
        
        for idx, (col_name, (times, values)) in enumerate(numeric_data.items()):
            ax = axes[idx]
            ax.plot(times, values, marker='o', markersize=3, linewidth=1.5, label=col_name)
            ax.set_xlabel('Time')
            ax.set_ylabel(col_name)
            ax.set_title(f'{col_name} over Time')
            ax.grid(True, alpha=0.3)
            ax.legend()
            
            # Format x-axis to show time nicely
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            fig.autofmt_xdate()
        
        plt.tight_layout()
        
        # Save if output path provided
        if output_path:
            try:
                fig.savefig(output_path, dpi=150, bbox_inches='tight')
                print(f"{LOG_PREFIX_MSG_INFO} Graph saved to: {output_path}")
            except Exception as e:
                print(f"[ERROR] Failed to save graph: {e}", file=sys.stderr)
        
        # Show interactive plot
        if show_interactive:
            plt.show()
        
        return fig

    def print_summary(self):
        """Print summary information about the parsed data."""
        print("# Available columns:")
        print(self.header)
        print()

        if self.base_time:
            print(f"# Base time = {self.base_time}")
        print()


def find_header_and_rows(text: str) -> Tuple[Optional[List[str]], List[List[str]]]:
    """
    Finds the tab-delimited header line starting with 'Time' and returns:
      (header_columns, rows_as_list_of_lists)
    """
    header: Optional[List[str]] = None
    rows: List[List[str]] = []

    lines = text.splitlines()
    for i, raw in enumerate(lines):
        line = raw.strip('\n')
        if line.startswith("Time\t"):
            header = line.split('\t')
            # The remaining lines until EOF that have tab separators are rows
            for data_line in lines[i+1:]:
                if '\t' in data_line:
                    rows.append(data_line.rstrip('\n').split('\t'))
            break
    return header, rows


def parse_time_components(row_time_str: str) -> Optional[Tuple[int, int, int, int]]:
    """
    Breaks a 'HH:MM:SS(.ffffff)' string into integer components.
    """
    match = re.match(r'^(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?$', row_time_str.strip())
    if not match:
        return None
    hh, mm, ss, fraction = match.groups()
    micro = int(fraction.ljust(6, '0')) if fraction else 0
    try:
        return int(hh), int(mm), int(ss), micro
    except ValueError:
        return None


def components_to_microseconds(parts: Tuple[int, int, int, int]) -> int:
    hh, mm, ss, micro = parts
    return ((hh * 3600 + mm * 60 + ss) * 1_000_000) + micro


def build_time_series(rows: List[List[str]], time_idx: int) -> Tuple[Optional[dt.datetime], List[Optional[dt.datetime]]]:
    """
    Uses the first data row to establish a base timestamp and returns parsed datetimes per row.
    The resulting datetimes are monotonic; day rollovers increment by 24 hours.
    """
    if not rows:
        return None, []

    first_row = rows[0]
    if time_idx >= len(first_row):
        return None, []

    base_parts = parse_time_components(first_row[time_idx])
    if not base_parts:
        return None, []

    base_micro = components_to_microseconds(base_parts)
    base_time = dt.datetime(1970, 1, 1, base_parts[0], base_parts[1], base_parts[2], base_parts[3])

    parsed: List[Optional[dt.datetime]] = []
    day_offset = 0
    prev_micro = base_micro

    for row in rows:
        if time_idx >= len(row):
            parsed.append(None)
            continue

        parts = parse_time_components(row[time_idx])
        if not parts:
            parsed.append(None)
            continue

        current_micro = components_to_microseconds(parts)
        if current_micro < prev_micro:
            day_offset += 1

        delta_micro = (current_micro - base_micro) + (day_offset * 86_400_000_000)
        parsed_dt = base_time + dt.timedelta(microseconds=delta_micro)
        parsed.append(parsed_dt)
        prev_micro = current_micro

    return base_time, parsed


def compute_time_bounds(all_times: List[dt.datetime], window_hours: float) -> Tuple[Optional[dt.datetime], Optional[dt.datetime]]:
    """
    Compute [start, end] bounds using the latest timestamp as 'end'.
    """
    if not all_times:
        return None, None
    end = max(all_times)
    window_seconds = float(window_hours) * 3600.0
    start = end - dt.timedelta(seconds=window_seconds)
    return start, end


def select_columns(header: List[str], targets: List[str]) -> Tuple[List[str], List[str]]:
    """
    Returns (valid_targets_in_order, missing_targets).
    Order is preserved from 'targets' input.
    """
    header_set = set(header)
    valid = [c for c in targets if c in header_set]
    missing = [c for c in targets if c not in header_set]
    return valid, missing


def parse_periodic_log(log_path: str, target_columns: List[str], max_time_capture: float) -> PLogData:
    # Read and parse file
    text = read_file_content(log_path, encoding="utf-8", errors="replace")
    header, all_rows = find_header_and_rows(text)

    if not header or TIME_COLUMN not in header:
        raise ValueError("Log file does not contain a valid header with 'Time' column")

    # Parse time series
    time_idx = header.index(TIME_COLUMN)
    base_time, parsed_times = build_time_series(all_rows, time_idx)

    if base_time is None:
        raise ValueError("The first data row does not provide a valid base time")

    # Validate target columns
    found_target_columns, missing = select_columns(header, target_columns)
    # Check for missing columns and raise error
    if missing:
        raise ValueError(f"Missing target columns: {missing}")

    # Gather rows with valid timestamps
    valid_rows: List[List[str]] = []
    valid_times: List[dt.datetime] = []
    for r, t in zip(all_rows, parsed_times):
        if t is not None:
            valid_rows.append(r)
            valid_times.append(t)

    # Compute time window bounds
    start, end = compute_time_bounds(valid_times, max_time_capture)

    # Filter rows within time window
    filtered_rows = []
    filtered_times = []
    if start is not None and end is not None:
        for r, t in zip(valid_rows, valid_times):
            if start <= t <= end:
                filtered_rows.append(r)
                filtered_times.append(t)
    else:
        filtered_rows = valid_rows
        filtered_times = valid_times

    return PLogData(header=header, rows=filtered_rows, target_columns=found_target_columns, 
                    base_time=base_time, timestamps=filtered_times)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Parse Intellian Periodic Log and pretty-print selected columns.")
    p.add_argument("--log", required=True, help="Path to the periodic log file")
    p.add_argument("--hours", type=float, default=1.0, help="Time window in hours (float). Default: 1.0")
    p.add_argument("--columns", nargs="+", default=[TIME_COLUMN], help="Target column names to display (default: Time)")
    p.add_argument("--format", default="fancy_grid",
                   help="Table format (grid, simple, fancy_grid, pipe, etc.). Default: fancy_grid")
    p.add_argument("--graph", nargs="*", help="Column names to plot (space-separated). If not specified, no graphs are generated.")
    p.add_argument("--no-show", action="store_true", help="Don't display interactive plot window")
    p.add_argument("--graph-output", help="Path to save graph image (PNG format recommended)")
    args = p.parse_args(argv)

    # Expand and validate path
    exists, log_path = expand_and_check_path(args.log)
    if not exists:
        print(f"[ERROR] Log path does not exist: {log_path}", file=sys.stderr)
        return 2

    try:
        # Parse log file using the new function
        plog_data = parse_periodic_log(
            log_path=log_path,
            target_columns=args.columns,
            max_time_capture=args.hours
        )
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    # Print summary
    plog_data.print_summary()

    # Print time window info
    window_seconds = args.hours * 3600.0
    window_minutes = args.hours * 60.0
    print(f"# Time window: {args.hours} hour(s) ≈ {window_minutes:.2f} minute(s) ≈ {window_seconds:.0f} second(s)")
    print()

    # Generate and print table
    if not plog_data.raw_rows:
        print(f"{LOG_PREFIX_MSG_INFO} No rows within the specified window. Nothing to print.")
        return 0

    table_str = plog_data.to_table_string(tablefmt=args.format)
    print(table_str)

    # Save table to file
    output_path = f"{TEMP_FOLDER_PATH}/PlogTest_output.txt"
    print(f"{LOG_PREFIX_MSG_INFO} Table output saved to: {output_path}")
    write_to_file(f"{output_path}", table_str)

    # Generate graphs if requested
    if args.graph is not None:
        if not args.graph:
            # If --graph is specified without arguments, use all numeric columns except Time
            graph_columns = [col for col in args.columns if col != TIME_COLUMN]
        else:
            graph_columns = args.graph
        
        if graph_columns:
            print(f"\n{LOG_PREFIX_MSG_INFO} Generating graphs for: {graph_columns}")
            
            # Determine output path for graph
            graph_output = args.graph_output
            if not graph_output:
                graph_output = f"{TEMP_FOLDER_PATH}/PlogTest_graph.png"
            
            plog_data.plot_columns(
                column_names=graph_columns,
                output_path=graph_output,
                show_interactive=not args.no_show
            )
        else:
            print("[WARNING] No columns specified for graphing")

    return 0


if __name__ == "__main__":
    sys.exit(main())