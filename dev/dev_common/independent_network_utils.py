import sys
from typing import Optional, Tuple
import paramiko
from dev.dev_common.core_independent_utils import LOG, ELogType


def open_ssh_client(host_ip: str, user: str, password: Optional[str] = None, timeout: int = 5, jump_host_ip: Optional[str] = None,
                    jump_user: Optional[str] = None, jump_password: Optional[str] = None) -> Tuple[paramiko.SSHClient, Optional[paramiko.SSHClient], Optional[paramiko.Channel]]:
    """Open an SSH client, optionally tunneled through a jump host."""
    target_client = paramiko.SSHClient()
    target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    auth_kwargs = dict(password=password, look_for_keys=not password, allow_agent=not password)
    connect_kwargs = dict(hostname=host_ip, username=user, timeout=timeout, **auth_kwargs)
    jump_client = None
    jump_channel = None

    if jump_host_ip:
        jump_client = paramiko.SSHClient()
        jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        jump_connect_kwargs = dict(hostname=jump_host_ip, username=jump_user or user, timeout=timeout,
                                   password=jump_password or password, look_for_keys=not (jump_password or password), allow_agent=not (jump_password or password))

        LOG(f"Connecting to jump host {jump_host_ip} using jump args {jump_connect_kwargs}", file=sys.stderr, log_type=ELogType.DEBUG)
        jump_client.connect(**jump_connect_kwargs)
        jump_transport = jump_client.get_transport()
        if jump_transport is None:
            close_ssh_client(target_client, jump_client, jump_channel)
            raise RuntimeError(f"Jump host transport unavailable: {jump_host_ip}")
        jump_channel = jump_transport.open_channel('direct-tcpip', (host_ip, 22), ('127.0.0.1', 0))
        connect_kwargs["sock"] = jump_channel

    try:
        LOG(f"Connecting to remote host {host_ip} using args {connect_kwargs}", file=sys.stderr)
        target_client.connect(**connect_kwargs)
    except Exception:
        LOG(f"Failed to connect to {host_ip}", file=sys.stderr)
        close_ssh_client(target_client, jump_client, jump_channel)
        raise
    return target_client, jump_client, jump_channel


def close_ssh_client(target_client: Optional[paramiko.SSHClient], jump_client: Optional[paramiko.SSHClient] = None,
                     jump_channel: Optional[paramiko.Channel] = None) -> None:
    if target_client:
        target_client.close()
    if jump_channel:
        jump_channel.close()
    if jump_client:
        jump_client.close()


def run_ssh_command(host_ip: str, user: str, password: str, command: str, timeout: int = 5, jump_host_ip: Optional[str] = None,
                    jump_user: Optional[str] = None, jump_password: Optional[str] = None) -> Tuple[str, str]:
    """Run a command over SSH with optional jump-host forwarding and return (stdout, stderr)."""
    target_client = None
    jump_client = None
    jump_channel = None
    try:
        target_client, jump_client, jump_channel = open_ssh_client(host_ip=host_ip, user=user, password=password, timeout=timeout, jump_host_ip=jump_host_ip,
                                                                   jump_user=jump_user, jump_password=jump_password)
        _, stdout, stderr = target_client.exec_command(command, timeout=timeout)
        return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')
    finally:
        close_ssh_client(target_client, jump_client, jump_channel)