# Avoid broad imports to prevent circular dependencies; keep minimal helpers only.
import hashlib
import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import List, Literal, Optional, Union, Tuple
from datetime import datetime
import traceback
import platform
from enum import IntEnum
from .shell_utils import get_shell_exec_cmd_as_list

WSL_ROOT_FROM_WIN_DRIVE = "X:"


class ELogType(IntEnum):
    DEBUG = 10
    NORMAL = 20
    WARNING = 30
    CRITICAL = 40


_CURRENT_LOG_LEVEL: ELogType = ELogType.NORMAL
_INTERNAL_LOGGER = logging.getLogger("local_tools.compat")
_INTERNAL_LOGGER.setLevel(logging.DEBUG)
_INTERNAL_LOGGER.propagate = False


def set_log_level(level: ELogType) -> None:
    global _CURRENT_LOG_LEVEL
    _CURRENT_LOG_LEVEL = level


def get_current_log_level() -> ELogType:
    return _CURRENT_LOG_LEVEL


def get_wsl_home_path() -> Path:
    if is_platform_windows():
        wsl_home_result = run_shell(["echo", "$HOME"], capture_output=True, is_run_wsl_if_window=True)
        wsl_home = wsl_home_result.stdout.strip()
        resolved_path = Path(f"{WSL_ROOT_FROM_WIN_DRIVE}/{wsl_home.lstrip('/')}")
        print(f"Using local home path: {resolved_path}")
    else:
        resolved_path = Path.home()
    return resolved_path

def get_win_home_path() -> Path:
    if is_platform_windows():
        # Running on Windows natively, USERPROFILE is available directly
        return Path(os.environ['USERPROFILE'])
    else:
        # Running on WSL, need to query Windows environment via cmd.exe
        result = run_shell( ["cmd.exe", "/c", "echo %USERPROFILE%"], capture_output=True )
        win_home = result.stdout.strip()
        # Convert Windows path to WSL-accessible path (e.g. C:\Users\foo -> /mnt/c/Users/foo)
        return Path(convert_win_to_wsl_path(win_home))

