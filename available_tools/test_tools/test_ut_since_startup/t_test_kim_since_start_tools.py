#!/usr/local/bin/local_python
import argparse
from datetime import datetime
from pathlib import Path
import threading
import time
from typing import List, Optional

from dev.dev_common import *
from dev.dev_common.custom_structures import EToolPriority, ToolData
from dev.dev_common.network_utils import ELineType
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from dev.dev_iesa.iesa_ut_install_utils import check_safe_reboot_ut
from available_tools.test_tools.test_ut_log.t_get_ut_live_log import ELogStreamMode, build_live_log_handlers, close_live_log_handlers, start_stop_timer, stream_live_remote_log_to_file
from available_tools.test_tools.test_ut_log.t_get_acu_logs import DEFAULT_LOG_OUTPUT_PATH
from available_tools.test_tools.test_ut_log.t_test_ins_status_ins_monitor_log import (
    DEFAULT_MAX_SPAN_OF,
    InsStatusData,
    build_decoded_entries,
    compute_ins_message_time_diff_stats,
    group_consecutive_status_spans,
    parse_ins_status_data_from_line,
    print_progression_summary,
    print_ins_messages_time_diff_stats,
    print_status_span_report,
    read_lines,
)

DEFAULT_LOG_FILENAME = "ins_monitor_live.log"
ARG_STREAM_DURATION_SECS = f"{ARGUMENT_LONG_PREFIX}stream_duration_secs"
SSM_IP = f"{ARGUMENT_LONG_PREFIX}ssm_host_ip"
ARG_REMOTE_PATH = f"{ARGUMENT_LONG_PREFIX}remote_path"
ARG_READ_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}read_timeout"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_FILE = f"{ARGUMENT_LONG_PREFIX}file"
ARG_MAX_SPAN_OF = f"{ARGUMENT_LONG_PREFIX}max_span_of"


def getToolData() -> ToolData:
    tool_templates = [
        ToolTemplate(
            name="Capture + analyze INS monitor log",
            extra_description="Stream INS monitor log for a duration, then analyze insStatus transitions.",
            args={SSM_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_STREAM_DURATION_SECS: 200},
        )
    ]
    return ToolData(tool_templates=tool_templates, tool_priority=EToolPriority.Level10_Last, hidden=False)



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture INS monitor log for a period, then run INS status analysis.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))
    parser.add_argument(ARG_STREAM_DURATION_SECS, type=float, default=300.0, help="How long to stream the log before analysis.")
    parser.add_argument(SSM_IP, default=f"{SSM_NORMAL_IP_PREFIX}.57", help="SSM IP for ACU log access.")
    parser.add_argument(ARG_REMOTE_PATH, default="/var/log/ins_monitor_log", help="Remote INS monitor log path.")
    parser.add_argument(ARG_READ_TIMEOUT, type=int, default=600, help="Read timeout while streaming log lines.")
    parser.add_argument(ARG_TAIL_LINES, type=int, default=0, help="Initial historical lines before follow mode.")
    parser.add_argument(ARG_MAX_SPAN_OF, type=int, default=DEFAULT_MAX_SPAN_OF, help="Maximum span cycle width for INS status grouping.")
    return parser.parse_args()


def _build_run_capture_path(jump_host_ip: str, run_started_at: datetime) -> Path:
    run_dir_name = get_file_timestamp_with_us(run_started_at)
    return Path(DEFAULT_LOG_OUTPUT_PATH) / jump_host_ip / Path(DEFAULT_LOG_FILENAME).stem / run_dir_name / DEFAULT_LOG_FILENAME


def _fmt_dt(value: Optional[datetime]) -> str:
    return get_log_timestamp(value) if value else "N/A"


def _capture_log_sort_key(log_path: Path, candidate: Path) -> int:
    if candidate == log_path:
        return 0
    suffix = candidate.name.removeprefix(f"{log_path.name}.")
    return int(suffix) if suffix.isdigit() else -1


def get_capture_log_paths(log_path: Path) -> List[Path]:
    candidates: List[Path] = []
    if log_path.is_file():
        candidates.append(log_path)
    candidates.extend(path for path in log_path.parent.glob(f"{log_path.name}.*") if path.is_file() and path.name.removeprefix(f"{log_path.name}.").isdigit())
    return sorted(set(candidates), key=lambda path: _capture_log_sort_key(log_path, path), reverse=True)


def analyze_ins_status_file(log_path: Path, max_span_of: int = DEFAULT_MAX_SPAN_OF) -> int:
    log_paths = get_capture_log_paths(log_path)
    if not log_paths:
        LOG("No captured INS monitor log files found for analysis.")
        return 0
    LOG(f"{LOG_PREFIX_MSG_INFO} Analyze {len(log_paths)} capture file(s): {', '.join(str(path) for path in log_paths)}")
    lines: List[str] = []
    for log_path in log_paths:
        lines.extend(read_lines(str(log_path)))
    status_entries: List[InsStatusData] = [entry for idx, line in enumerate(lines, 1) if (entry := parse_ins_status_data_from_line(line, idx)) is not None]
    if not status_entries:
        LOG("No INS1Msg lines found in input.")
        return 0
    LOG(f"Parsed {len(status_entries)} INS1Msg lines from {len(lines)} input lines across {len(log_paths)} capture file(s).")
    print()
    status_spans = group_consecutive_status_spans(status_entries, max_span_of=max_span_of)
    print_status_span_report(status_spans)
    print_ins_messages_time_diff_stats(compute_ins_message_time_diff_stats(status_entries))
    print_progression_summary(build_decoded_entries(status_entries))
    LOG("Analysis complete.")
    return 0


