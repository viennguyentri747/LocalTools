import hashlib
import os
from typing import Tuple


def expand_and_check_path(path_str: str) -> Tuple[bool, str]:
    """Expand a path (user and env vars) and check existence.

    Returns a tuple of (exists, expanded_path).
    """
    expanded = os.path.expanduser(os.path.expandvars(path_str))
    return os.path.exists(expanded), expanded


def get_file_md5sum(file_path):
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5
