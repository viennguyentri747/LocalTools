#!/home/vien/local_tools/MyVenvFolder/bin/python
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path
import argparse
from available_tools.remote_tools.common import *
from dev_common import *


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Get ACU Logs",
            extra_description="Copy flash log files from remote",
            args={"--type": ["P", "T", "E"], "--ips": LIST_MP_IPS,
                  "--date": ["20250625", "20250627", get_acu_log_datename_from_date(datetime.now())]},
        ),
    ]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Pull flash log files via SSH jump hosts.'
    )
    parser.formatter_class = argparse.RawTextHelpFormatter
    # Fill help epilog from templates
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument('-t', '--type', nargs='+', choices=['P', 'T', 'E'],
                        required=True, help='Log filename prefix(es) (P, T, or E).')
    parser.add_argument('-i', '--ips', nargs='+', required=True, help='UT IP address(es) to use as SSH jump host(s).')
    parser.add_argument('-d', '--date', nargs='+',
                        help='Date(s) to filter logs (YYYYMMDD format). If provided, only logs starting with these dates will be fetched.')
    return parser.parse_args()


@dataclass
class IpFetchSummary:
    """Minimal per-IP summary data for fetched ACU logs."""

    log_directory: Path = field(default_factory=Path)
    log_files: List[str] = field(default_factory=list)
    missing_logs: Optional[List[str]] = None
    fetch_success: bool = False


def _build_ip_summaries(ips: List[str], results: List[AcuLogInfo], log_types: List[str], date_filters: Optional[List[str]]) -> Dict[str, IpFetchSummary]:
    """Collect summary information per IP based on fetch results."""

    summaries: Dict[str, IpFetchSummary] = {}
    normalized_dates = date_filters or []

    for ip in ips:
        summaries[ip] = IpFetchSummary(log_directory=ACU_LOG_PATH / ip)

    for fetch_info in results:
        ip = str(fetch_info.ut_ip)
        summary = summaries.setdefault(ip, IpFetchSummary(log_directory=ACU_LOG_PATH / ip))
        summary.log_files = sorted(Path(path).name for path in fetch_info.log_paths)
        summary.fetch_success = fetch_info.is_valid
        if normalized_dates:
            summary.missing_logs = calc_missing_logs(summary.log_files, log_types, normalized_dates)

    if normalized_dates:
        for ip, summary in summaries.items():
            if summary.missing_logs is None:
                summary.missing_logs = calc_missing_logs(summary.log_files, log_types, normalized_dates)

    return summaries


def _format_missing_text(summary: IpFetchSummary, has_date_filters: bool) -> str:
    if not has_date_filters:
        return "Unknown (no date filters provided)"
    if summary.missing_logs:
        return str(summary.missing_logs)
    return "None"


def _summarize_fetch_results(ips: List[str], summaries: Dict[str, IpFetchSummary], has_date_filters: bool) -> None:
    ip_list_str = ", ".join(str(ip) for ip in ips)
    LOG(f"Log Fetch Summary for IPs [{ip_list_str}]")
    LOG("", show_time=False)
    LOG(f"{LINE_SEPARATOR}", show_time=False)

    for index, ip in enumerate(ips):
        summary = summaries.get(ip, IpFetchSummary(log_directory=ACU_LOG_PATH / ip))
        LOG(f"IP:{ip}")
        LOG(f"Log Directory: {summary.log_directory}")
        LOG("Log Files Status:")

        if summary.log_files:
            LOG(f"- ✓ Found: {summary.log_files}")
            LOG(f"- ✗ Missing: {_format_missing_text(summary, has_date_filters)}")
        else:
            LOG("- ✓ Found: None")
            LOG(f"- ✗ Missing: {_format_missing_text(summary, has_date_filters)}")
            if not summary.fetch_success:
                LOG("Fetch status: No log files were downloaded for this IP")

        if index < len(ips) - 1:
            LOG("", show_time=False)
            LOG(f"{LINE_SEPARATOR}", show_time=False)

    LOG("", show_time=False)
    LOG(f"{LINE_SEPARATOR}", show_time=False)


def main() -> None:
    args = parse_args()

    results: List[AcuLogInfo] = []
    for ip in args.ips:
        LOG(f"{LOG_PREFIX_MSG_INFO} Attempting batch download for {ip}...")
        dest_path = ACU_LOG_PATH / ip
        result: AcuLogInfo = fetch_acu_logs(log_types=args.type, ut_ip=ip,
                                            date_filters=args.date, dest_folder_path=dest_path, )
        results.append(result)

    summaries = _build_ip_summaries(args.ips, results, args.type, args.date)
    _summarize_fetch_results(args.ips, summaries, bool(args.date))
    show_noti(title="ACU Log Fetch Summary", message="See log for details")


if __name__ == '__main__':
    main()
