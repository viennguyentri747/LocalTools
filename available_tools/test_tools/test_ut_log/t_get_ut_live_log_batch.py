#!/usr/local/bin/local_python
import argparse
import fnmatch
import logging
import re
import shlex
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from available_tools.test_tools.test_ut_log.t_get_acu_logs import DEFAULT_LOG_OUTPUT_PATH
from available_tools.test_tools.test_ut_log.t_get_ut_live_log import ELogStreamMode, build_live_log_handlers, close_live_log_handlers, stream_live_remote_log_to_file
from dev.dev_common import *
from dev.dev_common.custom_structures import ToolData
from dev.dev_common.network_utils import ELineType, ping_remote_host_via_jump_host
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog

ARG_TARGET_IP = f"{ARGUMENT_LONG_PREFIX}target_ip"
ARG_ACU_IP = f"{ARGUMENT_LONG_PREFIX}acu_ip"
ARG_LOG_TYPES = f"{ARGUMENT_LONG_PREFIX}log_types"
ARG_LOG_DIR_NAME = f"{ARGUMENT_LONG_PREFIX}log_dir_name"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_READ_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}read_timeout"
ARG_STREAM_DURATION_SECS = f"{ARGUMENT_LONG_PREFIX}stream_duration_secs"
ARG_WAIT_ACU_REACHABLE = f"{ARGUMENT_LONG_PREFIX}wait_acu_reachable"
ARG_ACU_REACHABLE_WAIT_TIMEOUT_SECS = f"{ARGUMENT_LONG_PREFIX}acu_reachable_wait_timeout_secs"
ARG_STREAM_SAME_FILE = f"{ARGUMENT_LONG_PREFIX}stream_same_file"

DEFAULT_LOG_DIR_NAME = "TEMPORARY"
DEFAULT_STREAM_DURATION_SECS = 60.0
DEFAULT_ACU_REACHABLE_WAIT_TIMEOUT_SECS = 300
LOG_TARGET_PREFIX_SSM = "ssm_"
LOG_TARGET_PREFIX_ACU = "acu_"


class EUtLiveLogType(str, Enum):
    SSM_GNSS_LOG = "ssm_gnss_log"
    SSM_MM_OWEXT_LOG = "ssm_mm_owext_log"
    SSM_TIMEINJ_LOG = "ssm_timeinj_log"
    SSM_AMC_LOG = "ssm_amc_log"
    SSM_E_LOG = "ssm_e_log"
    SSM_P_LOG = "ssm_p_log"
    ACU_E_LOG = "acu_e_log"
    ACU_AIM_MANAGER_LOG = "acu_aim_manager_log"
    ACU_INS_LOG = "acu_ins_log"
    ACU_INS_MONITOR_LOG = "acu_ins_monitor_log"

    @classmethod
    def from_value(cls, value: Union[str, "EUtLiveLogType"]) -> "EUtLiveLogType":
        if isinstance(value, cls):
            return cls.ACU_INS_MONITOR_LOG if value == cls.ACU_INS_LOG else value
        normalized = (value or "").strip().lower()
        if normalized == cls.ACU_INS_LOG.value:
            return cls.ACU_INS_MONITOR_LOG
        for candidate in cls:
            if candidate.value == normalized:
                return candidate
        raise ValueError(f"Unsupported log type '{value}'. Supported: {', '.join(item.value for item in cls)}")

    def get_target_prefix(self) -> str:
        return LOG_TARGET_PREFIX_ACU if self.value.startswith(LOG_TARGET_PREFIX_ACU) else LOG_TARGET_PREFIX_SSM

    def get_remote_log_path_pattern(self) -> str:
        if self == EUtLiveLogType.SSM_GNSS_LOG:
            return "/var/log/gnss.log"
        if self == EUtLiveLogType.SSM_MM_OWEXT_LOG:
            return "/var/log/mm_owext.log"
        if self == EUtLiveLogType.SSM_TIMEINJ_LOG:
            return "/var/log/mm_timeinj.log"
        if self == EUtLiveLogType.SSM_AMC_LOG:
            return "/var/log/amc.log"
        if self == EUtLiveLogType.SSM_E_LOG:
            return "/var/log/E*"
        if self == EUtLiveLogType.SSM_P_LOG:
            return "/var/log/P*"
        if self == EUtLiveLogType.ACU_E_LOG:
            return "/var/log/E*"
        if self == EUtLiveLogType.ACU_AIM_MANAGER_LOG:
            return "/var/log/aim_manager.log"
        if self in {EUtLiveLogType.ACU_INS_LOG, EUtLiveLogType.ACU_INS_MONITOR_LOG}:
            return "/var/log/ins_monitor_log"
        raise ValueError(f"No remote log path pattern mapped for {self.value}")