def run_shell(cmd: Union[str, List[str]], show_cmd: bool = True, cwd: Optional[Path | str] = None,
              check_throw_exception_on_exit_code: bool = True, stdout=None, stderr=None,
              text: Optional[bool] = True, capture_output: bool = False, encoding: str = 'utf-8',
              want_shell: bool = True, executable: Optional[str] = None, timeout: Optional[int] = None, is_run_wsl_if_window: bool = True) -> subprocess.CompletedProcess:
    """Echo + run a shell command. Note: capture_output will catpure stdout/stderr and return within CompletedProcess object -> Also Suppress stdout/stderr"""

    def _stringify_cmd_list(cmd_list: List[Union[str, Path]]) -> str:
        return ' '.join(shlex.quote(str(arg)) for arg in cmd_list)

    def _looks_like_windows_path(token: str) -> bool:
        stripped = token.strip().strip('"').strip("'")
        return bool(re.match(r'^[a-zA-Z]:[\\/]', stripped)) or stripped.startswith('\\\\')

    def _normalize_wsl_args(args: List[Union[str, Path]]) -> List[str]:
        normalized: List[str] = []
        for arg in args:
            arg_str = str(arg)
            if _looks_like_windows_path(arg_str):
                normalized.append(convert_win_to_wsl_path(arg_str))
            else:
                normalized.append(arg_str)
        return normalized

    def format_cmd_for_log(target_cmd):
        cmd_type = type(target_cmd).__name__      # "list", "str", "tuple", ...
        cmd_str = " ".join(target_cmd) if isinstance(target_cmd, list) else str(target_cmd)
        return f"[{cmd_type} CMD] >>> {cmd_str}"

    def _wrap_cmd_for_wsl(raw_cmd: Union[str, List[Union[str, Path]]], wants_shell: bool, wsl_cwd: Optional[str]) -> List[str]:
        wsl_cmd: List[str] = ["wsl"]
        if wsl_cwd:
            wsl_cmd.extend(["--cd", wsl_cwd])

        if wants_shell:
            if isinstance(raw_cmd, list):
                cmd_str = _stringify_cmd_list(raw_cmd)
            else:
                cmd_str = str(raw_cmd)
            wsl_cmd.extend([*get_shell_exec_cmd_as_list(), cmd_str])
        else:
            if isinstance(raw_cmd, list):
                cmd_args = [str(arg) for arg in raw_cmd]
            else:
                cmd_args = shlex.split(str(raw_cmd))
            wsl_cmd.extend(_normalize_wsl_args(cmd_args))
        return wsl_cmd

    def _is_already_wsl_wrapped(raw_cmd: Union[str, List[Union[str, Path]]]) -> bool:
        if isinstance(raw_cmd, list):
            if not raw_cmd:
                return False
            first_token = str(raw_cmd[0]).strip().lower()
        else:
            parts = shlex.split(str(raw_cmd))
            if not parts:
                return False
            first_token = parts[0].strip().lower()
        return first_token in {"wsl", "wsl.exe"}

    is_windows = is_platform_windows()
    run_in_wsl = is_windows and is_run_wsl_if_window
    use_shell = want_shell and not is_windows
    exec_path = executable
    exec_cwd = cwd
    wsl_cwd: Optional[str] = None
    if is_windows:
        if run_in_wsl:
            exec_path = None
            if cwd:
                wsl_cwd = convert_win_to_wsl_path(str(cwd))
                LOG(f"Converting cwd '{cwd}' to WSL path '{wsl_cwd}'")
                exec_cwd = wsl_cwd
        else:
            if cwd:
                cwd_str = str(cwd)
                if ":" not in cwd_str and "\\\\" not in cwd_str:
                    exec_cwd = convert_wsl_to_win_path(Path(cwd))
                if not os.path.exists(str(exec_cwd)):
                    LOG(f"WARNING: CWD '{exec_cwd}' not found. Mapped drives ({WSL_ROOT_FROM_WIN_DRIVE}) may be invisible to Python.")

            exec_path = None  # Let Windows resolve binaries (e.g., git.exe)
            if want_shell:
                LOG("Windows: Forcing shell=False for UNC path support.")
                want_shell = False

    if run_in_wsl:
        if not _is_already_wsl_wrapped(cmd):
            cmd = _wrap_cmd_for_wsl(cmd, use_shell, wsl_cwd)
        want_shell = False
    else:
        if want_shell and isinstance(cmd, List):
            #LOG(f"Shell mode but cmd is a list -> Converting to string...")
            cmd = _stringify_cmd_list(cmd)
        elif not want_shell and isinstance(cmd, str):
            #LOG(f"Non-shell mode but cmd is a string -> Converting to list...")
            cmd = shlex.split(cmd)

    if show_cmd:
        LOG(f"{format_cmd_for_log(cmd)} (cwd={exec_cwd or Path.cwd()})")

    return subprocess.run(cmd, shell=want_shell, cwd=exec_cwd, check=check_throw_exception_on_exit_code, stdout=stdout, stderr=stderr, text=text, capture_output=capture_output, encoding=encoding, executable=exec_path, timeout=timeout)


def convert_wsl_to_win_path(file_path: Path) -> str:
    """
    Convert a WSL/Linux path to a Windows path using wslpath.
    Detects platform to invoke the command correctly.
    """
    path_str = str(file_path)

    # 1. Optimization: If it's already a Windows path (has drive letter or backslash), return it.
    if ":" in path_str or "\\" in path_str:
        return path_str.replace("/", "\\")

    cmd = []

    # 2. Determine how to call wslpath based on OS
    if is_platform_windows():
        # On Windows, 'wslpath' is not in PATH. We must call 'wsl.exe' with the command.
        cmd = ["wsl", "wslpath", "-w", path_str]
    else:
        # On Linux/WSL, wslpath is a native binary
        cmd = ["wslpath", "-w", path_str]

    try:
        result = run_shell(
            cmd,
            capture_output=True,
            text=True,
            check_throw_exception_on_exit_code=True
        )
        win_path = result.stdout.strip()
        LOG(f"Converted WSL path {file_path} to Windows path: {win_path}")
        return win_path
    except Exception as e:
        LOG_EXCEPTION_STR(f"Failed to convert WSL path {file_path} to Windows path: {e}")


def _apply_custom_win_to_wsl_aliases(win_path: str) -> Optional[str]:
    CUSTOM_WIN_TO_WSL_PREFIXES: List[Tuple[str, str]] = [  # (win_prefix, wsl_prefix)
        (f"{WSL_ROOT_FROM_WIN_DRIVE}/", "/"),
    ]
    normalized = win_path.replace("\\", "/")
    normalized_lower = normalized.lower()
    for alias_prefix, wsl_prefix in CUSTOM_WIN_TO_WSL_PREFIXES:
        alias_norm = alias_prefix.replace("\\", "/").lower().rstrip("/")
        if normalized_lower == alias_norm or normalized_lower.startswith(f"{alias_norm}/"):
            suffix = normalized[len(alias_norm):].lstrip("/")
            wsl_base = wsl_prefix.rstrip("/")
            if suffix:
                return f"{wsl_base}/{suffix}"
            return wsl_base or "/"
    return None


