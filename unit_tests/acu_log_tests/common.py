from datetime import timedelta
from pathlib import Path
from typing import List
from dev.dev_common import *
from available_tools.test_tools.log_test_tools.t_get_acu_logs import AcuLogInfo, fetch_acu_logs


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
            ut_ip=ip, log_types=log_types, date_filters=dates_to_check, dest_folder_path=final_path, clear_dest_folder=True, should_has_var_log = should_has_var_log)

        if not fetch_info.is_valid:
            LOG(f"Failed to fetch logs for {ip}. Skipping...")
            continue

        valid_fetch_infos.append(fetch_info)
    return valid_fetch_infos
