from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
import shlex
import subprocess
import sys
from typing import List, Optional, Tuple
from dev.dev_common.constants import *
from dev.dev_common.core_utils import LOG, run_shell

SSH_KEY_TYPE_RSA = 'rsa'
KEY_TYPE_ED25519 = 'ed25519'


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
