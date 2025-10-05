from datetime import timedelta
from pathlib import Path
from typing import Iterable, List
from dev_common import *

SSH_KEY_TYPE_RSA = 'rsa'
KEY_TYPE_ED25519 = 'ed25519'


class AcuLogInfo:
    """Holds information about the log fetch operation."""

    def __init__(self, is_valid: bool, ip: str, log_paths: Optional[List[str]] = None):
        self.is_valid: bool = is_valid
        self.ut_ip: str = ip
        self.log_paths: List[str] = log_paths or []


def _get_last_n_days(n: int) -> List[str]:
    """
    Generates a list of date strings in YYYYYMMDD format for the last n days, including today.
    """
    date_list = []
    today = datetime.now()
    for i in range(n + 1):
        date = today - timedelta(days=i)
        date_list.append(date.strftime("%Y%m%d"))
    return date_list


def get_acu_log_datename_from_date(date: datetime) -> str:
    return date.strftime("%Y%m%d")


def batch_fetch_acu_logs_for_days(list_ips: List[str], extra_days_before_today: int, log_types: List[str], parent_path: Path, should_has_var_log: bool = False) -> List[AcuLogInfo]:
    """Fetch E-logs for motion detection from all MP IPs"""
    dates_to_check = _get_last_n_days(extra_days_before_today)
    LOG(f"{LOG_PREFIX_MSG_INFO} Checking logs for the following dates: {', '.join(dates_to_check)}")
    if not dates_to_check:
        return

    valid_fetch_infos: List[AcuLogInfo] = []
    for ip in list_ips:
        LOG(f"{LOG_PREFIX_MSG_INFO} Fetching E-logs for IP: {ip}")

        # Fetch E-logs for the specified IP and dates
        final_path = parent_path / ip
        fetch_info: AcuLogInfo = fetch_acu_logs(
            ut_ip=ip, log_types=log_types, date_filters=dates_to_check, dest_folder_path=final_path, clear_dest_folder=True, should_has_var_log=should_has_var_log)

        if not fetch_info.is_valid:
            LOG(f"Failed to fetch logs for {ip}. Skipping...")
            continue

        valid_fetch_infos.append(fetch_info)
    return valid_fetch_infos


def fetch_acu_logs(ut_ip: str, log_types: List[str], dest_folder_path: str | Path,
                   ssh_key_type: str = SSH_KEY_TYPE_RSA, date_filters: List[str] = None, clear_dest_folder: bool = True, should_has_var_log: bool = False) -> AcuLogInfo:
    """Fetch all logs in a single scp command to minimize password prompts."""
    if not ping_host(ut_ip, total_pings=2, time_out_per_ping=3):
        LOG(f"{LOG_PREFIX_MSG_ERROR} Jump host {ut_ip} is not reachable. Aborting.", file=sys.stderr)
        return AcuLogInfo(is_valid=False, ip=ut_ip)

    remove_known_hosts_entries([ut_ip, ACU_IP])
    if not setup_passwordless_ssh(ACU_USER, ut_ip, ACU_IP, ssh_key_type):
        LOG(f"{LOG_PREFIX_MSG_ERROR} SSH key setup failed for {ut_ip}. Continuing with password authentication...")

    try:
        os.makedirs(dest_folder_path, exist_ok=True)
        if clear_dest_folder:
            clear_directory_content(dest_folder_path)
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to prepare destination '{dest_folder_path}': {exc}", file=sys.stderr)
        return AcuLogInfo(is_valid=False, ip=ut_ip)

    start_time = time.time()
    cmd = build_scp_log_cmd(ACU_USER, ut_ip, log_types, str(dest_folder_path),
                            date_filters, should_has_var_log=should_has_var_log)
    LOG(f"{LOG_PREFIX_MSG_INFO} Fetching all logs for {ut_ip} into '{dest_folder_path}' in batch...")
    LOG(f"Running command: {' '.join(cmd)}")

    scp_cmd_failed = False
    try:
        subprocess.check_call(cmd)
    except Exception as e:
        scp_cmd_failed = True

    # Collect any files fetched during the operation, regardless of scp exit status
    try:
        new_log_paths = sorted(
            str(f) for f in Path(dest_folder_path).rglob("*")
            if f.is_file() and f.stat().st_mtime >= start_time
        )
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to enumerate fetched logs in '{dest_folder_path}': {exc}", file=sys.stderr)
        new_log_paths = []

    if new_log_paths:
        if scp_cmd_failed:
            LOG(f"{LOG_PREFIX_MSG_WARNING} Partial fetch for {ut_ip}: copied {len(new_log_paths)} file(s) despite scp errors.")
        else:
            LOG(f"{LOG_PREFIX_MSG_INFO} Scp batch completed for {ut_ip}, logs saved in '{dest_folder_path}'")
    else:
        LOG(f"{LOG_PREFIX_MSG_WARNING} No log files copied for {ut_ip}{' (scp failed)' if scp_cmd_failed else ' despite scp completion'}.")

    return AcuLogInfo(is_valid=bool(new_log_paths), ip=ut_ip, log_paths=new_log_paths)

