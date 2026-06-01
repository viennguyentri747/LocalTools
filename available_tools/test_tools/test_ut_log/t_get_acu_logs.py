#!/usr/local/bin/local_python
import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional
from available_tools.test_tools.common import *
from dev.dev_common import *

DEFAULT_LOG_TYPE_PREFIXES = [P_LOG_PREFIX, E_LOG_PREFIX]
ACU_LOG_PATH = get_temp_path(ETargetPlatform.WINDOWS) / "acu_logs"
DEFAULT_LOG_OUTPUT_PATH = ACU_LOG_PATH
LOCAL_LOG_WRAPPER_CMD = f"{Path(__file__).resolve().parents[1] / 't_test_logs_from_local.py'} --mode get_acu_logs"
ARG_LOG_TYPES = f"{ARGUMENT_LONG_PREFIX}type"
ARG_DATE_FILTERS = f"{ARGUMENT_LONG_PREFIX}date"
ARG_LOG_OUTPUT_DIR_PATH = f"{ARGUMENT_LONG_PREFIX}log_output_path"
ARG_MAX_THREAD_COUNT = f"{ARGUMENT_LONG_PREFIX}max_threads"
DEFAULT_MAX_THREAD_COUNT = 20
DEFAULT_EXTRA_DAYS = 1

DEFAULT_DATE_VALUES = [
    get_acu_log_datename_from_date(get_datetime_now() - timedelta(days=days_to_cut))
    for days_to_cut in range(DEFAULT_EXTRA_DAYS + 1) # Starts at 0 (for today), ends at DEFAULT_EXTRA_DAYS (for old days)
]

def getToolData() -> ToolData:
    tool_templates = [
        ToolTemplate(
            name="Get ACU Logs",
            extra_description="Copy flash log files from remote",
            args={
                ARG_LOG_OUTPUT_DIR_PATH: str(DEFAULT_LOG_OUTPUT_PATH),
                ARG_LOG_TYPES: list(DEFAULT_LOG_TYPE_PREFIXES),
                ARG_LIST_IPS: [f"{SSM_NORMAL_IP_PREFIX}.57", f"{SSM_NORMAL_IP_PREFIX}.59"],
                ARG_DATE_FILTERS: DEFAULT_DATE_VALUES,
            },
            override_cmd_invocation=LOCAL_LOG_WRAPPER_CMD,
        ),
    ]
    return ToolData(tool_templates=tool_templates, tool_priority=EToolPriority.Level0_First, hidden=False)



