import os
import shlex
import shutil
from pathlib import Path
from typing import List, Union


def resolve_executable_path(cmd: Union[str, Path]) -> str:
    """Resolve executable path for any command; return original if unresolved."""
    cmd_str = str(cmd)
    if not cmd_str:
        return cmd_str
    expanded = os.path.expanduser(cmd_str)
    if os.path.sep in expanded or (os.path.altsep and os.path.altsep in expanded):
        return expanded if Path(expanded).exists() else cmd_str
    resolved = shutil.which(expanded)
    return resolved or cmd_str


def wrap_cmd_for_bash(cmd: str) -> str:
    return cmd if cmd.strip().startswith("bash -lic ") else f"bash -lic {shlex.quote(cmd)}"


def _proc_name(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except Exception:
        return ""


def get_shell_exec_cmd_as_list() -> List[str]:
    """
    Return the shell command with flags for executing commands as a list.
    Uses login shell (-l) to ensure PATH and environment are properly set up.

    Returns a list like ["bash", "-lc"] that can be used directly with subprocess.
    """
    shell = get_shell_name()
    return [shell, "-lc"]


def get_shell_name() -> str:
    """
    Return the shell command to use (bash/zsh/sh), preferring the *current* shell,
    not the login shell stored in $SHELL.
    """
    BASH = "bash"
    ZSH = "zsh"
    SH = "sh"

    # 1) If we're actually running inside bash/zsh, these are the most reliable.
    if os.environ.get("BASH_VERSION") and shutil.which(BASH):
        return BASH
    if os.environ.get("ZSH_VERSION") and shutil.which(ZSH):
        return ZSH

    # 2) Try to infer from the immediate parent process of this Python script.
    #    Works for interactive shell sessions, but may fail for nested processes
    #    (IDEs, make, systemd, etc.) where the parent isn't a shell.
    ppid = os.getppid()
    parent = _proc_name(ppid)
    KNOWN_SHELLS = (BASH, ZSH, SH)
    if parent in KNOWN_SHELLS and shutil.which(parent):
        return parent

    # 3) Fallback to user's preferred/login shell ($SHELL basename).
    env_shell = os.environ.get("SHELL")
    if env_shell:
        shell_name = os.path.basename(env_shell)
        if shutil.which(shell_name):
            return shell_name

    # 4) Final fallback
    return BASH if shutil.which(BASH) else SH
