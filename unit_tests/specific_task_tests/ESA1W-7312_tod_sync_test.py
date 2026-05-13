#!/usr/local/bin/local_python
import argparse
from datetime import datetime
import re
import shlex
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from available_tools.test_tools.test_ut_log.t_get_acu_logs import DEFAULT_LOG_OUTPUT_PATH
from available_tools.test_tools.test_ut_log.t_get_ut_live_log import ELogStreamMode, stream_live_remote_log_to_file
from dev.dev_common import *
from dev.dev_iesa.iesa_ut_install_utils import check_safe_reboot_ut
from dev.dev_common.custom_structures import ToolData
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from dev.dev_common.noti_utils import show_noti

ARG_TARGET_IP = f"{ARGUMENT_LONG_PREFIX}target_ip"
ARG_ACU_IP = f"{ARGUMENT_LONG_PREFIX}acu_ip"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_STREAM_DURATION_SECS = f"{ARGUMENT_LONG_PREFIX}stream_duration_secs"
ARG_WAIT_BEFORE_REBOOT_SECS = f"{ARGUMENT_LONG_PREFIX}wait_before_reboot_secs"
ARG_WAIT_BETWEEN_CYCLES_SECS = f"{ARGUMENT_LONG_PREFIX}wait_between_cycles_secs"
ARG_TRIGGER_TIMEOUT_SECS = f"{ARGUMENT_LONG_PREFIX}trigger_timeout_secs"
ARG_WAIT_SECS_ON_FAIL = f"{ARGUMENT_LONG_PREFIX}wait_secs_on_fail"
ARG_REPEAT_COUNT = f"{ARGUMENT_LONG_PREFIX}repeat_count"

REMOTE_MM_OWEXT_LOG = "/var/log/mm_owext.log"
REMOTE_GNSS_LOG = "/var/log/gnss.log"
REMOTE_INS_MONITOR_LOG = "/var/log/ins_monitor_log"
TRIGGER_PATTERN = re.compile(r"KIM/FTM CONFIGURATION COMPLETE", re.IGNORECASE)
FTMRESET_PATTERN = re.compile(r"ftmreset", re.IGNORECASE)
MODEM_LOC_SYNC_LOST_PATTERN = re.compile(r"modem_loc_sync_lost", re.IGNORECASE)
MODEM_TOD_SYNC_LOST_PATTERN = re.compile(r"modem_tod_sync_lost", re.IGNORECASE)
INS_MONITOR_POST_TRIGGER_WAIT_SECS = 60
MM_OWEXT_POST_TRIGGER_WAIT_SECS = 120
GNSSLOG_POST_TRIGGER_WAIT_SECS = 60
PING_TIMEOUT_AFTER_REBOOT_SECS = 300
STREAM_DURATION_HIGH_SECS = 9999.0
RUN_DIR_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _fmt_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_cycle_base_dir(target_ip: str, cycle: int) -> Path:
    return Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / "ESA1W-7312_tod_sync_test" / RUN_DIR_TIMESTAMP / f"cycle_{cycle}"


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(name="ESA1W-7312 default (2 cycles)", extra_description="Capture mm_owext + ins_monitor, detect KIM/FTM complete, reboot, repeat once.", args={ARG_TARGET_IP: f"{SSM_NORMAL_IP_PREFIX}.57"}),
        ToolTemplate(name="ESA1W-7312 custom waits", extra_description="Tune trigger/reboot timing for slower systems.", args={ARG_TARGET_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_WAIT_BEFORE_REBOOT_SECS: 15, ARG_TRIGGER_TIMEOUT_SECS: 400, ARG_REPEAT_COUNT: 2}),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESA1W-7312 TOD sync test helper: capture logs, wait for KIM/FTM complete, then reboot and repeat.", formatter_class=argparse.RawTextHelpFormatter)
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_TARGET_IP, required=True, help="UT jump-host IP. Accepts full IP or last octet (e.g. 57).")
    parser.add_argument(ARG_ACU_IP, default=ACU_IP, help=f"ACU IP (default: {ACU_IP}).")
    parser.add_argument(ARG_TAIL_LINES, type=int, default=0, help="Initial lines before follow.")
    parser.add_argument(ARG_STREAM_DURATION_SECS, type=float, default=STREAM_DURATION_HIGH_SECS, help=f"Per-cycle stream duration for each log (default high value: {STREAM_DURATION_HIGH_SECS}, stop is trigger/timeout-driven).")
    parser.add_argument(ARG_WAIT_BEFORE_REBOOT_SECS, type=int, default=30, help="Wait after trigger line before reboot.")
    parser.add_argument(ARG_WAIT_BETWEEN_CYCLES_SECS, type=int, default=5, help="Wait between test cycles.")
    parser.add_argument(ARG_TRIGGER_TIMEOUT_SECS, type=int, default=400, help="Max wait for trigger line per cycle.")
    parser.add_argument(ARG_WAIT_SECS_ON_FAIL, type=int, default=10, help="Wait before retry when a cycle attempt fails.")
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
    base = _build_cycle_base_dir(target_ip=target_ip, cycle=cycle)
    return base / "mm_owext.live.log", base / "ins_monitor.live.log"