@dataclass(frozen=True)
class UtLiveLogRoute:
    host_ip: str
    jump_host_ip: Optional[str]
    remote_log_path: str


@dataclass
class UtLiveLogStreamHandle:
    log_type: EUtLiveLogType
    log_path: Path
    stop_event: threading.Event
    thread: threading.Thread
    errors: List[BaseException]


@dataclass
class UtLiveLogBatchSession:
    stop_event: threading.Event
    streams: Dict[EUtLiveLogType, UtLiveLogStreamHandle]
    stop_timer: Optional[threading.Timer] = None

    def stop(self, log_types: Optional[Sequence[Union[str, EUtLiveLogType]]] = None) -> None:
        if self.stop_timer and log_types is None:
            self.stop_timer.cancel()
            self.stop_timer = None
        if log_types is None:
            self.stop_event.set()
            for handle in self.streams.values():
                handle.stop_event.set()
            return
        for raw_type in log_types:
            log_type = EUtLiveLogType.from_value(raw_type)
            handle = self.streams.get(log_type)
            if handle:
                handle.stop_event.set()

    def join(self, timeout_per_thread: Optional[float] = None, log_types: Optional[Sequence[Union[str, EUtLiveLogType]]] = None) -> None:
        handles = self.streams.values() if log_types is None else [self.streams[item] for item in normalize_live_log_types(log_types) if item in self.streams]
        for handle in handles:
            handle.thread.join(timeout=timeout_per_thread)
        if log_types is None and self.stop_timer and not any(item.thread.is_alive() for item in self.streams.values()):
            self.stop_timer.cancel()
            self.stop_timer = None

    def get_first_error(self) -> Optional[Tuple[EUtLiveLogType, BaseException]]:
        for log_type, handle in self.streams.items():
            if handle.errors:
                return log_type, handle.errors[0]
        return None

    def get_log_paths(self) -> Dict[EUtLiveLogType, Path]:
        return {log_type: handle.log_path for log_type, handle in self.streams.items()}


def getToolData() -> ToolData:
    tool_templates = [
        ToolTemplate(name="Stream GNSS + INS monitor", extra_description="Route SSM logs directly and ACU logs via jump host automatically.", args={ARG_TARGET_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_ACU_IP: ACU_IP, ARG_LOG_TYPES: [EUtLiveLogType.SSM_GNSS_LOG.value, EUtLiveLogType.ACU_INS_MONITOR_LOG.value], ARG_LOG_DIR_NAME: DEFAULT_LOG_DIR_NAME, ARG_STREAM_DURATION_SECS: DEFAULT_STREAM_DURATION_SECS}),
    ]
    return ToolData(tool_templates=tool_templates, tool_priority=EToolPriority.Level10_Last, hidden=False)



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream multiple UT live logs with enum-based routing (acu_/ssm_ prefix).", formatter_class=argparse.RawTextHelpFormatter)
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))
    parser.add_argument(ARG_TARGET_IP, required=True, help="UT/SSM target IP. Accepts full IP or last octet.")
    parser.add_argument(ARG_ACU_IP, default=ACU_IP, help=f"ACU IP (default: {ACU_IP}).")
    parser.add_argument(ARG_LOG_TYPES, nargs="+", required=True, choices=[item.value for item in EUtLiveLogType], help="Live log types. Prefix decides route: ssm_* direct, acu_* via jump host.")
    parser.add_argument(ARG_LOG_DIR_NAME, default=DEFAULT_LOG_DIR_NAME, help=f"Subdir under DEFAULT_LOG_OUTPUT_PATH/<target_ip>/ (default: {DEFAULT_LOG_DIR_NAME}).")
    parser.add_argument(ARG_TAIL_LINES, type=int, default=0, help="Initial history lines to print before follow mode.")
    parser.add_argument(ARG_READ_TIMEOUT, type=int, default=600, help="Fail if no data received within this many seconds.")
    parser.add_argument(ARG_STREAM_DURATION_SECS, type=float, default=DEFAULT_STREAM_DURATION_SECS, help=f"Auto-stop after this many seconds (default: {DEFAULT_STREAM_DURATION_SECS}).")
    parser.add_argument(ARG_WAIT_ACU_REACHABLE, type=lambda value: str(value).lower() in {"1", "true", "t", "yes", "y"}, default=True, help="For acu_* logs, wait for ACU reachability via jump host before streaming.")
    parser.add_argument(ARG_ACU_REACHABLE_WAIT_TIMEOUT_SECS, type=int, default=DEFAULT_ACU_REACHABLE_WAIT_TIMEOUT_SECS, help=f"Max wait for ACU reachability via jump host (default: {DEFAULT_ACU_REACHABLE_WAIT_TIMEOUT_SECS}).")
    parser.add_argument(ARG_STREAM_SAME_FILE, type=lambda value: str(value).lower() in {"1", "true", "t", "yes", "y"}, default=True, help="Write to same file (True) or create timestamped file path (False).")
    return parser.parse_args()


