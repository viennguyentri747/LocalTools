#!/usr/local/bin/local_python
import argparse
import re
import threading
import time
from pathlib import Path
from typing import List, Optional

from available_tools.test_tools.test_ut_log.t_get_acu_logs import DEFAULT_LOG_OUTPUT_PATH
from available_tools.test_tools.test_ut_log.t_get_ut_live_log import ELogStreamMode, stream_live_remote_log_to_file
from dev.dev_common import *
from dev.dev_iesa.iesa_ut_install_utils import check_safe_reboot_ut
from dev.dev_common.custom_structures import ToolData
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog

ARG_TARGET_IP = f"{ARGUMENT_LONG_PREFIX}target_ip"
ARG_ACU_IP = f"{ARGUMENT_LONG_PREFIX}acu_ip"
ARG_READ_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}read_timeout"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_STREAM_DURATION_SECS = f"{ARGUMENT_LONG_PREFIX}stream_duration_secs"
ARG_WAIT_BEFORE_REBOOT_SECS = f"{ARGUMENT_LONG_PREFIX}wait_before_reboot_secs"
ARG_WAIT_BETWEEN_CYCLES_SECS = f"{ARGUMENT_LONG_PREFIX}wait_between_cycles_secs"
ARG_TRIGGER_TIMEOUT_SECS = f"{ARGUMENT_LONG_PREFIX}trigger_timeout_secs"
ARG_REPEAT_COUNT = f"{ARGUMENT_LONG_PREFIX}repeat_count"

REMOTE_MM_OWEXT_LOG = "/var/log/mm_owext.log"
REMOTE_INS_MONITOR_LOG = "/var/log/ins_monitor_log"
TRIGGER_PATTERN = re.compile(r"KIM/FTM CONFIGURATION COMPLETE", re.IGNORECASE)


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(name="ESA1W-7312 default (2 cycles)", extra_description="Capture mm_owext + ins_monitor, detect KIM/FTM complete, reboot, repeat once.", args={ARG_TARGET_IP: f"{SSM_NORMAL_IP_PREFIX}.57"}),
        ToolTemplate(name="ESA1W-7312 custom waits", extra_description="Tune trigger/reboot timing for slower systems.", args={ARG_TARGET_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_WAIT_BEFORE_REBOOT_SECS: 15, ARG_TRIGGER_TIMEOUT_SECS: 300, ARG_REPEAT_COUNT: 2}),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESA1W-7312 TOD sync test helper: capture logs, wait for KIM/FTM complete, then reboot and repeat.", formatter_class=argparse.RawTextHelpFormatter)
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_TARGET_IP, required=True, help="UT jump-host IP. Accepts full IP or last octet (e.g. 57).")
    parser.add_argument(ARG_ACU_IP, default=ACU_IP, help=f"ACU IP (default: {ACU_IP}).")
    parser.add_argument(ARG_READ_TIMEOUT, type=int, default=600, help="Read timeout while tailing.")
    parser.add_argument(ARG_TAIL_LINES, type=int, default=0, help="Initial lines before follow.")
    parser.add_argument(ARG_STREAM_DURATION_SECS, type=float, default=180.0, help="Per-cycle stream duration for each log.")
    parser.add_argument(ARG_WAIT_BEFORE_REBOOT_SECS, type=int, default=30, help="Wait after trigger line before reboot.")
    parser.add_argument(ARG_WAIT_BETWEEN_CYCLES_SECS, type=int, default=5, help="Wait between test cycles.")
    parser.add_argument(ARG_TRIGGER_TIMEOUT_SECS, type=int, default=180, help="Max wait for trigger line per cycle.")
    parser.add_argument(ARG_REPEAT_COUNT, type=int, required=True, help="Number of cycles.")
    return parser.parse_args()


def _normalize_target_ip(target_ip: str) -> str:
    value = (target_ip or "").strip()
    if value.count(".") == 3:
        return value
    if value.isdigit():
        return f"{SSM_NORMAL_IP_PREFIX}.{int(value)}"
    raise ValueError(f"Invalid target_ip '{target_ip}'. Use full IP or last octet.")


def _build_cycle_log_paths(target_ip: str, cycle: int) -> tuple[Path, Path]:
    base = Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / "ESA1W-7312_tod_sync_test" / f"cycle_{cycle}"
    return base / "mm_owext.live.log", base / "ins_monitor.live.log"


def _wait_for_pattern_in_file(log_path: Path, pattern: re.Pattern[str], timeout_secs: int, mm_thread: Optional[threading.Thread] = None, ins_thread: Optional[threading.Thread] = None, mm_error: Optional[List[BaseException]] = None, ins_error: Optional[List[BaseException]] = None) -> bool:
    deadline = time.time() + max(1, timeout_secs)
    position = 0
    while time.time() < deadline:
        if mm_error and mm_error[0]:
            LOG(f"{LOG_PREFIX_MSG_ERROR} mm_owext stream failed: {mm_error[0]}")
            return False
        if ins_error and ins_error[0]:
            LOG(f"{LOG_PREFIX_MSG_ERROR} ins_monitor stream failed: {ins_error[0]}")
            return False
        if mm_thread and ins_thread and (not mm_thread.is_alive()) and (not ins_thread.is_alive()) and not log_path.exists():
            LOG(f"{LOG_PREFIX_MSG_ERROR} Both stream threads ended before ins_monitor log file was created: {log_path}")
            return False
        if not log_path.exists():
            time.sleep(1)
            continue
        with open(log_path, "r", encoding="utf-8", errors="ignore") as file_obj:
            file_obj.seek(position)
            while True:
                line = file_obj.readline()
                if not line:
                    break
                if pattern.search(line):
                    return True
            position = file_obj.tell()
        time.sleep(1)
    return False


