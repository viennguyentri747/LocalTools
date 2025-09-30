#!/home/vien/local_tools/MyVenvFolder/bin/python
from dev_common import *
from misc_tools.t_get_acu_logs import AcuLogInfo
from unit_tests.acu_log_tests.periodic_log_helper import *
from unit_tests.acu_log_tests.common import batch_fetch_acu_logs_for_days

ACU_PLOG_PATH = TEMP_FOLDER_PATH / "acu_plogs/"
EXTRA_DAYS_BEFORE_TODAY = 0
LOG_HOUR_CAPTURE = 0.1  # 0.01 hour = 36 secs
TARGET_COLUMNS = [TIME_COLUMN, LAST_VELOCITY_COLUMN, LAST_RTK_COMPASS_STATUS_COLUMN]

USE_DUMMY_DATA = False


def main():
    """
    Main function to fetch and analyze ACU E-logs for motion detection events.
    """

    # Create dummy data
    if USE_DUMMY_DATA:
        ut_ip1 = f"{SSM_IP_PREFIX}.101.79"
        valid_fetch_infos: AcuLogInfo = [
            AcuLogInfo(
                ip=ut_ip1,
                log_paths=[f"/home/vien/local_tools/temp/acu_plogs/192.168.101.79/P_20250929_000000.txt"],
                is_valid=True
            )
        ]
    else:
        valid_fetch_infos = batch_fetch_acu_logs_for_days(
            list_ips=LIST_FD_IPS, extra_days_before_today=EXTRA_DAYS_BEFORE_TODAY, log_types=["P"], parent_path=ACU_PLOG_PATH)

    # Process the fetched logs
    counter = 0
    for ip, ip_log_files in [(fetch_info.ut_ip, fetch_info.log_paths) for fetch_info in valid_fetch_infos]:
        for log_file in ip_log_files:
            LOG(f"{LOG_PREFIX_MSG_INFO} Parsing periodic log: {log_file} of IP: {ip}")
            plog_data: PLogData = parse_periodic_log(
                log_path=log_file,
                target_columns=TARGET_COLUMNS,
                max_time_capture=LOG_HOUR_CAPTURE
            )

            table_str = f"UNIT TEST: {ip}\n" + plog_data.to_table_string(tablefmt="fancy_grid") + "\n\n"
            output_path = f"{TEMP_FOLDER_PATH}/PlogTest_output.txt"
            write_to_file(output_path, table_str,
                          mode=WriteMode.OVERWRITE if counter == 0 else WriteMode.APPEND)
            # print(table_str)
            counter += 1

            graph_output_path = f"{TEMP_FOLDER_PATH}/PlogTest_graph_{ip}_{counter}.png"
            LOG(f"{LOG_PREFIX_MSG_INFO} Plotting graph...")
            plog_data.plot_columns(
                column_names=[col for col in TARGET_COLUMNS if col != "Time"],  # Exclude Time column
                output_path=graph_output_path,
                show_interactive=False  # Don't show interactive window for each iteration
            )

    print(f"{LOG_PREFIX_MSG_INFO} Output saved to: {output_path}")


if __name__ == "__main__":
    main()