def _normalize_target_ip(target_ip: str) -> str:
    value = (target_ip or "").strip()
    if value.count(".") == 3:
        return value
    if value.isdigit():
        return f"{SSM_NORMAL_IP_PREFIX}.{int(value)}"
    raise ValueError(f"Invalid target_ip '{target_ip}'. Use full IP or last octet.")


def normalize_live_log_types(log_types: Sequence[Union[str, EUtLiveLogType]]) -> List[EUtLiveLogType]:
    normalized: List[EUtLiveLogType] = []
    seen: set[EUtLiveLogType] = set()
    for raw_type in log_types:
        log_type = EUtLiveLogType.from_value(raw_type)
        if log_type in seen:
            continue
        seen.add(log_type)
        normalized.append(log_type)
    return normalized


def resolve_live_log_route(log_type: EUtLiveLogType, target_ip: str, acu_ip: str) -> UtLiveLogRoute:
    if log_type.get_target_prefix() == LOG_TARGET_PREFIX_SSM:
        return UtLiveLogRoute(host_ip=target_ip, jump_host_ip=None, remote_log_path=log_type.get_remote_log_path_pattern())
    if log_type.get_target_prefix() == LOG_TARGET_PREFIX_ACU:
        return UtLiveLogRoute(host_ip=acu_ip, jump_host_ip=target_ip, remote_log_path=log_type.get_remote_log_path_pattern())
    raise ValueError(f"Unsupported log type prefix for {log_type.value}. Expected {LOG_TARGET_PREFIX_ACU} or {LOG_TARGET_PREFIX_SSM}.")


def build_live_log_output_path(target_ip: str, log_type: EUtLiveLogType, log_dir_name: str = DEFAULT_LOG_DIR_NAME) -> Path:
    safe_dir = (log_dir_name or DEFAULT_LOG_DIR_NAME).strip() or DEFAULT_LOG_DIR_NAME
    return Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / safe_dir / f"{log_type.value}.live.log"


def _build_live_log_stream_mode(stream_same_file: bool) -> ELogStreamMode:
    return ELogStreamMode.OverrideSingleFile if stream_same_file else ELogStreamMode.CreateNewFile


