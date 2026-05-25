#!/usr/local/bin/local_python
import argparse
import logging
from datetime import datetime
import re
import threading
import time
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from available_tools.test_tools.test_ut_log.t_get_acu_logs import DEFAULT_LOG_OUTPUT_PATH
from available_tools.test_tools.test_ut_log.t_get_ut_live_log_batch import EUtLiveLogType, UtLiveLogBatchSession, start_ut_live_log_batch_stream
from available_tools.test_tools.test_ut_log.t_get_ut_live_log import ELogStreamMode, build_live_log_handlers
from dev.dev_common import *
from dev.dev_common.custom_structures import ToolData
from dev.dev_common.noti_utils import show_noti
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from unit_tests.specific_task_tests.common import copy_events_db_for_cycle

ARG_TARGET_IP = f"{ARGUMENT_LONG_PREFIX}target_ip"
ARG_ACU_IP = f"{ARGUMENT_LONG_PREFIX}acu_ip"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_STREAM_DURATION_SECS = f"{ARGUMENT_LONG_PREFIX}stream_duration_secs"
ARG_TRIGGER_TIMEOUT_SECS = f"{ARGUMENT_LONG_PREFIX}trigger_timeout_secs"
ARG_WAIT_BETWEEN_CYCLES_SECS = f"{ARGUMENT_LONG_PREFIX}wait_between_cycles_secs"
ARG_WAIT_SECS_ON_FAIL = f"{ARGUMENT_LONG_PREFIX}wait_secs_on_fail"
ARG_REPEAT_COUNT = f"{ARGUMENT_LONG_PREFIX}repeat_count"

TRIGGER_PATTERN = re.compile(r"INVALID TIME SYNC Occured Master KIM-RESET SKIP", re.IGNORECASE)
LINE_TS_PATTERN = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
E_LOG_POST_TRIGGER_WAIT_SECS = 60
INS_MONITOR_POST_TRIGGER_WAIT_SECS = 60
GNSS_LOG_POST_TRIGGER_WAIT_SECS = 60
MM_OWEXT_POST_TRIGGER_WAIT_SECS = 60
TIMEINJ_LOG_POST_TRIGGER_WAIT_SECS = 60
AMC_LOG_POST_TRIGGER_WAIT_SECS = 60
AIM_MANAGER_LOG_POST_TRIGGER_WAIT_SECS = 60
PING_TIMEOUT_AFTER_REBOOT_SECS = 300
STREAM_DURATION_HIGH_SECS = 9999.0
LIVE_LOG_READ_TIMEOUT_SECS = 60
TIME_SYNC_TEST_LOG_DIR_NAME = "ESA1W-7316_time_sync_test"
RUN_DIR_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
LOG_RETENTION_MAX_FILES_PER_TYPE = 10
LOG_RETENTION_WINDOW_SECS = 3600


def _fmt_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_cycle_base_dir(target_ip: str, cycle: int) -> Path:
    return Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / TIME_SYNC_TEST_LOG_DIR_NAME / RUN_DIR_TIMESTAMP / f"cycle_{cycle}"


def _build_cycle_log_dir_name(cycle: int) -> str:
    return f"{TIME_SYNC_TEST_LOG_DIR_NAME}/{RUN_DIR_TIMESTAMP}/cycle_{cycle}"


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(name="ESA1W-7316 default", extra_description="Capture ACU E*/ins_monitor + SSM gnss/mm_owext and stop by INVALID TIME SYNC trigger.", args={ARG_TARGET_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_REPEAT_COUNT: 1}),
        ToolTemplate(name="ESA1W-7316 custom timeout", extra_description="Adjust timeout/waits for slower trigger reproduction.", args={ARG_TARGET_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_TRIGGER_TIMEOUT_SECS: 400, ARG_REPEAT_COUNT: 2}),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_templates=get_tool_templates())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ESA1W-7316 time sync test helper: collect target logs and stop after INVALID TIME SYNC trigger with per-log post-trigger windows.", formatter_class=argparse.RawTextHelpFormatter)
    parser.epilog = build_examples_epilog(getToolData().tool_templates, Path(__file__))
    parser.add_argument(ARG_TARGET_IP, required=True, help="UT jump-host IP. Accepts full IP or last octet (e.g. 57).")
    parser.add_argument(ARG_ACU_IP, default=ACU_IP, help=f"ACU IP (default: {ACU_IP}).")
    parser.add_argument(ARG_TAIL_LINES, type=int, default=0, help="Initial lines before follow.")
    parser.add_argument(ARG_STREAM_DURATION_SECS, type=float, default=STREAM_DURATION_HIGH_SECS, help=f"Per-cycle stream duration (default high value: {STREAM_DURATION_HIGH_SECS}, stop is trigger/timeout-driven).")
    parser.add_argument(ARG_TRIGGER_TIMEOUT_SECS, type=int, default=400, help="Max wait for trigger line per cycle.")
    parser.add_argument(ARG_WAIT_BETWEEN_CYCLES_SECS, type=int, default=5, help="Wait between test cycles.")
    parser.add_argument(ARG_WAIT_SECS_ON_FAIL, type=int, default=10, help="Wait before retry when a cycle attempt fails.")
    parser.add_argument(ARG_REPEAT_COUNT, type=int, default=1, help="Number of cycles.")
    return parser.parse_args()


