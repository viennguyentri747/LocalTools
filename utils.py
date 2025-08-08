import hashlib
import os
from pathlib import Path
import subprocess
import sys
from typing import List, Literal, Optional, Union


def run_shell(cmd: Union[str, List[str]], cwd: Optional[Path] = None, check_throw_exception_on_exit_code: bool = True, stdout=None, stderr=None, text=None, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Echo + run a shell command"""
    LOG(f"\n>>> {cmd} (cwd={cwd or Path.cwd()})")
    is_shell = isinstance(cmd, str)
    return subprocess.run(cmd, shell=is_shell, cwd=cwd, check=check_throw_exception_on_exit_code, stdout=stdout, stderr=stderr, text=text, capture_output=capture_output)

def change_dir(path: str):
    LOG(f"Changing directory to {path}")
    os.chdir(path)

def get_file_md5sum(file_path):
    with open(file_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    return md5

def LOG(*values: object, sep: str = " ", end: str = "\n", file=None, highlight: bool = False):
    if highlight:
        HIGHLIGHT_COLOR = "\033[92m"  # green
        BOLD = "\033[1m"
        RESET = "\033[0m"
        print(f"{BOLD}{HIGHLIGHT_COLOR}", end="", file=file)  # turn to highlight color
        print(*values, sep=sep, end="", file=file)  # print message
        print(f"{RESET}", end=end, file=file)       # reset
    else:
        print(*values, sep=sep, end=end, file=file)


def is_diff_ignore_eol(file1: Path, file2: Path) -> bool:
    return normalize_lines(file1) != normalize_lines(file2)

def normalize_lines(p: Path) -> bytes:
    with p.open("rb") as f:
        return f.read().replace(b"\r\n", b"\n")
