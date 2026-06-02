#!/usr/local/bin/local_python
import argparse
from contextlib import redirect_stdout
from datetime import datetime
import io
from pathlib import Path
import re
import shlex
import threading
import time
from typing import Callable, List, Optional, Sequence

from dev.dev_common import *
from dev.dev_common.custom_structures import EToolPriority, ToolData
from dev.dev_common.network_utils import ELineType
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from available_tools.inertial_sense_tools.decode_ins_status_utils import decode_ins_status
from dev.dev_iesa.iesa_ut_install_utils import check_safe_reboot_ut
from available_tools.test_tools.test_ut_log.t_get_ut_live_log import ELogStreamMode, build_live_log_handlers, close_live_log_handlers, start_stop_timer, stream_live_remote_log_to_file
from available_tools.test_tools.test_ut_log.t_get_acu_logs import DEFAULT_LOG_OUTPUT_PATH
from available_tools.test_tools.test_ut_log.t_test_ins_status_ins_monitor_log import (
    DEFAULT_MAX_SPAN_OF,
    InsStatusData,
    build_decoded_entries,
    compute_ins_message_time_diff_stats,
    group_consecutive_status_spans,
    parse_ins_status_data_from_line,
    print_progression_summary,
    print_ins_messages_time_diff_stats,
    print_status_span_report,
    read_lines,
)

DEFAULT_LOG_FILENAME = "ins_monitor_live.log"
ARG_STREAM_DURATION_SECS = f"{ARGUMENT_LONG_PREFIX}stream_duration_secs"
SSM_IP = f"{ARGUMENT_LONG_PREFIX}ssm_host_ip"
ARG_REMOTE_PATH = f"{ARGUMENT_LONG_PREFIX}remote_path"
ARG_READ_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}read_timeout"
ARG_TAIL_LINES = f"{ARGUMENT_LONG_PREFIX}tail_lines"
ARG_FILE = f"{ARGUMENT_LONG_PREFIX}file"
ARG_MAX_SPAN_OF = f"{ARGUMENT_LONG_PREFIX}max_span_of"
IMX_VERSION_PATH = "/usr/local/config/system_config/current_imx_version"
GPX_VERSION_PATH = "/usr/local/config/system_config/current_gpx_version"
KIM_SINCE_START_ANALYSIS_DIR = LOCAL_TOOL_STORAGE_PATH / "kim_since_start_analysis"
ANSI_ESCAPE_RE = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")


def getToolData() -> ToolData:
    tool_templates = [
        ToolTemplate(
            name="Capture + analyze INS monitor log",
            extra_description="Stream INS monitor log for a duration, then analyze insStatus transitions.",
            args={SSM_IP: f"{SSM_NORMAL_IP_PREFIX}.57", ARG_STREAM_DURATION_SECS: 200},
        )
    ]
    return ToolData(tool_templates=tool_templates, tool_priority=EToolPriority.Level10_Last, hidden=False)



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture INS monitor log for a period, then run INS status analysis.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))
    parser.add_argument(ARG_STREAM_DURATION_SECS, type=float, default=300.0, help="How long to stream the log before analysis.")
    parser.add_argument(SSM_IP, default=f"{SSM_NORMAL_IP_PREFIX}.57", help="SSM IP for ACU log access.")
    parser.add_argument(ARG_REMOTE_PATH, default="/var/log/ins_monitor_log", help="Remote INS monitor log path.")
    parser.add_argument(ARG_READ_TIMEOUT, type=int, default=600, help="Read timeout while streaming log lines.")
    parser.add_argument(ARG_TAIL_LINES, type=int, default=0, help="Initial historical lines before follow mode.")
    parser.add_argument(ARG_MAX_SPAN_OF, type=int, default=DEFAULT_MAX_SPAN_OF, help="Maximum span cycle width for INS status grouping.")
    return parser.parse_args()


def _build_run_capture_path(jump_host_ip: str, run_started_at: datetime) -> Path:
    run_dir_name = get_file_timestamp_with_us(run_started_at)
    return Path(DEFAULT_LOG_OUTPUT_PATH) / jump_host_ip / Path(DEFAULT_LOG_FILENAME).stem / run_dir_name / DEFAULT_LOG_FILENAME


def _read_acu_version_file(version_file_path: str, jump_host_ip: str, timeout: int = 20) -> str:
    cmd = f"cat {shlex.quote(version_file_path)}"
    ssm_password = get_ssm_password()
    stdout, stderr = run_ssh_command(host_ip=ACU_IP, user=SSM_USER, password=ssm_password, command=cmd, timeout=timeout, jump_host_ip=jump_host_ip, jump_user=SSM_USER, jump_password=ssm_password)
    version = next((line.strip() for line in (stdout or EMPTY_STR_VALUE).splitlines() if line.strip()), EMPTY_STR_VALUE)
    if not version:
        raise RuntimeError(f"Failed to read version file '{version_file_path}' via jump host {jump_host_ip}. stderr='{stderr.strip()}'")
    return version