def _normalize_target_ip(target_ip: str) -> str:
    value = (target_ip or "").strip()
    if value.count(".") == 3:
        return value
    if value.isdigit():
        return f"{SSM_NORMAL_IP_PREFIX}.{int(value)}"
    raise ValueError(f"Invalid target_ip '{target_ip}'. Use full IP or last octet.")


class _CycleMonitor:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.trigger_detected_event = threading.Event()
        self.trigger_ts: Optional[float] = None
        self.trigger_line: str = EMPTY_STR_VALUE

    def on_e_log_line(self, line: str) -> None:
        line_text = (line or "").strip()
        if not line_text:
            return
        now = time.time()
        with self.lock:
            if self.trigger_ts is None and TRIGGER_PATTERN.search(line_text):
                self.trigger_ts = now
                self.trigger_line = line_text
                self.trigger_detected_event.set()
                LOG(f"{LOG_PREFIX_MSG_INFO} Trigger detected in ACU E log. line='{line_text}'")


@dataclass
class _TrackedLogWindow:
    path: Path
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None


class _TimeSyncLiveLogRetention:
    def __init__(self, target_ip: str, cycle_log_dir_name: str, max_files_per_type: int = LOG_RETENTION_MAX_FILES_PER_TYPE, rolling_window_secs: int = LOG_RETENTION_WINDOW_SECS) -> None:
        self.target_ip = target_ip
        self.cycle_log_dir_name = cycle_log_dir_name
        self.max_files_per_type = max(1, int(max_files_per_type))
        self.rolling_window_secs = max(1, int(rolling_window_secs))
        self.base_dir = Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / cycle_log_dir_name
        self.persistent_dir = self.base_dir / f"persistent_{self.rolling_window_secs}s"
        self.persistent_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.windows_by_type: Dict[EUtLiveLogType, Dict[Path, _TrackedLogWindow]] = {}
        self.last_trigger_ts: Optional[float] = None

    def _parse_line_ts(self, line: str) -> float:
        text = (line or "").strip()
        match = LINE_TS_PATTERN.match(text)
        if not match:
            return time.time()
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            return time.time()

    def on_log_line(self, log_type: EUtLiveLogType, line: str) -> None:
        ts = self._parse_line_ts(line)
        with self.lock:
            path = self.base_dir / f"{log_type.value}.live.log"
            tracked = self.windows_by_type.setdefault(log_type, {}).setdefault(path, _TrackedLogWindow(path=path))
            if tracked.start_ts is None:
                tracked.start_ts = ts
            tracked.end_ts = ts

    def on_trigger(self, trigger_ts: Optional[float] = None) -> None:
        ts = float(trigger_ts if trigger_ts is not None else time.time())
        with self.lock:
            self.last_trigger_ts = ts
            window_start = ts - self.rolling_window_secs
            window_end = ts + self.rolling_window_secs
            for log_type, tracked_map in self.windows_by_type.items():
                for tracked in tracked_map.values():
                    if not tracked.path.exists():
                        continue
                    start = tracked.start_ts if tracked.start_ts is not None else tracked.path.stat().st_mtime
                    end = tracked.end_ts if tracked.end_ts is not None else tracked.path.stat().st_mtime
                    if end < window_start or start > window_end:
                        continue
                    dst_dir = self.persistent_dir / log_type.value
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    dst_name = f"{tracked.path.stem}.{int(ts)}{tracked.path.suffix}"
                    dst_path = dst_dir / dst_name
                    try:
                        shutil.copy2(tracked.path, dst_path)
                    except Exception as exc:
                        LOG(f"{LOG_PREFIX_MSG_WARNING} Failed to persist trigger-overlap log {tracked.path} -> {dst_path}: {exc}")

    def _get_sort_key(self, path: Path, tracked_map: Dict[Path, _TrackedLogWindow]) -> float:
        tracked = tracked_map.get(path)
        if tracked and tracked.end_ts is not None:
            return tracked.end_ts
        try:
            return path.stat().st_mtime
        except Exception:
            return 0.0

    def build_should_keep(self, log_type: EUtLiveLogType) -> Callable[[List[Path]], List[Tuple[Path, bool]]]:
        def _should_keep(paths: List[Path]) -> List[Tuple[Path, bool]]:
            with self.lock:
                tracked_map = self.windows_by_type.setdefault(log_type, {})
                now = time.time()
                cutoff = now - self.rolling_window_secs
                existing_paths = [Path(p) for p in paths if Path(p).exists()]
                for path in existing_paths:
                    tracked_map.setdefault(path, _TrackedLogWindow(path=path))
                overlap_paths: List[Path] = []
                non_overlap_paths: List[Path] = []
                for path in existing_paths:
                    tracked = tracked_map.get(path)
                    start = tracked.start_ts if tracked and tracked.start_ts is not None else None
                    end = tracked.end_ts if tracked and tracked.end_ts is not None else None
                    if start is None or end is None:
                        sort_key = self._get_sort_key(path, tracked_map)
                        start = sort_key
                        end = sort_key
                    if end >= cutoff:
                        overlap_paths.append(path)
                    else:
                        non_overlap_paths.append(path)
                overlap_paths.sort(key=lambda p: self._get_sort_key(p, tracked_map), reverse=True)
                non_overlap_paths.sort(key=lambda p: self._get_sort_key(p, tracked_map), reverse=True)
                keep_order = overlap_paths + non_overlap_paths
                keep_set = set(keep_order[:self.max_files_per_type])
                return [(path, path in keep_set) for path in existing_paths]
        return _should_keep