class _CycleMonitor:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.trigger_detected_event = threading.Event()
        self.trigger_ts: Optional[float] = None
        self.ftmreset_lines: List[str] = []
        self.modem_loc_sync_lost_lines: List[str] = []
        self.modem_tod_sync_lost_lines: List[str] = []

    def on_ins_monitor_line(self, line: str) -> None:
        line_text = (line or "").strip()
        now = time.time()
        with self.lock:
            if self.trigger_ts is None and TRIGGER_PATTERN.search(line_text):
                self.trigger_ts = now
                self.trigger_detected_event.set()
                LOG(f"{LOG_PREFIX_MSG_INFO} Trigger detected in ins_monitor. Applying wait windows: ins_monitor={INS_MONITOR_POST_TRIGGER_WAIT_SECS}s, mm_owext={MM_OWEXT_POST_TRIGGER_WAIT_SECS}s")
            if FTMRESET_PATTERN.search(line_text):
                self.ftmreset_lines.append(line_text)

    def on_mm_owext_line(self, line: str) -> None:
        line_text = (line or "").strip()
        with self.lock:
            if MODEM_LOC_SYNC_LOST_PATTERN.search(line_text):
                self.modem_loc_sync_lost_lines.append(line_text)
            if MODEM_TOD_SYNC_LOST_PATTERN.search(line_text):
                self.modem_tod_sync_lost_lines.append(line_text)


def _append_program_log(program_log_path: Path, message: str) -> None:
    program_log_path.parent.mkdir(parents=True, exist_ok=True)
    with program_log_path.open("a", encoding="utf-8") as fp:
        fp.write(f"[{_fmt_now()}] {message}\n")


def _log_event_with_line(program_log_path: Path, cycle: int, event_name: str, line_text: str, count_so_far: int) -> None:
    message = f"Cycle {cycle}: {event_name} #{count_so_far} at line: {line_text}"
    LOG(f"{LOG_PREFIX_MSG_INFO} {message}")
    _append_program_log(program_log_path=program_log_path, message=message)


def _drain_pattern_logs(cycle: int, monitor: _CycleMonitor, program_log_path: Path, seen_ftmreset_count: int, seen_modem_loc_sync_lost_count: int, seen_modem_tod_sync_lost_count: int) -> tuple[int, int, int]:
    with monitor.lock:
        ftm_lines = monitor.ftmreset_lines
        modem_lines = monitor.modem_loc_sync_lost_lines
        modem_tod_lines = monitor.modem_tod_sync_lost_lines
        new_ftm_lines = ftm_lines[seen_ftmreset_count:]
        new_modem_lines = modem_lines[seen_modem_loc_sync_lost_count:]
        new_modem_tod_lines = modem_tod_lines[seen_modem_tod_sync_lost_count:]
        total_ftm = len(ftm_lines)
        total_modem = len(modem_lines)
        total_modem_tod = len(modem_tod_lines)
    for idx, line_text in enumerate(new_ftm_lines, start=seen_ftmreset_count + 1):
        _log_event_with_line(program_log_path=program_log_path, cycle=cycle, event_name="ftmreset", line_text=line_text, count_so_far=idx)
    for idx, line_text in enumerate(new_modem_lines, start=seen_modem_loc_sync_lost_count + 1):
        _log_event_with_line(program_log_path=program_log_path, cycle=cycle, event_name="modem_loc_sync_lost", line_text=line_text, count_so_far=idx)
    for idx, line_text in enumerate(new_modem_tod_lines, start=seen_modem_tod_sync_lost_count + 1):
        _log_event_with_line(program_log_path=program_log_path, cycle=cycle, event_name="modem_tod_sync_lost", line_text=line_text, count_so_far=idx)
    return total_ftm, total_modem, total_modem_tod


