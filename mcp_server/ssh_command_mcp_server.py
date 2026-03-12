#!/usr/local/bin/local_python

from dev.dev_common.constants import *
from dev.dev_common.core_independent_utils import read_value_from_credential_file
from dev.dev_common.network_utils import run_ssh_command
from mcp.server.fastmcp import FastMCP


# Configuration - It's safer to pull these from your environment
SSH_HOST_IP_PREFIX = SSM_NORMAL_IP_PREFIX
SSH_USER = SSM_USER
ACU_HOST_IP = ACU_IP
ACU_USER_NAME = ACU_USER
SSH_PASSWORD = read_value_from_credential_file(CREDENTIALS_FILE_PATH, UT_PWD_KEY_NAME)

SAFE_COMMANDS = ["find", "cat", "ls", "grep", "head", "tail"]
NOT_SO_SAFE_COMMANDS = ["reboot"]

mcp = FastMCP("SecureSSH")

def is_command_safe(command: str) -> bool:
    # Basic check: first word must be in whitelist
    # Also blocks shell chaining like ';' or '&&' to prevent injection
    parts = command.split()
    if not parts:
        return False

    base_command = parts[0]
    # Check for common shell injection characters
    forbidden = [";", "&&", "||", "|", ">", "<", "`", "$"]
    if any(char in command for char in forbidden):
        return False

    return base_command in SAFE_COMMANDS or base_command in NOT_SO_SAFE_COMMANDS


def build_ssh_host_ip(last_ip_octet: int) -> str:
    if not (0 <= last_ip_octet <= 255):
        raise ValueError("last_ip_octet must be between 0 and 255.")
    return f"{SSH_HOST_IP_PREFIX}.{last_ip_octet}"


@mcp.tool()
def run_ssm_cmd(command: str, last_ip_octet: int) -> str:
    """Executes a restricted remote command using password auth."""
    if not SSH_PASSWORD:
        return "Error: SSH_PASSWORD environment variable not set."

    if not is_command_safe(command):
        return f"Error: Command '{command}' is not permitted or contains unsafe characters."

    try:
        ssh_host_ip = build_ssh_host_ip(last_ip_octet)
        output, error = run_ssh_command(ssh_host_ip, SSH_USER, SSH_PASSWORD, command, timeout=5)
        if error:
            return f"Remote Error: {error}"
        return output if output else "Success (No output)."
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Connection Failed: {str(e)}"


@mcp.tool()
def run_acu_cmd(command: str, last_ip_octet: int) -> str:
    """Executes a restricted command on ACU through SSM jump host."""
    if not SSH_PASSWORD:
        return "Error: SSH_PASSWORD environment variable not set."

    if not is_command_safe(command):
        return f"Error: Command '{command}' is not permitted or contains unsafe characters."

    try:
        ssh_host_ip = build_ssh_host_ip(last_ip_octet)
        output, error = run_ssh_command(ACU_HOST_IP, ACU_USER_NAME, SSH_PASSWORD, command, timeout=5, jump_host_ip=ssh_host_ip,
                                        jump_user=SSH_USER, jump_password=SSH_PASSWORD)
        if error:
            return f"Remote Error: {error}"
        return output if output else "Success (No output)."
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Connection Failed: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
    #mcp.run()
