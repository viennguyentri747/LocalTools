#!/home/vien/local_tools/MyVenvFolder/bin/python
import argparse
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from available_tools.test_tools.common import *
from dev_common import *

DEFAULT_LOG_TYPE_PREFIXES = [P_LOG_PREFIX, T_LOG_PREFIX, E_LOG_PREFIX]
DEFAULT_LOG_OUTPUT_PATH = ACU_LOG_PATH
ARG_LOG_TYPES = f"{ARGUMENT_LONG_PREFIX}type"
ARG_DATE_FILTERS = f"{ARGUMENT_LONG_PREFIX}date"
ARG_LOG_OUTPUT_PATH = f"{ARGUMENT_LONG_PREFIX}log_output_path"
ARG_PATTERNS = f"{ARGUMENT_LONG_PREFIX}patterns"
ARG_MAX_THREAD_COUNT = f"{ARGUMENT_LONG_PREFIX}max_threads"
MOTION_DETECT_PATTERN = r"MOTION DETECT"
INS_MONITOR_START_PATTERN = r"INS-READY"
DEFAULT_MAX_THREAD_COUNT = 20


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name=f"Get ACU E Logs + Show command to grep pattern {MOTION_DETECT_PATTERN}",
            extra_description="Copy flash log files from remote",
            args={
                ARG_LOG_OUTPUT_PATH: str(DEFAULT_LOG_OUTPUT_PATH),
                ARG_LOG_TYPES: [E_LOG_PREFIX],
                ARG_LIST_IPS: LIST_MP_IPS,
                ARG_DATE_FILTERS: [
                    get_acu_log_datename_from_date(datetime.now() - timedelta(days=1)),
                    get_acu_log_datename_from_date(datetime.now()),
                ],
                ARG_PATTERNS: [quote(MOTION_DETECT_PATTERN), quote(INS_MONITOR_START_PATTERN)],
            },
        ),
        ToolTemplate(
            name="Get ACU Logs",
            extra_description="Copy flash log files from remote",
            args={
                ARG_LOG_OUTPUT_PATH: str(DEFAULT_LOG_OUTPUT_PATH),
                ARG_LOG_TYPES: list(DEFAULT_LOG_TYPE_PREFIXES),
                ARG_LIST_IPS: LIST_MP_IPS,
                ARG_DATE_FILTERS: [
                    get_acu_log_datename_from_date(datetime.now() - timedelta(days=1)),
                    get_acu_log_datename_from_date(datetime.now()),
                ],
            },
        ),
    ]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Pull flash log files via SSH jump hosts.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument(
        ARG_LOG_TYPES,
        nargs='+',
        choices=DEFAULT_LOG_TYPE_PREFIXES,
        default=list(DEFAULT_LOG_TYPE_PREFIXES),
        help='Log filename prefix(es) (P, T, or E).',
    )
    parser.add_argument(
        ARG_LIST_IPS,
        nargs='+',
        default=list(LIST_MP_IPS),
        help='UT IP address(es) to use as SSH jump host(s).',
    )
    parser.add_argument(
        ARG_DATE_FILTERS,
        nargs='+',
        default=None,
        help='Date(s) to filter logs (YYYYMMDD format). If provided, only logs starting with these dates will be fetched.',
    )
    parser.add_argument(
        ARG_LOG_OUTPUT_PATH,
        type=str,
        default=str(DEFAULT_LOG_OUTPUT_PATH),
        help='Directory where fetched logs will be stored.',
    )
    parser.add_argument(
        ARG_PATTERNS,
        nargs='+',
        default=None,
        help='Optional regex patterns to search within fetched logs via a generated grep command.',
    )
    parser.add_argument(
        ARG_MAX_THREAD_COUNT,
        type=int,
        default=DEFAULT_MAX_THREAD_COUNT,
        help='Maximum concurrent fetch operations (must be >= 1).',
    )
    return parser.parse_args()


@dataclass
class IpFetchSummary:
    """Minimal per-IP summary data for fetched ACU logs."""

    log_directory: Path = field(default_factory=Path)
    log_files: List[str] = field(default_factory=list)
    missing_logs: Optional[List[str]] = None
    fetch_success: bool = False


