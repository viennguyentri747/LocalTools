#!/usr/local/bin/local_python
import argparse
from datetime import datetime
import re
import threading
import time
from pathlib import Path
from typing import List, Optional

from available_tools.test_tools.test_ut_log.t_get_acu_logs import DEFAULT_LOG_OUTPUT_PATH
from available_tools.test_tools.test_ut_log.t_get_ut_live_log_batch import EUtLiveLogType, UtLiveLogBatchSession, start_ut_live_log_batch_stream
from available_tools.test_tools.test_ut_log.t_get_ut_live_log import ELogStreamMode, build_live_log_handlers
from dev.dev_common import *
from dev.dev_iesa.iesa_ut_install_utils import check_safe_reboot_ut
from dev.dev_common.custom_structures import ToolData
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from dev.dev_common.noti_utils import show_noti
from unit_tests.specific_task_tests.common import copy_events_db_for_cycle

ARG_TARGET_IP = f"{ARGUMENT_LONG_PREFIX}target_ip"
ARG_ACU_IP = f"{ARGUMENT_LONG_PREFIX}acu_ip"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_STREAM_DURATION_SECS = f"{ARGUMENT_LONG_PREFIX}stream_duration_secs"
ARG_WAIT_BEFORE_REBOOT_SECS = f"{ARGUMENT_LONG_PREFIX}wait_before_reboot_secs"
ARG_WAIT_BETWEEN_CYCLES_SECS = f"{ARGUMENT_LONG_PREFIX}wait_between_cycles_secs"
ARG_TRIGGER_TIMEOUT_SECS = f"{ARGUMENT_LONG_PREFIX}trigger_timeout_secs"
ARG_WAIT_SECS_ON_FAIL = f"{ARGUMENT_LONG_PREFIX}wait_secs_on_fail"
ARG_REPEAT_COUNT = f"{ARGUMENT_LONG_PREFIX}repeat_count"

TRIGGER_PATTERN = re.compile(r"KIM/FTM CONFIGURATION COMPLETE", re.IGNORECASE)
FTMRESET_PATTERN = re.compile(r"ftmreset", re.IGNORECASE)
MODEM_LOC_SYNC_LOST_PATTERN = re.compile(r"modem_loc_sync_lost", re.IGNORECASE)
MODEM_TOD_SYNC_LOST_PATTERN = re.compile(r"modem_tod_sync_lost", re.IGNORECASE)
INS_MONITOR_POST_TRIGGER_WAIT_SECS = 5
MM_OWEXT_POST_TRIGGER_WAIT_SECS = 60
GNSSLOG_POST_TRIGGER_WAIT_SECS = 60
TIMEINJ_POST_TRIGGER_WAIT_SECS = 60
AIM_MANAGER_LOG_POST_TRIGGER_WAIT_SECS = 10
AMC_LOG_POST_TRIGGER_WAIT_SECS = 10
PING_TIMEOUT_AFTER_REBOOT_SECS = 300
STREAM_DURATION_HIGH_SECS = 9999.0
LIVE_LOG_READ_TIMEOUT_SECS = 60
TOD_SYNC_LOG_DIR_NAME = "ESA1W-7312_tod_sync_test"
RUN_DIR_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _fmt_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_cycle_base_dir(target_ip: str, cycle: int) -> Path:
    return Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / TOD_SYNC_LOG_DIR_NAME / RUN_DIR_TIMESTAMP / f"cycle_{cycle}"


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


def _build_cycle_log_dir_name(cycle: int) -> str:
    return f"{TOD_SYNC_LOG_DIR_NAME}/{RUN_DIR_TIMESTAMP}/cycle_{cycle}"


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


def _check_batch_stream_error(session: UtLiveLogBatchSession, cycle: int, attempt: int, program_log_path: Path, stage: str) -> bool:
    first_error = session.get_first_error()
    if not first_error:
        return False
    log_type, error = first_error
    message = f"Cycle {cycle} attempt {attempt}: {log_type.value} stream failed ({stage}): {error}"
    LOG(f"{LOG_PREFIX_MSG_ERROR} {message}")
    _append_program_log(program_log_path=program_log_path, message=message)
    return True


def _stop_streams_by_wait_windows(session: UtLiveLogBatchSession, wait_by_type_secs: dict[EUtLiveLogType, float]) -> None:
    if not wait_by_type_secs:
        return
    grouped: dict[float, list[EUtLiveLogType]] = {}
    for log_type, secs in wait_by_type_secs.items():
        grouped.setdefault(max(0.0, float(secs)), []).append(log_type)
    elapsed = 0.0
    for target_wait in sorted(grouped.keys()):
        delta = max(0.0, target_wait - elapsed)
        if delta > 0:
            time.sleep(delta)
        log_types = grouped[target_wait]
        session.stop(log_types=log_types)
        session.join(timeout_per_thread=15.0, log_types=log_types)
        elapsed = target_wait


