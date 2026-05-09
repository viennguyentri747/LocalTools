#!/usr/local/bin/local_python
import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import sys
from typing import List, Optional
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

DEFAULT_GNSS_LOG_PATH = "/var/log/gnss.log"
DEFAULT_INS_MONITOR_LOG_PATH = "/var/log/ins_monitor_log"
DEFAULT_LIVE_LOG_FILENAME = "live.log"
LIVE_LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LIVE_LOG_FILE_BACKUP_COUNT = 5
DEFAULT_REACHABLE_WAIT_SECS = 300


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(name="Tail GNSS log", extra_description="Direct tail on an SSM host",
                     args={ARG_HOST_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_REMOTE_PATH: DEFAULT_GNSS_LOG_PATH, ARG_STREAM_DURATION_SECS: 60.0}),
        ToolTemplate(name="Tail INS monitor log", extra_description="Tail ACU log through an SSM jump host",
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
    return parser.parse_args()


def _build_default_capture_path(host_ip: str, jump_host_ip: Optional[str], remote_log_path: str) -> Path:
    target_ip = jump_host_ip or host_ip
    log_name = Path(remote_log_path).name or DEFAULT_LIVE_LOG_FILENAME
    return Path(DEFAULT_LOG_OUTPUT_PATH) / target_ip / f"{log_name}.live.log"


def build_live_log_handlers(log_path: str, should_clear_log_first: bool = True) -> List[logging.Handler]:
    """Handle where to send live log messages (file + rotation)"""
    LOG(f"{LOG_PREFIX_MSG_INFO} Build live log handlers. log_path={log_path}")
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if should_clear_log_first:
        with open(log_file, "w", encoding="utf-8") as file_obj:
            file_obj.write("")
    handlers.append(RotatingFileHandler(log_file, maxBytes=LIVE_LOG_FILE_MAX_BYTES,
                    backupCount=LIVE_LOG_FILE_BACKUP_COUNT))
    for handler in handlers:
        handler.setFormatter(logging.Formatter("%(message)s"))
    return handlers


def stream_live_remote_log_to_file(host_ip: str, remote_log_path: str, user: str = SSM_USER, password: Optional[str] = None, jump_host_ip: Optional[str] = None,
                        jump_user: Optional[str] = None, jump_password: Optional[str] = None, timeout: int = 5, read_timeout: int = 60, tail_lines: int = 0,
                        stream_duration_secs: float = 0.0, log_path: Optional[str] = None, should_clear_log_first: bool = True) -> None:
    password = password or read_value_from_credential_file(CREDENTIALS_FILE_PATH, UT_PWD_KEY_NAME)
    if not password:
        raise ValueError(f"Missing UT password in {CREDENTIALS_FILE_PATH} with key {UT_PWD_KEY_NAME}")
    resolved_jump_user = jump_user or user
    resolved_jump_password = jump_password or password
    is_reachable = ping_remote_host_via_jump_host(
        remote_host_ip=host_ip,
        jump_host_ip=jump_host_ip,
        jump_user=resolved_jump_user,
        jump_password=resolved_jump_password,
        max_wait_sec=DEFAULT_REACHABLE_WAIT_SECS,
        retry_interval_sec=5.0,
        ping_count=1,
        ping_timeout_sec=2,
        ssh_timeout_sec=10,
        check_jump_host_reachable=True,
        mute=False,
    )
    if not is_reachable:
        via_text = f" via jump host {jump_host_ip}" if jump_host_ip else EMPTY_STR_VALUE
        raise RuntimeError(f"{host_ip} is not reachable{via_text} within {DEFAULT_REACHABLE_WAIT_SECS}s")
    resolved_log_path = log_path or str(_build_default_capture_path(host_ip=host_ip, jump_host_ip=jump_host_ip, remote_log_path=remote_log_path))
    LOG(f"{LOG_PREFIX_MSG_INFO} Capture live log to {resolved_log_path}")
    handlers = build_live_log_handlers(log_path=resolved_log_path, should_clear_log_first=should_clear_log_first)
    stop_event = threading.Event()
    stop_timer: Optional[threading.Timer] = None
    if stream_duration_secs < 0:
        raise ValueError(f"{ARG_STREAM_DURATION_SECS} must be >= 0")
    if stream_duration_secs > 0:
        stop_timer = threading.Timer(stream_duration_secs, stop_event.set)
        stop_timer.daemon = True
        stop_timer.start()
    try:
        stream_live_remote_log(host_ip=host_ip, user=user, password=password, remote_log_path=remote_log_path, timeout=timeout, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=resolved_jump_password, tail_lines=tail_lines, read_timeout=read_timeout, stop_event=stop_event, on_line=lambda line: LOG(line, show_time=True, handlers=handlers))
    finally:
        if stop_timer:
            stop_timer.cancel()
        for handler in handlers:
            try:
                handler.flush()
                handler.close()
            except Exception:
                pass


def main() -> int:
    args = parse_args()
    try:
        stream_live_remote_log_to_file(host_ip=args.host_ip, remote_log_path=args.remote_path, user=args.user, jump_host_ip=args.jump_host_ip, jump_user=args.jump_user, timeout=args.timeout,
                            read_timeout=args.read_timeout, tail_lines=args.tail_lines, stream_duration_secs=args.stream_duration_secs, log_path=args.log_path)
    except KeyboardInterrupt:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Stopped by user.")
        return 130
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to stream '{args.remote_path}' from {args.host_ip}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
