#!/usr/local/bin/local_python
import argparse
from enum import Enum
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import sys
from typing import Callable, List, Optional, Sequence, Tuple
from dev.dev_common import *
from dev.dev_common.core_independent_utils import read_value_from_credential_file
from dev.dev_common.network_utils import ping_remote_host_via_jump_host
from dev.dev_common.network_utils import stream_live_remote_log
from available_tools.test_tools.test_ut_log.t_get_acu_logs import DEFAULT_LOG_OUTPUT_PATH

ARG_HOST_IP = f"{ARGUMENT_LONG_PREFIX}host_ip"
ARG_JUMP_HOST_IP = f"{ARGUMENT_LONG_PREFIX}jump_host_ip"
ARG_REMOTE_PATH = f"{ARGUMENT_LONG_PREFIX}remote_path"
ARG_USER = f"{ARGUMENT_LONG_PREFIX}user"
ARG_JUMP_USER = f"{ARGUMENT_LONG_PREFIX}jump_user"
ARG_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}timeout"
ARG_READ_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}read_timeout"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_STREAM_DURATION_SECS = f"{ARGUMENT_LONG_PREFIX}stream_duration_secs"
ARG_CAPTURE_LOG_PATH = f"{ARGUMENT_LONG_PREFIX}log_path"
ARG_STREAM_SAME_FILE = f"{ARGUMENT_LONG_PREFIX}stream_same_file"

DEFAULT_GNSS_LOG_PATH = "/var/log/gnss.log"
DEFAULT_INS_MONITOR_LOG_PATH = "/var/log/ins_monitor_log"
DEFAULT_LIVE_LOG_FILENAME = "live.log"
LIVE_LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LIVE_LOG_FILE_BACKUP_COUNT = 5
DEFAULT_REACHABLE_WAIT_SECS = 300


class ELogStreamMode(str, Enum):
    OverrideSingleFile = "OverrideSingleFile"
    CreateNewFile = "CreateNewFile"


class RotateWithDiscardHandler(RotatingFileHandler):
    def __init__(self, log_file: Path, should_keep: Callable[[List[Path]], List[Tuple[Path, bool]]], max_bytes: int = LIVE_LOG_FILE_MAX_BYTES, backup_count: int = LIVE_LOG_FILE_BACKUP_COUNT):
        self._log_file = Path(log_file)
        self._should_keep = should_keep
        self._did_cleanup = False
        super().__init__(str(self._log_file), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")

    def _run_discard_if_needed(self) -> None:
        if self._did_cleanup:
            return
        self._did_cleanup = True
        candidates: List[Path] = [self._log_file]
        candidates.extend(sorted(self._log_file.parent.glob(f"{self._log_file.name}.*")))
        decisions: List[Tuple[Path, bool]] = [(item, True) for item in candidates]
        try:
            decisions = self._should_keep(candidates)
        except Exception as exc:
            LOG(f"{LOG_PREFIX_MSG_WARNING} should_keep callback failed for {self._log_file}: {exc}")
            decisions = [(item, True) for item in candidates]
        keep_map = {Path(path): bool(should_keep) for path, should_keep in decisions}
        for candidate in candidates:
            if keep_map.get(Path(candidate), True):
                continue
            try:
                if candidate.exists():
                    candidate.unlink()
            except Exception as exc:
                LOG(f"{LOG_PREFIX_MSG_WARNING} Failed to discard log file {candidate}: {exc}")

    def close(self) -> None:
        try:
            super().close()
        finally:
            self._run_discard_if_needed()


# Keep the misspelled alias for compatibility with existing user notes/usages.
RotateWithDisacardHandler = RotateWithDiscardHandler


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(name="Tail GNSS live log", extra_description="Direct tail on an SSM host",
                     args={ARG_HOST_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_REMOTE_PATH: DEFAULT_GNSS_LOG_PATH, ARG_STREAM_DURATION_SECS: 60.0}),
        ToolTemplate(name="Tail INS monitor live log", extra_description="Tail ACU log through an SSM jump host",
                     args={ARG_HOST_IP: ACU_IP, ARG_JUMP_HOST_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_REMOTE_PATH: DEFAULT_INS_MONITOR_LOG_PATH, ARG_STREAM_DURATION_SECS: 60.0}),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tail a remote UT log over SSH with optional jump-host forwarding.", formatter_class=argparse.RawTextHelpFormatter)
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_HOST_IP, help="Target host IP to tail on. Use the ACU IP when getting ACU logs.")
    parser.add_argument(ARG_REMOTE_PATH, help="Absolute remote log path to follow.")
    parser.add_argument(ARG_JUMP_HOST_IP, default=None,
                        help="Optional jump host IP. Leave empty for direct SSM logs such as gnss.log.")
    parser.add_argument(ARG_USER, default=SSM_USER, help="SSH user for the target host.")
    parser.add_argument(ARG_JUMP_USER, default=None, help="SSH user for the jump host. Defaults to the target user.")
    parser.add_argument(ARG_TIMEOUT, type=int, default=5, help="SSH connect timeout in seconds.")
    parser.add_argument(ARG_READ_TIMEOUT, type=int, default=600,
                        help="Fail if no log data arrives within this many seconds.")
    parser.add_argument(ARG_TAIL_LINES, type=int, default=0,
                        help="Initial number of historical lines to print before following.")
    parser.add_argument(ARG_STREAM_DURATION_SECS, type=float, default=0.0,
                        help="Stop streaming after this many seconds. Use 0 to stream until interrupted.")
    parser.add_argument(ARG_CAPTURE_LOG_PATH, default=None,
                        help="Optional local output log path. Auto-generated when omitted.")
    parser.add_argument(ARG_STREAM_SAME_FILE, type=lambda value: str(value).lower() in {"1", "true", "t", "yes", "y"}, default=True,
                        help="Write to same file (True, default) or create timestamped file path (False).")
    return parser.parse_args()