def _resolve_imx_gpx_version(jump_host_ip: str) -> str:
    imx_version = _read_acu_version_file(IMX_VERSION_PATH, jump_host_ip=jump_host_ip)
    gpx_version = _read_acu_version_file(GPX_VERSION_PATH, jump_host_ip=jump_host_ip)
    if imx_version != gpx_version:
        raise RuntimeError(f"IMX/GPX version mismatch detected. IMX='{imx_version}', GPX='{gpx_version}'")
    return imx_version


def _build_analysis_base_dir(jump_host_ip: str, imx_gpx_version: str) -> Path:
    out_dir = KIM_SINCE_START_ANALYSIS_DIR / f"imx_gpx_{imx_gpx_version}" / jump_host_ip
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _build_analysis_artifact_paths(jump_host_ip: str, imx_gpx_version: str) -> tuple[Path, Path]:
    out_dir = _build_analysis_base_dir(jump_host_ip=jump_host_ip, imx_gpx_version=imx_gpx_version)
    ts = get_file_timestamp_with_us(get_datetime_now())
    return out_dir / f"ins_status_summary_{ts}.log", out_dir / f"ins_status_spans_{ts}.log"


def _strip_ansi(value: str) -> str:
    return ANSI_ESCAPE_RE.sub("", value).replace("\r", "")


def _capture_plain_log_output(render_fn: Callable[[], None]) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        render_fn()
    return _strip_ansi(buffer.getvalue())


def _fmt_dt(value: Optional[datetime]) -> str:
    return get_log_timestamp(value) if value else "N/A"


def _capture_log_sort_key(log_path: Path, candidate: Path) -> int:
    if candidate == log_path:
        return 0
    suffix = candidate.name.removeprefix(f"{log_path.name}.")
    return int(suffix) if suffix.isdigit() else -1


def get_capture_log_paths(log_path: Path) -> List[Path]:
    candidates: List[Path] = []
    if log_path.is_file():
        candidates.append(log_path)
    candidates.extend(path for path in log_path.parent.glob(f"{log_path.name}.*") if path.is_file() and path.name.removeprefix(f"{log_path.name}.").isdigit())
    return sorted(set(candidates), key=lambda path: _capture_log_sort_key(log_path, path), reverse=True)


def _render_span_lines_without_ansi(status_spans: Sequence) -> str:
    lines: List[str] = []
    ts = get_log_timestamp()
    lines.append(f"[{ts}] === Status Changes Summary ===")
    unique_statuses = {status for span in status_spans for status in span.pattern_statuses}
    lines.append(f"[{ts}] Total spans: {len(status_spans)}")
    lines.append(f"[{ts}] Unique insStatus values: {len(unique_statuses)}")
    lines.append(f"[{ts}] Position key: startMsg# is the 1-based index among parsed INS1Msg lines.")
    for idx, span in enumerate(status_spans, 1):
        lines.append("")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"[{ts}] === SPAN-OF-{span.span_of} [{idx}] ===")
        lines.append(f"[{ts}]     start={span.start_time} end={span.end_time} duration={span.duration_secs:.3f}s msgs={span.message_count} startMsg#={span.start_offset + 1} loop={span.loop_count}")
        if span.span_of == 1:
            lines.append(f"[{ts}] {decode_ins_status(span.status).to_compact_str()}")
        else:
            for pattern_idx, status in enumerate(span.pattern_statuses, 1):
                lines.append(f"[{ts}]     pattern[{pattern_idx}] status=0x{status:08X} ({status})")
                lines.append(f"[{ts}] {decode_ins_status(status).to_compact_str()}")
        lines.append("")
        lines.append("=" * 70)
    lines.append("")
    return "\n".join(lines)


