#!/home/vien/local_tools/MyVenvFolder/bin/python
from dev_common import *
from dev_common.algo_utils import get_match_info
from dev_common.custom_structures import MatchInfo
from unit_tests.acu_log_tests.common import batch_fetch_acu_logs_for_days

REGEX_PATTERNS = ["MOTION DETECT", "INS-READY"]
ACU_ELOG_PATH = TEMP_FOLDER_PATH / "acu_elogs/"
EXTRA_DAYS_BEFORE_TODAY = 2

def main():
    """
    Main function to fetch and analyze ACU E-logs for motion detection events.
    """
    # Fetch E-logs for the specified dates
    valid_fetch_infos = batch_fetch_acu_logs_for_days(
        list_ips=LIST_MP_IPS, extra_days_before_today=EXTRA_DAYS_BEFORE_TODAY, log_types=["E"], parent_path=ACU_ELOG_PATH)

    # Process the fetched logs
    match_infos: Dict[int, MatchInfo] = {}
    for ip, log_files in [(fetch_info.ut_ip, fetch_info.log_paths) for fetch_info in valid_fetch_infos]:
        all_logs_content = ""

        for log_file in log_files:
            try:
                LOG(f"Processing file: {log_file} of IP: {ip}")
                all_logs_content += read_file_content(log_file)
            except Exception as e:
                LOG(f"Error reading or processing file {log_file}: {e}")
        match_info: MatchInfo = get_match_info(all_logs_content, REGEX_PATTERNS, '\n')
        match_infos[ip] = match_info

    for ip, match_info in match_infos.items():
        LOG(f"\n--- Summary for IP: {ip} ---")
        for pattern in match_info.get_patterns():
            lines: List[str] = match_info.get_matched_lines(pattern)
            LOG(f"  - Pattern '{pattern}': Matched lines:")
            for line in lines:
                LOG(f"    {line}")
        LOG("-------------------------\n")


if __name__ == "__main__":
    main()
