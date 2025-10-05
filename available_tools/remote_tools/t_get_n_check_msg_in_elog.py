#!/home/vien/local_tools/MyVenvFolder/bin/python
"""Fetch ACU E-logs, run pattern search, and print a summarized report."""

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from dev_common import *
from dev_common.algo_utils import get_match_info
from dev_common.custom_structures import MatchInfo
from available_tools.remote_tools.common import *

MOTION_DETECT_PATTERN = r"MOTION DETECT"
INS_MONITOR_START_PATTERN = r"INS-READY"
DEFAULT_ELOG_OUTPUT_PATH = TEMP_FOLDER_PATH / "acu_elogs/"
DEFAULT_EXTRA_DAYS_BEFORE_TODAY = 4
DEFAULT_LOG_TYPES = ["E"]

ARG_SEARCH_PATTERNS = f"{ARGUMENT_LONG_PREFIX}search_patterns"
ARG_EXTRA_DAYS_BEFORE_TODAY = f"{ARGUMENT_LONG_PREFIX}extra_days_before_today"
ARG_ELOG_OUTPUT_PATH = f"{ARGUMENT_LONG_PREFIX}elog_output_path"
ARG_LIST_IPS = f"{ARGUMENT_LONG_PREFIX}ips"


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Summarize motion detection and INS readiness",
            args={
                ARG_SEARCH_PATTERNS: ['"MOTION DETECT"', '"INS-READY"'],
                ARG_ELOG_OUTPUT_PATH: str(DEFAULT_ELOG_OUTPUT_PATH),
                ARG_EXTRA_DAYS_BEFORE_TODAY: DEFAULT_EXTRA_DAYS_BEFORE_TODAY,
                ARG_LIST_IPS: LIST_MP_IPS,
            },
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch ACU E-logs and search for specific patterns, then summarize the results.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument(
        ARG_SEARCH_PATTERNS,
        nargs='+',
        default=[],
        help="List of regex patterns to search for in the fetched E-logs.",
    )
    parser.add_argument(
        ARG_EXTRA_DAYS_BEFORE_TODAY,
        type=int,
        default=DEFAULT_EXTRA_DAYS_BEFORE_TODAY,
        help=f"Number of extra days before today to fetch logs (default: {DEFAULT_EXTRA_DAYS_BEFORE_TODAY}).",
    )
    parser.add_argument(
        ARG_ELOG_OUTPUT_PATH,
        type=str,
        default=str(DEFAULT_ELOG_OUTPUT_PATH),
        help="Directory where fetched E-logs will be stored.",
    )
    parser.add_argument(
        ARG_LIST_IPS,
        nargs='+',
        default=list(LIST_MP_IPS),
        help="List of UT IPs to fetch logs from (defaults to known MP IPs).",
    )

    return parser.parse_args()


@dataclass
class IpSummaryData:
    log_directory: Path = field(default_factory=Path)
    log_files: List[str] = field(default_factory=list)
    missing_logs: List[str] = field(default_factory=list)
    match_info: Optional[MatchInfo] = None


def _generate_date_filters(extra_days_before_today: int) -> List[str]:
    """Return date strings (YYYYMMDD) covering today and the prior N days."""
    dates: List[str] = []
    today = datetime.now()
    for offset in range(extra_days_before_today + 1):
        target_day = today - timedelta(days=offset)
        dates.append(get_acu_log_datename_from_date(target_day))
    return dates