def _append_program_log(program_log_path: Path, message: str) -> None:
    program_log_path.parent.mkdir(parents=True, exist_ok=True)
    with program_log_path.open("a", encoding="utf-8") as fp:
        fp.write(f"[{_fmt_now()}] {message}\n")


def _check_batch_stream_error(session: UtLiveLogBatchSession, cycle: int, attempt: int, program_log_path: Path, stage: str) -> bool:
    first_error = session.get_first_error()
    if not first_error:
        return False
    log_type, error = first_error
    message = f"Cycle {cycle} attempt {attempt}: {log_type.value} stream failed ({stage}): {error}"
    LOG(f"{LOG_PREFIX_MSG_ERROR} {message}")
    _append_program_log(program_log_path=program_log_path, message=message)
    return True


def _stop_streams_by_wait_windows(session: UtLiveLogBatchSession, wait_by_type_secs: Dict[EUtLiveLogType, float]) -> None:
    if not wait_by_type_secs:
        return
    grouped: Dict[float, List[EUtLiveLogType]] = {}
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


def _run_one_cycle(cycle: int, attempt: int, target_ip: str, acu_ip: str, tail_lines: int, stream_duration_secs: float, trigger_timeout_secs: int) -> bool:
    cycle_base = _build_cycle_base_dir(target_ip=target_ip, cycle=cycle)
    program_log_path = cycle_base.parent / "time_sync_program.log"
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: started")

    def _copy_cycle_event_dump(event_stage: str) -> None:
        copy_events_db_for_cycle(cycle=cycle, attempt=attempt, target_ip=target_ip, cycle_base=cycle_base, program_log_path=program_log_path, append_program_log_fn=_append_program_log, event_stage=event_stage)

    monitor = _CycleMonitor()
    requested_log_types = [EUtLiveLogType.ACU_E_LOG, EUtLiveLogType.ACU_AIM_MANAGER_LOG, EUtLiveLogType.SSM_GNSS_LOG, EUtLiveLogType.SSM_MM_OWEXT_LOG, EUtLiveLogType.SSM_TIMEINJ_LOG, EUtLiveLogType.SSM_AMC_LOG, EUtLiveLogType.ACU_INS_MONITOR_LOG]
    LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: start streaming {', '.join(item.value for item in requested_log_types)}")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: start streaming {', '.join(item.value for item in requested_log_types)}")
    cycle_log_dir_name = _build_cycle_log_dir_name(cycle=cycle)
    retention = _TimeSyncLiveLogRetention(target_ip=target_ip, cycle_log_dir_name=cycle_log_dir_name)
    handlers_by_type: Dict[EUtLiveLogType, Sequence[logging.Handler]] = {}
    for log_type in requested_log_types:
        log_path = Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / cycle_log_dir_name / f"{log_type.value}.live.log"
        handlers_by_type[log_type] = build_live_log_handlers(output_log_path=str(log_path), log_stream_mode=ELogStreamMode.OverrideSingleFile, should_keep=retention.build_should_keep(log_type), backup_count=64)

    def _on_e_log_line(line: str) -> None:
        retention.on_log_line(EUtLiveLogType.ACU_E_LOG, line)
        was_triggered = monitor.trigger_detected_event.is_set()
        monitor.on_e_log_line(line)
        if not was_triggered and monitor.trigger_detected_event.is_set():
            retention.on_trigger(monitor.trigger_ts)

    def _on_aim_log_line(line: str) -> None:
        retention.on_log_line(EUtLiveLogType.ACU_AIM_MANAGER_LOG, line)

    def _on_ins_log_line(line: str) -> None:
        retention.on_log_line(EUtLiveLogType.ACU_INS_MONITOR_LOG, line)

    def _on_gnss_log_line(line: str) -> None:
        retention.on_log_line(EUtLiveLogType.SSM_GNSS_LOG, line)

    def _on_mm_log_line(line: str) -> None:
        retention.on_log_line(EUtLiveLogType.SSM_MM_OWEXT_LOG, line)

    def _on_timeinj_log_line(line: str) -> None:
        retention.on_log_line(EUtLiveLogType.SSM_TIMEINJ_LOG, line)

    def _on_amc_log_line(line: str) -> None:
        retention.on_log_line(EUtLiveLogType.SSM_AMC_LOG, line)

    session = start_ut_live_log_batch_stream(target_ip=target_ip, acu_ip=acu_ip, log_types=requested_log_types, log_dir_name=cycle_log_dir_name, tail_lines=tail_lines, read_timeout=LIVE_LOG_READ_TIMEOUT_SECS, stream_duration_secs=stream_duration_secs, handlers_by_type=handlers_by_type, on_line_recv_by_type={EUtLiveLogType.ACU_E_LOG: _on_e_log_line, EUtLiveLogType.ACU_AIM_MANAGER_LOG: _on_aim_log_line, EUtLiveLogType.ACU_INS_MONITOR_LOG: _on_ins_log_line, EUtLiveLogType.SSM_GNSS_LOG: _on_gnss_log_line, EUtLiveLogType.SSM_MM_OWEXT_LOG: _on_mm_log_line, EUtLiveLogType.SSM_TIMEINJ_LOG: _on_timeinj_log_line, EUtLiveLogType.SSM_AMC_LOG: _on_amc_log_line}, wait_acu_reachable=True, acu_reachable_wait_timeout_secs=PING_TIMEOUT_AFTER_REBOOT_SECS)

    has_trigger = monitor.trigger_detected_event.wait(timeout=max(1, trigger_timeout_secs))
    if _check_batch_stream_error(session=session, cycle=cycle, attempt=attempt, program_log_path=program_log_path, stage="before trigger handling"):
        session.stop()
        session.join(timeout_per_thread=15.0)
        _copy_cycle_event_dump(event_stage="after stream failure before trigger")
        return False
    if not has_trigger:
        message = f"Cycle {cycle} attempt {attempt}: trigger line not found within {trigger_timeout_secs}s"
        LOG(f"{LOG_PREFIX_MSG_WARNING} {message}")
        _append_program_log(program_log_path=program_log_path, message=message)
        session.stop()
        session.join(timeout_per_thread=15.0)
        _check_batch_stream_error(session=session, cycle=cycle, attempt=attempt, program_log_path=program_log_path, stage="after timeout stop")
        _copy_cycle_event_dump(event_stage="after trigger timeout")
        return False

    with monitor.lock:
        trigger_line = monitor.trigger_line
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: trigger detected in ACU E log. line='{trigger_line}'")
    wait_windows = {
        EUtLiveLogType.ACU_E_LOG: E_LOG_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.ACU_AIM_MANAGER_LOG: AIM_MANAGER_LOG_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.ACU_INS_MONITOR_LOG: INS_MONITOR_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.SSM_GNSS_LOG: GNSS_LOG_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.SSM_MM_OWEXT_LOG: MM_OWEXT_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.SSM_TIMEINJ_LOG: TIMEINJ_LOG_POST_TRIGGER_WAIT_SECS,
        EUtLiveLogType.SSM_AMC_LOG: AMC_LOG_POST_TRIGGER_WAIT_SECS,
    }
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle}: post-trigger wait windows secs = {', '.join(f'{k.value}:{int(v)}' for k, v in wait_windows.items())}")
    _stop_streams_by_wait_windows(session=session, wait_by_type_secs=wait_windows)

    if _check_batch_stream_error(session=session, cycle=cycle, attempt=attempt, program_log_path=program_log_path, stage="after post-trigger stop"):
        _copy_cycle_event_dump(event_stage="after post-trigger stream failure")
        return False
    _copy_cycle_event_dump(event_stage="after cycle log collection")
    _append_program_log(program_log_path=program_log_path, message=f"Cycle {cycle} attempt {attempt}: success")
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Cycle {cycle} attempt {attempt}: success")
    return True


