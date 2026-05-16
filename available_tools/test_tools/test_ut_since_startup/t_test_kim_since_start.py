#!/usr/local/bin/local_python
import argparse
from pathlib import Path
import threading
from typing import List

from dev.dev_common import *
from dev.dev_common.custom_structures import ToolData
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from available_tools.test_tools.test_ut_log.t_get_ut_live_log import ELogStreamMode, build_live_log_handlers, close_live_log_handlers, start_stop_timer, stream_live_remote_log_to_file
from available_tools.test_tools.test_ut_log.t_get_acu_logs import DEFAULT_LOG_OUTPUT_PATH
from available_tools.test_tools.test_ut_log.t_test_ins_status_ins_monitor_log import (
    compute_time_diff_stats,
    group_statuses,
    parse_ins1msg_line,
    print_grouped_report,
    print_time_diff_stats,
    read_lines,
)

DEFAULT_LOG_FILENAME = "ins_monitor_live.log"
ARG_STREAM_DURATION_SECS = f"{ARGUMENT_LONG_PREFIX}stream_duration_secs"
ARG_JUMP_HOST_IP = f"{ARGUMENT_LONG_PREFIX}jump_host_ip"
ARG_REMOTE_PATH = f"{ARGUMENT_LONG_PREFIX}remote_path"
ARG_READ_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}read_timeout"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_FILE = f"{ARGUMENT_LONG_PREFIX}file"


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Capture + analyze INS monitor log",
            extra_description="Stream INS monitor log for a duration, then analyze insStatus transitions.",
            args={ARG_JUMP_HOST_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_STREAM_DURATION_SECS: 300},
        )
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture INS monitor log for a period, then run INS status analysis.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_STREAM_DURATION_SECS, type=float, default=300.0, help="How long to stream the log before analysis.")
    parser.add_argument(ARG_JUMP_HOST_IP, default=f"{SSM_NORMAL_IP_PREFIX}.57", help="SSM jump-host IP for ACU log access.")
    parser.add_argument(ARG_REMOTE_PATH, default="/var/log/ins_monitor_log", help="Remote INS monitor log path.")
    parser.add_argument(ARG_READ_TIMEOUT, type=int, default=600, help="Read timeout while streaming log lines.")
    parser.add_argument(ARG_TAIL_LINES, type=int, default=0, help="Initial historical lines before follow mode.")
    return parser.parse_args()


def _build_default_capture_path(jump_host_ip: str) -> Path:
    return Path(DEFAULT_LOG_OUTPUT_PATH) / jump_host_ip / DEFAULT_LOG_FILENAME


def analyze_ins_status_file(log_path: Path) -> int:
    lines = read_lines(str(log_path))
    parsed = [entry for line in lines if (entry := parse_ins1msg_line(line)) is not None]
    if not parsed:
        LOG("No INS1Msg lines found in input.")
        return 0
    LOG(f"Parsed {len(parsed)} INS1Msg lines from {len(lines)} input lines.")
    print()
    print_time_diff_stats(compute_time_diff_stats(parsed))
    grouped = group_statuses(parsed)
    LOG("=== Status Changes Summary ===")
    LOG(f"Unique insStatus values: {len(grouped)}")
    print_grouped_report(grouped, len(parsed))
    LOG("Analysis complete.")
    return 0

def main() -> int:
    args = parse_args()
    stream_duration_secs: float = get_arg_value(args, ARG_STREAM_DURATION_SECS)
    #capture_log_path: str | None = get_arg_value(args, ARG_CAPTURE_LOG_PATH)
    jump_host_ip: str = get_arg_value(args, ARG_JUMP_HOST_IP)
    host_ip: str = ACU_IP
    remote_path: str = get_arg_value(args, ARG_REMOTE_PATH)
    read_timeout: int = get_arg_value(args, ARG_READ_TIMEOUT)
    tail_lines: int = get_arg_value(args, ARG_TAIL_LINES)

    log_path = _build_default_capture_path(jump_host_ip)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers = build_live_log_handlers(log_path=str(log_path), log_stream_mode=ELogStreamMode.OverrideSingleFile)
    stop_event = threading.Event()
    stop_timer = None

    LOG(f"{LOG_PREFIX_MSG_INFO} Capture live INS monitor log to {log_path}")
    try:
        stop_timer = start_stop_timer(stream_duration_secs=stream_duration_secs, stop_event=stop_event)
        stream_live_remote_log_to_file(host_ip=host_ip, remote_log_path=remote_path, jump_host_ip=jump_host_ip, read_timeout=read_timeout, tail_lines=tail_lines, handlers=handlers, stop_event=stop_event)
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Capture live INS monitor log failed: {exc}")
        return 1
    finally:
        if stop_timer:
            stop_timer.cancel()
        close_live_log_handlers(handlers)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Capture live INS monitor log completed.")

    LOG(f"{LOG_PREFIX_MSG_INFO} Analyze INS status")
    rc = analyze_ins_status_file(log_path)
    if rc != 0: return rc
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Analyze INS status completed.")

    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Capture and analysis done. Log file: {log_path}")
    show_noti(title="Capture + analyze INS monitor log", message=f"Capture and analysis done. Log file: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
