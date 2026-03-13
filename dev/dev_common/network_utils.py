from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import paramiko
import posixpath
import shlex
import time
import subprocess
import sys
from typing import Callable, List, Optional, Tuple
from dev.dev_common.constants import *
from dev.dev_common.core_utils import *
from dev.dev_common.format_utils import format_bytes_human

SSH_KEY_TYPE_RSA = 'rsa'
KEY_TYPE_ED25519 = 'ed25519'


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

        LOG(f"Connecting to jump host {jump_host_ip}")
        jump_client.connect(**jump_connect_kwargs)
        jump_transport = jump_client.get_transport()
        if jump_transport is None:
            close_ssh_client(target_client, jump_client, jump_channel)
            raise RuntimeError(f"Jump host transport unavailable: {jump_host_ip}")
        jump_channel = jump_transport.open_channel('direct-tcpip', (host_ip, 22), ('127.0.0.1', 0))
        connect_kwargs["sock"] = jump_channel

    try:
        LOG(f"Connecting to host {host_ip}")
        target_client.connect(**connect_kwargs)
    except Exception:
        LOG(f"Failed to connect to {host_ip}")
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


def get_live_remote_log(host_ip: str, user: str, password: str, remote_log_path: str, timeout: int = 5, jump_host_ip: Optional[str] = None,
                        jump_user: Optional[str] = None, jump_password: Optional[str] = None, tail_lines: int = 0, read_timeout: int = 300,
                        poll_interval: float = 0.1, stop_event=None, on_line: Optional[Callable[[str], None]] = None) -> None:
    """Continuously tail a remote log file or read from a serial device until interrupted or stop_event is set."""
    target_client = None
    jump_client = None
    jump_channel = None
    stdout = stderr = None
    on_line = on_line or (lambda line: print(line, flush=True))

    # /dev/ paths are character devices — use cat instead of tail
    is_device = remote_log_path.startswith("/dev/")
    if is_device:
        remote_cmd = f"cat {shlex.quote(remote_log_path)}"
    else:
        remote_cmd = f"tail -F -n {max(0, int(tail_lines))} {shlex.quote(remote_log_path)}"

    try:
        target_client, jump_client, jump_channel = open_ssh_client(host_ip=host_ip, user=user, password=password, timeout=timeout, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
        _, stdout, stderr = target_client.exec_command(remote_cmd)
        channel_read_timeout = 1.0
        stdout.channel.settimeout(channel_read_timeout)
        last_output_time = time.time()
        waiting_start_time = last_output_time
        waiting_last_second = -1
        waiting_last_text_len = 0
        saw_first_log = False
        
        while not (stop_event and stop_event.is_set()):
            if target_client.get_transport() is None or not target_client.get_transport().is_active():
                raise ConnectionError(f"SSH connection lost for {host_ip}")
            if not saw_first_log:
                elapsed_seconds = int(time.time() - waiting_start_time)
                if elapsed_seconds != waiting_last_second:
                    waiting_text = f"Waiting for log output from '{remote_log_path}'... Elapsed: {elapsed_seconds}/{read_timeout}s"
                    waiting_last_text_len = max(waiting_last_text_len, len(waiting_text))
                    LOG(f"{waiting_text}{' ' * (waiting_last_text_len - len(waiting_text))}", same_line=True, show_time=False)
                    waiting_last_second = elapsed_seconds
            try:
                line = stdout.readline()
            except TimeoutError:
                if is_device:
                    # Serial ports can be silent for long periods — don't timeout, just keep waiting
                    last_output_time = time.time()
                    continue
                if time.time() - last_output_time >= read_timeout:
                    raise TimeoutError(f"No data received from '{remote_log_path}' for {read_timeout} seconds")
                continue
            if line:
                if not saw_first_log:
                    on_line(line.rstrip() + f"\r\nGET_UT_LIVE_LOG START at {time.strftime('%Y-%m-%d %H:%M:%S')}!!")
                    saw_first_log = True
                on_line(line.rstrip('\r\n'))
                last_output_time = time.time()
                continue
            if stdout.channel.exit_status_ready():
                stderr_text = stderr.read().decode('utf-8', errors='replace').strip() if stderr else ""
                if stderr_text:
                    raise RuntimeError(stderr_text)
                return
            remain_secs = read_timeout - (time.time() - last_output_time)
            if not is_device and remain_secs < 0:
                raise TimeoutError(f"No data received from '{remote_log_path}' for {read_timeout} seconds")
            time.sleep(max(0.01, poll_interval))
    finally:
        if stdout:
            stdout.close()
        if stderr:
            stderr.close()
        close_ssh_client(target_client, jump_client, jump_channel)


@dataclass
class SshPwlessStatuses:
    """Categorized results for SSH passwordless checks."""

    passwordless_ips: List[str] = field(default_factory=list)
    password_required_ips: List[str] = field(default_factory=list)
    unreachable_ips: List[str] = field(default_factory=list)


def ping_host(host: str, total_pings: int = 3, time_out_per_ping: int = 3, mute: bool = False) -> bool:
    try:
        if not mute:
            LOG(f"[INFO] Pinging {host}...")
        cmd = ['ping', '-c', str(total_pings), '-W', str(time_out_per_ping), host]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=time_out_per_ping * total_pings + 2  # Total timeout
        )

        if not mute:
            LOG(f"Host {host} is {'reachable' if result.returncode == 0 else 'not reachable'}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        if not mute:
            LOG(f"[WARNING] Ping to {host} timed out")
        return False
    except Exception as e:
        if not mute:
            LOG(f"[WARNING] Ping to {host} failed: {e}")
        return False


def _sftp_mkdir_p(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    remote_dir = remote_dir.strip()
    if not remote_dir or remote_dir == ".":
        return
    current = "/" if remote_dir.startswith("/") else ""
    for part in PurePosixPath(remote_dir).parts:
        if part in ("", "/"):
            continue
        current = posixpath.join(current, part) if current not in ("", "/") else (f"/{part}" if current == "/" else part)
        try:
            sftp.stat(current)
        except IOError:
            sftp.mkdir(current)


def _sftp_put_file(sftp: paramiko.SFTPClient, local_file: Path, remote_file_path: str) -> str:
    _sftp_mkdir_p(sftp, posixpath.dirname(remote_file_path))
    sftp.put(str(local_file), remote_file_path)
    return remote_file_path


class _TransferProgressReporter:
    def __init__(self, label: str, total_bytes: int, log_interval_sec: float = 1.0):
        self.label = label
        self.total_bytes = max(0, int(total_bytes))
        self.log_interval_sec = log_interval_sec
        self.start_time = time.time()
        self.last_log_time = 0.0
        self.last_logged_percent = -1

    def report(self, transferred_bytes: int, force: bool = False) -> None:
        transferred_bytes = max(0, min(int(transferred_bytes), self.total_bytes))
        elapsed = max(time.time() - self.start_time, 1e-6)
        percent = 100 if self.total_bytes == 0 else int((transferred_bytes * 100) / self.total_bytes)
        if not force and percent == self.last_logged_percent and (time.time() - self.last_log_time) < self.log_interval_sec:
            return
        rate_mib_s = (transferred_bytes / elapsed) / (1024 * 1024)
        transferred_h = format_bytes_human(transferred_bytes)
        total_h = format_bytes_human(self.total_bytes)
        LOG(f"{LOG_PREFIX_MSG_INFO} {self.label}: {percent}% ({transferred_h}/{total_h}), elapsed {elapsed:.1f}s, rate {rate_mib_s:.2f} MiB/s", same_line=True)
        self.last_logged_percent = percent
        self.last_log_time = time.time()


def _sftp_put_file_with_progress(sftp: paramiko.SFTPClient, local_file: Path, remote_file_path: str, base_offset: int = 0, total_bytes: Optional[int] = None, label: Optional[str] = None) -> str:
    file_size = local_file.stat().st_size
    file_uploaded = 0
    overall_total = file_size if total_bytes is None else max(file_size, int(total_bytes))
    LOG(f"{LOG_PREFIX_MSG_INFO} Uploading {local_file} to {remote_file_path} ({format_bytes_human(file_size)})")
    reporter = _TransferProgressReporter(label=label or f"Upload Progress:", total_bytes=overall_total)

    def _on_progress(transferred: int, total: int) -> None:
        nonlocal file_uploaded
        file_uploaded = max(0, min(transferred, file_size if file_size >= 0 else total))
        reporter.report(base_offset + file_uploaded)

    _sftp_mkdir_p(sftp, posixpath.dirname(remote_file_path))
    reporter.report(0, force=True)
    sftp.put(str(local_file), remote_file_path, callback=_on_progress)
    reporter.report(base_offset + file_size, force=True)
    return remote_file_path


def _sftp_put_directory(sftp: paramiko.SFTPClient, local_dir: Path, remote_dir_path: str) -> str:
    _sftp_mkdir_p(sftp, remote_dir_path)
    local_items = sorted(local_dir.rglob("*"))
    files = [item for item in local_items if item.is_file()]
    total_bytes = sum(item.stat().st_size for item in files)
    uploaded_bytes = 0
    for local_item in local_items:
        rel_path = local_item.relative_to(local_dir).as_posix()
        remote_item_path = posixpath.join(remote_dir_path, rel_path)
        if local_item.is_dir():
            _sftp_mkdir_p(sftp, remote_item_path)
        else:
            _sftp_put_file_with_progress(sftp, local_item, remote_item_path, base_offset=uploaded_bytes, total_bytes=total_bytes)
            uploaded_bytes += local_item.stat().st_size
    return remote_dir_path


def _copy_to_remote_impl(local_path: str | Path, remote_host_ip: str, remote_dest_path: str, remote_user: str = ACU_USER,
                         password: Optional[str] = None, jump_host_ip: Optional[str] = None, jump_user: Optional[str] = None,
                         jump_password: Optional[str] = None, recursive: Optional[bool] = None, timeout: Optional[int] = None) -> str:
    local_path_obj = Path(local_path).expanduser().resolve()
    should_use_recursive = local_path_obj.is_dir() if recursive is None else recursive
    if local_path_obj.is_dir() and not should_use_recursive:
        raise ValueError(f"Local path '{local_path_obj}' is a directory. Set recursive=True to copy it.")
    target_client = jump_client = jump_channel = None
    sftp = None
    try:
        target_client, jump_client, jump_channel = open_ssh_client(host_ip=remote_host_ip, user=remote_user, password=password, timeout=timeout or 5, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
        transport = target_client.get_transport()
        if transport is None or not transport.is_active():
            raise RuntimeError(f"SSH transport unavailable for {remote_host_ip}")
        sftp = paramiko.SFTPClient.from_transport(transport)
        if should_use_recursive and local_path_obj.is_dir():
            return _sftp_put_directory(sftp, local_path_obj, remote_dest_path)
        result = _sftp_put_file_with_progress(sftp, local_path_obj, remote_dest_path)
        return result
    finally:
        if sftp:
            sftp.close()
        close_ssh_client(target_client, jump_client, jump_channel)


def copy_to_remote(local_path: str | Path, remote_host_ip: str, remote_dest_path: str, remote_user: str = ACU_USER,
                   password: Optional[str] = None, recursive: Optional[bool] = None, strict_host_key_checking: bool = False,
                   timeout: Optional[int] = None) -> str:
    """Copy a local file or directory to a remote host using Paramiko SFTP."""
    if strict_host_key_checking:
        LOG(f"{LOG_PREFIX_MSG_WARNING} strict_host_key_checking is ignored for Paramiko-based copy_to_remote().")
    LOG(f"{LOG_PREFIX_MSG_INFO} Copying '{Path(local_path).expanduser()}' to {remote_user}@{remote_host_ip}:{remote_dest_path} via Paramiko")
    return _copy_to_remote_impl(local_path=local_path, remote_host_ip=remote_host_ip, remote_dest_path=remote_dest_path, remote_user=remote_user,
                                password=password, recursive=recursive, timeout=timeout)


def copy_to_remote_via_jump_host(local_path: str | Path, remote_host_ip: str, remote_dest_path: str, jump_host_ip: str,
                                 remote_user: str = ACU_USER, password: Optional[str] = None, jump_user: Optional[str] = None,
                                 jump_password: Optional[str] = None, recursive: Optional[bool] = None, strict_host_key_checking: bool = False,
                                 timeout: Optional[int] = None) -> str:
    """Copy a local file or directory to a remote host through a jump host using Paramiko SFTP."""
    if strict_host_key_checking:
        LOG(f"{LOG_PREFIX_MSG_WARNING} strict_host_key_checking is ignored for Paramiko-based copy_to_remote_via_jump_host().")
    LOG(f"{LOG_PREFIX_MSG_INFO} Copying '{Path(local_path).expanduser()}' to {remote_user}@{remote_host_ip}:{remote_dest_path} via jump host {jump_user}@{jump_host_ip} using Paramiko")
    return _copy_to_remote_impl(local_path=local_path, remote_host_ip=remote_host_ip, remote_dest_path=remote_dest_path, remote_user=remote_user,password=password, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password,
recursive=recursive, timeout=timeout)


def setup_passwordless_ssh(user: str, jump_host: str, remote_host: str,
                           key_type: str = SSH_KEY_TYPE_RSA) -> bool:
    """Set up passwordless SSH authentication."""
    LOG(f"{LOG_PREFIX_MSG_INFO} Setting up passwordless SSH authentication...")

    # Remove known_hosts entries first (in case of host key changes)
    all_hosts = [jump_host] + [remote_host]
    remove_known_hosts_entries(all_hosts)

    # Generate SSH key if needed
    if not generate_ssh_key(key_type):
        return False

    _, public_key_path = check_ssh_key_exists(key_type)

    # Copy key to jump hosts first
    if not setup_host_ssh_key(user, jump_host, public_key_path):
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to setup SSH key for jump host {jump_host}")
        return False

    LOG(f"{LOG_PREFIX_MSG_INFO} Passwordless SSH setup completed successfully!")
    return True


def remove_known_hosts_entries(hosts: List[str]) -> None:
    """Remove known_hosts entries for given hosts to handle key changes."""
    for host in hosts:
        try:
            LOG(f"{LOG_PREFIX_MSG_INFO} Removing known_hosts entry for {host}...")
            subprocess.run(['ssh-keygen', '-R', host],
                           capture_output=True, check=False)
        except Exception as e:
            LOG(f"[WARNING] Failed to remove known_hosts entry for {host}: {e}")


def check_ssh_pwless_statuses(ips: List[str], user: str, public_key_path: Path, max_workers: int = 10) -> SshPwlessStatuses:
    """Check SSH key status for multiple hosts in parallel.

    Returns:
        SshPwlessStatuses with passwordless, password required, and unreachable IPs.
    """
    statuses = SshPwlessStatuses()

    try:
        with open(public_key_path, 'r') as f:
            public_key = f.read().strip()
        key_parts = public_key.split()
        key_fingerprint = key_parts[1] if len(key_parts) > 1 else public_key
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Unable to read public key at {public_key_path}: {exc}")
        key_fingerprint = None

    unreachable_markers = (
        "connection timed out",
        "no route to host",
        "could not resolve hostname",
        "name or service not known",
        "connection refused",
        "connection closed by remote host",
        "connection reset",
        "network is unreachable",
        "host is down",
    )

    permission_markers = (
        "permission denied",
        "authentication failed",
        "publickey,password",
        "publickey,keyboard-interactive",
    )

    def _check_single_ip(ip: str) -> Tuple[str, str]:
        if not key_fingerprint:
            # Without a readable key we cannot check remotely; treat as requiring setup.
            return ip, "password_required"

        cmd = (
            f'ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=5 '
            f'{user}@{ip} \'grep -q "{key_fingerprint}" ~/.ssh/authorized_keys 2>/dev/null\''
        )
        try:
            result = run_shell(cmd, show_cmd=False, capture_output=True, timeout=10,
                               check_throw_exception_on_exit_code=False, )
        except Exception as exc:
            LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to execute SSH status check for {ip}: {exc}")
            return ip, "unreachable"

        combined_output = f"{result.stdout or ''}\n{result.stderr or ''}".lower()

        if result.returncode == 0:
            return ip, "passwordless"

        if any(marker in combined_output for marker in unreachable_markers):
            return ip, "unreachable"

        if any(marker in combined_output for marker in permission_markers):
            return ip, "password_required"

        # Default to password-required for other failures so we attempt remediation.
        LOG(f"{LOG_PREFIX_MSG_WARNING} {ip} SSH check failed with unexpected output (treating as password-required). Raw: {combined_output.strip()}")
        return ip, "password_required"

    LOG(f"{LOG_PREFIX_MSG_INFO} Checking SSH key status for {len(ips)} hosts in parallel with max_workers={max_workers}")
    with ThreadPoolExecutor(max_workers=min(max_workers, len(ips))) as executor:
        future_map = {executor.submit(_check_single_ip, ip): ip for ip in ips}

        for future in as_completed(future_map):
            ip = future_map[future]
            try:
                checked_ip, status = future.result()
                if status == "passwordless":
                    statuses.passwordless_ips.append(checked_ip)
                    LOG(f"{LOG_PREFIX_MSG_INFO} ✓ {checked_ip} - SSH key already installed")
                elif status == "password_required":
                    statuses.password_required_ips.append(checked_ip)
                    LOG(f"{LOG_PREFIX_MSG_WARNING} {checked_ip} - SSH key not found, will require password")
                else:
                    statuses.unreachable_ips.append(checked_ip)
                    LOG(f"{LOG_PREFIX_MSG_WARNING} {checked_ip} - Host unreachable, skipping")
            except Exception as exc:
                LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to check SSH status for {ip}: {exc}")
                statuses.unreachable_ips.append(ip)

    return statuses


def is_ssh_key_already_installed(user: str, host: str, public_key_path: Path) -> bool:
    """Check if SSH key is already installed on remote host."""
    try:
        with open(public_key_path, 'r') as f:
            public_key = f.read().strip()

        # Extract just the key part (not the comment)
        key_fingerprint = public_key.split()[1] if len(public_key.split()) > 1 else public_key
        cmd = f'ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=5 {user}@{host} \'grep -q "{key_fingerprint}" ~/.ssh/authorized_keys 2>/dev/null\''
        # batch mode=yes - Fail if password is needed
        result = run_shell(cmd, show_cmd=False, capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def check_ssh_key_exists(key_type: str = SSH_KEY_TYPE_RSA) -> Tuple[bool, Path]:
    """Check if SSH key pair already exists."""
    ssh_dir = Path.home() / '.ssh'
    if key_type == KEY_TYPE_ED25519:
        private_key = ssh_dir / 'id_ed25519'
        public_key = ssh_dir / 'id_ed25519.pub'
    else:
        private_key = ssh_dir / 'id_rsa'
        public_key = ssh_dir / 'id_rsa.pub'

    exists = private_key.exists() and public_key.exists()
    return exists, public_key


def generate_ssh_key(key_type: str = SSH_KEY_TYPE_RSA) -> bool:
    """Generate SSH key pair if it doesn't exist."""
    ssh_dir = Path.home() / '.ssh'
    ssh_dir.mkdir(mode=0o700, exist_ok=True)

    exists, pub_key_path = check_ssh_key_exists(key_type)

    if exists:
        LOG(f"{LOG_PREFIX_MSG_INFO} SSH key already exists: {pub_key_path}")
        return True

    LOG(f"{LOG_PREFIX_MSG_INFO} Generating {key_type.upper()} SSH key pair...")

    if key_type == KEY_TYPE_ED25519:
        key_path = ssh_dir / 'id_ed25519'
        cmd = ['ssh-keygen', '-t', key_type, '-f', str(key_path), '-N', '']
    else:
        key_path = ssh_dir / 'id_rsa'
        cmd = ['ssh-keygen', '-t', key_type, '-b', '4096', '-f', str(key_path), '-N', '']

    try:
        subprocess.check_call(cmd)
        LOG(f"{LOG_PREFIX_MSG_INFO} SSH key generated successfully: {key_path}")
        return True
    except subprocess.CalledProcessError as e:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to generate SSH key: {e}", file=sys.stderr)
        return False


def remove_target_ssh_key_from_known_host(ip: str) -> bool:
    """
    Attempts to remove the offending host key from the user's known_hosts file.
    This is the fix suggested by SSH when a host key mismatch occurs.
    """
    known_hosts_path = Path.home() / ".ssh" / "known_hosts"
    if not known_hosts_path.exists():
        LOG(f"{LOG_PREFIX_MSG_INFO} No known_hosts file found, skipping key removal for {ip}.")
        return True  # Nothing to remove, so "success"

    # Use shlex.quote to prevent command injection
    command = f"ssh-keygen -f {shlex.quote(str(known_hosts_path))} -R {shlex.quote(ip)}"
    LOG(f"{LOG_PREFIX_MSG_INFO} Attempting to remove old host key for {ip}: {command}")

    try:
        # Run the command
        result = subprocess.run(shlex.split(command), capture_output=True, text=True, check=True, timeout=10)
        LOG(f"{LOG_PREFIX_MSG_INFO} Successfully removed host key for {ip}.")
        if result.stdout:
            LOG(f"ssh-keygen stdout: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        # Command returned a non-zero exit code
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to remove host key for {ip}. Error: {e.stderr.strip()}")
        return False
    except Exception as e:
        # Other errors (e.g., timeout)
        LOG(f"{LOG_PREFIX_MSG_ERROR} An unexpected error occurred while running ssh-keygen for {ip}: {e}")
        return False


def setup_host_ssh_key(user: str, host: str, public_key_path: Path,
                       via_jump: Optional[str] = None) -> bool:
    """
    Copy SSH public key to remote host.
    Proactively removes any existing host key from known_hosts before attempting.
    """
    LOG(f"{LOG_PREFIX_MSG_INFO} Copying SSH key to {user}@{host}...")

    # --- NEW: Proactively remove the host key first ---
    LOG(f"{LOG_PREFIX_MSG_INFO} Attempting to remove any old host key for {host}...")
    if not remove_target_ssh_key_from_known_host(host):
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to remove old host key for {host}. Aborting key copy.", file=sys.stderr)
        return False
    LOG(f"{LOG_PREFIX_MSG_INFO} Old host key removed (or did not exist). Proceeding with copy...")
    # --- End NEW ---

    try:
        # Read the public key
        with open(public_key_path, 'r') as f:
            public_key = f.read().strip()

        # Build the command to add the key to authorized_keys
        if via_jump:
            cmd = [
                'ssh', '-o', f'ProxyJump={user}@{via_jump}',
                '-o', 'StrictHostKeyChecking=no',  # Now accepts the new key automatically
                f'{user}@{host}',
                f'mkdir -p ~/.ssh && echo "{public_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh'
            ]
        else:
            cmd = [
                'ssh', '-o', 'StrictHostKeyChecking=no',
                f'{user}@{host}',
                f'mkdir -p ~/.ssh && echo "{public_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh'
            ]

        # Run the SSH command (one attempt)
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)

        LOG(f"{LOG_PREFIX_MSG_INFO} SSH key successfully copied to {host}.")
        return True

    except subprocess.CalledProcessError as e:
        # The command failed. This will now almost certainly be the "Permission denied" error.
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to copy key to {host}. Error: {e.stderr.strip()}", file=sys.stderr)
        return False
    except Exception as e:
        # Catch other errors (e.g., file not found, timeout)
        LOG(f"{LOG_PREFIX_MSG_ERROR} An unexpected error occurred while copying key to {host}: {e}", file=sys.stderr)
        return False