def main() -> int:
    args = parse_args()
    target_ip = _normalize_target_ip(get_arg_value(args, ARG_TARGET_IP))
    acu_ip = get_arg_value(args, ARG_ACU_IP)
    tail_lines = get_arg_value(args, ARG_TAIL_LINES)
    stream_duration_secs = get_arg_value(args, ARG_STREAM_DURATION_SECS)
    trigger_timeout_secs = get_arg_value(args, ARG_TRIGGER_TIMEOUT_SECS)
    wait_between_cycles_secs = get_arg_value(args, ARG_WAIT_BETWEEN_CYCLES_SECS)
    wait_secs_on_fail = get_arg_value(args, ARG_WAIT_SECS_ON_FAIL)
    repeat_count = get_arg_value(args, ARG_REPEAT_COUNT)

    if repeat_count < 1:
        raise ValueError(f"{ARG_REPEAT_COUNT} must be >= 1")
    if stream_duration_secs <= 0:
        raise ValueError(f"{ARG_STREAM_DURATION_SECS} must be > 0")

    cycle, attempt = 1, 1
    while cycle <= repeat_count:
        is_ok = _run_one_cycle(cycle=cycle, attempt=attempt, target_ip=target_ip, acu_ip=acu_ip, tail_lines=tail_lines, stream_duration_secs=stream_duration_secs, trigger_timeout_secs=trigger_timeout_secs)
        if is_ok:
            if cycle < repeat_count:
                LOG(f"{LOG_PREFIX_MSG_INFO} Cycle {cycle}: sleep {wait_between_cycles_secs}s before next cycle")
                time.sleep(max(0, wait_between_cycles_secs))
            cycle += 1
            attempt = 1
            continue
        LOG(f"{LOG_PREFIX_MSG_WARNING} Cycle {cycle} attempt {attempt} failed. Retry same cycle after {wait_secs_on_fail}s")
        time.sleep(max(0, wait_secs_on_fail))
        attempt += 1

    LOG(f"{LOG_PREFIX_MSG_SUCCESS} ESA1W-7316 time sync test flow completed. target_ip={target_ip}, repeat_count={repeat_count}")
    show_noti(title="ESA1W-7316 completed", message=f"target_ip={target_ip}, repeat_count={repeat_count}", no_log_on_success=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