def _resolve_events_db_path_from_cfg(target_ip: str, acu_ip: str) -> str:
    cfg_url = f"http://{acu_ip}/api/cm/cfg_all"
    cmd = f"curl -s {shlex.quote(cfg_url)} | jq -r '.[] | select(.name == \"events_db_location\") | .value'"
    stdout, stderr = run_ssh_command(host_ip=target_ip, user=SSM_USER, password=SSM_PASSWORD, command=cmd, timeout=20)
    if stderr.strip():
        LOG(f"{LOG_PREFIX_MSG_WARNING} events_db_location query stderr: {stderr.strip()}")
    for line in (stdout or "").splitlines():
        value = line.strip()
        if value and value != "null":
            return value
    raise RuntimeError(f"Unable to resolve events_db_location from {cfg_url}. stdout='{stdout.strip()}' stderr='{stderr.strip()}'")


def _copy_events_db_before_reboot(cycle: int, attempt: int, target_ip: str, acu_ip: str, cycle_base: Path, program_log_path: Path) -> None:
    try:
        events_db_remote_path = _resolve_events_db_path_from_cfg(target_ip=target_ip, acu_ip=acu_ip)
        dest_dir = cycle_base / "events_db_before_reboot"
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied_files = copy_to_local(remote_src_paths=events_db_remote_path, remote_host_ip=target_ip, remote_user=SSM_USER, password=SSM_PASSWORD, local_dest_path=dest_dir, timeout=30)
        copied_text = ", ".join(copied_files) if copied_files else "none"
        msg = f"Cycle {cycle} attempt {attempt}: copied events DB before reboot. remote={events_db_remote_path}, local={copied_text}"
        LOG(f"{LOG_PREFIX_MSG_INFO} {msg}")
        _append_program_log(program_log_path=program_log_path, message=msg)
    except Exception as exc:
        msg = f"Cycle {cycle} attempt {attempt}: failed to copy events DB before reboot: {type(exc).__name__}: {exc}"
        LOG(f"{LOG_PREFIX_MSG_WARNING} {msg}")
        _append_program_log(program_log_path=program_log_path, message=msg)


def _start_stream_thread(host_ip: str, remote_log_path: str, jump_host_ip: str, tail_lines: int, stream_duration_secs: float, log_path: Path, on_line_recv: Optional[Callable[[str], None]] = None, stop_event: Optional[threading.Event] = None, wait_until_reachable_via_jump_host: bool = False, reachable_wait_timeout_secs: int = PING_TIMEOUT_AFTER_REBOOT_SECS) -> tuple[threading.Thread, List[BaseException]]:
    error_box: List[BaseException] = []

    def _run() -> None:
        try:
            if wait_until_reachable_via_jump_host:
                is_reachable = ping_remote_host_via_jump_host(remote_host_ip=host_ip, jump_host_ip=jump_host_ip, jump_user=SSM_USER, jump_password=SSM_PASSWORD, max_wait_sec=reachable_wait_timeout_secs, retry_interval_sec=5.0, ping_count=1, ping_timeout_sec=2, ssh_timeout_sec=10, check_jump_host_reachable=True, mute=False)
                if not is_reachable:
                    raise RuntimeError(f"{host_ip} is not reachable via jump host {jump_host_ip} within {reachable_wait_timeout_secs}s")
            stream_live_remote_log_to_file(host_ip=host_ip, remote_log_path=remote_log_path, jump_host_ip=jump_host_ip, read_timeout=max(1, int(stream_duration_secs)), tail_lines=tail_lines, stream_duration_secs=stream_duration_secs, log_path=str(log_path), log_stream_mode=ELogStreamMode.OverrideSingleFile, on_line_recv=on_line_recv, stop_event=stop_event)
        except BaseException as exc:
            error_box.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread, error_box


