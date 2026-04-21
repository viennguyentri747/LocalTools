#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
from os import path as osp
from pathlib import Path
import re
from typing import List, Optional, Sequence, Tuple

from dev.dev_common import LOCAL_TOOL_REPO_PATH, convert_wsl_to_win_path, run_module_via_win_python


ARG_MODULE = "--module"
ARG_PACKAGE_ROOT = "--package-root"
ARG_WIN_PYTHON_PATH = "--win-python-path"
ARG_SHUTDOWN_TIMEOUT_SEC = "--shutdown-timeout-sec"
PATH_OPTION_TOKENS = ("path", "paths", "dir", "dirs", "file", "files", "folder", "folders", "root")


def _is_path_option_name(option_name: str) -> bool:
    normalized = option_name.strip().lower().lstrip("-")
    if not normalized:
        return False
    for token in PATH_OPTION_TOKENS:
        if token in normalized:
            return True
    return False


def _looks_like_wsl_or_unc_path(value: str) -> bool:
    stripped = str(value).strip().strip('"').strip("'")
    if not stripped:
        return False
    if re.match(r"^[a-zA-Z]:[\\/]", stripped):
        return False
    if stripped.startswith(("/mnt/", "/home/", "/tmp/", "/")):
        return True
    if stripped.startswith(("//wsl.localhost/", "\\\\wsl.localhost\\")):
        return True
    return False


def _normalize_path_arg_value(value: str) -> str:
    raw_value = str(value)
    stripped = raw_value.strip()
    if not _looks_like_wsl_or_unc_path(stripped):
        return raw_value
    if stripped.startswith(("//wsl.localhost/", "\\\\wsl.localhost\\")):
        return stripped.replace("/", "\\")
    try:
        win_value = convert_wsl_to_win_path(Path(stripped))
        if win_value:
            return win_value
    except Exception:
        pass
    return raw_value


def normalize_forwarded_module_args(forwarded_args: Sequence[str]) -> List[str]:
    """Normalize forwarded CLI args for Win-Python execution.

    Behavior:
    - Only path-like option values are converted (option names containing tokens like path/dir/file/root).
    - Supports `--opt value`, `--opt=value`, and multi-value path options.
    - Converts WSL/UNC-style values to Windows paths so Win Python can access them.
    - Leaves non-path options and positional values unchanged.
    """
    args = [str(arg) for arg in forwarded_args]
    normalized_args: List[str] = []
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token == "--":
            normalized_args.extend(args[idx:])
            break
        if not token.startswith("-"):
            normalized_args.append(token)
            idx += 1
            continue

        if "=" in token: # `--opt=value`
            option_name, option_value = token.split("=", 1)
            if _is_path_option_name(option_name):
                option_value = _normalize_path_arg_value(option_value)
            normalized_args.append(f"{option_name}={option_value}")
            idx += 1
            continue

        normalized_args.append(token)
        idx += 1
        if not _is_path_option_name(token):
            continue
        while idx < len(args):
            #Consume multi-value path options
            candidate = args[idx]
            if candidate == "--" or (candidate.startswith("-") and not osp.isabs(candidate)):
                break
            normalized_args.append(_normalize_path_arg_value(candidate))
            idx += 1

    return normalized_args


def parse_args(argv: Optional[Sequence[str]] = None) -> Tuple[argparse.Namespace, List[str]]:
    parser = argparse.ArgumentParser(description="Run module via shared Win Python launcher with reliable Ctrl+C stop.")
    parser.add_argument(ARG_MODULE, required=True, help="Dotted module path to run with Windows Python.")
    parser.add_argument(ARG_PACKAGE_ROOT, default=str(LOCAL_TOOL_REPO_PATH), help="Working directory to run the module from.")
    parser.add_argument(ARG_WIN_PYTHON_PATH, default=None, help="Optional explicit Windows Python path (WSL path form).")
    parser.add_argument(ARG_SHUTDOWN_TIMEOUT_SEC, type=float, default=2.0, help="Grace period before force-killing process tree after Ctrl+C.")
    parsed, forwarded_args = parser.parse_known_args(argv)
    filtered_args = [arg for arg in forwarded_args if arg != "--"]
    return parsed, normalize_forwarded_module_args(filtered_args)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parsed, module_args = parse_args(argv)
    exit_code = run_module_via_win_python(
        module_path=str(parsed.module),
        module_args=module_args,
        package_root=Path(parsed.package_root).expanduser(),
        win_python_executable_path=parsed.win_python_path,
        graceful_shutdown_timeout_sec=float(parsed.shutdown_timeout_sec),
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