def _run_one_cycle(cycle: int, attempt: int, target_ip: str, acu_ip: str, tail_lines: int, stream_duration_secs: float, wait_before_reboot_secs: int, trigger_timeout_secs: int) -> tuple[bool, int, int, int]:
    cycle_base = _build_cycle_base_dir(target_ip=target_ip, cycle=cycle)
    program_log_path = cycle_base.parent / "tod_program.log"
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: started")

    def _copy_cycle_event_dump(event_stage: str) -> None:
        copy_events_db_for_cycle(cycle=cycle, attempt=attempt, target_ip=target_ip, cycle_base=cycle_base, program_log_path=program_log_path, append_program_log_fn=_append_program_log, event_stage=event_stage)

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

    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: start streaming mm_owext, mm_timeinj, gnss, amc, aim_manager, and ins_monitor logs")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: start streaming mm_owext, mm_timeinj, gnss, amc, aim_manager, and ins_monitor logs")
    monitor = _CycleMonitor()
    requested_log_types = [EUtLiveLogType.SSM_MM_OWEXT_LOG, EUtLiveLogType.SSM_TIMEINJ_LOG, EUtLiveLogType.SSM_GNSS_LOG, EUtLiveLogType.SSM_AMC_LOG, EUtLiveLogType.ACU_AIM_MANAGER_LOG, EUtLiveLogType.ACU_INS_MONITOR_LOG]
    cycle_log_dir_name = _build_cycle_log_dir_name(cycle=cycle)
    handlers_by_type = {log_type: build_live_log_handlers(output_log_path=str(Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / cycle_log_dir_name / f"{log_type.value}.live.log"), log_stream_mode=ELogStreamMode.OverrideSingleFile) for log_type in requested_log_types}
    session = start_ut_live_log_batch_stream(target_ip=target_ip, acu_ip=acu_ip, log_types=requested_log_types, log_dir_name=cycle_log_dir_name, tail_lines=tail_lines, read_timeout=LIVE_LOG_READ_TIMEOUT_SECS, stream_duration_secs=stream_duration_secs, handlers_by_type=handlers_by_type, on_line_recv_by_type={EUtLiveLogType.SSM_MM_OWEXT_LOG: monitor.on_mm_owext_line, EUtLiveLogType.ACU_INS_MONITOR_LOG: monitor.on_ins_monitor_line}, wait_acu_reachable=True, acu_reachable_wait_timeout_secs=PING_TIMEOUT_AFTER_REBOOT_SECS)

    seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count = 0, 0, 0
    has_trigger = monitor.trigger_detected_event.wait(timeout=max(1, trigger_timeout_secs))
    seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count = _drain_pattern_logs(cycle=cycle, monitor=monitor, program_log_path=program_log_path, seen_ftmreset_count=seen_ftmreset_count, seen_modem_loc_sync_lost_count=seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count=seen_modem_tod_sync_lost_count)
    if _check_batch_stream_error(session=session, cycle=cycle, attempt=attempt, program_log_path=program_log_path, stage="before trigger handling"):
        session.stop()
        session.join(timeout_per_thread=15.0)
        _copy_cycle_event_dump(event_stage="after stream failure before trigger")
        return False, 0, 0, 0
    if not has_trigger:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Cycle {cycle}: trigger line not found within {trigger_timeout_secs}s")
        _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: trigger line not found within {trigger_timeout_secs}s")
        session.stop()
        session.join(timeout_per_thread=15.0)
        seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count = _drain_pattern_logs(cycle=cycle, monitor=monitor, program_log_path=program_log_path, seen_ftmreset_count=seen_ftmreset_count, seen_modem_loc_sync_lost_count=seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count=seen_modem_tod_sync_lost_count)
        _check_batch_stream_error(session=session, cycle=cycle, attempt=attempt, program_log_path=program_log_path, stage="after timeout stop")
        _copy_cycle_event_dump(event_stage="after trigger timeout")
        return False, 0, 0, 0

    wait_windows = {
        EUtLiveLogType.ACU_INS_MONITOR_LOG: INS_MONITOR_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.SSM_MM_OWEXT_LOG: MM_OWEXT_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.SSM_TIMEINJ_LOG: TIMEINJ_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.SSM_GNSS_LOG: GNSSLOG_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.SSM_AMC_LOG: AMC_LOG_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.ACU_AIM_MANAGER_LOG: AIM_MANAGER_LOG_POST_TRIGGER_WAIT_SECS,
    }
    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: trigger detected, post-trigger wait windows secs = {', '.join(f'{k.value}:{int(v)}' for k, v in wait_windows.items())}")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: trigger detected, post-trigger wait windows secs = {', '.join(f'{k.value}:{int(v)}' for k, v in wait_windows.items())}")
    _stop_streams_by_wait_windows(session=session, wait_by_type_secs=wait_windows)
    seen_ftmreset_count, seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count = _drain_pattern_logs(cycle=cycle, monitor=monitor, program_log_path=program_log_path, seen_ftmreset_count=seen_ftmreset_count, seen_modem_loc_sync_lost_count=seen_modem_loc_sync_lost_count, seen_modem_tod_sync_lost_count=seen_modem_tod_sync_lost_count)
    if _check_batch_stream_error(session=session, cycle=cycle, attempt=attempt, program_log_path=program_log_path, stage="after post-trigger stop"):
        _copy_cycle_event_dump(event_stage="after post-trigger stream failure")
        return False, 0, 0, 0

    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: post-trigger waits done, wait {wait_before_reboot_secs}s before reboot")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: post-trigger waits done, wait {wait_before_reboot_secs}s before reboot")
    time.sleep(max(0, wait_before_reboot_secs))
    _copy_cycle_event_dump(event_stage="after cycle log collection")
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
        is_ok, cycle_ftmreset_count, cycle_modem_loc_sync_lost_count, cycle_modem_tod_sync_lost_count = _run_one_cycle(cycle=cycle, attempt=attempt, target_ip=target_ip, acu_ip=acu_ip, tail_lines=tail_lines, stream_duration_secs=stream_duration_secs, wait_before_reboot_secs=wait_before_reboot_secs, trigger_timeout_secs=trigger_timeout_secs)
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
