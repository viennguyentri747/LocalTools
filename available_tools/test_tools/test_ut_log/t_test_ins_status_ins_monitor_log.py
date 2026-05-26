#!/usr/local/bin/local_python

import argparse
from dataclasses import dataclass
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from dev.dev_common.custom_structures import EToolPriority, ToolData
from dev.dev_common.core_independent_utils import LOG
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from available_tools.inertial_sense_tools.decode_ins_status_utils import (
    build_ins_status_progress_snapshot,
    decode_ins_status,
    get_category_label_from_snapshot,
    get_category_rank_from_snapshot,
    get_category_value_from_snapshot,
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
    line_no: int


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


@dataclass(frozen=True)
class InsProgressEvent:
    category_key: str
    category_label: str
    from_label: str
    to_label: str
    timestamp: datetime
    elapsed_secs: float
    line_no: int
    offset: int
    from_line_no: Optional[int] = None
    from_offset: Optional[int] = None
    from_timestamp: Optional[datetime] = None
    from_rank: Optional[int] = None
    to_rank: Optional[int] = None
    is_regression: bool = False


@dataclass(frozen=True)
class InsFaultEvent:
    category_key: str
    category_label: str
    old_value: bool
    new_value: bool
    timestamp: datetime
    elapsed_secs: float
    line_no: int
    offset: int


@dataclass(frozen=True)
class InsMilestone:
    category_key: str
    category_label: str
    value_label: str
    rank: int
    timestamp: datetime
    elapsed_secs: float
    line_no: int
    offset: int


@dataclass(frozen=True)
class DecodedInsStatusEntry:
    offset: int
    line_no: int
    timestamp: datetime
    status: int
    decoded: object
    snapshot: object


PROGRESSION_CATEGORIES = [
    ("solution", "Solution"),
    ("gps_fix", "GPS Fix"),
    ("rtk_compassing", "RTK Compassing"),
    ("fine_alignment", "Fine Alignment"),
]
FAULT_BOOL_CATEGORIES = [
    ("general_fault", "General Fault"),
    ("rtos_overrun", "RTOS Task Period Overrun"),
    ("mag_bad_cal", "Magnetometer Bad Cal"),
]


def getToolData() -> ToolData:
    tool_templates = [
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
    return ToolData(tool_templates=tool_templates, tool_priority=EToolPriority.Level10_Last, hidden=False)

def parse_ins_status_data_from_line(line: str, line_no: int) -> Optional[InsStatusData]:
    m = INS1MSG_PATTERN.search(line)
    if not m:
        return None
    return InsStatusData(timestamp=datetime.strptime(m.group("timestamp"), TS_FMT), status=int(m.group("status"), 0), line_no=line_no)


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


def _extract_bool_from_snapshot(snapshot: object, key: str) -> bool:
    return bool(getattr(snapshot, key))


def _build_decoded_entries(status_entries: Sequence[InsStatusData]) -> List[DecodedInsStatusEntry]:
    decoded_entries: List[DecodedInsStatusEntry] = []
    for offset, entry in enumerate(status_entries):
        decoded = decode_ins_status(entry.status)
        snapshot = build_ins_status_progress_snapshot(decoded)
        decoded_entries.append(
            DecodedInsStatusEntry(offset=offset, line_no=entry.line_no, timestamp=entry.timestamp, status=entry.status, decoded=decoded, snapshot=snapshot)
        )
    return decoded_entries


def build_decoded_entries(status_entries: Sequence[InsStatusData]) -> List[DecodedInsStatusEntry]:
    """Public wrapper for callers that need decoded entries for progression summaries."""
    return _build_decoded_entries(status_entries)


def _analyze_progress(decoded_entries: Sequence[DecodedInsStatusEntry]) -> tuple[List[InsMilestone], List[InsProgressEvent], List[InsProgressEvent], List[InsFaultEvent]]:
    milestones: List[InsMilestone] = []
    transitions: List[InsProgressEvent] = []
    regressions: List[InsProgressEvent] = []
    fault_events: List[InsFaultEvent] = []
    if not decoded_entries:
        return milestones, transitions, regressions, fault_events

    t0 = decoded_entries[0].timestamp
    for category_key, category_label in PROGRESSION_CATEGORIES:
        seen_ranks: set[int] = set()
        prev_value: Optional[object] = None
        prev_label: Optional[str] = None
        prev_rank: Optional[int] = None
        prev_line_no: Optional[int] = None
        prev_offset: Optional[int] = None
        prev_timestamp: Optional[datetime] = None
        for entry in decoded_entries:
            value = get_category_value_from_snapshot(entry.snapshot, category_key)
            label = get_category_label_from_snapshot(entry.snapshot, category_key)
            rank = get_category_rank_from_snapshot(entry.snapshot, category_key)
            if value is None or label is None:
                continue
            elapsed = (entry.timestamp - t0).total_seconds()
            if rank is not None and rank not in seen_ranks:
                milestones.append(InsMilestone(category_key=category_key, category_label=category_label, value_label=label, rank=rank, timestamp=entry.timestamp, elapsed_secs=elapsed, line_no=entry.line_no, offset=entry.offset))
                seen_ranks.add(rank)
            if prev_value is None:
                prev_value, prev_label, prev_rank = value, label, rank
                prev_line_no, prev_offset, prev_timestamp = entry.line_no, entry.offset, entry.timestamp
                continue
            if value != prev_value:
                is_regression = rank is not None and prev_rank is not None and rank < prev_rank
                event = InsProgressEvent(
                    category_key=category_key, category_label=category_label, from_label=prev_label, to_label=label, from_rank=prev_rank, to_rank=rank,
                    timestamp=entry.timestamp, elapsed_secs=elapsed, line_no=entry.line_no, offset=entry.offset,
                    from_line_no=prev_line_no, from_offset=prev_offset, from_timestamp=prev_timestamp,
                    is_regression=is_regression
                )
                transitions.append(event)
                if is_regression:
                    regressions.append(event)
            prev_value, prev_label, prev_rank = value, label, rank
            prev_line_no, prev_offset, prev_timestamp = entry.line_no, entry.offset, entry.timestamp

    for key, label in FAULT_BOOL_CATEGORIES:
        prev: Optional[bool] = None
        for entry in decoded_entries:
            value = _extract_bool_from_snapshot(entry.snapshot, key)
            if prev is None:
                prev = value
                continue
            if value != prev:
                fault_events.append(
                    InsFaultEvent(
                        category_key=key, category_label=label, old_value=prev, new_value=value,
                        timestamp=entry.timestamp, elapsed_secs=(entry.timestamp - t0).total_seconds(), line_no=entry.line_no, offset=entry.offset
                    )
                )
            prev = value

    return milestones, transitions, regressions, fault_events


def print_progression_summary(decoded_entries: Sequence[DecodedInsStatusEntry]) -> None:
    if not decoded_entries:
        return
    milestones, transitions, regressions, fault_events = _analyze_progress(decoded_entries)
    LOG("=== Status Progression Summary ===")
    LOG(f"Start timestamp: {decoded_entries[0].timestamp}")
    for category_key, category_label in PROGRESSION_CATEGORIES:
        category_milestones = [m for m in milestones if m.category_key == category_key]
        if not category_milestones:
            LOG(f"{category_label}: no milestones")
            continue
        reached = ", ".join([f"{m.value_label} @ +{m.elapsed_secs:.3f}s (line {m.line_no}, offset {m.offset})" for m in category_milestones])
        LOG(f"{category_label}: {reached}")
    print()

    LOG("=== Fault/Warning State Changes ===")
    if not fault_events:
        LOG("No fault/mag boolean transitions detected.")
    else:
        for event in fault_events:
            LOG(f"{event.category_label}: {event.old_value} -> {event.new_value} at +{event.elapsed_secs:.3f}s (line {event.line_no}, offset {event.offset}, ts={event.timestamp})")
    print()

    LOG("=== Regression Check (Monotonic Categories) ===")
    if not regressions:
        LOG("No backward transitions detected for ranked categories.")
    else:
        LOG(f"Detected {len(regressions)} backward transition(s):")
        for event in regressions:
            LOG(
                f"{event.category_label}: {event.from_label} (rank={event.from_rank}) -> {event.to_label} (rank={event.to_rank}) "
                f"at +{event.elapsed_secs:.3f}s "
                f"(from line {event.from_line_no}, offset {event.from_offset}, ts={event.from_timestamp} -> "
                f"line {event.line_no}, offset {event.offset}, ts={event.timestamp})"
            )
    print()

    LOG("=== Key Transitions ===")
    if not transitions:
        LOG("No category transitions detected.")
    else:
        for event in transitions:
            LOG(f"{event.category_label}: {event.from_label} -> {event.to_label} at +{event.elapsed_secs:.3f}s (line {event.line_no}, offset {event.offset})")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze INS1Msg lines grouped by insStatus changes.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))
    parser.add_argument(
        "-f", "--file", type=str, default=None,
        help="Log file to parse (reads from stdin if omitted).",
    )
    args = parser.parse_args()

    lines = read_lines(args.file)
    status_entries = [entry for idx, line in enumerate(lines, 1) if (entry := parse_ins_status_data_from_line(line, idx)) is not None]

    if not status_entries:
        LOG("No INS1Msg lines found in input.")
        return

    LOG(f"Parsed {len(status_entries)} INS1Msg lines from {len(lines)} input lines.")
    print()

    time_diff_stats = compute_ins_message_time_diff_stats(status_entries)
    print_ins_messages_time_diff_stats(time_diff_stats)

    decoded_entries = _build_decoded_entries(status_entries)
    print_progression_summary(decoded_entries)

    status_spans = group_consecutive_status_spans(status_entries)
    LOG("=== Status Changes Summary ===")
    print_status_span_report(status_spans)

    LOG("Analysis complete.")


if __name__ == "__main__":
    main()
