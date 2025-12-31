# No import from other files to avoid circular import
import hashlib
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

WSL_ROOT_FROM_WIN_DRIVE = "X:"


class ELogType(IntEnum):
    DEBUG = 10
    NORMAL = 20
    WARNING = 30
    CRITICAL = 40


_CURRENT_LOG_LEVEL: ELogType = ELogType.NORMAL


def set_log_level(level: ELogType) -> None:
    global _CURRENT_LOG_LEVEL
    _CURRENT_LOG_LEVEL = level


def get_current_log_level() -> ELogType:
    return _CURRENT_LOG_LEVEL


def get_home_path() -> Path:
    if is_platform_windows():
        wsl_home_result = run_shell(["echo", "$HOME"], capture_output=True, is_run_wsl_if_window=True)
        wsl_home = wsl_home_result.stdout.strip()
        resolved_path = Path(f"{WSL_ROOT_FROM_WIN_DRIVE}/{wsl_home.lstrip('/')}")
        print(f"Using local home path: {resolved_path}")
    else:
        resolved_path = Path.home()
    return resolved_path


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

    is_windows = is_platform_windows()
    run_in_wsl = is_windows and is_run_wsl_if_window
    use_shell = want_shell and not is_windows
    exec_path = executable
    exec_cwd = cwd
    wsl_cwd: Optional[str] = None
    # breakpoint()
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
        cmd = _wrap_cmd_for_wsl(cmd, use_shell, wsl_cwd)
        want_shell = False
    else:
        if want_shell and isinstance(cmd, List):
            LOG(f"Shell mode but cmd is a list -> Converting to string...")
            cmd = _stringify_cmd_list(cmd)
        elif not want_shell and isinstance(cmd, str):
            LOG(f"Non-shell mode but cmd is a string -> Converting to list...")
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
    wsl_path = win_path
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


def LOG(*values: object, sep: str = " ", end: str = "\n", file=None, highlight: bool = False,
        show_time: bool = True, show_traceback: bool = False, flush: bool = True,
        log_type: ELogType = ELogType.NORMAL) -> None:
    if log_type < get_current_log_level():
        return
    # Prepare the message
    message = sep.join(str(value) for value in values)

    # Add timestamp if requested
    if show_time:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"[{timestamp}] {message}"

    # Add backtrace if requested
    if show_traceback:
        tb = traceback.format_stack()
        print(f"Total stack frames: {len(tb)}")  # Debug line
        max_frames = 5  # Maximum number of frames to print
        if len(tb) > max_frames:
            # Keep only the last 10 frames
            filtered_tb = tb[-max_frames:]
        else:
            filtered_tb = tb  # Keep all frames if stack is shallow
        message = f"{message}\nBacktrace:\n" + "".join(filtered_tb)

    auto_highlight = False
    if not highlight and log_type in (ELogType.WARNING, ELogType.CRITICAL):
        auto_highlight = True

    if highlight or auto_highlight:
        HIGHLIGHT_COLOR = "\033[92m"  # green
        BOLD = "\033[1m"
        RESET = "\033[0m"
        print(f"{BOLD}{HIGHLIGHT_COLOR}", end="", file=file, flush=flush)  # turn to highlight color
        print(message, end="", file=file, flush=flush)  # print message
        print(f"{RESET}", end=end, file=file, flush=flush)  # reset
    else:
        print(message, end=end, file=file, flush=flush)


def is_diff_ignore_eol(file1: Path, file2: Path) -> bool:
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

def _proc_name(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except Exception:
        return ""


def get_shell_exec_cmd_as_list() -> List[str]:
    """
    Return the shell command with flags for executing commands as a list.
    Uses login shell (-l) to ensure PATH and environment are properly set up.

    Returns a list like ["bash", "-lc"] that can be used directly with subprocess.
    """
    shell = get_shell_name()
    return [shell, "-lc"]


def get_shell_name() -> str:
    """
    Return the shell command to use (bash/zsh/sh), preferring the *current* shell,
    not the login shell stored in $SHELL.
    """
    BASH = "bash"
    ZSH = "zsh"
    SH = "sh"

    # 1) If we're actually running inside bash/zsh, these are the most reliable.
    if os.environ.get("BASH_VERSION") and shutil.which(BASH):
        return BASH
    if os.environ.get("ZSH_VERSION") and shutil.which(ZSH):
        return ZSH

    # 2) Try to infer from the immediate parent process of this Python script.
    #    Works for interactive shell sessions, but may fail for nested processes
    #    (IDEs, make, systemd, etc.) where the parent isn't a shell.
    ppid = os.getppid()
    parent = _proc_name(ppid)
    KNOWN_SHELLS = (BASH, ZSH, SH)
    if parent in KNOWN_SHELLS and shutil.which(parent):
        return parent

    # 3) Fallback to user's preferred/login shell ($SHELL basename).
    env_shell = os.environ.get("SHELL")
    if env_shell:
        shell_name = os.path.basename(env_shell)
        if shutil.which(shell_name):
            return shell_name

    # 4) Final fallback
    return BASH if shutil.which(BASH) else SH