def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Pull flash log files via SSH jump hosts.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))
    parser.add_argument(
        ARG_LOG_TYPES,
        nargs='+',
        choices=DEFAULT_LOG_TYPE_PREFIXES,
        required=True,
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
        ARG_LOG_OUTPUT_DIR_PATH,
        type=str,
        default=str(DEFAULT_LOG_OUTPUT_PATH),
        help='Directory where fetched logs will be stored.',
    )
    parser.add_argument(
        ARG_MAX_THREAD_COUNT,
        type=int,
        default=DEFAULT_MAX_THREAD_COUNT,
        #default=1,
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


class FetchProgressTracker:
    """Per-IP ACU fetch tracker built on top of generic ParallelSpinner."""

    STATUS_LABELS = {
        "pending": "waiting",
        "copying": "copying",
        "done": "done",
        "failed": "failed",
        "skipped": "skipped",
    }
    STATUS_ORDER = ("pending", "copying", "done", "failed", "skipped")

    def __init__(self, ips: List[str]) -> None:
        self._status_by_ip: Dict[str, str] = {ip: "pending" for ip in ips}
        self._lock = threading.RLock()
        self._active = bool(ips)
        self._spinner = ParallelSpinner(title="ACU Log Fetch Progress")
        if self._active:
            LOG(f"{LOG_PREFIX_MSG_INFO} Progress UI backend: {self._spinner.backend_name}")
            self._spinner.start()
            for ip in ips:
                self._spinner.add_task(task_id=ip, label=ip, status=self.STATUS_LABELS["pending"], detail="Waiting")

    def set_status(self, ip: str, status: str) -> None:
        if not self._active:
            return
        with self._lock:
            if ip not in self._status_by_ip:
                return
            self._status_by_ip[ip] = status
            status_label = self.STATUS_LABELS.get(status, status)
            percent = 100.0 if status in ("done", "failed", "skipped") else None
            self._spinner.update_task(task_id=ip, status=status_label, detail=f"State: {status_label}", percent=percent)

    def set_transfer_progress(self, ip: str, label: str, transferred_bytes: int, total_bytes: int) -> None:
        if not self._active:
            return
        with self._lock:
            if ip not in self._status_by_ip:
                return
            percent = 100.0 if total_bytes <= 0 else (max(0, min(transferred_bytes, total_bytes)) * 100.0 / float(total_bytes))
            transferred_h = format_bytes_human(max(0, transferred_bytes))
            total_h = format_bytes_human(max(0, total_bytes))
            detail = f"{label}: {transferred_h}/{total_h}"
            self._spinner.update_task(task_id=ip, status=self.STATUS_LABELS["copying"], detail=detail, percent=percent)

    def finish(self) -> None:
        if not self._active:
            return
        final_text = self._build_status_text()
        for ip, status in self._status_by_ip.items():
            self._spinner.update_task(task_id=ip, status=self.STATUS_LABELS.get(status, status), detail="Completed")
        self._spinner.stop(final_message=final_text, emit_final=True)
        self._active = False

    def _build_status_text(self) -> str:
        parts: List[str] = []
        with self._lock:
            for status in self.STATUS_ORDER:
                ips = [ip for ip, stat in self._status_by_ip.items() if stat == status]
                if not ips:
                    continue
                parts.append(self._format_group(self.STATUS_LABELS.get(status, status), ips))
        return " | ".join(parts) if parts else "no hosts to track"

    @staticmethod
    def _format_group(label: str, ips: List[str]) -> str:
        display_ips = ", ".join(ips[:3])
        if len(ips) > 3:
            display_ips += f"...(+{len(ips) - 3})"
        display_ips = display_ips or "-"
        return f"{label}:{len(ips)}[{display_ips}]"


def batch_fetch_acu_logs(ut_ips: List[str], log_types: List[str], date_filters: Optional[List[str]], log_output_dir: Path, max_thread_count: int, user: str = "root", public_key_path: Path = Path.home() / ".ssh" / "id_rsa.pub", should_has_var_logs: bool = False) -> List[AcuLogInfo]:
    if not ut_ips:
        return []

    progress_tracker = FetchProgressTracker(ut_ips)
    # Separate IPs into those with and without passwordless access
    passwordless_ips = []
    password_required_ips = []
    results_by_ip: Dict[str, AcuLogInfo] = {}

    # Check SSH status in parallel
    ssh_statuses = check_ssh_pwless_statuses(
        ut_ips, user, public_key_path, max_workers=max_thread_count
    )
    passwordless_ips = list(ssh_statuses.passwordless_ips)
    password_required_ips = list(ssh_statuses.password_required_ips)

    if ssh_statuses.unreachable_ips:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Skipping {len(ssh_statuses.unreachable_ips)} unreachable host(s): {', '.join(ssh_statuses.unreachable_ips)}")
        for ut_ip in ssh_statuses.unreachable_ips:
            results_by_ip[ut_ip] = AcuLogInfo(is_valid=False, ip=ut_ip)
            progress_tracker.set_status(ut_ip, "skipped")

    # First, handle hosts that need password (sequentially)
    if password_required_ips:
        LOG(f"{LOG_PREFIX_MSG_INFO} Installing SSH keys on {len(password_required_ips)} hosts (requires password)...")
        for ut_ip in password_required_ips:
            LOG(f"{LOG_PREFIX_MSG_INFO} Setting up SSH key for {ut_ip}...")

            # This function now contains the proactive removal logic
            if setup_host_ssh_key(user, ut_ip, public_key_path, password=SSM_PASSWORD):
                passwordless_ips.append(ut_ip)
            else:
                LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to copy SSH key to {ut_ip}, skipping...")
                results_by_ip[ut_ip] = AcuLogInfo(is_valid=False, ip=ut_ip)
                progress_tracker.set_status(ut_ip, "failed")
                #LOG_EXCEPTION(f"Failed to copy SSH key to {ip}, quitting, check make sure enter correct PW!")

    # Now fetch logs from all hosts with passwordless access (parallel)
    if passwordless_ips:
        effective_workers = max(1, max_thread_count or 1)
        max_workers = min(effective_workers, len(passwordless_ips))

        def _fetch_single_ip(ip: str) -> AcuLogInfo:
            LOG(f"{LOG_PREFIX_MSG_INFO} Attempting batch download for {ip}...")
            dest_path = log_output_dir / ip
            progress_tracker.set_status(ip, "copying")
            try:
                fetch_info = fetch_acu_logs(
                    log_types=log_types, ut_ip=ip, date_filters=date_filters, dest_folder_path=dest_path, should_has_var_log=should_has_var_logs,
                    open_in_explorer=False, on_progress=lambda label, transferred, total: progress_tracker.set_transfer_progress(ip, label, transferred, total),
                    emit_progress_log=False,
                )
            except Exception:
                progress_tracker.set_status(ip, "failed")
                raise
            progress_tracker.set_status(ip, "done" if fetch_info.is_valid else "failed")
            return fetch_info

        if max_workers == 1:
            for ut_ip in passwordless_ips:
                results_by_ip[ut_ip] = _fetch_single_ip(ut_ip)
        else:
            start_time = time.time()
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(_fetch_single_ip, ip): ip for ip in passwordless_ips}
                for future in as_completed(future_map):
                    ut_ip = future_map[future]
                    try:
                        results_by_ip[ut_ip] = future.result()
                    except Exception as exc:
                        LOG(f"{LOG_PREFIX_MSG_ERROR} Unexpected error while fetching logs for {ut_ip}: {exc}")
                        results_by_ip[ut_ip] = AcuLogInfo(is_valid=False, ip=ut_ip)
                        progress_tracker.set_status(ut_ip, "failed")
            LOG(f"All fetch tasks completed in {time.time() - start_time:.1f} seconds.")

    consolidated_results = [results_by_ip.get(ip, AcuLogInfo(is_valid=False, ip=ip)) for ip in ut_ips]
    progress_tracker.finish()
    return consolidated_results


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


