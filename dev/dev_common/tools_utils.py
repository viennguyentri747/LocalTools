from dataclasses import dataclass
# import fcntl
import importlib.util
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import IntEnum, auto
import pyperclip
from dev.dev_common.constants import LINE_SEPARATOR, CMD_EXPLORER, WSL_SELECT_FLAG, LOCAL_TOOL_REPO_PATH
from dev.dev_common import *
# from dev.dev_common.core_utils import LOG, convert_win_to_wsl_path, run_shell, convert_wsl_to_win_path

HIDDEN_TOOL_FILENAMES = {} #Can put thing like: "t_test_ut_from_local.py"
LOCAL_PYTHON_BIN_PATH = "/usr/local/bin/local_python"
WIN_PYTHON_RUNNER_SCRIPT_PATH = LOCAL_TOOL_REPO_PATH / "dev" / "dev_common" / "win_python_runner.py"
WIN_PYTHON_TRACKED_MODULES: Set[str] = set()


def get_local_python_runner_executable() -> str:
    """Return preferred local Python executable for launching helper scripts."""
    return LOCAL_PYTHON_BIN_PATH if Path(LOCAL_PYTHON_BIN_PATH).exists() else str(sys.executable)


class ToolFolderPriority(IntEnum):
    TOP = 0
    code_tool = auto()
    iesa_tool = auto()
    content_tool = auto()
    inertial_sense_tool = auto()
    test_tool = auto()
    # TODO: Add more priorities

    misc_hidden_tools = auto()
    LAST = 999


@dataclass
class ToolEntry:
    folder: str
    filename: str
    path: Path

    @property
    def full_path(self) -> str:
        return str(Path(self.folder) / self.filename)

    @property
    def folder_path(self) -> Path:
        return self.path.parent.resolve()

    @property
    def module_path(self) -> str:
        return ".".join(Path(self.folder).parts)

    @property
    def stem(self) -> str:
        return Path(self.filename).stem


@dataclass
class ToolFolderMetadata:
    """Metadata describing how a tool folder should be displayed."""

    title: Optional[str] = None
    extra_title_description: str = ""
    always_expand: bool = False
    start_collapsed: Optional[bool] = None
    priority: ToolFolderPriority = ToolFolderPriority.LAST

    def __init__(self, **kwargs: Any):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def get_display_title(self, fallback_title: str) -> str:
        base = self.title or fallback_title
        if self.extra_title_description:
            return f"{base} - {self.extra_title_description}"
        return base

    def is_collapsed(self) -> bool:
        if self.always_expand:
            return False
        if self.start_collapsed is not None:
            return self.start_collapsed
        return True


def discover_tools(root: Path, folder_pattern: str, prefix: str, is_recursive: bool) -> List[ToolEntry]:
    tools: List[ToolEntry] = []
    for folder in discover_tool_folders(root, folder_pattern, is_recursive):
        for child in sorted(folder.iterdir()):
            if child.is_file() and is_tool_file(child, prefix):
                folder_rel = folder.relative_to(root)
                tools.append(ToolEntry(folder=str(folder_rel), filename=child.name, path=child))
    return tools


def discover_tool_folders(root: Path, folder_pattern: str, is_recursive: bool = False) -> List[Path]:
    pattern = re.compile(folder_pattern)
    folders: List[Path] = []
    # Choose iterator based on recursion flag
    iterator = root.rglob("*") if is_recursive else root.iterdir()
    
    for p in sorted(iterator):
        if p.is_dir() and pattern.match(p.name):
            LOG(f"Discovered tool folder: {p}, pattern: {folder_pattern}")
            folders.append(p)
        # else:
            # LOG(f"Skipped path: {p}, does not match folder pattern: {folder_pattern}")
    return folders


def is_tool_file(path: Path, prefix: str) -> bool:
    name = path.name
    if name in HIDDEN_TOOL_FILENAMES:
        return False
    if not name.startswith(prefix):
        return False
    if path.suffix == ".py":
        return True
    # Allow any executable file
    return os.access(str(path), os.X_OK)