def batch_fetch_acu_logs(ips: List[str], log_types: List[str], date_filters: Optional[List[str]], log_output_dir: Path, max_thread_count: int, user: str = "root", public_key_path: Path = Path.home() / ".ssh" / "id_rsa.pub", ) -> List[AcuLogInfo]:
    if not ips:
        return []

    # Separate IPs into those with and without passwordless access
    passwordless_ips = []
    password_required_ips = []

    # Check SSH status in parallel
    passwordless_ips, password_required_ips = check_ssh_pwless_statuses(
        ips, user, public_key_path, max_workers=max_thread_count
    )

    results_by_ip: Dict[str, AcuLogInfo] = {}
    # First, handle hosts that need password (sequentially)
    if password_required_ips:
        LOG(f"{LOG_PREFIX_MSG_INFO} Installing SSH keys on {len(password_required_ips)} hosts (requires password)...")
        for ip in password_required_ips:
            LOG(f"{LOG_PREFIX_MSG_INFO} Setting up SSH key for {ip}...")
            
            # This function now contains the proactive removal logic
            if setup_host_ssh_key(user, ip, public_key_path):
                passwordless_ips.append(ip)
            else:
                LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to copy SSH key to {ip}, skipping...")
                results_by_ip[ip] = AcuLogInfo(is_valid=False, ip=ip)    

    # Now fetch logs from all hosts with passwordless access (parallel)
    if passwordless_ips:
        effective_workers = max(1, max_thread_count or 1)
        max_workers = min(effective_workers, len(passwordless_ips))

        def _fetch_single_ip(ip: str) -> AcuLogInfo:
            LOG(f"{LOG_PREFIX_MSG_INFO} Attempting batch download for {ip}...")
            dest_path = log_output_dir / ip
            return fetch_acu_logs( log_types=log_types, ut_ip=ip, date_filters=date_filters, dest_folder_path=dest_path, )

        if max_workers == 1:
            for ip in passwordless_ips:
                results_by_ip[ip] = _fetch_single_ip(ip)
        else:
            start_time = time.time()
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(_fetch_single_ip, ip): ip for ip in passwordless_ips}
                for future in as_completed(future_map):
                    ip = future_map[future]
                    try:
                        results_by_ip[ip] = future.result()
                    except Exception as exc:
                        LOG(f"{LOG_PREFIX_MSG_ERROR} Unexpected error while fetching logs for {ip}: {exc}")
                        results_by_ip[ip] = AcuLogInfo(is_valid=False, ip=ip)
            LOG(f"All fetch tasks completed in {time.time() - start_time:.1f} seconds.")

    return [results_by_ip.get(ip, AcuLogInfo(is_valid=False, ip=ip)) for ip in ips]


def _build_result_summaries(
    results: List[AcuLogInfo],
    log_types: List[str],
    date_filters: Optional[List[str]],
    log_output_dir: Path,
) -> Dict[str, IpFetchSummary]:
    """Collect summary information per IP based on fetch results."""

    summaries: Dict[str, IpFetchSummary] = {}
    normalized_dates = date_filters or []

    # Build summaries from fetch results
    for fetch_info in results:
        ip = str(fetch_info.ut_ip)
        summary = summaries.setdefault(ip, IpFetchSummary(log_directory=log_output_dir / ip))
        summary.log_files = sorted(Path(path).name for path in fetch_info.log_paths)
        summary.fetch_success = fetch_info.is_valid

    # Calculate missing logs once for all summaries if dates provided
    if normalized_dates:
        for summary in summaries.values():
            summary.missing_logs = calc_missing_logs(summary.log_files, log_types, normalized_dates)

    return summaries


def _summarize_fetch_results( ips: List[str], summaries: Dict[str, IpFetchSummary], has_date_filters: bool, log_output_dir: Path ) -> None:
    ip_list_str = ", ".join(str(ip) for ip in ips)
    LOG(f"Log Fetch Summary for IPs [{ip_list_str}]")
    LOG("", show_time=False)
    LOG(f"{LINE_SEPARATOR}", show_time=False)

    for index, ip in enumerate(ips):
        summary = summaries.get(ip, IpFetchSummary(log_directory=log_output_dir / ip))
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


def _format_missing_text(summary: IpFetchSummary, has_date_filters: bool) -> str:
    if not has_date_filters:
        return "Unknown (no date filters provided)"
    if summary.missing_logs:
        return str(summary.missing_logs)
    return "None"


def _build_pattern_analysis_command(
    summaries: Dict[str, IpFetchSummary], patterns: List[str]
) -> str:
    """Build a single grep command covering all fetched log files."""
    if not summaries or not patterns:
        return ""

    sanitized_patterns = [strip_quotes(p) for p in patterns if p]
    sanitized_patterns = [p for p in sanitized_patterns if p]
    if not sanitized_patterns:
        return ""

    combined_pattern = "|".join(sanitized_patterns)
    log_file_paths: List[Path] = []

    for summary in summaries.values():
        if not summary.log_files:
            continue
        for file_name in summary.log_files:
            log_file_paths.append(summary.log_directory / file_name)

    if not log_file_paths:
        return ""

    unique_paths = sorted({path for path in log_file_paths})
    file_arguments = " ".join(quote(str(path)) for path in unique_paths)
    return f"grep -E --color=always {quote(combined_pattern)} {file_arguments}"


def main() -> None:
    args = parse_args()
    log_types: List[str] = get_arg_value(args, ARG_LOG_TYPES)
    ips: List[str] = get_arg_value(args, ARG_LIST_IPS)
    date_filters: Optional[List[str]] = get_arg_value(args, ARG_DATE_FILTERS)
    log_output_dir = Path(get_arg_value(args, ARG_LOG_OUTPUT_PATH)).expanduser()
    pattern_inputs: Optional[List[str]] = (get_arg_value(args, ARG_PATTERNS))
    max_thread_count: int = get_arg_value(args, ARG_MAX_THREAD_COUNT)
    log_output_dir.mkdir(parents=True, exist_ok=True)

    LOG(f"Storing fetched logs under: {log_output_dir}")
    results = batch_fetch_acu_logs(
        ips=ips,
        log_types=log_types,
        date_filters=date_filters,
        log_output_dir=log_output_dir,
        max_thread_count=max_thread_count,
    )

    summaries: Dict[str, IpFetchSummary] = _build_result_summaries(results, log_types, date_filters, log_output_dir)
    _summarize_fetch_results(ips, summaries, bool(date_filters), log_output_dir)

    if pattern_inputs:
        command: str = _build_pattern_analysis_command(summaries, pattern_inputs)
        if command:
            display_content_to_copy(command, purpose=f"capture patterns {pattern_inputs}", is_copy_to_clipboard=True)

    show_noti(title="ACU Log Fetch Summary", message="See log for details")


if __name__ == '__main__':
    main()