def _get_log_stream_mode(stream_same_file: bool) -> ELogStreamMode:
    return ELogStreamMode.OverrideSingleFile if stream_same_file else ELogStreamMode.CreateNewFile


def _build_default_capture_path(host_ip: str, jump_host_ip: Optional[str], remote_log_path: str) -> Path:
    target_ip = jump_host_ip or host_ip
    log_name = Path(remote_log_path).name or DEFAULT_LIVE_LOG_FILENAME
    return Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / f"{log_name}.live.log"


def _resolve_capture_path_by_mode(log_path: str, log_stream_mode: ELogStreamMode) -> Path:
    base_log_path = Path(log_path)
    if log_stream_mode == ELogStreamMode.OverrideSingleFile:
        return base_log_path
    return base_log_path.parent / base_log_path.stem / get_file_timestamp() / base_log_path.name


def close_live_log_handlers(handlers: Sequence[logging.Handler]) -> None:
    for handler in handlers:
        try:
            handler.flush()
            handler.close()
        except Exception:
            pass


def start_stop_timer(stream_duration_secs: float, stop_event: threading.Event) -> Optional[threading.Timer]:
    if stream_duration_secs < 0:
        raise ValueError(f"{ARG_STREAM_DURATION_SECS} must be >= 0")
    if stream_duration_secs == 0:
        return None
    stop_timer = threading.Timer(stream_duration_secs, stop_event.set)
    stop_timer.daemon = True
    stop_timer.start()
    return stop_timer


def build_live_log_handlers(output_log_path: str, log_stream_mode: ELogStreamMode = ELogStreamMode.OverrideSingleFile,
                            should_keep: Optional[Callable[[List[Path]], List[Tuple[Path, bool]]]] = None,
                            max_bytes: int = LIVE_LOG_FILE_MAX_BYTES, backup_count: int = LIVE_LOG_FILE_BACKUP_COUNT) -> List[logging.Handler]:
    """Handle where to send live log messages (file + rotation)"""
    resolved_log_path = _resolve_capture_path_by_mode(log_path=output_log_path, log_stream_mode=log_stream_mode)
    LOG(f"{LOG_PREFIX_MSG_INFO} Build live log handlers. log_path={resolved_log_path}, mode={log_stream_mode.value}")
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    log_file = resolved_log_path
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if log_stream_mode == ELogStreamMode.OverrideSingleFile:
        with open(log_file, "w", encoding="utf-8") as file_obj:
            file_obj.write("")
    if should_keep is None:
        handlers.append(RotatingFileHandler(log_file, maxBytes=max_bytes,
                        backupCount=backup_count, encoding="utf-8"))
    else:
        handlers.append(RotateWithDiscardHandler(log_file=log_file, should_keep=should_keep,
                        max_bytes=max_bytes, backup_count=backup_count))
    for handler in handlers:
        handler.setFormatter(logging.Formatter("%(message)s"))
    return handlers


