#!/usr/local/bin/local_python

import argparse
from dataclasses import dataclass
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from dev.dev_common.custom_structures import EToolPriority, ToolData
from dev.dev_common.core_independent_utils import LOG, LOG_EMPTY_LINE, LOG_LINE_SEPARATOR
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from available_tools.inertial_sense_tools.decode_ins_status_utils import (
    INS_FAULT_BOOL_CATEGORY_SPECS,
    INS_PROGRESSION_CATEGORY_SPECS,
    InsStatusCategory,
    InsStatusCategorySpec,
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
DEFAULT_MAX_SPAN_OF = 3
MAX_SUPPORTED_SPAN_OF = 3


@dataclass(frozen=True)
class InsStatusData:
    timestamp: datetime
    status: int
    line_no: int
    raw_line: str


@dataclass(frozen=True)
class InsStatusSpan:
    start_time: datetime
    end_time: datetime
    message_count: int
    start_offset: int
    span_of: int
    loop_count: int
    pattern_statuses: tuple[int, ...]

    @property
    def status(self) -> int:
        return self.pattern_statuses[0]

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
    category_key: InsStatusCategory
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
    from_line_text: Optional[str] = None
    to_line_text: Optional[str] = None
    from_rank: Optional[int] = None
    to_rank: Optional[int] = None
    is_regression: bool = False


@dataclass(frozen=True)
class InsFaultEvent:
    category_key: InsStatusCategory
    category_label: str
    old_value: bool
    new_value: bool
    timestamp: datetime
    elapsed_secs: float
    line_no: int
    offset: int
    from_line_no: Optional[int] = None
    from_offset: Optional[int] = None
    from_timestamp: Optional[datetime] = None
    old_line_text: Optional[str] = None
    new_line_text: Optional[str] = None


@dataclass(frozen=True)
class InsMilestone:
    category_key: InsStatusCategory
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
    raw_line: str
    decoded: object
    snapshot: object


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
    return InsStatusData(timestamp=datetime.strptime(m.group("timestamp"), TS_FMT), status=int(m.group("status"), 0), line_no=line_no, raw_line=line)


def read_lines(source: str | Path | None) -> List[str]:
    if source is None:
        return [line.rstrip("\n") for line in sys.stdin.readlines()]
    return Path(source).read_text().splitlines()


def _count_pattern_loops(status_entries: Sequence[InsStatusData], start_idx: int, pattern: Sequence[int]) -> int:
    # Count how many contiguous repeats of `pattern` exist starting at `start_idx`.
    k = len(pattern)
    n = len(status_entries)
    loops = 0
    while start_idx + (loops + 1) * k <= n:
        seg_start = start_idx + loops * k
        seg_end = seg_start + k
        if [entry.status for entry in status_entries[seg_start:seg_end]] != list(pattern):
            break
        loops += 1
    return loops


def group_consecutive_status_spans(status_entries: Sequence[InsStatusData], max_span_of: int = DEFAULT_MAX_SPAN_OF) -> List[InsStatusSpan]:
    spans: List[InsStatusSpan] = []
    n = len(status_entries)
    if n == 0: return spans
    max_span_of = max(1, min(MAX_SUPPORTED_SPAN_OF, max_span_of))
    i = 0
    while i < n:
        # Prefer wider (not more repeat) repeating cycles first (e.g. SPAN-OF-3 over SPAN-OF-2 over SPAN-OF-1).
        # so periodic sequences collapse into one span with `loop_count`.
        selected_span_width, selected_repeat_count = 1, 1
        # Try candidate cycle widths from large to small:
        # - upper bound: `min(max_span_of, n - i)` so we don't read past remaining entries
        # - lower bound: 1 to allow SPAN-OF-1 fallback
        # - descending (-1): first valid match keeps the widest cycle
        for k in range(min(max_span_of, n - i), 0, -1):
            pattern = [entry.status for entry in status_entries[i:i + k]]
            total_pattern_loops = _count_pattern_loops(status_entries, i, pattern)
            # For SPAN-OF-N (N >= 1), require at least 2 repeats to collapse into a looped span.
            if total_pattern_loops < 2:
                continue
            if k == 1:
                # SPAN-OF-1 fallback when no valid repeating multi-status cycle is found. (If found already break as below)
                selected_span_width, selected_repeat_count = 1, total_pattern_loops
                continue
            if len(set(pattern)) < 2:
                # Pure same-status repetitions are represented as SPAN-OF-1.
                continue
            selected_span_width, selected_repeat_count = k, total_pattern_loops
            break

        total_entry_consumed = selected_span_width * selected_repeat_count
        start_entry = status_entries[i]
        end_entry = status_entries[i + total_entry_consumed - 1]
        pattern_statuses = tuple(entry.status for entry in status_entries[i:i + selected_span_width])
        spans.append(
            InsStatusSpan(
                start_time=start_entry.timestamp,
                end_time=end_entry.timestamp,
                message_count=total_entry_consumed,
                start_offset=i,
                span_of=selected_span_width,
                loop_count=selected_repeat_count,
                pattern_statuses=pattern_statuses,
            )
        )
        i += total_entry_consumed
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
    LOG("=== Status Changes Summary ===", highlight=True)
    unique_statuses = {status for span in status_spans for status in span.pattern_statuses}
    LOG(f"Total spans: {len(status_spans)}")
    LOG(f"Unique insStatus values: {len(unique_statuses)}")
    for idx, span in enumerate(status_spans, 1):
        LOG_LINE_SEPARATOR()
        LOG(f"=== SPAN-OF-{span.span_of} [{idx}] ===")
        LOG(f"    start={span.start_time} end={span.end_time} duration={span.duration_secs:.3f}s msgs={span.message_count} offset={span.start_offset} loop={span.loop_count}")
        if span.span_of == 1:
            print_decoded_status(decode_ins_status(span.status), is_compact=True)
        else:
            for pattern_idx, status in enumerate(span.pattern_statuses, 1):
                LOG(f"    pattern[{pattern_idx}] status=0x{status:08X} ({status})")
                print_decoded_status(decode_ins_status(status), is_compact=True)
        LOG_LINE_SEPARATOR()


def print_ins_messages_time_diff_stats(stats: Optional[InsMessageTimeDiffStats]) -> None:
    LOG("=== Time Diff Stats ===", highlight=True)
    if stats is None:
        LOG("No time differences to compute (only one message or none).")
        return
    LOG(f"    Count : {stats.count}")
    LOG(f"    Min   : {stats.min_secs:.6f}s")
    LOG(f"    Avg   : {stats.avg_secs:.6f}s")
    LOG(f"    Median: {stats.median_secs:.6f}s")
    LOG(f"    Max   : {stats.max_secs:.6f}s")
    LOG_LINE_SEPARATOR()


def _extract_bool_from_snapshot(snapshot: object, category_spec: InsStatusCategorySpec) -> bool:
    return bool(get_category_value_from_snapshot(snapshot, category_spec))


def _build_decoded_entries(status_entries: Sequence[InsStatusData]) -> List[DecodedInsStatusEntry]:
    decoded_entries: List[DecodedInsStatusEntry] = []
    for offset, entry in enumerate(status_entries):
        decoded = decode_ins_status(entry.status)
        snapshot = build_ins_status_progress_snapshot(decoded)
        decoded_entries.append(
            DecodedInsStatusEntry(offset=offset, line_no=entry.line_no, timestamp=entry.timestamp, status=entry.status, raw_line=entry.raw_line, decoded=decoded, snapshot=snapshot)
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
    for category_spec in INS_PROGRESSION_CATEGORY_SPECS:
        category_key, category_label = category_spec.category, category_spec.label
        seen_ranks: set[int] = set()
        prev_value: Optional[object] = None
        prev_label: Optional[str] = None
        prev_rank: Optional[int] = None
        prev_line_no: Optional[int] = None
        prev_offset: Optional[int] = None
        prev_timestamp: Optional[datetime] = None
        for entry in decoded_entries:
            value = get_category_value_from_snapshot(entry.snapshot, category_spec)
            label = get_category_label_from_snapshot(entry.snapshot, category_spec)
            rank = get_category_rank_from_snapshot(entry.snapshot, category_spec)
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
                    from_line_text=decoded_entries[prev_offset].raw_line if prev_offset is not None else None,
                    to_line_text=entry.raw_line,
                    is_regression=is_regression
                )
                transitions.append(event)
                if is_regression:
                    regressions.append(event)
            prev_value, prev_label, prev_rank = value, label, rank
            prev_line_no, prev_offset, prev_timestamp = entry.line_no, entry.offset, entry.timestamp

    for category_spec in INS_FAULT_BOOL_CATEGORY_SPECS:
        key, label = category_spec.category, category_spec.label
        prev: Optional[bool] = None
        prev_line_no: Optional[int] = None
        prev_offset: Optional[int] = None
        prev_timestamp: Optional[datetime] = None
        prev_line_text: Optional[str] = None
        for entry in decoded_entries:
            value = _extract_bool_from_snapshot(entry.snapshot, category_spec)
            if prev is None:
                prev = value
                prev_line_no, prev_offset, prev_timestamp, prev_line_text = entry.line_no, entry.offset, entry.timestamp, entry.raw_line
                continue
            if value != prev:
                fault_events.append(
                    InsFaultEvent(
                        category_key=key, category_label=label, old_value=prev, new_value=value,
                        timestamp=entry.timestamp, elapsed_secs=(entry.timestamp - t0).total_seconds(), line_no=entry.line_no, offset=entry.offset,
                        from_line_no=prev_line_no, from_offset=prev_offset, from_timestamp=prev_timestamp,
                        old_line_text=prev_line_text, new_line_text=entry.raw_line
                    )
                )
            prev = value
            prev_line_no, prev_offset, prev_timestamp, prev_line_text = entry.line_no, entry.offset, entry.timestamp, entry.raw_line

    return milestones, transitions, regressions, fault_events


def print_progression_summary(decoded_entries: Sequence[DecodedInsStatusEntry]) -> None:
    LOG("=== Status Progression Summary ===", highlight=True)
    if not decoded_entries:
        return
    milestones, transitions, regressions, fault_events = _analyze_progress(decoded_entries)
    t0 = decoded_entries[0].timestamp
    LOG(f"Start timestamp: {t0}")
    LOG_LINE_SEPARATOR()
    LOG("=== Transition Summary (Streamlined) ===")
    covered_transition_ids: set[int] = set()
    for category_spec in INS_PROGRESSION_CATEGORY_SPECS:
        category_key, category_label = category_spec.category, category_spec.label
        start_label = get_category_label_from_snapshot(decoded_entries[0].snapshot, category_spec)
        end_label = get_category_label_from_snapshot(decoded_entries[-1].snapshot, category_spec)
        end_entry = next((entry for entry in decoded_entries if get_category_label_from_snapshot(entry.snapshot, category_spec) == end_label), decoded_entries[-1])
        category_transitions = [event for event in transitions if event.category_key == category_key]
        covered_transition_ids.update(id(event) for event in category_transitions)
        if not category_transitions:
            LOG(f"{category_label}: {start_label} -> {end_label} in {(end_entry.timestamp - t0).total_seconds():.3f}s (no transition)")
            LOG_EMPTY_LINE()
            continue
        first, last = category_transitions[0], category_transitions[-1]
        regress_count = sum(1 for event in category_transitions if event.is_regression)
        LOG(
            f"{category_label}: {start_label} -> {end_label} in {(end_entry.timestamp - t0).total_seconds():.3f}s "
            f"({len(category_transitions)} transition(s), regressions={regress_count}, "
            f"first +{first.elapsed_secs:.3f}s line {first.line_no}/offset {first.offset}, "
            f"last +{last.elapsed_secs:.3f}s line {last.line_no}/offset {last.offset})"
        )
        for event in category_transitions:
            LOG(
                f"- {category_label}: {event.from_label} -> {event.to_label} at +{event.elapsed_secs:.3f}s "
                f"(from line {event.from_line_no}, offset {event.from_offset} -> line {event.line_no}, offset {event.offset})"
            )
        LOG_EMPTY_LINE()

    uncovered_transitions = [event for event in transitions if id(event) not in covered_transition_ids]
    if uncovered_transitions:
        LOG("Unmapped transitions (not covered by configured progression categories):", highlight=True)
        for event in uncovered_transitions:
            LOG(
                f"- {event.category_label} [{event.category_key}]: {event.from_label} -> {event.to_label} at +{event.elapsed_secs:.3f}s "
                f"(line {event.line_no}, offset {event.offset})"
            )
        LOG_EMPTY_LINE()

    LOG_LINE_SEPARATOR()
    LOG("=== Milestones ===")
    for category_spec in INS_PROGRESSION_CATEGORY_SPECS:
        category_key, category_label = category_spec.category, category_spec.label
        category_milestones = [mile_stone for mile_stone in milestones if mile_stone.category_key == category_key]
        if not category_milestones:
            LOG(f"{category_label}: no milestones")
            continue
        reached = ", ".join([f"{m.value_label} @ +{m.elapsed_secs:.3f}s (line {m.line_no}, offset {m.offset})" for m in category_milestones])
        LOG(f"{category_label}: {reached}")
    LOG_LINE_SEPARATOR()
    LOG("=== Fault/Warning State Changes ===")
    if not fault_events:
        LOG("No fault/mag boolean transitions detected.")
    else:
        for event in fault_events:
            LOG(f"{event.category_label}: {event.old_value} -> {event.new_value} at +{event.elapsed_secs:.3f}s (line {event.line_no}, offset {event.offset}, ts={event.timestamp})", highlight=True)
            LOG(f"  - {event.category_label} {event.old_value} Line From = {event.old_line_text}")
            LOG(f"  - {event.category_label} {event.new_value} Line To = {event.new_line_text}")
    LOG_LINE_SEPARATOR()
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
    LOG_LINE_SEPARATOR()

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
    parser.add_argument(
        "--max_span_of", type=int, default=DEFAULT_MAX_SPAN_OF,
        help=f"Maximum cycle width used for span grouping (1..{MAX_SUPPORTED_SPAN_OF}).",
    )
    args = parser.parse_args()

    lines = read_lines(args.file)
    status_entries = [entry for idx, line in enumerate(lines, 1) if (entry := parse_ins_status_data_from_line(line, idx)) is not None]

    if not status_entries:
        LOG("No INS1Msg lines found in input.")
        return

    LOG(f"Parsed {len(status_entries)} INS1Msg lines from {len(lines)} input lines.")
    LOG_LINE_SEPARATOR()

    status_spans = group_consecutive_status_spans(status_entries, max_span_of=args.max_span_of)
    print_status_span_report(status_spans)

    time_diff_stats = compute_ins_message_time_diff_stats(status_entries)
    print_ins_messages_time_diff_stats(time_diff_stats)

    decoded_entries = _build_decoded_entries(status_entries)
    print_progression_summary(decoded_entries)

    LOG("Analysis complete.", highlight=True)


if __name__ == "__main__":
    main()