def _write_analysis_artifacts(summary_output_path: Path, spans_output_path: Path, jump_host_ip: str, acu_ip: str, imx_gpx_version: str, source_log_path: Path,
                              analyzed_log_paths: Sequence[Path], status_entries: Sequence[InsStatusData], status_spans: Sequence, decoded_entries: Sequence, time_diff_stats: Optional[object]) -> None:
    spans_output_path.parent.mkdir(parents=True, exist_ok=True)
    spans_output_path.write_text(_render_span_lines_without_ansi(status_spans), encoding="utf-8")
    summary_body = _capture_plain_log_output(lambda: (print_ins_messages_time_diff_stats(time_diff_stats), print_progression_summary(decoded_entries)))
    summary_lines = [
        f"jump_host_ip={jump_host_ip}",
        f"acu_ip={acu_ip}",
        f"imx_version={imx_gpx_version}",
        f"gpx_version={imx_gpx_version}",
        f"log_path={source_log_path}",
        f"status_spans_file={spans_output_path}",
        f"status_spans_count={len(status_spans)}",
        f"parsed_ins1msg_count={len(status_entries)}",
        f"analyzed_log_files={', '.join(str(path) for path in analyzed_log_paths)}",
        "",
        summary_body.rstrip(),
        "",
    ]
    summary_output_path.write_text("\n".join(summary_lines), encoding="utf-8")


def analyze_ins_status_file(log_path: Path, max_span_of: int = DEFAULT_MAX_SPAN_OF, *, summary_output_path: Optional[Path] = None,
                            spans_output_path: Optional[Path] = None, jump_host_ip: Optional[str] = None, acu_ip: Optional[str] = None,
                            imx_gpx_version: Optional[str] = None) -> int:
    log_paths = get_capture_log_paths(log_path)
    if not log_paths:
        LOG_ISSUE("No captured INS monitor log files found for analysis.")
        return 0
    LOG(f"{LOG_PREFIX_MSG_INFO} Analyze {len(log_paths)} capture file(s): {', '.join(str(path) for path in log_paths)}")
    lines: List[str] = []
    for log_path in log_paths:
        lines.extend(read_lines(str(log_path)))
    status_entries: List[InsStatusData] = [entry for idx, line in enumerate(lines, 1) if (entry := parse_ins_status_data_from_line(line, idx)) is not None]
    if not status_entries:
        LOG_ISSUE("No INS1Msg lines found in input.")
        return 0
    LOG(f"Parsed {len(status_entries)} INS1Msg lines from {len(lines)} input lines across {len(log_paths)} capture file(s).")
    print()
    status_spans = group_consecutive_status_spans(status_entries, max_span_of=max_span_of)
    print_status_span_report(status_spans)
    time_diff_stats = compute_ins_message_time_diff_stats(status_entries)
    decoded_entries = build_decoded_entries(status_entries)
    print_ins_messages_time_diff_stats(time_diff_stats)
    print_progression_summary(decoded_entries)
    if summary_output_path and spans_output_path and jump_host_ip and acu_ip and imx_gpx_version:
        _write_analysis_artifacts(summary_output_path=summary_output_path, spans_output_path=spans_output_path, jump_host_ip=jump_host_ip, acu_ip=acu_ip,
                                  imx_gpx_version=imx_gpx_version, source_log_path=log_path, analyzed_log_paths=log_paths, status_entries=status_entries,
                                  status_spans=status_spans, decoded_entries=decoded_entries, time_diff_stats=time_diff_stats)
    LOG("Analysis complete.")
    return 0


