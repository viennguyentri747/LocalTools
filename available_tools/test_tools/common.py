from datetime import timedelta
from pathlib import Path
from typing import Iterable, List
from dev_common import *


ARG_LOG_OUTPUT_PATH = f"{ARGUMENT_LONG_PREFIX}log_output_path"
ARG_LIST_IPS = f"{ARGUMENT_LONG_PREFIX}ips"
E_LOG_PREFIX = "E"
P_LOG_PREFIX = "P"
T_LOG_PREFIX = "T"


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


def fetch_acu_logs(ut_ip: str, log_types: List[str], dest_folder_path: str | Path, ssh_key_type: str = SSH_KEY_TYPE_RSA,
                   date_filters: List[str] = None, clear_dest_folder: bool = True, should_has_var_log: bool = False) -> AcuLogInfo:
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
            clear_directory(dest_folder_path)
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
