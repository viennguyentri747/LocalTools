import hashlib
from pathlib import Path
from typing import Literal


def get_file_md5sum(file_path):
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5


def LOG(*values: object, sep: str = " ", end: str = "\n", file=None):
    print(*values, sep=sep, end=end, file=file)

def is_diff_ignore_eol(file1: Path, file2: Path) -> bool:
    return normalize_lines(file1) != normalize_lines(file2)

def normalize_lines(p: Path) -> bytes:
    with p.open("rb") as f:
        return f.read().replace(b"\r\n", b"\n")