def _resolve_remote_log_path_pattern(host_ip: str, user: str, password: str, remote_path_pattern: str, jump_host_ip: Optional[str], jump_user: Optional[str], jump_password: Optional[str], timeout: int = 20) -> str:
    pattern = (remote_path_pattern or "").strip()
    if not pattern:
        raise ValueError("remote_path_pattern is empty")
    if not any(token in pattern for token in ["*", "?", "["]):
        return pattern

    remote_dir = str(Path(pattern).parent).strip() or "/"
    filename_pattern = Path(pattern).name
    filename_regex = re.compile(fnmatch.translate(filename_pattern))
    find_cmd = f"find {shlex.quote(remote_dir)} -maxdepth 1 -type f -printf '%T@ %p\\n' 2>/dev/null | sort -nr"
    stdout, stderr = run_ssh_command(host_ip=host_ip, user=user, password=password, command=find_cmd, timeout=timeout, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
    if stderr.strip():
        LOG(f"{LOG_PREFIX_MSG_WARNING} Pattern resolve stderr for '{pattern}' on {host_ip}: {stderr.strip()}")
    for raw_line in (stdout or "").splitlines():
        line = raw_line.strip()
        if not line or " " not in line:
            continue
        _, remote_path = line.split(" ", 1)
        candidate = remote_path.strip()
        if filename_regex.fullmatch(Path(candidate).name):
            LOG(f"{LOG_PREFIX_MSG_INFO} Pattern '{pattern}' resolved to '{candidate}' on {host_ip}")
            return candidate
    raise RuntimeError(f"No remote file matched pattern '{pattern}' on {host_ip}")


def _start_batch_stream(log_type: EUtLiveLogType, route: UtLiveLogRoute, log_path: Path, handlers: Sequence[logging.Handler], tail_lines: int, read_timeout: int, on_line_recv_single: Optional[Callable[[str, ELineType], None]], stop_event: threading.Event, wait_acu_reachable: bool, acu_reachable_wait_timeout_secs: int) -> UtLiveLogStreamHandle:
    errors: List[BaseException] = []

    def _stream_on_line(line: str, line_type: ELineType) -> None:
        if on_line_recv_single:
            on_line_recv_single(line, line_type)

    def _run() -> None:
        try:
            should_wait_acu = wait_acu_reachable and log_type.get_target_prefix() == LOG_TARGET_PREFIX_ACU and bool(route.jump_host_ip)
            if should_wait_acu:
                is_reachable = ping_remote_host_via_jump_host(remote_host_ip=route.host_ip, jump_host_ip=route.jump_host_ip, jump_user=SSM_USER, jump_password=get_ssm_password(), max_wait_sec=max(1, int(acu_reachable_wait_timeout_secs)), retry_interval_sec=5.0, ping_count=1, ping_timeout_sec=2, ssh_timeout_sec=10, check_jump_host_reachable=True, mute=False)
                if not is_reachable:
                    raise RuntimeError(f"ACU {route.host_ip} is not reachable via jump host {route.jump_host_ip} within {acu_reachable_wait_timeout_secs}s")
            resolved_remote_path = _resolve_remote_log_path_pattern(host_ip=route.host_ip, user=SSM_USER, password=get_ssm_password(), remote_path_pattern=route.remote_log_path, jump_host_ip=route.jump_host_ip, jump_user=SSM_USER, jump_password=get_ssm_password())
            stream_live_remote_log_to_file(host_ip=route.host_ip, remote_log_path=resolved_remote_path, jump_host_ip=route.jump_host_ip, read_timeout=max(1, int(read_timeout)), tail_lines=tail_lines, handlers=handlers, on_line_recv=_stream_on_line, stop_event=stop_event)
        except BaseException as exc:
            errors.append(exc)
        finally:
            close_live_log_handlers(handlers)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return UtLiveLogStreamHandle(log_type=log_type, log_path=log_path, stop_event=stop_event, thread=thread, errors=errors)


def start_ut_live_log_batch_stream(target_ip: str, acu_ip: str, log_types: Sequence[Union[str, EUtLiveLogType]], log_dir_name: str = DEFAULT_LOG_DIR_NAME,
                                   tail_lines: int = 0, read_timeout: int = 600, stream_duration_secs: float = DEFAULT_STREAM_DURATION_SECS,
                                   handlers_by_type: Optional[Dict[Union[str, EUtLiveLogType], Sequence[logging.Handler]]] = None,
                                   on_line_recv_by_type: Optional[Dict[Union[str, EUtLiveLogType], Callable[[str, ELineType], None]]] = None,
                                   stop_event: Optional[threading.Event] = None,
                                   wait_acu_reachable: bool = True,
                                   acu_reachable_wait_timeout_secs: int = DEFAULT_ACU_REACHABLE_WAIT_TIMEOUT_SECS) -> UtLiveLogBatchSession:
    if stream_duration_secs < 0:
        raise ValueError(f"{ARG_STREAM_DURATION_SECS} must be >= 0")
    normalized_target_ip = _normalize_target_ip(target_ip)
    normalized_types = normalize_live_log_types(log_types)
    if not normalized_types:
        raise ValueError("No log types requested")
    if not handlers_by_type:
        raise ValueError("handlers_by_type is required. Caller must build and pass handlers for each requested log type.")

    per_type_cb: Dict[EUtLiveLogType, Callable[[str, ELineType], None]] = {}
    if on_line_recv_by_type:
        for raw_log_type, callback in on_line_recv_by_type.items():
            per_type_cb[EUtLiveLogType.from_value(raw_log_type)] = callback
    per_type_handlers: Dict[EUtLiveLogType, Sequence[logging.Handler]] = {}
    for raw_log_type, handlers in handlers_by_type.items():
        normalized_type = EUtLiveLogType.from_value(raw_log_type)
        if not handlers:
            raise ValueError(f"handlers_by_type for {normalized_type.value} is empty")
        per_type_handlers[normalized_type] = handlers

    batch_stop_event = stop_event or threading.Event()
    streams: Dict[EUtLiveLogType, UtLiveLogStreamHandle] = {}
    for log_type in normalized_types:
        stream_handlers = per_type_handlers.get(log_type)
        if not stream_handlers:
            raise ValueError(f"Missing handlers for requested log type: {log_type.value}")
        route = resolve_live_log_route(log_type=log_type, target_ip=normalized_target_ip, acu_ip=acu_ip)
        output_path = build_live_log_output_path(target_ip=normalized_target_ip, log_type=log_type, log_dir_name=log_dir_name)
        stream_stop_event = batch_stop_event if stop_event is not None else threading.Event()
        stream_handle = _start_batch_stream(log_type=log_type, route=route, log_path=output_path, handlers=stream_handlers, tail_lines=tail_lines, read_timeout=read_timeout,
                                                  on_line_recv_single=per_type_cb.get(log_type), stop_event=stream_stop_event,
                                                  wait_acu_reachable=wait_acu_reachable, acu_reachable_wait_timeout_secs=acu_reachable_wait_timeout_secs)
        streams[log_type] = stream_handle

    session = UtLiveLogBatchSession(stop_event=batch_stop_event, streams=streams)
    if stream_duration_secs > 0:
        stop_timer = threading.Timer(stream_duration_secs, session.stop)
        stop_timer.daemon = True
        stop_timer.start()
        session.stop_timer = stop_timer
    return session


def main() -> int:
    args = parse_args()
    target_ip = get_arg_value(args, ARG_TARGET_IP)
    normalized_target_ip = _normalize_target_ip(target_ip)
    acu_ip = get_arg_value(args, ARG_ACU_IP)
    log_types: List[str] = get_arg_value(args, ARG_LOG_TYPES)
    log_dir_name = get_arg_value(args, ARG_LOG_DIR_NAME)
    output_dir = Path(DEFAULT_LOG_OUTPUT_PATH) / normalized_target_ip / ((log_dir_name or DEFAULT_LOG_DIR_NAME).strip() or DEFAULT_LOG_DIR_NAME)
    tail_lines = get_arg_value(args, ARG_TAIL_LINES)
    read_timeout = get_arg_value(args, ARG_READ_TIMEOUT)
    stream_duration_secs = get_arg_value(args, ARG_STREAM_DURATION_SECS)
    wait_acu_reachable = get_arg_value(args, ARG_WAIT_ACU_REACHABLE)
    acu_reachable_wait_timeout_secs = get_arg_value(args, ARG_ACU_REACHABLE_WAIT_TIMEOUT_SECS)
    stream_same_file = get_arg_value(args, ARG_STREAM_SAME_FILE)
    log_stream_mode = _build_live_log_stream_mode(stream_same_file)

    try:
        handlers_by_type: Dict[EUtLiveLogType, Sequence[logging.Handler]] = {}
        for log_type in normalize_live_log_types(log_types):
            output_path = build_live_log_output_path(target_ip=normalized_target_ip, log_type=log_type, log_dir_name=log_dir_name)
            handlers_by_type[log_type] = build_live_log_handlers(output_log_path=str(output_path), log_stream_mode=log_stream_mode)
        session = start_ut_live_log_batch_stream(target_ip=target_ip, acu_ip=acu_ip, log_types=log_types, log_dir_name=log_dir_name, tail_lines=tail_lines,
                                                 read_timeout=read_timeout, stream_duration_secs=stream_duration_secs,
                                                 handlers_by_type=handlers_by_type, wait_acu_reachable=wait_acu_reachable,
                                                 acu_reachable_wait_timeout_secs=acu_reachable_wait_timeout_secs)
        session.join(timeout_per_thread=None)
        first_error = session.get_first_error()
        if first_error:
            log_type, error = first_error
            LOG(f"{LOG_PREFIX_MSG_ERROR} Live log stream failed for {log_type.value}: {error}")
            return 1
        for log_type, log_path in session.get_log_paths().items():
            LOG(f"{LOG_PREFIX_MSG_SUCCESS} {log_type.value} captured at {log_path}")
    except KeyboardInterrupt:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Stopped by user.")
        return 130
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to stream UT live logs: {exc}")
        return 1
    has_non_empty_artifact = output_dir.exists() and any(path.is_file() and path.stat().st_size > 0 for path in output_dir.rglob("*.live.log"))
    if has_non_empty_artifact:
        open_directory_in_explorer(output_dir)
    else:
        LOG_ISSUE(f"No live-log artifacts generated under {format_path_for_display(output_dir)}; skipping Explorer open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