def summarize_single_ip(ip: str, summary: IpSummaryData) -> None:
    LOG(f"{LINE_SEPARATOR}", show_time=False)
    LOG(f"IP:{ip}")
    if summary.log_directory:
        LOG(f"Log Directory: {summary.log_directory}")
    LOG("Log Files Status:")
    if summary.log_files:
        LOG(f"- ✓ Found: {summary.log_files}")
        if summary.missing_logs:
            LOG(f"- ✗ Missing: {summary.missing_logs}")
        else:
            LOG("- ✗ Missing: None")
    else:
        LOG("- ✓ Found: None")
        LOG(f"- ✗ Missing: {summary.missing_logs or ['No E-log files downloaded']}")
        LOG("Pattern check skipped since no log files found")
        return

    match_info = summary.match_info
    if match_info is None:
        LOG("> Pattern check skipped since no match info")
        return

    LOG("Pattern Analysis:")
    for pattern in match_info.get_patterns():
        matched_lines = match_info.get_matched_lines(pattern)
        LOG(f"Pattern: `{pattern}`")
        LOG(f"- Matches: {len(matched_lines)}")
        if matched_lines:
            LOG("- Lines:")
            for line in matched_lines:
                LOG(f"  - {line}")
        else:
            LOG("- Lines: None")

    LOG(f"{LINE_SEPARATOR}", show_time=False)


def main() -> None:
    args = parse_args()

    search_patterns: List[str] = get_arg_value(args, ARG_SEARCH_PATTERNS)
    extra_days_before_today: int = get_arg_value(args, ARG_EXTRA_DAYS_BEFORE_TODAY)
    elog_output_dir = Path(get_arg_value(args, ARG_ELOG_OUTPUT_PATH)).expanduser()
    list_ips: List[str] = get_arg_value(args, ARG_LIST_IPS)

    LOG(f"Using search patterns: {search_patterns}")
    LOG(f"Fetching logs from the last {extra_days_before_today} day(s) before today.")
    LOG(f"Storing fetched E-logs under: {elog_output_dir}")
    LOG(f"Fetching logs for IPs: {list_ips}")

    valid_fetch_infos: List[AcuLogInfo] = batch_fetch_acu_logs_for_days(
        list_ips=list_ips,
        extra_days_before_today=extra_days_before_today,
        log_types=DEFAULT_LOG_TYPES,
        parent_path=elog_output_dir,
    ) or []

    summaries: Dict[str, IpSummaryData] = {
        str(ip): IpSummaryData(log_directory=elog_output_dir / str(ip)) for ip in list_ips
    }

    date_filters = _generate_date_filters(extra_days_before_today)

    for fetch_info in valid_fetch_infos:
        ip = str(fetch_info.ut_ip)
        summary: IpSummaryData = summaries.setdefault(ip, IpSummaryData(log_directory=elog_output_dir / ip))
        all_logs_content = ""
        resolved_paths: List[str] = []
        for log_file in fetch_info.log_paths:
            try:
                LOG(f"Processing file: {log_file} of IP: {ip}")
                resolved_paths.append(str(log_file))
                all_logs_content += read_file_content(log_file)
            except Exception as exc:
                LOG(f"Error reading or processing file {log_file}: {exc}")
        summary.log_directory = Path(summary.log_directory) if summary.log_directory else Path(elog_output_dir) / ip
        summary.log_files = sorted(Path(p).name for p in resolved_paths)
        summary.missing_logs = calc_missing_logs(summary.log_files, DEFAULT_LOG_TYPES, date_filters)
        summary.match_info = get_match_info(all_logs_content, search_patterns,
                                            '\n') if all_logs_content and search_patterns else None

    for ip in list_ips:
        ip_str = str(ip)
        summary = summaries.setdefault(ip_str, IpSummaryData(log_directory=elog_output_dir / ip_str))
        if not summary.missing_logs:
            summary.missing_logs = calc_missing_logs(summary.log_files, DEFAULT_LOG_TYPES, date_filters)

    ip_list_str = ", ".join(str(ip) for ip in list_ips)
    LOG(f"{LINE_SEPARATOR}", show_time=False)
    LOG(f"Log Analysis Summary for IPs [{ip_list_str}]")

    for ip in list_ips:
        ip_str = str(ip)
        summary = summaries.get(ip_str, IpSummaryData(log_directory=elog_output_dir / ip_str))
        summarize_single_ip(ip_str, summary)

    show_noti(title="ACU E-log pattern summary completed", message="Check console output for details.")


if __name__ == "__main__":
    main()
