#!/usr/local/bin/local_python

import argparse
from dataclasses import dataclass
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

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


@dataclass(frozen=True)
class InsStatusData:
    timestamp: datetime
    status: int


@dataclass(frozen=True)
class InsStatusSpan:
    start_time: datetime
    end_time: datetime
    message_count: int
    start_offset: int
    status: int

    @property
    def duration_secs(self) -> float:
        return (self.end_time - self.start_time).total_seconds()


@dataclass(frozen=True)
class InsMessageTimeDiffStats:
    min_secs: float
    max_secs: float
    avg_secs: float
    median_secs: float
    count: int


def parse_ins_status_data_from_line(line: str) -> Optional[InsStatusData]:
    m = INS1MSG_PATTERN.search(line)
    if not m:
        return None
    return InsStatusData(timestamp=datetime.strptime(m.group("timestamp"), TS_FMT), status=int(m.group("status"), 0))


def read_lines(source: str | Path | None) -> List[str]:
    if source is None:
        return [line.rstrip("\n") for line in sys.stdin.readlines()]
    return Path(source).read_text().splitlines()


def group_consecutive_status_spans(status_entries: Sequence[InsStatusData]) -> List[InsStatusSpan]:
    spans: List[InsStatusSpan] = []
    n = len(status_entries)
    if n == 0: return spans
    i = 0
    while i < n:
        start_entry = status_entries[i]
        j = i + 1
        while j < n and status_entries[j].status == start_entry.status:
            j += 1
        end_entry = status_entries[j - 1]
        spans.append(InsStatusSpan(start_time=start_entry.timestamp, end_time=end_entry.timestamp, message_count=j - i, start_offset=i, status=start_entry.status))
        i = j
    return spans


def compute_ins_message_time_diff_stats(status_entries: Sequence[InsStatusData]) -> Optional[InsMessageTimeDiffStats]:
    diffs: List[float] = []
    for i in range(1, len(status_entries)):
        diffs.append((status_entries[i].timestamp - status_entries[i - 1].timestamp).total_seconds())
    if not diffs:
        return None
    diffs.sort()
    return InsMessageTimeDiffStats(min_secs=diffs[0], max_secs=diffs[-1], avg_secs=sum(diffs) / len(diffs), median_secs=diffs[len(diffs) // 2], count=len(diffs))


def print_status_span_report(status_spans: Sequence[InsStatusSpan]) -> None:
    unique_statuses = {span.status for span in status_spans}
    LOG(f"Total spans: {len(status_spans)}")
    LOG(f"Unique insStatus values: {len(unique_statuses)}")
    for idx, span in enumerate(status_spans, 1):
        decoded = decode_ins_status(span.status)
        print()
        LOG(f"=== Span [{idx}] ===")
        LOG(f"    start={span.start_time} end={span.end_time} duration={span.duration_secs:.3f}s msgs={span.message_count} offset={span.start_offset}")
        print_decoded_status(decoded, is_compact=True)
        print()


def print_ins_messages_time_diff_stats(stats: Optional[InsMessageTimeDiffStats]) -> None:
    if stats is None:
        LOG("No time differences to compute (only one message or none).")
        return
    LOG("=== Time Diff Between Consecutive Messages ===")
    LOG(f"    Count : {stats.count}")
    LOG(f"    Min   : {stats.min_secs:.6f}s")
    LOG(f"    Avg   : {stats.avg_secs:.6f}s")
    LOG(f"    Median: {stats.median_secs:.6f}s")
    LOG(f"    Max   : {stats.max_secs:.6f}s")
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
    status_entries = [entry for line in lines if (entry := parse_ins_status_data_from_line(line)) is not None]

    if not status_entries:
        LOG("No INS1Msg lines found in input.")
        return

    LOG(f"Parsed {len(status_entries)} INS1Msg lines from {len(lines)} input lines.")
    print()

    time_diff_stats = compute_ins_message_time_diff_stats(status_entries)
    print_ins_messages_time_diff_stats(time_diff_stats)

    status_spans = group_consecutive_status_spans(status_entries)
    LOG("=== Status Changes Summary ===")
    print_status_span_report(status_spans)

    LOG("Analysis complete.")


if __name__ == "__main__":
    main()
