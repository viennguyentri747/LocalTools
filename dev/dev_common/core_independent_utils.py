# Avoid broad imports to prevent circular dependencies; keep minimal helpers only.
import hashlib
import logging
import os
from functools import lru_cache
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import List, Optional, Sequence, Union, Tuple
from datetime import datetime, timezone, tzinfo
import traceback
import platform
from enum import Enum, IntEnum

WSL_ROOT_FROM_WIN_DRIVE = "X:"
DEFAULT_TIMEZONE: tzinfo = timezone.utc
_LOG_TIME_FORMAT: str = "%Y-%m-%d %H:%M:%S"
_FILE_TIMESTAMP_FORMAT: str = "%Y%m%d_%H%M%S"
_FILE_TIMESTAMP_WITH_US_FORMAT: str = "%Y%m%d_%H%M%S_%f"
_DATE_NAME_FORMAT: str = "%Y%m%d"


def get_datetime_now(tz: tzinfo = DEFAULT_TIMEZONE) -> datetime:
    """Return the current aware datetime in the configured timezone."""
    return datetime.now(tz)


def _as_configured_datetime(value: datetime | None = None, tz: tzinfo = DEFAULT_TIMEZONE) -> datetime:
    if value is None:
        return get_datetime_now(tz)
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def get_log_timestamp(value: datetime | None = None) -> str:
    return _as_configured_datetime(value).strftime(_LOG_TIME_FORMAT)


def get_file_timestamp(value: datetime | None = None) -> str:
    return _as_configured_datetime(value).strftime(_FILE_TIMESTAMP_FORMAT)


def get_file_timestamp_with_us(value: datetime | None = None) -> str:
    return _as_configured_datetime(value).strftime(_FILE_TIMESTAMP_WITH_US_FORMAT)


def get_date_name(value: datetime | None = None) -> str:
    return _as_configured_datetime(value).strftime(_DATE_NAME_FORMAT)


def get_iso_timestamp(value: datetime | None = None, timespec: str = "seconds") -> str:
    return _as_configured_datetime(value).isoformat(timespec=timespec)


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


def LOG(*values: object, sep: str = " ", end: str = "\n", file=None, highlight: bool = False,
        show_time: bool = True, show_traceback: bool = False, flush: bool = True,
        log_type: ELogType = ELogType.NORMAL, same_line: bool = False,
        handlers: Optional[Union[logging.Handler, List[logging.Handler], Tuple[logging.Handler, ...]]] = None) -> None:
    if log_type < get_current_log_level():
        return
    message = sep.join(str(value) for value in values)
    if show_time:
        message = f"[{get_log_timestamp()}] {message}"
    if show_traceback:
        tb = traceback.format_stack()
        filtered_tb = tb[-5:] if len(tb) > 5 else tb
        message = f"{message}\nBacktrace:\n" + "".join(filtered_tb)
    normalized_handlers: List[logging.Handler]
    if handlers is None:
        auto_highlight = highlight or log_type in (ELogType.WARNING, ELogType.CRITICAL)
        default_handler = _BaseStreamHandler(
            stream=file or sys.stdout, highlight=auto_highlight, same_line=same_line, flush=flush, terminator=end)
        default_handler.setFormatter(logging.Formatter("%(message)s"))
        normalized_handlers = [default_handler]
    elif isinstance(handlers, logging.Handler):
        normalized_handlers = [handlers]
    else:
        normalized_handlers = list(handlers)

    record = _INTERNAL_LOGGER.makeRecord(_INTERNAL_LOGGER.name, _map_log_type_to_level(
        log_type), fn="", lno=0, msg=message, args=(), exc_info=None)
    for handler in normalized_handlers:
        if handler.formatter is None:
            handler.setFormatter(logging.Formatter("%(message)s"))
        handler.handle(record)
        if flush and hasattr(handler, "flush"):
            handler.flush()


def get_wsl_home_path() -> Path:
    if is_platform_windows():
        wsl_home_result = run_shell(["echo", "$HOME"], capture_output=True, is_run_wsl_if_window=True)
        wsl_home = wsl_home_result.stdout.strip()
        resolved_path = Path(f"{WSL_ROOT_FROM_WIN_DRIVE}/{wsl_home.lstrip('/')}")
        LOG(f"Using local home path: {resolved_path}", log_type=ELogType.DEBUG)
    else:
        resolved_path = Path.home()
    return resolved_path