def calc_missing_logs(found_files: Iterable[str], log_types: Iterable[str], date_filters: Iterable[str]) -> List[str]:
    """Determine expected log prefixes that were not downloaded."""
    found_names = [Path(path).name for path in found_files]
    missing: List[str] = []
    for log_type in log_types:
        for date_filter in date_filters:
            expected_prefix = f"{log_type}_{date_filter}"
            if not any(name.startswith(expected_prefix) for name in found_names):
                missing.append(f"{expected_prefix}*")
    return missing

def remove_known_hosts_entries(hosts: List[str]) -> None:
    """Remove known_hosts entries for given hosts to handle key changes."""
    for host in hosts:
        try:
            LOG(f"{LOG_PREFIX_MSG_INFO} Removing known_hosts entry for {host}...")
            subprocess.run(['ssh-keygen', '-R', host],
                           capture_output=True, check=False)
        except Exception as e:
            LOG(f"[WARNING] Failed to remove known_hosts entry for {host}: {e}")


def build_scp_log_cmd(user: str, jump_ip: str, log_types: List[str],
                      dest_path_str: str, date_filters: List[str] = None, should_has_var_log: bool = False) -> List[str]:
    """Build a single scp command to fetch multiple files in one go."""
    remote_paths = []
    dates_to_process = date_filters if date_filters else [None]

    for log_type_prefix in log_types:
        for date_filter in dates_to_process:
            if should_has_var_log:
                remote_paths.append(f"{str(ACU_VAR_LOG_PATH)}/{log_type_prefix}*")

            if date_filter:
                remote_paths.append(f"{str(ACU_FLASH_LOGS_PATH)}/{log_type_prefix}_{date_filter}*")
            else:
                remote_paths.append(f"{str(ACU_FLASH_LOGS_PATH)}/{log_type_prefix}*")

    # Create a single command to copy all files
    proxy = f"{user}@{jump_ip}"
    cmd: List[str] = ['scp', '-r', '-o', f'ProxyJump={proxy}', '-o', 'StrictHostKeyChecking=no']

    # Add all remote paths
    for path in remote_paths:
        cmd.append(f"{user}@{ACU_IP}:{path}")

    cmd.append(dest_path_str)
    return cmd


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
    if not copy_ssh_key_to_host(user, jump_host, public_key_path):
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to setup SSH key for jump host {jump_host}")
        return False

    LOG(f"{LOG_PREFIX_MSG_INFO} Passwordless SSH setup completed successfully!")
    return True


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


def copy_ssh_key_to_host(user: str, host: str, public_key_path: Path,
                         via_jump: Optional[str] = None) -> bool:
    """Copy SSH public key to remote host."""
    LOG(f"{LOG_PREFIX_MSG_INFO} Copying SSH key to {user}@{host}...")

    try:
        # Read the public key
        with open(public_key_path, 'r') as f:
            public_key = f.read().strip()

        # Build the command to add the key to authorized_keys
        if via_jump:
            # Copy via jump host
            cmd = [
                'ssh', '-o', f'ProxyJump={user}@{via_jump}',
                '-o', 'StrictHostKeyChecking=no',
                f'{user}@{host}',
                f'mkdir -p ~/.ssh && echo "{public_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh'
            ]
        else:
            # Direct copy
            cmd = [
                'ssh', '-o', 'StrictHostKeyChecking=no',
                f'{user}@{host}',
                f'mkdir -p ~/.ssh && echo "{public_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh'
            ]

        subprocess.check_call(cmd)
        LOG(f"{LOG_PREFIX_MSG_INFO} SSH key successfully copied to {host}")
        return True

    except Exception as e:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Error copying SSH key to {host}: {e}", file=sys.stderr)
        return False