def _summarize_fetch_results(ips: List[str], summaries: Dict[str, IpFetchSummary], has_date_filters: bool, log_output_dir: Path) -> None:
    ip_list_str = ", ".join(str(ip) for ip in ips)
    LOG(f"Log Fetch Summary for IPs [{ip_list_str}]")
    LOG("", show_time=False)
    LOG_LINE_SEPARATOR()

    for index, ip in enumerate(ips):
        summary = summaries.get(ip, IpFetchSummary(log_directory=log_output_dir / ip))
        LOG(f"IP:{ip}")
        LOG(f"Log Directory: {format_path_for_display(summary.log_directory)}")
        LOG("Log Files Status:")

        if summary.log_files:
            LOG(f"- ✓ Found: {summary.log_files}")
            LOG(f"- ✗ Missing: {_format_missing_text(summary, has_date_filters)}")
        else:
            LOG("- ✓ Found: None")
            LOG(f"- ✗ Missing: {_format_missing_text(summary, has_date_filters)}")
            if not summary.fetch_success:
                LOG_ISSUE("Fetch status: No log files were downloaded for this IP")

        if index < len(ips) - 1:
            LOG("", show_time=False)
            LOG_LINE_SEPARATOR()

    LOG("", show_time=False)
    LOG(f"{LINE_SEPARATOR}", show_time=False)


def _format_missing_text(summary: IpFetchSummary, has_date_filters: bool) -> str:
    if not has_date_filters:
        return "Unknown (no date filters provided)"
    if summary.missing_logs:
        return str(summary.missing_logs)
    return "None"


def _open_result_path_in_explorer(ips: List[str], log_output_dir: Path, summaries: Dict[str, IpFetchSummary]) -> None:
    has_any_downloaded_logs = any(bool(summary.log_files) for summary in summaries.values())
    if not has_any_downloaded_logs:
        LOG_ISSUE("No logs were downloaded; skipping Explorer open.")
        return

    if len(ips) == 1:
        ip_dir = log_output_dir / ips[0]
        open_directory_in_explorer(ip_dir)
        return
    open_directory_in_explorer(log_output_dir)



def main() -> None:
    args = parse_args()
    log_types: List[str] = get_arg_value(args, ARG_LOG_TYPES)
    ips: List[str] = get_arg_value(args, ARG_LIST_IPS)
    date_filters: Optional[List[str]] = get_arg_value(args, ARG_DATE_FILTERS)
    log_output_dir = Path(get_arg_value(args, ARG_LOG_OUTPUT_DIR_PATH)).expanduser()
    max_thread_count: int = get_arg_value(args, ARG_MAX_THREAD_COUNT)
    log_output_dir.mkdir(parents=True, exist_ok=True)

    LOG(f"Storing fetched logs under: {format_path_for_display(log_output_dir)}")
    results = batch_fetch_acu_logs(
        ut_ips=ips,
        log_types=log_types,
        date_filters=date_filters,
        log_output_dir=log_output_dir,
        max_thread_count=max_thread_count,
    )

    summaries: Dict[str, IpFetchSummary] = _build_result_summaries(results, log_types, date_filters, log_output_dir)
    _summarize_fetch_results(ips, summaries, bool(date_filters), log_output_dir)
    _open_result_path_in_explorer(ips=ips, log_output_dir=log_output_dir, summaries=summaries)

    show_noti(title="ACU Log Fetch Summary", message="See log for details")


if __name__ == '__main__':
    main()
