#!/usr/local/bin/local_python

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dev.dev_common.custom_structures import ToolData
from dev.dev_common.core_independent_utils import LOG
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from available_tools.inertial_sense_tools.decode_ins_status_utils import (
    decode_ins_status,
    print_decoded_status,
)

INS1MSG_PATTERN = re.compile(
    r"\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\].*?"
    r"insStatus\[(?P<status>0x[0-9A-Fa-f]+)\]"
)
TS_FMT = "%Y-%m-%d %H:%M:%S.%f"


def parse_ins1msg_line(line: str) -> Optional[Tuple[datetime, int]]:
    m = INS1MSG_PATTERN.search(line)
    if not m:
        return None
    ts = datetime.strptime(m.group("timestamp"), TS_FMT)
    status = int(m.group("status"), 0)
    return ts, status


def read_lines(source) -> List[str]:
    if source is None:
        return [line.rstrip("\n") for line in sys.stdin.readlines()]
    return Path(source).read_text().splitlines()


GroupedEntry = Tuple[datetime, datetime, int, int, int]


def group_statuses(parsed: List[Tuple[datetime, int]]) -> List[GroupedEntry]:
    result: List[GroupedEntry] = []
    n = len(parsed)
    if n == 0: return result
    i = 0
    while i < n:
        ts_start, status = parsed[i]
        j = i + 1
        while j < n and parsed[j][1] == status:
            j += 1
        ts_end, _ = parsed[j - 1]
        result.append((ts_start, ts_end, j - i, i, status))
        i = j
    return result


def compute_time_diff_stats(parsed: List[Tuple[datetime, int]]) -> Optional[Dict[str, float]]:
    diffs = []
    for i in range(1, len(parsed)):
        delta = (parsed[i][0] - parsed[i - 1][0]).total_seconds()
        diffs.append(delta)
    if not diffs:
        return None
    diffs.sort()
    return {
        "min": diffs[0],
        "max": diffs[-1],
        "avg": sum(diffs) / len(diffs),
        "median": diffs[len(diffs) // 2],
        "count": len(diffs),
    }


def print_grouped_report(grouped: List[GroupedEntry], total_lines: int) -> None:
    unique_statuses = {entry[4] for entry in grouped}
    LOG(f"Total spans: {len(grouped)}")
    LOG(f"Unique insStatus values: {len(unique_statuses)}")
    for idx, (ts_start, ts_end, count, offset, status_val) in enumerate(grouped, 1):
        decoded = decode_ins_status(status_val)
        duration = (ts_end - ts_start).total_seconds()
        print()
        LOG(f"=== Span [{idx}] ===")
        LOG(f"    start={ts_start} end={ts_end} duration={duration:.3f}s msgs={count} offset={offset}")
        LOG(f"    insStatus: {decoded.overall_status_hex} ({status_val})")
        LOG(f"    Solution: {decoded.solution_status}")
        print_decoded_status(decoded)
        print()


def print_time_diff_stats(stats: Optional[Dict[str, float]]) -> None:
    if stats is None:
        LOG("No time differences to compute (only one message or none).")
        return
    LOG("=== Time Diff Between Consecutive Messages ===")
    LOG(f"    Count : {stats['count']}")
    LOG(f"    Min   : {stats['min']:.6f}s")
    LOG(f"    Avg   : {stats['avg']:.6f}s")
    LOG(f"    Median: {stats['median']:.6f}s")
    LOG(f"    Max   : {stats['max']:.6f}s")
    print()


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Analyze INS Status from log",
            extra_description=(
                "Parse INS1Msg lines from stdin and group by insStatus changes. "
                "Example: `grep INS1Msg /var/log/ins_monitor_log | t_is_analyze_ins_status`"
            ),
            args={},
        ),
        ToolTemplate(
            name="Analyze INS Status from file",
            extra_description="Parse INS1Msg lines from a log file.",
            args={"-f": "/path/to/ins_monitor_log"},
        ),
    ]


def getToolData():
    return ToolData(tool_template=get_tool_templates())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze INS1Msg lines grouped by insStatus changes.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(
        "-f", "--file", type=str, default=None,
        help="Log file to parse (reads from stdin if omitted).",
    )
    args = parser.parse_args()

    lines = read_lines(args.file)
    parsed = [entry for line in lines if (entry := parse_ins1msg_line(line)) is not None]

    if not parsed:
        LOG("No INS1Msg lines found in input.")
        return

    LOG(f"Parsed {len(parsed)} INS1Msg lines from {len(lines)} input lines.")
    print()

    time_diff_stats = compute_time_diff_stats(parsed)
    print_time_diff_stats(time_diff_stats)

    grouped = group_statuses(parsed)
    LOG("=== Status Changes Summary ===")
    print_grouped_report(grouped, len(parsed))

    LOG("Analysis complete.")


if __name__ == "__main__":
    main()
