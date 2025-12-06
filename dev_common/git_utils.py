#!/home/vien/local_tools/MyVenvFolder/bin/python

import subprocess
import re
import sys
from pathlib import Path
from typing import List, Optional

from dev_common.core_utils import *
from dev_common.input_utils import prompt_confirmation

# --- Constants ---
CMD_GIT = 'git'


def run_git_wsl(*args, **kwargs):
    """
    Wrapper around run_shell that enforces WSL execution when running on Windows.
    Normalizes legacy 'check' argument to the proper run_shell flag.
    """
    if 'check' in kwargs:
        kwargs['check_throw_exception_on_exit_code'] = kwargs.pop('check')
    else:
        kwargs['check_throw_exception_on_exit_code'] = True  # True by default

    kwargs['is_run_this_in_wsl'] = is_platform_windows()
    return run_shell(*args, **kwargs)


def sanitize_ref_for_filename(ref: str) -> str:
    """Sanitizes a git ref name to be used in a filename."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', ref)


def git_get_current_branch(repo_path: Path | str) -> Optional[str]:
    """Returns the current branch name of the given repo, or None if the repo is not a git repo."""
    current_branch = run_git_wsl("git branch --show-current", cwd=repo_path,
                                       capture_output=True, text=True).stdout.strip()
    return current_branch


def git_get_sha1_of_head_commit(repo_path: Path) -> Optional[str]:
    """Returns the SHA1 of the HEAD commit in the given repo, or None if the repo is not a git repo."""
    commit_sha1 = run_git_wsl("git rev-parse HEAD", cwd=repo_path, capture_output=True,
                                    text=True).stdout.strip()
    return commit_sha1


def git_is_ancestor(ancestor_ref: str, descentdant_ref: str, cwd: Union[str, Path]) -> bool:
    """
    Checks the ancestry relationship between two Git references.

    Args:
        ref1: The first Git reference (commit hash, branch, tag).
        ref2: The second Git reference.
        cwd: The working directory for the Git command.

    Returns:
        True if the ancestry condition is met, False otherwise.
    """
    cmd = f"git merge-base --is-ancestor {ancestor_ref} {descentdant_ref}"
    result = run_git_wsl(cmd, cwd=cwd, check_throw_exception_on_exit_code=False)
    return result.returncode == 0


def git_is_ref_or_branch_existing(repo_path: Path, branch_name: str) -> bool:
    """Checks if a branch exists in the given repo."""
    result = run_git_wsl(
        f"git rev-parse --verify {branch_name}",
        cwd=repo_path,
        capture_output=True,
        text=True,
        check_throw_exception_on_exit_code=False
    )
    return result.returncode == 0


def checkout_branch(repo_path: Path, branch_name: str, *, create_when_missing: bool = True) -> bool:
    """Checkout (optionally create) a branch inside ``repo_path``.

    Returns ``True`` when the checkout succeeds and ``False`` otherwise.
    """
    current_branch = git_get_current_branch(repo_path)
    if current_branch == branch_name:
        LOG(f"✅ Already on branch '{branch_name}'.")
        return True

    LOG(f"🔀 Switching to branch '{branch_name}' in '{repo_path}'...")
    branch_exists = git_is_ref_or_branch_existing(repo_path, branch_name)
    if not branch_exists and not create_when_missing:
        LOG(
            f"❌ ERROR: Branch '{branch_name}' does not exist in '{repo_path}' and auto-create is disabled."
        )
        return False

    checkout_cmd: List[str]
    if branch_exists:
        checkout_cmd = [CMD_GIT, 'checkout', branch_name]
    else:
        checkout_cmd = [CMD_GIT, 'checkout', '-b', branch_name]
    run_git_wsl(checkout_cmd, cwd=repo_path, check=True)
    LOG(f"✅ Now on branch '{branch_name}'.")


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
        run_git_wsl(command, cwd=repo_path, check=True, capture_output=True, text=True, encoding='utf-8')
        LOG("Fetch completed successfully.")
        return True
    except Exception as e:
        LOG(f"'git fetch' failed for '{repo_path}' with error: {e}", file=sys.stderr)
        return False


def git_pull(repo_path: Path, remote_name: str, branch_name: str) -> bool:
    """
    Runs 'git pull' in the specified repository.

    Args:
        repo_path: The local path to the git repository.
        remote_name: The name of the remote to pull from.
        branch_name: The name of the branch to pull.

    Returns:
        A tuple containing a success boolean and a message.
    """
    command = [CMD_GIT, 'pull', remote_name, branch_name]
    try:
        LOG(f"Pulling latest changes from '{remote_name}' in '{repo_path.name}'...")
        run_git_wsl(command, cwd=repo_path, check=True, capture_output=True, text=True, encoding='utf-8')
        LOG("Pull completed successfully.")
        return True
    except Exception as e:
        LOG(f"'git pull' failed for '{repo_path}' with error: {e}", file=sys.stderr)
        return False


def git_get_git_remotes(repo_path: Path) -> List[str]:
    """
    Get a list of remote names for a git repository.

    Args:
        repo_path: The local path to the git repository.

    Returns:
        A list of remote names.
    """
    if not repo_path.is_dir() or not (repo_path / '.git').exists():
        LOG(f"The path '{repo_path}' is not a valid git repository.")
        return []

    command = [CMD_GIT, 'remote']
    try:
        process = run_git_wsl(
            command,
            cwd=repo_path,
            check_throw_exception_on_exit_code=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        remotes = process.stdout.strip().split('\n')
        return [remote for remote in remotes if remote]  # Filter out empty strings
    except subprocess.CalledProcessError as e:
        error_msg = (
            f"'git remote' failed for '{repo_path}' with exit code {e.returncode}.\n"
            f"  Command: {' '.join(command)}\n"
            f"  Stderr: {e.stderr.strip()}"
        )
        LOG(error_msg, file=sys.stderr)
        return []
    except Exception as e:
        LOG(f"An unexpected error occurred while getting remotes: {e}", file=sys.stderr)
        return []


def extract_git_diff(repo_local_path: Path, base_ref: str, target_ref: str) -> Optional[str]:
    """
    Extracts a git diff between two references using --patch-with-stat.

    Args:
        repo_path: The local path to the git repository.
        base_ref: The base ref for the diff.
        target_ref: The target ref for the diff.

    Returns:
        The diff content as a string, or None on failure.
    """
    if not repo_local_path.is_dir() or not (repo_local_path / '.git').exists():
        LOG(f"The path '{repo_local_path}' is not a valid git repository.")
        return None

    command = [CMD_GIT, 'diff', '--patch-with-stat', f"{base_ref}..{target_ref}"]

    try:
        LOG(f"Running git diff in '{repo_local_path}'... Command:\n{' '.join(command)}")
        process = run_git_wsl(command, cwd=repo_local_path, check_throw_exception_on_exit_code=True,
                                    capture_output=True, text=True, encoding='utf-8')
        return process.stdout
    except Exception as e:
        LOG_EXCEPTION(e)


def git_diff_on_file(repo_path: Path | str, base_ref: str, rel_path: str) -> str:
    """
    Returns the diff output of the specified path against a given ref.
    """
    result = run_git_wsl(f"{CMD_GIT} diff {base_ref} -- {rel_path}", cwd=repo_path,
                               capture_output=True, text=True)
    return result.stdout


def git_stage_and_commit(
    repo_path: Path,
    message: str,
    *,
    show_diff: bool = False,
    stage_paths: Optional[List[str]] = None,
    auto_confirm: bool = False,
    prompt: Optional[str] = None,
) -> bool:
    """
    Stage changes (optionally limited to specific paths) and create a commit in the given repo.

    Args:
        repo_path: Path to the git repository to operate in.
        message: Commit message.
        show_diff: If True, show the staged diff before committing.
        stage_paths: Specific paths to stage (relative or absolute). If None or empty, stage all changes (-A).
        auto_confirm: If True, skip interactive confirmation prompt.
        prompt: Optional custom confirmation prompt message.

    Returns:
        True if commit succeeded, False otherwise.
    """
    if not repo_path.is_dir() or not (repo_path / '.git').exists():
        LOG(f"❌ ERROR: The path '{repo_path}' is not a valid git repository.")
        return False

    if not auto_confirm:
        confirm_msg = prompt or f"Do you want to commit '{message}' to Git?"
        if not prompt_confirmation(confirm_msg):
            LOG("Skipped commit by user choice.")
            return False

    try:
        if stage_paths and len(stage_paths) > 0:
            # Convert paths to strings (git accepts absolute or relative)
            paths = [str(p) for p in stage_paths]
            run_git_wsl([CMD_GIT, 'add', *paths], check=True, cwd=repo_path)
        else:
            run_git_wsl([CMD_GIT, 'add', '-A'], check=True, cwd=repo_path)

        if show_diff:
            run_git_wsl([CMD_GIT, '--no-pager', 'diff', '--cached'], check=True, cwd=repo_path)

        run_git_wsl([CMD_GIT, 'commit', '-m', message], check=True, cwd=repo_path)
        LOG("✅ Changes committed successfully.")
        return True
    except Exception as e:
        LOG_EXCEPTION(e)
        return False


def git_get_porcelain_status_lines(repo_path: Path, exclude_pattern: str | None = None) -> List[str]:
    """Returns filtered list of porcelain status lines."""
    cmd = [f"{CMD_GIT}", "status", "--porcelain", "."]
    if exclude_pattern:
        cmd.append(exclude_pattern)

    result = run_git_wsl(
        cmd, cwd=repo_path, capture_output=True, text=True, check=False, is_run_this_in_wsl=is_platform_windows()
    )

    status_lines: List[str] = [line for line in result.stdout.splitlines() if line.strip()]
    return status_lines