def _run_one_cycle(cycle: int, attempt: int, target_ip: str, acu_ip: str, tail_lines: int, wait_before_reboot_secs: int, trigger_timeout_secs: int) -> tuple[bool, int, int, int]:
    mm_log_path, ins_log_path = _build_cycle_log_paths(target_ip=target_ip, cycle=cycle)
    gnss_log_path = mm_log_path.parent / "gnss.live.log"
    cycle_base = _build_cycle_base_dir(target_ip=target_ip, cycle=cycle)
    program_log_path = cycle_base.parent / "tod_program.log"
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: started")
    _copy_events_db_before_reboot(cycle=cycle, attempt=attempt, target_ip=target_ip, acu_ip=acu_ip, cycle_base=cycle_base, program_log_path=program_log_path)
    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: run safe reboot at cycle start")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: run safe reboot at cycle start")
    if not check_safe_reboot_ut(ut_ip=target_ip, should_ping_after_reboot=False):
        LOG(f"{LOG_PREFIX_MSG_ERROR} Cycle {cycle}: check_safe_reboot_ut failed at cycle start")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: check_safe_reboot_ut failed at cycle start")
        return False, 0, 0, 0
    sleep_before_streaming = 10
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Cycle {cycle}: reboot issued at cycle start. Sleep for {sleep_before_streaming} seconds before try streaming logs")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: reboot issued at cycle start")
    time.sleep(sleep_before_streaming)

    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: start streaming mm_owext, gnss, and ins_monitor logs")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: start streaming mm_owext, gnss, and ins_monitor logs")
    monitor = _CycleMonitor()
    stream_stop_event = threading.Event()
    mm_thread, mm_error = _start_stream_thread(host_ip=target_ip, remote_log_path=REMOTE_MM_OWEXT_LOG, jump_host_ip=None, tail_lines=tail_lines, stream_duration_secs=STREAM_DURATION_HIGH_SECS, log_path=mm_log_path, on_line_recv=monitor.on_mm_owext_line, stop_event=stream_stop_event)
    gnss_thread, gnss_error = _start_stream_thread(host_ip=target_ip, remote_log_path=REMOTE_GNSS_LOG, jump_host_ip=None, tail_lines=tail_lines, stream_duration_secs=STREAM_DURATION_HIGH_SECS, log_path=gnss_log_path, stop_event=stream_stop_event)
    ins_thread, ins_error = _start_stream_thread(host_ip=acu_ip, remote_log_path=REMOTE_INS_MONITOR_LOG, jump_host_ip=target_ip, tail_lines=tail_lines, stream_duration_secs=STREAM_DURATION_HIGH_SECS, log_path=ins_log_path, on_line_recv=monitor.on_ins_monitor_line, stop_event=stream_stop_event, wait_until_reachable_via_jump_host=True, reachable_wait_timeout_secs=PING_TIMEOUT_AFTER_REBOOT_SECS)

    seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count = 0, 0, 0
    has_trigger = monitor.trigger_detected_event.wait(timeout=max(1, trigger_timeout_secs))
    seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count = _drain_pattern_logs(cycle=cycle, monitor=monitor, program_log_path=program_log_path, seen_ftmreset_count=seen_ftmreset_count, seen_modem_loc_sync_lost_count=seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count=seen_modem_tod_sync_lost_count)
    if mm_error:
        LOG(f"{LOG_PREFIX_MSG_ERROR} mm_owext stream failed: {mm_error[0]}")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: mm_owext stream failed: {mm_error[0]}")
        return False, 0, 0, 0
    if ins_error:
        LOG(f"{LOG_PREFIX_MSG_ERROR} ins_monitor stream failed: {ins_error[0]}")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: ins_monitor stream failed: {ins_error[0]}")
        return False, 0, 0, 0
    if gnss_error:
        LOG(f"{LOG_PREFIX_MSG_ERROR} gnss stream failed: {gnss_error[0]}")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: gnss stream failed: {gnss_error[0]}")
        return False, 0, 0, 0
    if not has_trigger:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Cycle {cycle}: trigger line not found within {trigger_timeout_secs}s")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: trigger line not found within {trigger_timeout_secs}s")
        stream_stop_event.set()
        mm_thread.join(timeout=15.0)
        gnss_thread.join(timeout=15.0)
        ins_thread.join(timeout=15.0)
        seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count = _drain_pattern_logs(cycle=cycle, monitor=monitor, program_log_path=program_log_path, seen_ftmreset_count=seen_ftmreset_count, seen_modem_loc_sync_lost_count=seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count=seen_modem_tod_sync_lost_count)
        if mm_error:
            LOG(f"{LOG_PREFIX_MSG_ERROR} mm_owext stream failed after join: {mm_error[0]}")
            _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: mm_owext stream failed after join: {mm_error[0]}")
        if ins_error:
            LOG(f"{LOG_PREFIX_MSG_ERROR} ins_monitor stream failed after join: {ins_error[0]}")
            _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: ins_monitor stream failed after join: {ins_error[0]}")
        if gnss_error:
            LOG(f"{LOG_PREFIX_MSG_ERROR} gnss stream failed after join: {gnss_error[0]}")
            _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: gnss stream failed after join: {gnss_error[0]}")
        return False, 0, 0, 0

    post_trigger_wait_secs = float(max(INS_MONITOR_POST_TRIGGER_WAIT_SECS, MM_OWEXT_POST_TRIGGER_WAIT_SECS, GNSSLOG_POST_TRIGGER_WAIT_SECS))
    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: trigger detected, wait ins_monitor={INS_MONITOR_POST_TRIGGER_WAIT_SECS}s, mm_owext={MM_OWEXT_POST_TRIGGER_WAIT_SECS}s, gnss={GNSSLOG_POST_TRIGGER_WAIT_SECS}s")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: trigger detected, wait ins_monitor={INS_MONITOR_POST_TRIGGER_WAIT_SECS}s, mm_owext={MM_OWEXT_POST_TRIGGER_WAIT_SECS}s, gnss={GNSSLOG_POST_TRIGGER_WAIT_SECS}s")
    time.sleep(post_trigger_wait_secs)
    stream_stop_event.set()
    seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count = _drain_pattern_logs(cycle=cycle, monitor=monitor, program_log_path=program_log_path, seen_ftmreset_count=seen_ftmreset_count, seen_modem_loc_sync_lost_count=seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count=seen_modem_tod_sync_lost_count)

    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: post-trigger waits done, wait {wait_before_reboot_secs}s before reboot")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: post-trigger waits done, wait {wait_before_reboot_secs}s before reboot")
    time.sleep(max(0, wait_before_reboot_secs))
    ins_thread.join(timeout=15.0)
    mm_thread.join(timeout=15.0)
    gnss_thread.join(timeout=15.0)
    if mm_error:
        LOG(f"{LOG_PREFIX_MSG_ERROR} mm_owext stream failed after join: {mm_error[0]}")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: mm_owext stream failed after join: {mm_error[0]}")
        return False, 0, 0, 0
    if ins_error:
        LOG(f"{LOG_PREFIX_MSG_ERROR} ins_monitor stream failed after join: {ins_error[0]}")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: ins_monitor stream failed after join: {ins_error[0]}")
        return False, 0, 0, 0
    if gnss_error:
        LOG(f"{LOG_PREFIX_MSG_ERROR} gnss stream failed after join: {gnss_error[0]}")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: gnss stream failed after join: {gnss_error[0]}")
        return False, 0, 0, 0
    seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count = _drain_pattern_logs(cycle=cycle, monitor=monitor, program_log_path=program_log_path, seen_ftmreset_count=seen_ftmreset_count, seen_modem_loc_sync_lost_count=seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count=seen_modem_tod_sync_lost_count)
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} summary: ftmreset_count={seen_ftmreset_count}, modem_loc_sync_lost_count={seen_modem_loc_sync_lost_count}, modem_tod_sync_lost_count={seen_modem_tod_sync_lost_count}")
    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle} summary: ftmreset_count={seen_ftmreset_count}, modem_loc_sync_lost_count={seen_modem_loc_sync_lost_count}, modem_tod_sync_lost_count={seen_modem_tod_sync_lost_count}")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: success")

    return True, seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count