@lru_cache(maxsize=1)
def get_win_home_path() -> Path:
    if is_platform_windows():
        # Running on Windows natively, USERPROFILE is available directly
        return Path(os.environ['USERPROFILE'])
    else:
        # Running on WSL, need to query Windows environment via cmd.exe
        result = run_shell(["cmd.exe", "/c", "echo %USERPROFILE%"], capture_output=True, timeout=3)
        win_home = result.stdout.strip()
        return Path(get_normalized_path(win_home, target_platform=ETargetPlatform.WSL_OR_LINUX))


@lru_cache(maxsize=1)
def get_win_persistent_temp_path() -> Path:
    return get_win_home_path() / "temp"


class ETargetPlatform(str, Enum):
    CURRENT = "current"
    WINDOWS = "windows"
    WSL_OR_LINUX = "linux"


def _coerce_target_platform(target_platform: ETargetPlatform | str) -> ETargetPlatform:
    if isinstance(target_platform, ETargetPlatform):
        return target_platform
    normalized = str(target_platform).strip().lower()
    if normalized in {"wsl", "linux", "wsl_or_linux"}:
        return ETargetPlatform.WSL_OR_LINUX
    return ETargetPlatform(normalized)


def _is_running_in_wsl() -> bool:
    if is_platform_windows():
        return False
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        with open("/proc/version", "r", encoding="utf-8", errors="replace") as fp:
            content = fp.read().lower()
        return "microsoft" in content or "wsl" in content
    except Exception:
        return False


def _get_local_repo_temp_path() -> Path:
    return Path(__file__).resolve().parents[2] / "temp"


def _resolve_current_platform_target() -> ETargetPlatform:
    if is_platform_windows():
        return ETargetPlatform.WINDOWS
    return ETargetPlatform.WSL_OR_LINUX


def get_temp_path(prefer_platform: ETargetPlatform | str = ETargetPlatform.WINDOWS) -> Path:
    prefer_platform = _coerce_target_platform(prefer_platform)

    local_temp_path = _get_local_repo_temp_path()
    if prefer_platform == ETargetPlatform.CURRENT:
        prefer_platform = _resolve_current_platform_target()

    if is_platform_windows():
        if prefer_platform == ETargetPlatform.WSL_OR_LINUX:
            return Path(get_normalized_path(get_win_persistent_temp_path(), target_platform=ETargetPlatform.WSL_OR_LINUX))
        return get_win_persistent_temp_path()

    if _is_running_in_wsl():
        if prefer_platform == ETargetPlatform.WINDOWS:
            return get_win_persistent_temp_path()
        return local_temp_path

    if prefer_platform == ETargetPlatform.WINDOWS:
        LOG(f"[WARNING] Windows temp path is not supported on pure Linux. Falling back to Linux/local temp path: {local_temp_path}")
    return local_temp_path


def _is_windows_path_text(path_text: str) -> bool:
    stripped = path_text.strip().strip('"').strip("'")
    return bool(re.match(r'^[a-zA-Z]:[\\/]', stripped)) or stripped.startswith(('\\\\', '//wsl.localhost/', '//wsl$/'))


def _is_wsl_unc_path_text(path_text: str) -> bool:
    stripped = path_text.strip().strip('"').strip("'").replace("\\", "/")
    return bool(re.match(r'^//wsl(?:\.localhost|\$)/[^/]+(/.*)?$', stripped, flags=re.IGNORECASE))

def _normalize_windows_path_separators(path_text: str) -> str:
    clean = str(path_text).strip().strip('"').strip("'")
    if not clean:
        return clean
    if re.match(r'^[a-zA-Z]:/', clean):
        return clean.replace("/", "\\")
    if clean.startswith("//"):
        return clean.replace("/", "\\")
    return clean


def format_path_for_display(path_like: str | Path) -> str:
    """Return a user-facing path string in WSL/POSIX style when possible."""
    raw_text = str(path_like)
    clean_text = raw_text.strip().strip('"').strip("'")
    if not clean_text:
        return clean_text
    try:
        if _is_windows_path_text(clean_text):
            return convert_win_to_wsl_path(clean_text)
    except Exception:
        pass
    return clean_text.replace("\\", "/")