def main() -> int:
    test_start_at = get_datetime_now()
    test_start_wall = time.time()
    args = parse_args()
    stream_duration_secs: float = get_arg_value(args, ARG_STREAM_DURATION_SECS)
    first_log_timeout_secs = stream_duration_secs
    #capture_log_path: str | None = get_arg_value(args, ARG_CAPTURE_LOG_PATH)
    ssm_ip: str = get_arg_value(args, SSM_IP)
    host_ip: str = ACU_IP
    remote_path: str = get_arg_value(args, ARG_REMOTE_PATH)
    read_timeout: int = get_arg_value(args, ARG_READ_TIMEOUT)
    tail_lines: int = get_arg_value(args, ARG_TAIL_LINES)
    max_span_of: int = get_arg_value(args, ARG_MAX_SPAN_OF)

    log_path = _build_run_capture_path(ssm_ip, run_started_at=test_start_at)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    LOG(f"{LOG_PREFIX_MSG_INFO} Safe reboot target UT {ssm_ip} before streaming")
    if not check_safe_reboot_ut(ut_ip=ssm_ip, should_ping_after_reboot=False):
        LOG(f"{LOG_PREFIX_MSG_ERROR} Safe reboot failed for target UT {ssm_ip}")
        return 1
    sleep_before_streaming = 10
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Reboot issued for target UT {ssm_ip}. Sleep for {sleep_before_streaming} seconds before streaming logs")
    time.sleep(sleep_before_streaming)

    handlers = build_live_log_handlers(output_log_path=str(log_path), log_stream_mode=ELogStreamMode.OverrideSingleFile)
    stop_event = threading.Event()
    stop_timer: Optional[threading.Timer] = None
    first_log_timeout_timer: Optional[threading.Timer] = None
    first_log_at: Optional[datetime] = None
    first_log_monotonic: Optional[float] = None
    first_log_timeout_hit = False

    def _on_first_log_timeout() -> None:
        nonlocal first_log_timeout_hit
        if first_log_at is not None:
            return
        first_log_timeout_hit = True
        LOG(f"{LOG_PREFIX_MSG_ERROR} No log line received within {int(first_log_timeout_secs)}s. Stop streaming.")
        stop_event.set()

    def _on_line_recv(line: str, line_type: ELineType) -> None:
        nonlocal first_log_at, first_log_monotonic, stop_timer
        if line_type != ELineType.LiveLog:
            return
        if first_log_at is not None:
            return
        first_log_at, first_log_monotonic = get_datetime_now(), time.time()
        LOG(f"{LOG_PREFIX_MSG_INFO} First log line received at {_fmt_dt(first_log_at)}. Start stream duration timer ({stream_duration_secs}s).")
        stop_timer = start_stop_timer(stream_duration_secs=stream_duration_secs, stop_event=stop_event)

    LOG(f"{LOG_PREFIX_MSG_INFO} Capture live INS monitor log to {log_path}")
    try:
        first_log_timeout_timer = threading.Timer(first_log_timeout_secs, _on_first_log_timeout)
        first_log_timeout_timer.daemon = True
        first_log_timeout_timer.start()
        stream_live_remote_log_to_file(host_ip=host_ip, remote_log_path=remote_path, jump_host_ip=ssm_ip, read_timeout=read_timeout, tail_lines=tail_lines, handlers=handlers, stop_event=stop_event, on_line_recv=_on_line_recv)
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Capture live INS monitor log failed: {exc}")
        return 1
    finally:
        if first_log_timeout_timer:
            first_log_timeout_timer.cancel()
        if stop_timer:
            stop_timer.cancel()
        close_live_log_handlers(handlers)
    stream_end_at, stream_end_wall = get_datetime_now(), time.time()
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Capture live INS monitor log completed.")
    

    LOG(f"{LOG_PREFIX_MSG_INFO} Analyze INS status")
    rc = analyze_ins_status_file(log_path, max_span_of=max_span_of)
    if rc != 0: return rc
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Analyze INS status completed.")

    LOG("=== Capture Summary ===")
    LOG(f"test start at: {_fmt_dt(test_start_at)}")
    LOG(f"log file: {log_path}")
    LOG(f"analyzed log files: {', '.join(str(path) for path in get_capture_log_paths(log_path)) or 'N/A'}")
    LOG(f"log start at: {_fmt_dt(first_log_at)}")
    LOG(f"capture end at: {_fmt_dt(stream_end_at)}")
    LOG(f"ssm ip: {ssm_ip}")
    LOG(f"remote path: {remote_path}")
    LOG(f"configured stream duration (after first log): {stream_duration_secs:.1f}s")
    if first_log_timeout_hit:
        LOG(f"first-log timeout: {int(first_log_timeout_secs)}s")
        LOG(f"first-log timeout hit: {'YES' if first_log_timeout_hit else 'NO'}")
    LOG(f"capture wall duration (test start -> capture end): {max(0.0, stream_end_wall - test_start_wall):.1f}s")
    LOG(f"actual streaming duration (first log -> capture end): {max(0.0, stream_end_wall - first_log_monotonic):.1f}s" if first_log_monotonic else "actual streaming duration (first log -> capture end): N/A")
    show_noti(title="Capture + analyze INS monitor log", message=f"Capture and analysis done. Log file: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