def get_python_tool_help_output(tool: ToolEntry) -> Optional[str]:
    cmd = [sys.executable, str(tool.path), "-h"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        out = res.stdout.strip()
        err = res.stderr.strip()
        text = out or err
        if text:
            return text
    except Exception:
        LOG(f"Error getting help output for tool: {tool.full_path}")


def build_examples_epilog(templates: List[ToolTemplate], script_path: Path) -> str:
    """
    Build a help epilog string from a list of ToolTemplate entries.
        Each example line shows a runnable command using the current script path.
    """
    if not templates:
        return ""

    lines: List[str] = ["Examples:"]
    script_str = str(script_path)
    for i, t in enumerate(templates, 1):
        # Build argument string
        arg_parts: List[str] = []
        for arg, value in t.args.items():
            if isinstance(value, list):
                # arg then multiple values
                part = " ".join([arg] + [str(v) for v in value])
                arg_parts.append(part)
            elif isinstance(value, bool):
                arg_parts.append(f"{arg} {str(value).lower()}")
            else:
                arg_parts.append(f"{arg} {value}")

        cmd = f"{script_str} {' '.join(arg_parts)}".rstrip()
        lines.append("")
        lines.append(f"# Example {i}: {t.name}")
        if t.extra_description:
            lines.append(f"# {t.extra_description}")
        lines.append(cmd)

    return "\n".join(lines)


def load_tools_metadata(folder: Path) -> ToolFolderMetadata:
    """Load metadata customizations for a tools folder if present."""
    metadata_file_name = "_tools_metadata.py"
    metadata_path = folder / f"{metadata_file_name}"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}. Please check create it if haven't yet.")

    spec = importlib.util.spec_from_file_location(f"{folder.name}_tools_metadata", metadata_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to create module spec for {folder.name}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    metadata_factory = getattr(module, "get_tools_metadata", None)
    if metadata_factory is None:
        raise AttributeError(f"No get_tools_metadata function found in {folder.name}")

    metadata = metadata_factory()

    if isinstance(metadata, ToolFolderMetadata):
        return metadata

    if isinstance(metadata, dict):
        return ToolFolderMetadata(**metadata)

    raise TypeError(f"Unsupported metadata type {type(metadata)} for {folder.name}")


class PostActionType(IntEnum):
    NONE = 0
    RUN_CONTENT_IN_SHELL = auto()
    # PASTE_CONTENT_TO_SHELL_PROMPT = auto() #Have to set this but not safe: sudo sysctl -w dev.tty.legacy_tiocsti=1


def display_content_to_copy(
    content: str,
    purpose: str = "",
    is_copy_to_clipboard: bool = True,
    extra_prefix_descriptions: Optional[str] = None,
    post_actions: Optional[Set[PostActionType]] = None
) -> None:
    """
    Handles the final command display and clipboard copying.
    """
    purpose_text = f" to {purpose}" if purpose else ""

    # Initialize post_actions if None
    if post_actions is None:
        post_actions = set()

    # Try to copy to clipboard first
    clipboard_status = ""
    if is_copy_to_clipboard:
        try:
            pyperclip.copy(content)
            clipboard_status = " (copied to clipboard)"
        except Exception as e:
            clipboard_status = f" (clipboard failed: {e})"

    LOG(f"\n", show_time=False)
    if extra_prefix_descriptions:
        LOG(f"{extra_prefix_descriptions}", show_time=False)
        LOG(f"\n", show_time=False)
    LOG(f"✅ Content{purpose_text}{clipboard_status}:", show_time=True)
    LOG_LINE_SEPARATOR()
    LOG(f"{content}", show_time=False)
    LOG_LINE_SEPARATOR()

    # Process post actions
    for post_action in post_actions:
        if post_action == PostActionType.RUN_CONTENT_IN_SHELL:
            LOG(f"▶️  Running the above command in shell...", show_time=True)
            command_result: subprocess.CompletedProcess = run_shell(
                content, check_throw_exception_on_exit_code=False, want_shell=True, text=True)
            if command_result.returncode != 0:
                LOG_EXCEPTION_STR(
                    f"⚠️  Command exited with code {command_result.returncode}, error: {command_result.stderr}")


# def copy_to_wsl_shell_prompt(content: str) -> None:
#     """
#     Pushes content into the TTY's input buffer.
#     This only works on Unix-like systems (Linux, WSL, macOS).
#     """
#     if sys.platform == "win32" or fcntl is None or termios is None:
#         LOG("! Pasting to shell prompt is not supported on this platform.", show_time=False)
#         LOG("  (Content is in your clipboard for manual pasting).", show_time=False)
#         return
#     try:
#         # Get the file descriptor for standard input
#         fd = sys.stdin.fileno()
#         # Check if we are in an interactive terminal (TTY)
#         if not sys.stdin.isatty():
#             LOG("! Cannot paste to shell: Not running in an interactive TTY.", show_time=False)
#             return

#         # Push each character into the TTY's input buffer
#         for char in content:
#             # TIOCSTI: Terminal Input Output Control, Simulate Terminal Input
#             fcntl.ioctl(fd, termios.TIOCSTI, char.encode('utf-8'))

#     except (IOError, OSError) as e:
#         LOG(f"! Failed to paste to shell prompt: {e}", show_time=False)
#         LOG("  This feature (TIOCSTI) might be disabled by your system admin.", show_time=False)
#     except Exception as e:
#         LOG(f"! An unexpected error occurred during shell paste: {e}", show_time=False)


def open_path_in_explorer(file_path: Path) -> None:
    """
    Open Windows Explorer from WSL and highlight the specified file.
    """
    try:
        # Convert path using helper
        windows_path = convert_wsl_to_win_path(file_path)
        # Launch Explorer with selected file
        command_result = run_shell(
            [CMD_EXPLORER, WSL_SELECT_FLAG, windows_path],
            check_throw_exception_on_exit_code=False,
            # When this code runs under native Windows Python, do not wrap Explorer with `wsl`.
            is_run_wsl_if_window=False
        )

        if command_result.returncode != 0:
            LOG(f"{LOG_PREFIX_MSG_WARNING} Explorer returned code {command_result.returncode} for '{file_path}'")
            return
        LOG(f"Opened Explorer to highlight '{file_path}'")

    except SystemExit as e:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Failed to open Explorer (non-fatal): {e}")
    except Exception as e:
        LOG(f"Failed to open Explorer: {e}")


def run_win_cmd(command: str) -> Tuple[str, str, int]:
    """
    Run a Windows command from WSL and capture its output.
    Returns (stdout, stderr, returncode)
    """
    try:
        # Capture stdout + stderr, Decode to str instead of bytes
        result = run_shell(["cmd.exe", "/C", command], capture_output=True, text=True, check_throw_exception_on_exit_code=False)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        LOG(f"Executed Windows command: {command}")
        if stdout:
            LOG(f"[STDOUT] {stdout}")
        if stderr:
            LOG(f"[STDERR] {stderr}")

        return stdout, stderr, result.returncode

    except Exception as e:
        LOG(f"Failed to run Windows command: {e}")
        return "", str(e), -1

def _run_taskkill_for_pid(pid: int, force: bool = False) -> None:
    cmd = ["taskkill.exe"]
    if force:
        cmd.append("/F")
    cmd.extend(["/PID", str(pid), "/T"])
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.stdout.strip():
            LOG(f"{LOG_PREFIX_MSG_INFO} taskkill stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            stderr_text = result.stderr.strip()
            if "not found" in stderr_text.lower():
                LOG(f"{LOG_PREFIX_MSG_INFO} taskkill notice: {stderr_text}")
            else:
                LOG(f"{LOG_PREFIX_MSG_WARNING} taskkill stderr: {stderr_text}")
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Failed to execute taskkill for pid={pid}: {exc}")


def _send_signal_to_process_group(process: subprocess.Popen, sig: int) -> None:
    try:
        pgid = os.getpgid(process.pid)
        os.killpg(pgid, sig)
    except Exception:
        pass


def _wait_for_exit(process: subprocess.Popen, timeout_sec: float) -> bool:
    deadline = time.time() + max(0.0, float(timeout_sec))
    while process.poll() is None and time.time() < deadline:
        time.sleep(0.05)
    return process.poll() is not None


def _stop_win_process_tree(process: subprocess.Popen, graceful_timeout_sec: float = 2.0) -> None:
    if process.poll() is not None:
        return
    pid = int(process.pid)
    LOG(f"{LOG_PREFIX_MSG_INFO} Stopping process pid={pid} gracefully using local signals...")
    signal_plan = [
        ("SIGINT", signal.SIGINT, lambda: process.send_signal(signal.SIGINT), graceful_timeout_sec),
        ("SIGTERM", signal.SIGTERM, process.terminate, 1.5),
        ("SIGKILL", signal.SIGKILL, process.kill, 1.0),
    ]
    for idx, (sig_name, sig_value, send_to_process, wait_timeout_sec) in enumerate(signal_plan):
        try:
            send_to_process()
        except Exception:
            pass
        _send_signal_to_process_group(process, sig_value)
        if _wait_for_exit(process, wait_timeout_sec):
            return
        if idx < len(signal_plan) - 1:
            next_sig_name = signal_plan[idx + 1][0]
            LOG(f"{LOG_PREFIX_MSG_WARNING} Process pid={pid} did not exit after {sig_name}. Escalating to {next_sig_name}...")

    # Final fallback when local signaling cannot reach underlying Windows tree.
    LOG(f"{LOG_PREFIX_MSG_WARNING} Local signals could not stop pid={pid}. Trying taskkill fallback...")
    _run_taskkill_for_pid(pid, force=True)
    if not _wait_for_exit(process, 1.5):
        LOG(f"{LOG_PREFIX_MSG_WARNING} Process pid={pid} still appears alive after all stop attempts.")


def run_module_via_win_python(module_path: str, module_args: Optional[List[str]] = None, package_root: str | Path = LOCAL_TOOL_REPO_PATH,
                              win_python_executable_path: Optional[str] = None, graceful_shutdown_timeout_sec: float = 2.0) -> int:
    """Run a Python module through Windows Python and stop reliably on Ctrl+C by killing the process tree."""
    module_args = [str(arg) for arg in (module_args or [])]
    package_root_path = Path(package_root).expanduser()
    win_python_path = win_python_executable_path or get_win_python_executable_path_for_wsl()
    cmd = [str(win_python_path), "-m", module_path, *module_args]
    LOG(f"{LOG_PREFIX_MSG_INFO} Running Win Python module via shared runner: {' '.join(shlex.quote(str(part)) for part in cmd)}")
    # Detach child into its own session so terminal Ctrl+C is handled by this launcher process.
    # This avoids WSL interop cases where SIGINT appears to be delivered only to the Win child.
    process = subprocess.Popen(cmd, cwd=str(package_root_path), start_new_session=True)
    interrupted = False
    stop_requested = False
    previous_sigint_handler = None

    def _request_stop() -> None:
        nonlocal stop_requested
        if stop_requested:
            return
        stop_requested = True
        LOG(f"{LOG_PREFIX_MSG_INFO} Ctrl+C received. Stopping Win Python process tree (pid={process.pid})...")
        _stop_win_process_tree(process=process, graceful_timeout_sec=graceful_shutdown_timeout_sec)

    def _on_sigint(signum, frame) -> None:
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        # Signal handlers should stay minimal. Do not run subprocess/taskkill logic here.

    try:
        previous_sigint_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, _on_sigint)
    except Exception:
        previous_sigint_handler = None
    try:
        while True:
            if interrupted:
                _request_stop()
                return 130
            return_code = process.poll()
            if return_code is not None:
                return return_code
            time.sleep(0.1)
    except KeyboardInterrupt:
        interrupted = True
        _request_stop()
        return 130
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to run Win Python module: {exc}")
        return 1
    finally:
        if previous_sigint_handler is not None:
            try:
                signal.signal(signal.SIGINT, previous_sigint_handler)
            except Exception:
                pass

def get_win_python_runner_cmd_invocation(module_path: str, package_root: str = f"{LOCAL_TOOL_REPO_PATH}") -> str:
    """Return command string that routes Win Python execution through a shared runner script."""
    package_root_str = str(Path(package_root).expanduser())
    package_root_q = quote_arg_value_if_need(package_root_str)
    local_python_q = quote_arg_value_if_need(get_local_python_runner_executable())
    runner_script_q = quote_arg_value_if_need(str(WIN_PYTHON_RUNNER_SCRIPT_PATH))
    module_q = quote_arg_value_if_need(module_path)
    WIN_PYTHON_TRACKED_MODULES.add(module_path)
    return f"cd {package_root_q} && {local_python_q} {runner_script_q} --module {module_q} --package-root {package_root_q}"


def get_registered_win_python_modules() -> List[str]:
    """Return module paths currently registered for Win Python template invocation."""
    return sorted(WIN_PYTHON_TRACKED_MODULES)


def get_win_python_executable_path_for_wsl() -> str:
    """Return python executable path respecting template flags."""
    current_python_executable = sys.executable
    LOG(f"{LOG_PREFIX_MSG_INFO} Python runtime executable (sys.executable): {current_python_executable}")
    stdout, stderr, returncode = run_win_cmd("where python")
    if returncode != 0 or not stdout:
        LOG(f"Failed to detect Windows python (stdout='{stdout}', stderr='{stderr}').")
        return current_python_executable

    for candidate in stdout.splitlines():
        candidate = candidate.strip()
        if not candidate:
            continue
        wsl_path = convert_win_to_wsl_path(candidate)
        if wsl_path:
            LOG(f"{LOG_PREFIX_MSG_INFO} Windows python candidate selected from 'where python': {candidate} -> {wsl_path}")
            return wsl_path

    LOG(f"Could not parse Windows python path from output: {stdout}.")
    return current_python_executable