def format_paths_for_display(paths: Sequence[str | Path]) -> List[str]:
    return [format_path_for_display(path) for path in paths]


def run_shell(cmd: Union[str, List[str]], show_cmd: bool = True, cwd: Optional[Path | str] = None,
              check_throw_exception_on_exit_code: bool = True, stdout=None, stderr=None,
              text: Optional[bool] = True, input: Optional[str] = None, capture_output: bool = False, encoding: str = 'utf-8',
              want_shell: bool = True, executable: Optional[str] = None, timeout: Optional[int] = None, is_run_wsl_if_window: bool = True) -> subprocess.CompletedProcess:
    """Echo + run a shell command. Note: capture_output will catpure stdout/stderr and return within CompletedProcess object -> Also Suppress stdout/stderr"""

    def _stringify_cmd_list(cmd_list: List[Union[str, Path]]) -> str:
        return ' '.join(shlex.quote(str(arg)) for arg in cmd_list)

    def _looks_like_windows_path(token: str) -> bool:
        return _is_windows_path_text(token)

    def _normalize_wsl_args(args: List[Union[str, Path]]) -> List[str]:
        normalized: List[str] = []
        for arg in args:
            arg_str = str(arg)
            if _looks_like_windows_path(arg_str):
                normalized.append(str(get_normalized_path(arg_str, target_platform=ETargetPlatform.WSL_OR_LINUX)))
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
                cmd_str = _stringify_cmd_list(_normalize_wsl_args([str(arg) for arg in raw_cmd]))
            else:
                cmd_str = str(raw_cmd)
            wsl_cmd.extend([*get_shell_exec_cmd_as_list(), cmd_str])
        else:
            if isinstance(raw_cmd, list):
                cmd_args = _normalize_wsl_args([str(arg) for arg in raw_cmd])
            else:
                cmd_args = _normalize_wsl_args(shlex.split(str(raw_cmd)))
            wsl_cmd.extend(cmd_args)
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
    exec_path = executable
    exec_cwd = cwd
    wsl_cwd: Optional[str] = None
    if is_windows:
        if run_in_wsl:
            exec_path = None
            if cwd:
                wsl_cwd = str(get_normalized_path(cwd, target_platform=ETargetPlatform.WSL_OR_LINUX))
                LOG(f"Converting cwd '{cwd}' to WSL path '{wsl_cwd}'", log_type=ELogType.NORMAL)
                exec_cwd = wsl_cwd
        else:
            if cwd:
                exec_cwd = get_normalized_path(cwd, target_platform=ETargetPlatform.WINDOWS)
                if not os.path.exists(str(exec_cwd)):
                    LOG(f"WARNING: CWD '{exec_cwd}' not found. Mapped drives ({WSL_ROOT_FROM_WIN_DRIVE}) may be invisible to Python.",
                        log_type=ELogType.WARNING)

            exec_path = None  # Let Windows resolve binaries (e.g., git.exe)
            if want_shell:
                LOG("Windows: Forcing shell=False for UNC path support.", log_type=ELogType.NORMAL)
                want_shell = False

    if run_in_wsl:
        if not _is_already_wsl_wrapped(cmd):
            cmd = _wrap_cmd_for_wsl(cmd, want_shell, wsl_cwd)
        want_shell = False
    else:
        if want_shell and isinstance(cmd, List):
            # LOG(f"Shell mode but cmd is a list -> Converting to string...")
            cmd = _stringify_cmd_list(cmd)
        elif not want_shell and isinstance(cmd, str):
            # LOG(f"Non-shell mode but cmd is a string -> Converting to list...")
            cmd = shlex.split(cmd)

    if show_cmd:
        display_cwd = format_path_for_display(exec_cwd or Path.cwd())
        LOG(f"{format_cmd_for_log(cmd)} (cwd={display_cwd})" + (f"{input}" if input else ""), log_type=ELogType.NORMAL)

    return subprocess.run(cmd, shell=want_shell, cwd=exec_cwd, check=check_throw_exception_on_exit_code, stdout=stdout, stderr=stderr, text=text, input = input, capture_output=capture_output, encoding=encoding, executable=exec_path, timeout=timeout)


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