def main() -> int:
    test_start_at = get_datetime_now()
    test_start_wall = time.time()
    args = parse_args()
    stream_duration_secs: float = get_arg_value(args, ARG_STREAM_DURATION_SECS)
    first_log_timeout_secs = stream_duration_secs
    #capture_log_path: str | None = get_arg_value(args, ARG_CAPTURE_LOG_PATH)
    ssm_ip: str = get_arg_value(args, SSM_IP)
    host_ip: str = ACU_IP
    remote_path: str = get_arg_value(args, ARG_REMOTE_PATH)
    read_timeout: int = get_arg_value(args, ARG_READ_TIMEOUT)
    tail_lines: int = get_arg_value(args, ARG_TAIL_LINES)
    max_span_of: int = get_arg_value(args, ARG_MAX_SPAN_OF)

    log_path = _build_run_capture_path(ssm_ip, run_started_at=test_start_at)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    LOG(f"{LOG_PREFIX_MSG_INFO} Safe reboot target UT {ssm_ip} before streaming")
    if not check_safe_reboot_ut(ut_ip=ssm_ip, should_ping_after_reboot=False):
        LOG(f"{LOG_PREFIX_MSG_ERROR} Safe reboot failed for target UT {ssm_ip}")
        return 1
    sleep_before_streaming = 10
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Reboot issued for target UT {ssm_ip}. Sleep for {sleep_before_streaming} seconds before streaming logs")
    time.sleep(sleep_before_streaming)

    handlers = build_live_log_handlers(output_log_path=str(log_path), log_stream_mode=ELogStreamMode.OverrideSingleFile)
    stop_event = threading.Event()
    stop_timer: Optional[threading.Timer] = None
    first_log_timeout_timer: Optional[threading.Timer] = None
    first_log_at: Optional[datetime] = None
    first_log_monotonic: Optional[float] = None
    first_log_timeout_hit = False

    def _on_first_log_timeout() -> None:
        nonlocal first_log_timeout_hit
        if first_log_at is not None:
            return
        first_log_timeout_hit = True
        LOG(f"{LOG_PREFIX_MSG_ERROR} No log line received within {int(first_log_timeout_secs)}s. Stop streaming.")
        stop_event.set()

    def _on_line_recv(line: str, line_type: ELineType) -> None:
        nonlocal first_log_at, first_log_monotonic, stop_timer
        if line_type != ELineType.LiveLog:
            return
        if first_log_at is not None:
            return
        first_log_at, first_log_monotonic = get_datetime_now(), time.time()
        LOG(f"{LOG_PREFIX_MSG_INFO} First log line received at {_fmt_dt(first_log_at)}. Start stream duration timer ({stream_duration_secs}s).")
        stop_timer = start_stop_timer(stream_duration_secs=stream_duration_secs, stop_event=stop_event)

    LOG(f"{LOG_PREFIX_MSG_INFO} Capture live INS monitor log to {log_path}")
    try:
        first_log_timeout_timer = threading.Timer(first_log_timeout_secs, _on_first_log_timeout)
        first_log_timeout_timer.daemon = True
        first_log_timeout_timer.start()
        stream_live_remote_log_to_file(host_ip=host_ip, remote_log_path=remote_path, jump_host_ip=ssm_ip, read_timeout=read_timeout, tail_lines=tail_lines, handlers=handlers, stop_event=stop_event, on_line_recv=_on_line_recv)
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Capture live INS monitor log failed: {exc}")
        return 1
    finally:
        if first_log_timeout_timer:
            first_log_timeout_timer.cancel()
        if stop_timer:
            stop_timer.cancel()
        close_live_log_handlers(handlers)
    stream_end_at, stream_end_wall = get_datetime_now(), time.time()
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Capture live INS monitor log completed.")
    
    imx_gpx_version = _resolve_imx_gpx_version(ssm_ip)
    analysis_summary_path, analysis_spans_path = _build_analysis_artifact_paths(jump_host_ip=ssm_ip, imx_gpx_version=imx_gpx_version)
    LOG(f"{LOG_PREFIX_MSG_INFO} Analyze INS status")
    LOG(f"{LOG_PREFIX_MSG_INFO} Persist analysis summary to {analysis_summary_path}")
    LOG(f"{LOG_PREFIX_MSG_INFO} Persist status spans to {analysis_spans_path}")
    rc = analyze_ins_status_file(log_path, max_span_of=max_span_of, summary_output_path=analysis_summary_path, spans_output_path=analysis_spans_path, jump_host_ip=ssm_ip, acu_ip=host_ip, imx_gpx_version=imx_gpx_version)
    if rc != 0: return rc
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Analyze INS status completed.")
    has_non_empty_capture = any(path.stat().st_size > 0 for path in get_capture_log_paths(log_path))
    if has_non_empty_capture:
        open_path_in_explorer(log_path)
    else:
        LOG_ISSUE(f"No INS-monitor capture artifact generated at {format_path_for_display(log_path)}; skipping Explorer open.")

    LOG("=== Capture Summary ===")
    LOG(f"test start at: {_fmt_dt(test_start_at)}")
    LOG(f"log file: {log_path}")
    LOG(f"analysis summary file: {analysis_summary_path}")
    LOG(f"analysis spans file: {analysis_spans_path}")
    LOG(f"analyzed log files: {', '.join(str(path) for path in get_capture_log_paths(log_path)) or 'N/A'}")
    LOG(f"log start at: {_fmt_dt(first_log_at)}")
    LOG(f"capture end at: {_fmt_dt(stream_end_at)}")
    LOG(f"ssm ip: {ssm_ip}")
    LOG(f"remote path: {remote_path}")
    LOG(f"configured stream duration (after first log): {stream_duration_secs:.1f}s")
    if first_log_timeout_hit:
        LOG(f"first-log timeout: {int(first_log_timeout_secs)}s")
        LOG(f"first-log timeout hit: {'YES' if first_log_timeout_hit else 'NO'}")
    LOG(f"capture wall duration (test start -> capture end): {max(0.0, stream_end_wall - test_start_wall):.1f}s")
    LOG(f"actual streaming duration (first log -> capture end): {max(0.0, stream_end_wall - first_log_monotonic):.1f}s" if first_log_monotonic else "actual streaming duration (first log -> capture end): N/A")
    show_noti(title="Capture + analyze INS monitor log", message=f"Capture and analysis done. Log file: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