def convert_win_to_wsl_path(win_path: str) -> str:
    """
    Converts a Windows file path to a WSL path.
    Tries native `wslpath -u` first, falls back to manual string parsing.
    """
    win_path = str(win_path)  # <-- fix: handle WindowsPath or PurePosixPath objects
    clean_path = win_path.strip('"').strip("'")
    alias_result = _apply_custom_win_to_wsl_aliases(clean_path)
    if alias_result:
        wsl_path = alias_result
    else:
        # Strategy 1: Try using the native wslpath tool (most robust). This works if currently INSIDE WSL, or if we have `wsl.exe` on Windows.
        cmd = []
        if is_platform_windows():
            if shutil.which("wsl"):
                cmd = ["wsl", "wslpath", "-u", clean_path]
        else:
            cmd = ["wslpath", "-u", clean_path]

        if cmd:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass  # Fall through to manual parsing logic below

        # Strategy 2: Manual Parsing (Fallback)
        # Normalize slashes
        universal_path = clean_path.replace("\\", "/")
        wsl_path = universal_path

        # Handle Drive Letters: Look for pattern like "C:/" or "d:/" at the start
        drive_match = re.match(r'^([a-zA-Z]):/(.*)', universal_path)

        if drive_match:
            drive_letter = drive_match.group(1).lower()
            rest_of_path = drive_match.group(2)
            wsl_path = f"/mnt/{drive_letter}/{rest_of_path}"

    LOG(f"Converted Windows path {win_path} to WSL path: {wsl_path}")
    return wsl_path


def is_platform_windows() -> bool:
    return platform.system() == "Windows"


def change_dir(path: str):
    LOG(f"Changing directory to {path}")
    os.chdir(path)


def get_cwd_path_str():
    return str(Path.cwd())


def _map_log_type_to_level(log_type: ELogType) -> int:
    if log_type >= ELogType.CRITICAL:
        return logging.CRITICAL
    if log_type >= ELogType.WARNING:
        return logging.WARNING
    if log_type >= ELogType.NORMAL:
        return logging.INFO
    return logging.DEBUG


class _BaseStreamHandler(logging.StreamHandler):
    HIGHLIGHT_COLOR = "\033[92m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    def __init__(self, stream=None, *, highlight: bool = False, same_line: bool = False, flush: bool = True, terminator: str = "\n"):
        super().__init__(stream)
        self._highlight = highlight
        self._same_line = same_line
        self._flush_enabled = flush
        self.terminator = terminator

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if self._highlight:
                msg = f"{self.BOLD}{self.HIGHLIGHT_COLOR}{msg}{self.RESET}"
            self.stream.write(msg)
            self.stream.write("\r" if self._same_line else self.terminator)
            if self._flush_enabled:
                self.flush()
        except Exception:
            self.handleError(record)


def LOG(*values: object, sep: str = " ", end: str = "\n", file=None, highlight: bool = False,
        show_time: bool = True, show_traceback: bool = False, flush: bool = True,
        log_type: ELogType = ELogType.NORMAL, same_line: bool = False,
        handlers: Optional[Union[logging.Handler, List[logging.Handler], Tuple[logging.Handler, ...]]] = None) -> None:
    if log_type < get_current_log_level():
        return
    message = sep.join(str(value) for value in values)
    if show_time:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"[{timestamp}] {message}"
    if show_traceback:
        tb = traceback.format_stack()
        filtered_tb = tb[-5:] if len(tb) > 5 else tb
        message = f"{message}\nBacktrace:\n" + "".join(filtered_tb)
    normalized_handlers: List[logging.Handler]
    if handlers is None:
        auto_highlight = highlight or log_type in (ELogType.WARNING, ELogType.CRITICAL)
        default_handler = _BaseStreamHandler(stream=file or sys.stdout, highlight=auto_highlight, same_line=same_line, flush=flush, terminator=end)
        default_handler.setFormatter(logging.Formatter("%(message)s"))
        normalized_handlers = [default_handler]
    elif isinstance(handlers, logging.Handler):
        normalized_handlers = [handlers]
    else:
        normalized_handlers = list(handlers)

    record = _INTERNAL_LOGGER.makeRecord(_INTERNAL_LOGGER.name, _map_log_type_to_level(log_type), fn="", lno=0, msg=message, args=(), exc_info=None)
    for handler in normalized_handlers:
        if handler.formatter is None:
            handler.setFormatter(logging.Formatter("%(message)s"))
        handler.handle(record)
        if flush and hasattr(handler, "flush"):
            handler.flush()