def _start_stream_thread(host_ip: str, remote_log_path: str, jump_host_ip: str, read_timeout: int, tail_lines: int, stream_duration_secs: float, log_path: Path) -> tuple[threading.Thread, List[BaseException]]:
    error_box: List[BaseException] = []

    def _run() -> None:
        try:
            stream_live_remote_log_to_file(host_ip=host_ip, remote_log_path=remote_log_path, jump_host_ip=jump_host_ip, read_timeout=read_timeout, tail_lines=tail_lines, stream_duration_secs=stream_duration_secs, log_path=str(log_path), log_stream_mode=ELogStreamMode.OverrideSingleFile)
        except BaseException as exc:
            error_box.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread, error_box


def _run_one_cycle(cycle: int, target_ip: str, acu_ip: str, read_timeout: int, tail_lines: int, stream_duration_secs: float, wait_before_reboot_secs: int, trigger_timeout_secs: int) -> bool:
    mm_log_path, ins_log_path = _build_cycle_log_paths(target_ip=target_ip, cycle=cycle)
    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: run safe reboot at cycle start")
    if not check_safe_reboot_ut(ut_ip=target_ip, should_ping_after_reboot=False):
        LOG(f"{LOG_PREFIX_MSG_ERROR} Cycle {cycle}: check_safe_reboot_ut failed at cycle start")
        return False
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Cycle {cycle}: reboot issued at cycle start")
    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: start streaming mm_owext and ins_monitor logs")
    mm_thread, mm_error = _start_stream_thread(host_ip=target_ip, remote_log_path=REMOTE_MM_OWEXT_LOG, jump_host_ip=None, read_timeout=read_timeout, tail_lines=tail_lines, stream_duration_secs=stream_duration_secs, log_path=mm_log_path)
    ins_thread, ins_error = _start_stream_thread(host_ip=acu_ip, remote_log_path=REMOTE_INS_MONITOR_LOG, jump_host_ip=target_ip, read_timeout=read_timeout, tail_lines=tail_lines, stream_duration_secs=stream_duration_secs, log_path=ins_log_path)

    has_trigger = _wait_for_pattern_in_file(log_path=ins_log_path, pattern=TRIGGER_PATTERN, timeout_secs=trigger_timeout_secs, mm_thread=mm_thread, ins_thread=ins_thread, mm_error=mm_error, ins_error=ins_error)
    if not has_trigger:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Cycle {cycle}: trigger line not found within {trigger_timeout_secs}s")
        mm_thread.join(timeout=max(1.0, stream_duration_secs + 5))
        ins_thread.join(timeout=max(1.0, stream_duration_secs + 5))
        return False

    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: trigger detected, wait {wait_before_reboot_secs}s before reboot")

    time.sleep(max(0, wait_before_reboot_secs))
    ins_thread.join(timeout=max(1.0, stream_duration_secs + 5))
    mm_thread.join(timeout=max(1.0, stream_duration_secs + 5))

    return True


def main() -> int:
    args = parse_args()
    target_ip = _normalize_target_ip(get_arg_value(args, ARG_TARGET_IP))
    acu_ip = get_arg_value(args, ARG_ACU_IP)
    read_timeout = get_arg_value(args, ARG_READ_TIMEOUT)
    tail_lines = get_arg_value(args, ARG_TAIL_LINES)
    stream_duration_secs = get_arg_value(args, ARG_STREAM_DURATION_SECS)
    wait_before_reboot_secs = get_arg_value(args, ARG_WAIT_BEFORE_REBOOT_SECS)
    wait_between_cycles_secs = get_arg_value(args, ARG_WAIT_BETWEEN_CYCLES_SECS)
    trigger_timeout_secs = get_arg_value(args, ARG_TRIGGER_TIMEOUT_SECS)
    repeat_count = get_arg_value(args, ARG_REPEAT_COUNT)

    if repeat_count < 1:
        raise ValueError(f"{ARG_REPEAT_COUNT} must be >= 1")
    if stream_duration_secs <= 0:
        raise ValueError(f"{ARG_STREAM_DURATION_SECS} must be > 0")

    for cycle in range(1, repeat_count + 1):
        is_ok = _run_one_cycle(cycle=cycle, target_ip=target_ip, acu_ip=acu_ip, read_timeout=read_timeout, tail_lines=tail_lines, stream_duration_secs=stream_duration_secs, wait_before_reboot_secs=wait_before_reboot_secs, trigger_timeout_secs=trigger_timeout_secs)
        if not is_ok:
            return 1
        if cycle < repeat_count:
            LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: sleep {wait_between_cycles_secs}s before next cycle")
            time.sleep(max(0, wait_between_cycles_secs))

    LOG(f"{LOG_PREFIX_MSG_SUCCESS} ESA1W-7312 TOD sync test flow completed. target_ip={target_ip}, repeat_count={repeat_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