def resolve_executable_path(cmd: Union[str, Path]) -> str:
    """Resolve executable path for any command; return original if unresolved."""
    cmd_str = str(cmd)
    if not cmd_str:
        return cmd_str
    expanded = os.path.expanduser(cmd_str)
    if os.path.sep in expanded or (os.path.altsep and os.path.altsep in expanded):
        return expanded if Path(expanded).exists() else cmd_str
    resolved = shutil.which(expanded)
    return resolved or cmd_str


def wrap_cmd_for_bash(cmd: str) -> str:
    return cmd if cmd.strip().startswith("bash -lic ") else f"bash -lic {shlex.quote(cmd)}"


def _proc_name(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except Exception:
        return ""


def convert_wsl_to_win_path(file_path: Path) -> str:
    """
    Convert a WSL/Linux path to a Windows path using wslpath.
    Detects platform to invoke the command correctly.
    """
    path_str = str(file_path)

    # 1. Optimization: If it's already a Windows path (has drive letter or backslash), return it.
    if ":" in path_str or "\\" in path_str:
        return path_str.replace("/", "\\")
    resolved_wsl_path = _resolve_existing_wsl_path_text(path_str)

    cmd = []

    # 2. Determine how to call wslpath based on OS
    if is_platform_windows():
        # On Windows, 'wslpath' is not in PATH. We must call 'wsl.exe' with the command.
        cmd = ["wsl", "wslpath", "-w", resolved_wsl_path]
    else:
        # On Linux/WSL, wslpath is a native binary
        cmd = ["wslpath", "-w", resolved_wsl_path]

    try:
        result = run_shell(cmd, capture_output=True, text=True, check_throw_exception_on_exit_code=True )
        win_path = result.stdout.strip()
        LOG(f"Converted WSL path {format_path_for_display(file_path)} to Windows path: {win_path}")
        return win_path
    except Exception as e:
        alias_path = _apply_custom_wsl_to_win_aliases(resolved_wsl_path)
        if alias_path:
            LOG(f"[WARNING] Native WSL->Windows conversion failed; using alias path fallback: {alias_path}")
            return alias_path
        LOG_EXCEPTION_STR(f"Failed to convert WSL path {file_path} to Windows path: {e}")


def _resolve_existing_wsl_path_text(path_text: str) -> str:
    if not path_text.startswith("/"):
        return path_text
    path_obj = Path(path_text).expanduser()
    if not is_platform_windows():
        return str(path_obj.resolve()) if path_obj.exists() else str(path_obj)
    if shutil.which("wsl"):
        try:
            result = subprocess.run(["wsl", "readlink", "-f", str(path_obj)],
                                    capture_output=True, text=True, check=True)
            resolved = result.stdout.strip()
            if resolved:
                return resolved
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    return str(path_obj)


def _apply_custom_wsl_to_win_aliases(wsl_path: str) -> Optional[str]:
    normalized = str(wsl_path).replace("\\", "/")
    if not normalized.startswith("/"):
        return None
    mnt_drive_match = re.match(r'^/mnt/([a-zA-Z])(?:/(.*))?$', normalized)
    if mnt_drive_match:
        drive_letter = mnt_drive_match.group(1).upper()
        suffix = (mnt_drive_match.group(2) or "").replace("/", "\\")
        return f"{drive_letter}:\\{suffix}" if suffix else f"{drive_letter}:\\"
    return f"{WSL_ROOT_FROM_WIN_DRIVE}/{normalized.lstrip('/')}"


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
        unc_match = re.match(r'^//wsl(?:\.localhost|\$)/[^/]+(/.*)?$', universal_path, flags=re.IGNORECASE)
        if unc_match:
            return unc_match.group(1) or "/"

        # Handle Drive Letters: Look for pattern like "C:/" or "d:/" at the start
        drive_match = re.match(r'^([a-zA-Z]):/(.*)', universal_path)

        if drive_match:
            drive_letter = drive_match.group(1).lower()
            rest_of_path = drive_match.group(2)
            wsl_path = f"/mnt/{drive_letter}/{rest_of_path}"

    LOG(f"Converted Windows path {format_path_for_display(win_path)} to WSL path: {format_path_for_display(wsl_path)}", log_type=ELogType.DEBUG)
    return wsl_path


def get_normalized_path(path_like: str | Path, target_platform: ETargetPlatform | str = ETargetPlatform.CURRENT, *, log_label: str = "Path") -> str:
    """Normalize a path for the target runtime platform.

    Use ETargetPlatform.WINDOWS for paths passed to Windows tools,
    ETargetPlatform.WSL_OR_LINUX for paths passed to WSL/Linux tools, and
    ETargetPlatform.CURRENT for local file access.
    """
    target_platform = _coerce_target_platform(target_platform)
    path_text = str(path_like).strip().strip('"').strip("'")
    if target_platform == ETargetPlatform.CURRENT:
        target_platform = _resolve_current_platform_target()
    if target_platform == ETargetPlatform.WSL_OR_LINUX:
        normalized_text = convert_win_to_wsl_path(path_text) if _is_windows_path_text(path_text) else path_text
        normalized_obj = Path(normalized_text).expanduser()
        if not is_platform_windows() and normalized_obj.exists():
            normalized_obj = normalized_obj.resolve()
        normalized_path = str(normalized_obj)
    elif target_platform == ETargetPlatform.WINDOWS:
        if _is_windows_path_text(path_text) and not _is_wsl_unc_path_text(path_text):
            LOG(f"Normalizing Windows path: {path_text}", log_type=ELogType.DEBUG)
            normalized_path = _normalize_windows_path_separators(path_text)
        else:
            LOG(f"Normalizing WSL path for Windows target: {path_text}", log_type=ELogType.DEBUG)
            wsl_path = convert_win_to_wsl_path(path_text) if _is_wsl_unc_path_text(path_text) else path_text
            normalized_path = _normalize_windows_path_separators(convert_wsl_to_win_path(Path(wsl_path)))
    else:
        raise ValueError(
            f"Unsupported target_platform='{target_platform}'. Expected one of {[item.value for item in ETargetPlatform]}.")
    LOG(f"[INFO] Normalized {log_label}: {path_text} -> {normalized_path}, Target Platform: {target_platform}", log_type=ELogType.NORMAL)
    return normalized_path


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
            try:
                self.stream.write(msg)
            except UnicodeEncodeError:
                # Windows cp1252 consoles cannot encode many Unicode glyphs.
                # Fallback to best-effort printable text instead of crashing logging.
                safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
                self.stream.write(safe_msg)
            self.stream.write("\r" if self._same_line else self.terminator)
            if self._flush_enabled:
                self.flush()
        except Exception:
            self.handleError(record)


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
    credentials_file_path = get_normalized_path(credentials_file_path, target_platform=ETargetPlatform.CURRENT)
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
                            LOG(f"Warning: Skipping malformed line in {credentials_file_path}: {line}")
                            continue
        except Exception as e:
            if exit_on_error:
                LOG(f"Error reading credentials file {credentials_file_path}: {e}")
                sys.exit(1)
    else:
        LOG(f"Credentials file {credentials_file_path} not found.")
        # breakpoint()

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

    tb = traceback.extract_stack()
    if tb:
        LOG("- Call stack:", file=sys.stderr)

        for frame in tb:
            # Display everything identically with a uniform prefix
            prefix = "   "
            display_filename = frame.filename

            LOG(f"{prefix} {display_filename}:{frame.lineno} in {frame.name}()",
                file=sys.stderr, highlight=True)

    if exit:
        sys.exit(1)


def LOG_EMPTY_LINE():
    LOG("\n", show_time=False)

def LOG_LINE_SEPARATOR():
    separator = f"\n{'=' * 70}\n"
    LOG(f"{separator}", show_time=False)


def get_file_md5sum(file_path: Union[Path, str]) -> Optional[str]:
    file_path = Path(file_path)
    if not file_path.exists() or not file_path.is_file():
        return None
    try:
        file_path_str: str = str(file_path)
        with open(file_path_str, 'rb') as f:
            md5 = hashlib.md5(f.read()).hexdigest()
        return md5
    except Exception as e:
        LOG(f"WARNING: Failed to calculate md5sum for '{file_path}': {e}. Saving null md5 in metadata.", file=sys.stderr)
        return None
