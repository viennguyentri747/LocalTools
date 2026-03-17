#!/usr/local/bin/local_python

from typing import Tuple
import logging

from dev.dev_common.constants import *
from dev.dev_common.core_independent_utils import read_value_from_credential_file
from dev.dev_common.network_utils import run_ssh_command
from mcp.server.fastmcp import FastMCP

# Configuration
SSH_HOST_IP_PREFIX = SSM_NORMAL_IP_PREFIX
SSH_USER = SSM_USER
ACU_HOST_IP = ACU_IP
ACU_USER_NAME = ACU_USER
SSH_PASSWORD = read_value_from_credential_file(CREDENTIALS_FILE_PATH, UT_PWD_KEY_NAME)

mcp = FastMCP("SecureSSH")

# --- Security Lists ---
DESTRUCTIVE = ["rm", "mv", "dd", "shred", "format", "mkfs"]
SYSTEM_CTRL = ["reboot", "halt", "poweroff", "kill", "pkill", "stop", "init", "shutdown"]
PERMISSIONS = ["chmod", "chown", "chgrp", "visudo"]
NETWORK     = ["wget", "curl", "nc", "netcat", "ssh", "scp", "ftp", "tftp"]
EDITORS     = ["vi", "vim", "nano", "ed", "sed", "tee"]

UNSAFE_COMMANDS = DESTRUCTIVE + SYSTEM_CTRL + PERMISSIONS + NETWORK + EDITORS

def is_command_safe(command: str) -> Tuple[bool, str]:
    """Validates command against shell injection, blocklist, and dangerous flags."""
    parts = command.split()
    if not parts:
        return (False, "Empty command")

    base_command = parts[0]

    # 1. Block Shell Injection Characters
    # Added \n to prevent command chaining in some shells
    forbidden_chars = [";", "&&", "||", "|", ">", "<", "`", "$", "\n"]
    found_chars = [char for char in command if char in forbidden_chars]
    if found_chars:
        return (False, f"Shell injection detected, char found: {found_chars[0]}")

    # 2. Check Blocklist (Command Name)
    if base_command in UNSAFE_COMMANDS:
        return (False, f"Command '{base_command}' is restricted for security.")

    # 3. Check for Dangerous Flags
    # Prevents escaping grep/find/sed to run or read unauthorized data
    forbidden_flags = ["-exec", "-i", "--delete", "-f"]
    for flag in forbidden_flags:
        if any(flag == p or p.startswith(flag + "=") for p in parts):
            return (False, f"Use of forbidden flag: {flag}")

    return (True, "Command allowed")


def build_ssh_host_ip(last_ip_octet: int) -> str:
    if not (0 <= last_ip_octet <= 255):
        raise ValueError("last_ip_octet must be between 0 and 255.")
    return f"{SSH_HOST_IP_PREFIX}.{last_ip_octet}"


@mcp.tool()
def run_ssm_cmd(command: str, last_ip_octet: int) -> str:
    """Executes a restricted remote command on the SSM using password auth."""
    if not SSH_PASSWORD:
        return "Error: SSH_PASSWORD not found in credentials file."

    # Validate security
    is_safe, reason = is_command_safe(command)
    if not is_safe:
        return f"Security Error: {reason}"

    try:
        ssh_host_ip = build_ssh_host_ip(last_ip_octet)
        output, error = run_ssh_command(ssh_host_ip, SSH_USER, SSH_PASSWORD, command, timeout=5)
        if error:
            return f"Remote Error: {error}"
        return output if output else "Success (No output)."
    except Exception as e:
        return f"Connection Failed: {str(e)}"


@mcp.tool()
def run_acu_cmd(command: str, last_ip_octet: int) -> str:
    """Executes a restricted command on ACU through SSM jump host."""
    if not SSH_PASSWORD:
        return "Error: SSH_PASSWORD not found in credentials file."

    # Validate security
    is_safe, reason = is_command_safe(command)
    if not is_safe:
        return f"Security Error: {reason}"

    try:
        ssh_host_ip = build_ssh_host_ip(last_ip_octet)
        output, error = run_ssh_command( ACU_HOST_IP, ACU_USER_NAME, SSH_PASSWORD, command, timeout=5, jump_host_ip=ssh_host_ip, jump_user=SSH_USER, jump_password=SSH_PASSWORD )
        if error:
            return f"Remote Error: {error}"
        return output if output else "Success (No output)."
    except Exception as e:
        return f"Connection Failed: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")