def stream_live_remote_log_to_file(host_ip: str, remote_log_path: str, user: str = SSM_USER, password: Optional[str] = None, jump_host_ip: Optional[str] = None,
                        jump_user: Optional[str] = None, jump_password: Optional[str] = None, timeout: int = 5, read_timeout: int = 60, tail_lines: int = 0,
                        handlers: Optional[Sequence[logging.Handler]] = None,
                        on_line_recv: Optional[Callable[[str], None]] = None, stop_event: Optional[threading.Event] = None) -> None:
    password = password or read_value_from_credential_file(CREDENTIALS_FILE_PATH, UT_PWD_KEY_NAME)
    if not password:
        raise ValueError(f"Missing UT password in {CREDENTIALS_FILE_PATH} with key {UT_PWD_KEY_NAME}")
    resolved_jump_user = jump_user or user
    resolved_jump_password = jump_password or password
    is_reachable = ping_remote_host_via_jump_host( remote_host_ip=host_ip, jump_host_ip=jump_host_ip, jump_user=resolved_jump_user, jump_password=resolved_jump_password, max_wait_sec=DEFAULT_REACHABLE_WAIT_SECS, retry_interval_sec=5.0, ping_count=1, ping_timeout_sec=2, ssh_timeout_sec=10, check_jump_host_reachable=True, mute=False, )
    if not is_reachable:
        via_text = f" via jump host {jump_host_ip}" if jump_host_ip else EMPTY_STR_VALUE
        raise RuntimeError(f"{host_ip} is not reachable{via_text} within {DEFAULT_REACHABLE_WAIT_SECS}s")
    owns_handlers = handlers is None
    resolved_handlers: List[logging.Handler] = list(handlers) if handlers else [logging.StreamHandler(sys.stdout)]
    for handler in resolved_handlers:
        if handler.formatter is None:
            handler.setFormatter(logging.Formatter("%(message)s"))
    effective_stop_event = stop_event or threading.Event()
    def _on_line(line: str) -> None:
        if on_line_recv:
            on_line_recv(line)
        LOG(line, show_time=True, handlers=resolved_handlers)
    try:
        stream_live_remote_log(host_ip=host_ip, user=user, password=password, remote_log_path=remote_log_path, connect_timeout=timeout, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=resolved_jump_password, tail_lines=tail_lines, read_timeout=read_timeout, stop_event=effective_stop_event, on_line=_on_line)
    finally:
        if owns_handlers:
            close_live_log_handlers(resolved_handlers)


def main() -> int:
    args = parse_args()
    resolved_log_path = args.log_path or str(_build_default_capture_path(host_ip=args.host_ip, jump_host_ip=args.jump_host_ip, remote_log_path=args.remote_path))
    LOG(f"{LOG_PREFIX_MSG_INFO} Capture live log to {resolved_log_path}")
    handlers = build_live_log_handlers(output_log_path=resolved_log_path, log_stream_mode=_get_log_stream_mode(args.stream_same_file))
    stop_event = threading.Event()
    stop_timer: Optional[threading.Timer] = None
    try:
        stop_timer = start_stop_timer(stream_duration_secs=args.stream_duration_secs, stop_event=stop_event)
        stream_live_remote_log_to_file(host_ip=args.host_ip, remote_log_path=args.remote_path, user=args.user, jump_host_ip=args.jump_host_ip,
                                       jump_user=args.jump_user, timeout=args.timeout, read_timeout=args.read_timeout, tail_lines=args.tail_lines,
                                       handlers=handlers, stop_event=stop_event)
    except KeyboardInterrupt:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Stopped by user.")
        return 130
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to stream '{args.remote_path}' from {args.host_ip}: {exc}")
        return 1
    finally:
        if stop_timer:
            stop_timer.cancel()
        close_live_log_handlers(handlers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
