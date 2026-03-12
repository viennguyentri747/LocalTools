#!/usr/local/bin/local_python
import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from typing import List, Optional
from dev.dev_common import *
from dev.dev_common.core_independent_utils import read_value_from_credential_file
from dev.dev_common.network_utils import get_live_remote_log as stream_live_remote_log

ARG_HOST_IP = f"{ARGUMENT_LONG_PREFIX}host_ip"
ARG_JUMP_HOST_IP = f"{ARGUMENT_LONG_PREFIX}jump_host_ip"
ARG_REMOTE_PATH = f"{ARGUMENT_LONG_PREFIX}remote_path"
ARG_USER = f"{ARGUMENT_LONG_PREFIX}user"
ARG_JUMP_USER = f"{ARGUMENT_LONG_PREFIX}jump_user"
ARG_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}timeout"
ARG_READ_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}read_timeout"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_CAPTURE_LOG = f"{ARGUMENT_LONG_PREFIX}capture_log"
ARG_CAPTURE_LOG_PATH = f"{ARGUMENT_LONG_PREFIX}log_path"

DEFAULT_GNSS_LOG_PATH = "/var/log/gnss.log"
DEFAULT_INS_MONITOR_LOG_PATH = "/var/log/ins_monitor_log"
DEFAULT_GNSS_CAPTURE_LOG_PATH = str(PERSISTENT_TEMP_PATH / "live_logs" / "gnss_57.log")
DEFAULT_INS_CAPTURE_LOG_PATH = str(PERSISTENT_TEMP_PATH / "live_logs" / "ins_monitor_57.log")
LIVE_LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LIVE_LOG_FILE_BACKUP_COUNT = 5


def parse_bool_arg(value) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(name="Tail GNSS log", extra_description="Direct tail on an SSM host",
                     args={ARG_HOST_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_REMOTE_PATH: DEFAULT_GNSS_LOG_PATH, ARG_CAPTURE_LOG: True, ARG_CAPTURE_LOG_PATH: DEFAULT_GNSS_CAPTURE_LOG_PATH}),
        ToolTemplate(name="Tail INS monitor log", extra_description="Tail ACU log through an SSM jump host",
                     args={ARG_HOST_IP: ACU_IP, ARG_JUMP_HOST_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_REMOTE_PATH: DEFAULT_INS_MONITOR_LOG_PATH, ARG_CAPTURE_LOG: True, ARG_CAPTURE_LOG_PATH: DEFAULT_INS_CAPTURE_LOG_PATH}),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tail a remote UT log over SSH with optional jump-host forwarding.", formatter_class=argparse.RawTextHelpFormatter)
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_HOST_IP, help="Target host IP to tail on. Use the ACU IP when pairing with a jump host.")
    parser.add_argument(ARG_REMOTE_PATH, help="Absolute remote log path to follow.")
    parser.add_argument(ARG_JUMP_HOST_IP, default=None,
                        help="Optional jump host IP. Leave empty for direct SSM logs such as gnss.log.")
    parser.add_argument(ARG_USER, default=SSM_USER, help="SSH user for the target host.")
    parser.add_argument(ARG_JUMP_USER, default=None, help="SSH user for the jump host. Defaults to the target user.")
    parser.add_argument(ARG_TIMEOUT, type=int, default=5, help="SSH connect timeout in seconds.")
    parser.add_argument(ARG_READ_TIMEOUT, type=int, default=600, help="Fail if no log data arrives within this many seconds.")
    parser.add_argument(ARG_TAIL_LINES, type=int, default=0,
                        help="Initial number of historical lines to print before following.")
    parser.add_argument(ARG_CAPTURE_LOG, type=parse_bool_arg, nargs='?', const=True, default=False,
                        help="Also capture streamed log lines to a rotating local log file.")
    parser.add_argument(ARG_CAPTURE_LOG_PATH, default=None, help="Local output log path used when capture_log is enabled.")
    return parser.parse_args()


def build_live_log_handlers(capture_log: bool = False, log_path: Optional[str] = None) -> List[logging.Handler]:
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if capture_log:
        if not log_path:
            raise ValueError(f"{ARG_CAPTURE_LOG_PATH} is required when {ARG_CAPTURE_LOG} is enabled")
        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=LIVE_LOG_FILE_MAX_BYTES, backupCount=LIVE_LOG_FILE_BACKUP_COUNT))
    for handler in handlers:
        handler.setFormatter(logging.Formatter("%(message)s"))
    return handlers


def get_live_remote_log(host_ip: str, remote_log_path: str, user: str = SSM_USER, password: Optional[str] = None, jump_host_ip: Optional[str] = None,
                        jump_user: Optional[str] = None, jump_password: Optional[str] = None, timeout: int = 5, read_timeout: int = 60, tail_lines: int = 0,
                        capture_log: bool = False, log_path: Optional[str] = None) -> None:
    password = password or read_value_from_credential_file(CREDENTIALS_FILE_PATH, UT_PWD_KEY_NAME)
    if not password:
        raise ValueError(f"Missing UT password in {CREDENTIALS_FILE_PATH} with key {UT_PWD_KEY_NAME}")
    handlers = build_live_log_handlers(capture_log=capture_log, log_path=log_path)
    try:
        stream_live_remote_log(host_ip=host_ip, user=user, password=password, remote_log_path=remote_log_path, timeout=timeout, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password or password, tail_lines=tail_lines, read_timeout=read_timeout, on_line=lambda line: LOG(line, show_time=False, handlers=handlers))
    finally:
        for handler in handlers:
            try:
                handler.flush()
                handler.close()
            except Exception:
                pass


def main() -> int:
    args = parse_args()
    try:
        get_live_remote_log(host_ip=args.host_ip, remote_log_path=args.remote_path, user=args.user, jump_host_ip=args.jump_host_ip, jump_user=args.jump_user, timeout=args.timeout, read_timeout=args.read_timeout, tail_lines=args.tail_lines, capture_log=args.capture_log, log_path=args.log_path)
    except KeyboardInterrupt:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Stopped by user.")
        return 130
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to stream '{args.remote_path}' from {args.host_ip}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
