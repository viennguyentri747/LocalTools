from enum import Enum
import hashlib
import os
import shutil
from typing import Tuple


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


def clear_directory_content(dir_path: str) -> None:
    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)


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