def is_diff_ignore_eol(file1: Path, file2: Path) -> bool:
    if file1.is_dir() or file2.is_dir():
        LOG(f"Skipping directory: {file1} (is dir: {file1.is_dir()}) or {file2} (is dir: {file2.is_dir()})")
        return False  # treat directories as identical, skip copying
    return normalize_lines(file1) != normalize_lines(file2)


def normalize_lines(p: Path) -> bytes:
    with p.open("rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def md5sum(file_path):
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5


def read_value_from_credential_file(credentials_file_path: str, key_to_read: str, exit_on_error: bool = True) -> Union[str, None]:
    """
    Reads a specific key's value from a credentials file.
    Returns the value if found, otherwise None.
    """
    if is_platform_windows():
        LOG(f"Converting Windows path to WSL path: {credentials_file_path}")
        credentials_file_path = convert_win_to_wsl_path(credentials_file_path)

    if os.path.exists(credentials_file_path):
        try:
            with open(credentials_file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        try:
                            key, value = line.split('=', 1)
                            if key == key_to_read:
                                return value
                        except ValueError:
                            # Handle lines that don't contain '='
                            print(f"Warning: Skipping malformed line in {credentials_file_path}: {line}")
                            continue
        except Exception as e:
            if exit_on_error:
                print(f"Error reading credentials file {credentials_file_path}: {e}")
                sys.exit(1)
    else:
        print(f"Credentials file {credentials_file_path} not found.")

    LOG(f"ERROR: Key '{key_to_read}' not found in {credentials_file_path}")
    return None


def LOG_EXCEPTION_STR(exception_str: str, msg=None, exit: bool = True):
    # Capture REAL current exception context (or None if no exception active)
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is not None:
        # Use the actual exception that was just caught
        LOG_EXCEPTION(exc_value, msg or exception_str, exit=exit)
    else:
        # Fallback: create exception with fake traceback
        try:
            raise Exception(exception_str)
        except Exception as e:
            LOG_EXCEPTION(e, msg, exit=exit)


def LOG_EXCEPTION(exception: Exception, msg=None, exit: bool = True):
    """Log error with essential info to stderr."""

    # One-line header with key info
    LOG(f"{type(exception).__name__}: {exception}", file=sys.stderr, highlight=True)
    if msg:
        LOG(f"- Context: {msg}", file=sys.stderr, highlight=True)

    # Exception-specific critical info only
    if isinstance(exception, subprocess.CalledProcessError):
        LOG(f"Command: {exception.cmd} (exit {exception.returncode})", file=sys.stderr)
        if hasattr(exception, 'stderr') and exception.stderr:
            LOG(f"Error: {exception.stderr.strip()}", file=sys.stderr)
        if hasattr(exception, 'stdout') and exception.stdout:
            LOG(f"Output: {exception.stdout.strip()}", file=sys.stderr)
    elif isinstance(exception, (FileNotFoundError, PermissionError, OSError)):
        if hasattr(exception, 'filename') and exception.filename:
            LOG(f"File: {exception.filename}", file=sys.stderr)

    # Show full traceback but filter out library internals
    tb = traceback.extract_tb(exception.__traceback__)
    if tb:
        LOG("- Call stack:", file=sys.stderr)

        # Get the directory of your main script to identify "your" code
        main_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        for frame in tb:
            # Highlight frames from your code vs library code
            is_local = frame.filename.startswith(main_dir)
            prefix = "  →" if is_local else "   "
            # Make filename relative if it's in your project
            display_filename = frame.filename
            if is_local:
                display_filename = os.path.relpath(frame.filename, main_dir)

            LOG(f"{prefix} {display_filename}:{frame.lineno} in {frame.name}()",
                file=sys.stderr, highlight=is_local)

    if exit:
        sys.exit(1)

def LOG_LINE_SEPARATOR():
    separator = f"\n{'=' * 70}\n"
    LOG(f"{separator}", show_time = False)
