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

def copy_file(src_path, dst_path):
    shutil.copy(src_path, dst_path)

def get_file_md5sum(file_path):
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5
