from pathlib import Path
from enum import Enum
import hashlib
import os
from pathlib import Path, PosixPath, WindowsPath
import shlex
import shutil
import stat
from datetime import datetime
import time
from typing import Any, Callable, Tuple, Union
import xml.etree.ElementTree as ET

from dev.dev_common.core_utils import LOG, LOG_EXCEPTION, LOG_EXCEPTION_STR, run_shell


def expand_and_check_path(path_str: str) -> Tuple[bool, str]:
    """Expand a path (user and env vars) and check existence.

    Returns a tuple of (exists, expanded_path).
    """
    # 1. Clean the input string by removing leading/trailing whitespace and quotes.
    cleaned_path = path_str.strip().strip("'\"")
    # 2. Expand user and environment variables (e.g., '~' or '$HOME').
    expanded_path = os.path.expanduser(os.path.expandvars(cleaned_path))
    # 3. Convert to an absolute path to ensure the check is not relative to the CWD.
    absolute_path = os.path.abspath(expanded_path)
    # 4. Check if the final, absolute path exists.
    exists = os.path.exists(absolute_path)

    return exists, absolute_path


def copy_file(src_path: str, dst_path: str) -> None:
    shutil.copy(src_path, dst_path)


def remove_file(file_path: str) -> None:
    if os.path.exists(file_path):
        os.remove(file_path)


def clear_directory(dir_path: Union[str, Path], remove_dir_itself: bool = False) -> None:
    """
    Remove everything inside a directory (optionally the directory itself).
    Handles read-only files/folders via callbacks and attempts sudo fallback on POSIX.
    """
    path = Path(dir_path)
    if not path.exists():
        LOG(f"Directory does not exist: {path}")
        return

    # Helper: Core removal logic
    def remove_with_fallback(target: Path) -> None:
        is_dir = target.is_dir() and not target.is_symlink()

        try:
            make_path_writable_recursively(target)
            if is_dir:
                LOG(f"Removing directory: {target}")
                # onerror=on_rm_error handles read-only files inside the dir
                shutil.rmtree(target)
            else:
                LOG(f"Removing file/link: {target}")
                target.unlink()
        # except FileNotFoundError:
        #     LOG(f"Target already removed: {target}")
        #     pass  # Race condition: it's already gone
        except Exception as e:
            LOG(f"Failed to remove {target}: {e}")
            LOG(f"Permission denied. Attempting sudo fallback for: {target}")
            target_path = str(target)
            # if is_platform_windows():
            #     target_path = convert_win_to_wsl_path(target_path)
            cmd = f"sudo rm -rf {shlex.quote(target_path)}"
            run_shell(cmd)

    # 1. If we are removing the directory itself, we treat it as one big target
    if remove_dir_itself:
        remove_with_fallback(path)
        if path.exists():
            LOG_EXCEPTION_STR(f"Failed to remove directory: {path}!")
        return

    # 2. If clearing contents only, iterate children
    try:
        # Use list() to consume the generator so we don't modify the directory while iterating
        for item in list(path.iterdir()):
            remove_with_fallback(item)
    except FileNotFoundError:
        # The parent directory might have been deleted by another process
        pass


def make_path_writable_recursively(path: Path) -> None:
    """
    Make a file or directory (recursively) writable by the current user.
    Directories: add u+w,u+x; Files: add u+w.
    """
    try:
        path.stat()
    except FileNotFoundError:
        LOG(f"Path not found: {path}")
        return

    def _chmod_path(p: Path, extra: int) -> None:
        st = p.stat()
        os.chmod(p, st.st_mode | extra)

    if path.is_dir():
        _chmod_path(path, stat.S_IWUSR | stat.S_IXUSR)
        for root, dirs, files in os.walk(path):
            for d in dirs:
                _chmod_path(Path(root) / d, stat.S_IWUSR | stat.S_IXUSR)
            for f in files:
                _chmod_path(Path(root) / f, stat.S_IWUSR)
    else:
        _chmod_path(path, stat.S_IWUSR)


def get_file_md5sum(file_path: str) -> str:
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5


def read_file_content(file_path: str, encoding='utf-8', errors=None) -> str:
    """Reads the content of a file and returns it as a string."""
    with open(file_path, 'r', encoding=encoding, errors=errors) as f:
        return f.read()


def get_files_in_path(path: str, recursive: bool = True) -> list[str]:
    """
    Get all files in a directory.

    :param path: The path to the directory.
    :param recursive: If True, search recursively.
    :return: A list of file paths.
    """
    files = []
    if recursive:
        for root, _, filenames in os.walk(path):
            for filename in filenames:
                files.append(os.path.join(root, filename))
    else:
        for filename in os.listdir(path):
            if os.path.isfile(os.path.join(path, filename)):
                files.append(os.path.join(path, filename))
    return files


class WriteMode(Enum):
    """Enum for different file writing modes."""
    OVERWRITE = 'w'      # Write (overwrite existing content)
    APPEND = 'a'     # Append to existing content
    EXCLUSIVE = 'x'  # Exclusive creation (fails if file exists)


def write_to_file(file_path: str, content: str, mode: WriteMode = WriteMode.OVERWRITE) -> None:
    """
    Write content to a file with the specified mode (overwrite, append, or exclusive).
    """
    with open(file_path, mode.value) as f:
        f.write(content)


def is_same_xml(f1: Union[str, Path], f2: Union[str, Path]) -> bool:
    def canonicalize(p: Union[str, Path]):
        p = Path(p)

        def norm(e):
            e.attrib = dict(sorted(e.attrib.items()))
            for c in e:
                norm(c)
            e[:] = sorted(e, key=lambda x: (x.tag, sorted(x.attrib.items())))
        root = ET.parse(p).getroot()
        norm(root)
        return ET.tostring(root, encoding='utf-8')
    return canonicalize(f1) == canonicalize(f2)


def is_current_relative_to(current: Union[str, Path], target: Union[str, Path]) -> bool:
    """
    Check if the current path is relative to the target path. This also support symlinks by resolving both paths.
    """
    current_resolved = Path(current).resolve()
    target_resolved = Path(target).resolve()

    try:
        return current_resolved.is_relative_to(target_resolved)
    except (ValueError, AttributeError):
        # Fallback for older Python versions without is_relative_to
        try:
            current_resolved.relative_to(target_resolved)
            return True
        except ValueError:
            return False


def use_posix_paths():
    """Override Path to always use POSIX-style paths in string representation."""
    LOG("Using POSIX-style paths for all Path string representations.")
    _original_path_str = Path.__str__
    _original_posix_str = PosixPath.__str__
    _original_windows_str = WindowsPath.__str__
    Path.__str__ = lambda self: _original_path_str(self).replace('\\', '/')
    PosixPath.__str__ = lambda self: _original_posix_str(self).replace('\\', '/')
    WindowsPath.__str__ = lambda self: _original_windows_str(self).replace('\\', '/')