def main() -> int:
    args = parse_args()
    target_ip = _normalize_target_ip(get_arg_value(args, ARG_TARGET_IP))
    acu_ip = get_arg_value(args, ARG_ACU_IP)
    tail_lines = get_arg_value(args, ARG_TAIL_LINES)
    stream_duration_secs = get_arg_value(args, ARG_STREAM_DURATION_SECS)
    wait_before_reboot_secs = get_arg_value(args, ARG_WAIT_BEFORE_REBOOT_SECS)
    wait_between_cycles_secs = get_arg_value(args, ARG_WAIT_BETWEEN_CYCLES_SECS)
    trigger_timeout_secs = get_arg_value(args, ARG_TRIGGER_TIMEOUT_SECS)
    wait_secs_on_fail = get_arg_value(args, ARG_WAIT_SECS_ON_FAIL)
    repeat_count = get_arg_value(args, ARG_REPEAT_COUNT)

    if repeat_count < 1:
        raise ValueError(f"{ARG_REPEAT_COUNT} must be >= 1")
    if stream_duration_secs <= 0:
        raise ValueError(f"{ARG_STREAM_DURATION_SECS} must be > 0")

    cycle = 1
    attempt = 1
    total_ftmreset_count = 0
    total_modem_loc_sync_lost_count = 0
    total_modem_tod_sync_lost_count = 0
    while cycle <= repeat_count:
        is_ok, cycle_ftmreset_count, cycle_modem_loc_sync_lost_count, cycle_modem_tod_sync_lost_count = _run_one_cycle(cycle=cycle, attempt=attempt, target_ip=target_ip, acu_ip=acu_ip, tail_lines=tail_lines, wait_before_reboot_secs=wait_before_reboot_secs, trigger_timeout_secs=trigger_timeout_secs)
        if is_ok:
            #cycle_ftmreset_count > 0 or
            if(cycle_modem_loc_sync_lost_count > 0 or cycle_modem_tod_sync_lost_count > 0):
                show_noti(title=f"Cycle on {target_ip} has issue!!", message=f"Cycle {cycle} complete", no_log_on_success=True)

            total_ftmreset_count += cycle_ftmreset_count
            total_modem_loc_sync_lost_count += cycle_modem_loc_sync_lost_count
            total_modem_tod_sync_lost_count += cycle_modem_tod_sync_lost_count
            cycle_base = _build_cycle_base_dir(target_ip=target_ip, cycle=cycle)
            program_log_path = cycle_base.parent / "tod_program.log"
            summary_so_far_msg = f"Cycle {cycle} summary so far: ftmreset_count={total_ftmreset_count}, modem_loc_sync_lost_count={total_modem_loc_sync_lost_count}, modem_tod_sync_lost_count={total_modem_tod_sync_lost_count}"
            LOG(f"{LOG_PREFIX_MSG_INFO} {summary_so_far_msg}")
            _append_program_log(program_log_path=program_log_path, message=summary_so_far_msg)
            if cycle < repeat_count:
                LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: sleep {wait_between_cycles_secs}s before next cycle")
                time.sleep(max(0, wait_between_cycles_secs))
            cycle += 1
            attempt = 1
            continue
        cycle_base = _build_cycle_base_dir(target_ip=target_ip, cycle=cycle)
        program_log_path = cycle_base.parent / "tod_program.log"
        LOG(f"{LOG_PREFIX_MSG_WARNING} Cycle {cycle} attempt {attempt} failed. Retry same cycle after {wait_secs_on_fail}s")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt} failed. Retry same cycle after {wait_secs_on_fail}s")
        time.sleep(max(0, wait_secs_on_fail))
        attempt += 1

    LOG(f"{LOG_PREFIX_MSG_SUCCESS} ESA1W-7312 TOD sync test flow completed. target_ip={target_ip}, repeat_count={repeat_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
