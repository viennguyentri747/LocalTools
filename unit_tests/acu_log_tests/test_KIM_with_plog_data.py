#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Set

from available_tools.inertial_sense_tools.decode_ins_status_utils import decode_ins_status
from dev.dev_common import *
from unit_tests.acu_log_tests.periodic_log_helper import PLogData, parse_periodic_log
from unit_tests.acu_log_tests.periodic_log_constants import *
from available_tools.inertial_sense_tools.decode_ins_status_utils import (
    decode_ins_status,
    print_decoded_status as print_ins_status,
)

# Defaults mirror the SINR-focused unit tests while allowing overrides via CLI.
DEFAULT_TARGET_COLUMNS: List[str] = [
    TIME_COLUMN,
    LAST_AVG_SINR_COLUMN,
    LAST_KIM_HW_STATUS_COLUMN
    # LAST_RTK_COMPASS_STATUS_COLUMN,
]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse periodic log data for one or more provided file paths."
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        help="One or more periodic log file paths to parse.", required=True
    )
    parser.add_argument(
        "--columns",
        nargs="+",
        default=list(DEFAULT_TARGET_COLUMNS),
        help=f"Target column names to display. Default: {' '.join(DEFAULT_TARGET_COLUMNS)}",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=2,
        help="Time window to capture in hours.",
    )
    parser.add_argument(
        "--output",
        help="Optional file path to store table output. Default: temp/PlogPaths_output.txt",
    )

    return parser.parse_args(argv)


def get_unique_ins_statuses(plog_datas: List[PLogData]) -> List[str]:
    list_of_list_values: List[List[str]] = [plog_data.get_target_column_row_values(LAST_KIM_HW_STATUS_COLUMN) for plog_data in plog_datas]
    
    # Flatten the list of lists into a single list
    result: List[str] = []
    for status_list in list_of_list_values:
        result.extend(status_list)
    
    # Make unique order by appearance
    seen = set()
    unique_result = []
    for status in result:
        if status not in seen:
            seen.add(status)
            unique_result.append(status)
    return unique_result

def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    success_count = 0
    start_time = time.time()
    plog_datas: List[PLogData] = []
    for index, raw_path in enumerate(args.paths, start=1):
        exists, resolved_path = expand_and_check_path(raw_path)
        if not exists:
            LOG(f"{LOG_PREFIX_MSG_ERROR} Log path does not exist: {resolved_path}")
            continue

        LOG(f"{LOG_PREFIX_MSG_INFO} Parsing periodic log: {resolved_path}")
        try:
            plog_data: PLogData = parse_periodic_log( log_path=resolved_path, target_columns=args.columns, max_time_capture=args.hours, )
            plog_datas.append(plog_data)
        except ValueError as exc:
            LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to parse '{resolved_path}': {exc}")
            continue

        success_count += 1

    ins_statuses_list: List[str] = get_unique_ins_statuses(plog_datas)
    for ins_status in ins_statuses_list:
        print(ins_status)
        decoded_status = decode_ins_status(ins_status)
        print_ins_status(decoded_status)

    if success_count == 0:
        LOG(f"{LOG_PREFIX_MSG_WARNING} No logs were parsed successfully.")
        return 1

    LOG(f"{LOG_PREFIX_MSG_INFO} Finished parsing {success_count} log(s) in {time.time() - start_time:.2f} seconds.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
