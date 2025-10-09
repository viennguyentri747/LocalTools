import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import List, Literal, Optional, Union
from datetime import datetime
import traceback


def run_shell(cmd: Union[str, List[str]], show_cmd: bool = True, cwd: Optional[Path] = None, check_throw_exception_on_exit_code: bool = True, stdout=None, stderr=None, text=None, capture_output: bool = False, encoding: str = 'utf-8', shell: bool = True, executable: Optional[str] = None, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """Echo + run a shell command"""
    if shell and isinstance(cmd, List):
        LOG(f"Shell mode but cmd is a list -> Converting to string...")
        cmd = ' '.join(shlex.quote(str(arg)) for arg in cmd)
    elif not shell and isinstance(cmd, str):
        LOG(f"Non-shell mode but cmd is a string -> Converting to list...")
        cmd = shlex.split(cmd)

    if show_cmd:
        LOG(f">>> {cmd} (cwd={cwd or Path.cwd()})")
    return subprocess.run(cmd, shell=shell, cwd=cwd, check=check_throw_exception_on_exit_code, stdout=stdout, stderr=stderr, text=text, capture_output=capture_output, encoding=encoding, executable=executable, timeout=timeout)


def change_dir(path: str):
    LOG(f"Changing directory to {path}")
    os.chdir(path)


def LOG(*values: object, sep: str = " ", end: str = "\n", file=None, highlight: bool = False, show_time=True, show_traceback: bool = False, flush: bool = True) -> None:
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

    if highlight:
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


def LOG_EXCEPTION_STR(exception: str, msg=None, exit: bool = True):
    LOG_EXCEPTION(exception=Exception(exception), msg=msg, exit=exit)


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

    # Compact traceback (just the relevant line)
    tb = traceback.extract_tb(exception.__traceback__)
    if tb:
        last_frame = tb[-1]
        LOG(f"- Location: {last_frame.filename}:{last_frame.lineno} in {last_frame.name}()", file=sys.stderr)

    if exit:
        sys.exit(1)
