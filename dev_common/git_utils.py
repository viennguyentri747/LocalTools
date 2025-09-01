#!/usr/bin/env python3.10

import subprocess
import re
from pathlib import Path
from typing import Optional

# Assuming LOG and message prefixes are imported from dev_common
from dev_common import *

# --- Constants ---
CMD_GIT = 'git'


def sanitize_ref_for_filename(ref: str) -> str:
    """Sanitizes a git ref name to be used in a filename."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', ref)


def git_fetch(repo_path: Path) -> bool:
    """
    Runs 'git fetch --all --prune' in the specified repository.

    Args:
        repo_path: The local path to the git repository.

    Returns:
        A tuple containing a success boolean and a message.
    """
    command = [CMD_GIT, 'fetch', '--all', '--prune']
    try:
        LOG(f"Fetching latest changes from all remotes in '{repo_path.name}'...")
        subprocess.run(
            command,
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        LOG("Fetch completed successfully.")
        return True
    except Exception as e:
        LOG(f"'git fetch' failed for '{repo_path}' with error: {e}", file=sys.stderr)
        return False


def extract_git_diff(repo_path: Path, base_ref: str, target_ref: str) -> Optional[str]:
    """
    Extracts a git diff between two references using --patch-with-stat.

    Args:
        repo_path: The local path to the git repository.
        base_ref: The base ref for the diff.
        target_ref: The target ref for the diff.

    Returns:
        The diff content as a string, or None on failure.
    """
    if not repo_path.is_dir() or not (repo_path / '.git').exists():
        LOG(f"The path '{repo_path}' is not a valid git repository.")
        return None

    command = [CMD_GIT, 'diff', '--patch-with-stat', f"{base_ref}..{target_ref}"]

    try:
        LOG(f"Running git diff in '{repo_path}'... Command:\n{' '.join(command)}")
        process = subprocess.run(
            command,
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return process.stdout
    except subprocess.CalledProcessError as e:
        error_msg = (
            f"'git diff' failed for '{repo_path}' with exit code {e.returncode}.\n"
            f"  Command: {' '.join(command)}\n"
            f"  Stderr: {e.stderr.strip()}"
        )
        LOG(error_msg, file=sys.stderr)
        return None
    except Exception as e:
        LOG(f"An unexpected error occurred while extracting diff: {e}", file=sys.stderr)
        return None
