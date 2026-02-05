#!/home/vien/core_repos/local_tools/MyVenvFolder/bin/python
from __future__ import annotations
from dev.dev_common.python_misc_utils import get_arg_value
from dev.dev_common.constants import ARGUMENT_LONG_PREFIX

import argparse
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union

import requests
from requests import Response

# Ensure these imports exist in your environment
from dev.dev_common import *

SSM_USER = "root"
PING_TARGET = ACU_IP
PING_DISPLAY_NAME = "Ping ACU"
DEFAULT_HTTP_TIMEOUT = 10
DUPLICATE_LOG_REQUEST_THRESHOLD_SECS = 10
PING_CMD_TIMEOUT = 5
TN_OFFSET_FIELD = "dither_coarse_search_hypothesis0"
TN_OFFSET_MIN = -180
TN_OFFSET_MAX = 180
TN_CONFIG_ENDPOINT = "/aim/api/lui/data/config/antenna"


DEFAULT_SSM_REBOOT_TIMEOUT = 90  # seconds to wait for SSM to respond after reboot
DEFAULT_REQUEST_INTERVAL = 1  # seconds between url request attempts
DEFAULT_GPX_FIX_TIMEOUT = 200  # seconds to wait for gpx fix
DEFAULT_ONLINE_TIMEOUT = 900  # seconds to wait for the host to come back online
DEFAULT_PING_TIMEOUT = 240  # seconds to wait for UT ping to succeed
DEFAULT_TOTAL_ITERATIONS = 10  # number of test cycles to execute
DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION = 5  # seconds to wait between cycles

ARG_SSM_IP = f"{ARGUMENT_LONG_PREFIX}ssm"
ARG_SSM_REBOOT_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}ssm-reboot-timeout"
ARG_REQUEST_INTERVAL = f"{ARGUMENT_LONG_PREFIX}request-interval-secs"
ARG_GPX_FIX_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}gpx-fix-timeout"
ARG_ONLINE_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}online-timeout"
ARG_PING_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}ping-timeout"
ARG_TOTAL_ITERATIONS = f"{ARGUMENT_LONG_PREFIX}total-iterations"
ARG_WAIT_SECS_AFTER_EACH_ITERATION = f"{ARGUMENT_LONG_PREFIX}wait-secs-after-each-iteration"
ARG_PRINT_TIMESTAMP = f"{ARGUMENT_LONG_PREFIX}print-timestamp"
ARG_TESTS = f"{ARGUMENT_LONG_PREFIX}tests"

TEST_SSM_UP = "ssm_up"
TEST_GPS_FIX = "gps_fix"
TEST_PING = "ping"
TEST_AIM_READY = "aim_ready"
TEST_CONNECTED = "connected"

DEFAULT_TESTS: tuple[str, ...] = (
    TEST_SSM_UP,
    TEST_GPS_FIX,
    TEST_PING,
    TEST_AIM_READY,
    TEST_CONNECTED,
)


@dataclass(frozen=True)
class TestSequenceConfig:
    """Configuration for constructing the reboot + status command."""

    ssm_ip: str
    request_interval: int = DEFAULT_REQUEST_INTERVAL
    ssm_reboot_timeout: int = DEFAULT_SSM_REBOOT_TIMEOUT
    gpx_fix_timeout: int = DEFAULT_GPX_FIX_TIMEOUT
    aim_status_timeout: int = 200
    ping_timeout: int = DEFAULT_PING_TIMEOUT
    apn_online_timeout: int = DEFAULT_ONLINE_TIMEOUT
    total_iterations: int = DEFAULT_TOTAL_ITERATIONS
    wait_secs_after_each_iteration: int = DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION
    print_timestamp: bool = False
    tests_to_run: tuple[str, ...] = DEFAULT_TESTS

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "TestSequenceConfig":
        tests_arg = get_arg_value(args, ARG_TESTS)
        tests = tuple(tests_arg) if tests_arg else DEFAULT_TESTS
        return cls(
            ssm_ip=get_arg_value(args, ARG_SSM_IP),
            request_interval=int(get_arg_value(args, ARG_REQUEST_INTERVAL)),
            ssm_reboot_timeout=int(get_arg_value(args, ARG_SSM_REBOOT_TIMEOUT)),
            gpx_fix_timeout=int(get_arg_value(args, ARG_GPX_FIX_TIMEOUT)),
            ping_timeout=int(get_arg_value(args, ARG_PING_TIMEOUT)),
            apn_online_timeout=int(get_arg_value(args, ARG_ONLINE_TIMEOUT)),
            total_iterations=int(get_arg_value(args, ARG_TOTAL_ITERATIONS)),
            wait_secs_after_each_iteration=int(get_arg_value(args, ARG_WAIT_SECS_AFTER_EACH_ITERATION)),
            print_timestamp=bool(get_arg_value(args, ARG_PRINT_TIMESTAMP)),
            tests_to_run=tests,
        )


# --- Data Models & Parsing Logic ---

@dataclass
class MetricRecord:
    seconds: int
    timestamp: str


@dataclass
class IterationMetrics:
    iteration: int
    total_time: int
    total_timestamp: str = ""
    reboot_time: MetricRecord = field(default_factory=lambda: MetricRecord(seconds=-1, timestamp=""))
    server_up: Optional[MetricRecord] = None
    gps_fix: Optional[MetricRecord] = None
    ping_ready: Optional[MetricRecord] = None
    aim_ready: Optional[MetricRecord] = None
    connected: Optional[MetricRecord] = None


@dataclass
class RequestLogEntry:
    last_value: str
    last_notice_time: float


@dataclass
class ApiResponse:
    """Base class for API responses to enforce parsing and string representation."""

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> ApiResponse:
        raise NotImplementedError

    def __str__(self) -> str:
        return "<empty>"


@dataclass
class SystemState(ApiResponse):
    statecode: str = "UNKNOWN"

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> SystemState:
        return cls(statecode=str(payload.get("statecode", "UNKNOWN")))

    def __str__(self) -> str:
        return f"statecode: {self.statecode}"


@dataclass
class AntennaStatus(ApiResponse):
    status: str = "UNKNOWN"

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> "AntennaStatus":
        return cls(status=str(payload.get("status", "UNKNOWN")))

    def __str__(self) -> str:
        return f"status: {self.status}"

    @property
    def is_good(self) -> bool:
        return self.status.lower() == "good"


@dataclass
class GnssStatus(ApiResponse):
    fix_type: str = "0"
    fix_quality: str = "UNKNOWN"

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> GnssStatus:
        nmea = payload.get("nmea_data") or {}
        return cls(
            fix_type=str(nmea.get("fix_type", "0")),
            fix_quality=str(nmea.get("fix_quality", "UNKNOWN"))
        )

    def __str__(self) -> str:
        return f"fix_type: {self.fix_type}, fix_quality: {self.fix_quality}"

    @property
    def has_3d_fix(self) -> bool:
        return str(self.fix_type).upper() == "3D"


@dataclass
class ApnConnectionStatus(ApiResponse):
    statuses: List[str]

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> "ApnConnectionStatus":
        raw = payload.get("apn_connection_status") or []
        if isinstance(raw, list):
            statuses = [str(item) for item in raw]
        else:
            statuses = [str(raw)]
        return cls(statuses=statuses)

    def __str__(self) -> str:
        return f"apn_connection_status: {self.statuses if self.statuses else '<empty>'}"

    @property
    def is_connected(self) -> bool:
        normalized = [status.lower() for status in self.statuses]
        return len(normalized) == 2 and all(status == "connected" for status in normalized)


# --- Logging Infrastructure ---

class StatusLineRenderer:
    """Render a single status line that can be rewritten in place."""

    def __init__(self) -> None:
        self._active = False
        self._last_len = 0

    def show(self, text: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}"
        padding = max(0, self._last_len - len(line))
        sys.stderr.write(f"\r{line}{' ' * padding}")
        sys.stderr.flush()
        self._last_len = len(line)
        self._active = True

    def clear(self) -> None:
        if not self._active:
            return
        sys.stderr.write("\r" + " " * self._last_len + "\r")
        sys.stderr.flush()
        self._active = False
        self._last_len = 0


class RequestLogger:
    """Track HTTP responses and avoid spamming duplicate logs."""

    def __init__(self, threshold_secs: int = DUPLICATE_LOG_REQUEST_THRESHOLD_SECS) -> None:
        self._entries: Dict[str, RequestLogEntry] = {}
        self._log_dup_threshold_secs = threshold_secs

    def log(self, key: str, new_filtered_value: str) -> None:
        now = time.time()
        entry = self._entries.get(key)
        if entry and entry.last_value == new_filtered_value:
            if (now - entry.last_notice_time) >= self._log_dup_threshold_secs:
                LOG(f"{LOG_PREFIX_MSG_INFO} REQUEST: {key}", log_type=ELogType.DEBUG)
                entry.last_notice_time = now
            return

        self._entries[key] = RequestLogEntry(new_filtered_value, now)
        LOG(f"{LOG_PREFIX_MSG_INFO} REQUEST: {key}", log_type=ELogType.DEBUG)
        LOG(f"{LOG_PREFIX_MSG_INFO} RESPONSE: {new_filtered_value if new_filtered_value else '<empty>'}", log_type=ELogType.DEBUG)


# --- HTTP Client ---
T = TypeVar("T", bound=ApiResponse)


class SsmHttpClient:
    """HTTP helper that wraps requests.Session and logs calls with typed parsing."""

    def __init__(self, base_url: str, timeout: int = DEFAULT_HTTP_TIMEOUT, threshold_secs: int = DUPLICATE_LOG_REQUEST_THRESHOLD_SECS) -> None:
        self.base_url = self._normalize_base_url(base_url)
        self.timeout = timeout
        self.logger = RequestLogger(threshold_secs)
        self.session = requests.Session()

    @staticmethod
    def _normalize_base_url(raw: str) -> str:
        if not raw.startswith(("http://", "https://")):
            raw = f"http://{raw}"
        return raw.rstrip("/")

    def _build_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(self, path: str, *, method: str = "GET", response_type: Optional[Type[T]] = None, allow_read_timeout: bool = False) -> Union[T, str, None]:

        url = self._build_url(path)
        method = method.upper()
        key = f"{method} {url}"

        try:
            response = self.session.request(method=method, url=url, timeout=self.timeout)
            response.raise_for_status()
        except requests.ReadTimeout:
            if allow_read_timeout:
                self.logger.log(key, "READ TIMEOUT")
                return None
            else:
                self.logger.log(key, "ERROR: Read timeout")
                raise
        except requests.RequestException as exc:
            self.logger.log(key, f"ERROR: {exc}")
            raise

        # Generic text handling if no type provided
        if response_type is None:
            text = response.text.strip()
            self.logger.log(key, text if text else "<empty>")
            return text

        # Typed JSON handling
        try:
            payload = response.json()
            # Let the specific class parse the dict
            parsed_obj = response_type.from_json(payload)
            # Log the string representation defined in the class
            self.logger.log(key, str(parsed_obj))
            return parsed_obj
        except (ValueError, AttributeError) as exc:
            self.logger.log(key, f"PARSE ERROR: {exc}")
            return None

    def close(self) -> None:
        self.session.close()


def _tn_config_url(client: SsmHttpClient) -> str:
    return f"{client.base_url}{TN_CONFIG_ENDPOINT}"


def get_tn_offset(client: SsmHttpClient, retries: int = 5) -> float:
    url = _tn_config_url(client)
    for attempt in range(1, retries + 1):
        try:
            response = client.session.get(url, timeout=5)
            response.raise_for_status()
            payload = response.json()
            raw_value = payload.get(TN_OFFSET_FIELD, 0)
            return float(raw_value)
        except (requests.RequestException, ValueError, TypeError) as exc:
            LOG(f"{LOG_PREFIX_MSG_WARNING} Attempt {attempt}: failed to read TN offset ({exc})")
            time.sleep(1)
    raise RuntimeError("Failed to read TN offset after multiple attempts.")


def set_tn_offset(client: SsmHttpClient, offset: int) -> None:
    url = _tn_config_url(client)
    LOG(f"{LOG_PREFIX_MSG_INFO} Setting TN offset to {offset}...", highlight=True)
    try:
        response = client.session.get(url, timeout=5)
        response.raise_for_status()
        payload = response.json()
        payload[TN_OFFSET_FIELD] = str(offset)
        post_response = client.session.post(url, json=payload, timeout=5)
        post_response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to set TN offset: {exc}") from exc
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} TN offset updated.", highlight=True)


# --- Configuration & Setup ---

def get_tool_templates() -> List[ToolTemplate]:
    """Provide ready-to-run templates for integration with main_tools."""
    default_ssm = f"{LIST_MP_IPS[0]}" if LIST_MP_IPS else "192.168.100.54"

    base_args = {
        ARG_REQUEST_INTERVAL: DEFAULT_REQUEST_INTERVAL,
        ARG_SSM_REBOOT_TIMEOUT: DEFAULT_SSM_REBOOT_TIMEOUT,
        ARG_GPX_FIX_TIMEOUT: DEFAULT_GPX_FIX_TIMEOUT,
        ARG_PING_TIMEOUT: DEFAULT_PING_TIMEOUT,
        ARG_ONLINE_TIMEOUT: DEFAULT_ONLINE_TIMEOUT,
        ARG_WAIT_SECS_AFTER_EACH_ITERATION: DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION,
        ARG_TOTAL_ITERATIONS: DEFAULT_TOTAL_ITERATIONS,
        ARG_PRINT_TIMESTAMP: False,
        ARG_TESTS: list(DEFAULT_TESTS),
        ARG_SSM_IP: default_ssm,
    }

    return [
        ToolTemplate(
            name="Check UT statuses since startup (reboot) via python",
            extra_description="Reboot a UT/SSM, wait for acquisition, and record timing stats.",
            args=dict(base_args),
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reboot a UT, poll its REST APIs until acquisition completes, and log the timing.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=build_examples_epilog(get_tool_templates(), Path(__file__)),
    )
    add_arg_generic(parser, ARG_SSM_IP, required=True,
                    help_text="Base URL or IP for the SSM API (e.g. http://10.0.0.5 or 10.0.0.5:8080).", )
    add_arg_generic(parser, ARG_REQUEST_INTERVAL, arg_type=int, default=DEFAULT_REQUEST_INTERVAL,
                    help_text=f"Seconds between API requests (default: {DEFAULT_REQUEST_INTERVAL}).", )
    add_arg_generic(parser, ARG_SSM_REBOOT_TIMEOUT, arg_type=int, default=DEFAULT_SSM_REBOOT_TIMEOUT,
                    help_text=f"Seconds to wait for the SSM to respond after reboot (default: {DEFAULT_SSM_REBOOT_TIMEOUT}).", )
    add_arg_generic(parser, ARG_GPX_FIX_TIMEOUT, arg_type=int, default=DEFAULT_GPX_FIX_TIMEOUT,
                    help_text=f"Seconds to wait for the GNSS fix (default: {DEFAULT_GPX_FIX_TIMEOUT}).", )
    add_arg_generic(parser, ARG_PING_TIMEOUT, arg_type=int, default=DEFAULT_PING_TIMEOUT,
                    help_text=f"Seconds to wait for the UT ping to succeed (default: {DEFAULT_PING_TIMEOUT}).", )
    add_arg_generic(parser, ARG_ONLINE_TIMEOUT, arg_type=int, default=DEFAULT_ONLINE_TIMEOUT,
                    help_text=f"Seconds to wait for the CONNECTED status (default: {DEFAULT_ONLINE_TIMEOUT}).", )
    add_arg_generic(parser, ARG_TOTAL_ITERATIONS, arg_type=int, default=DEFAULT_TOTAL_ITERATIONS,
                    help_text=f"Number of test iterations to perform (default: {DEFAULT_TOTAL_ITERATIONS}).", )
    add_arg_generic(parser, ARG_WAIT_SECS_AFTER_EACH_ITERATION, arg_type=int, default=DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION,
                    help_text=f"Seconds to wait between iterations (default: {DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION}).", )
    add_arg_bool(parser, ARG_PRINT_TIMESTAMP, default=False,
                 help_text="Include timestamp breakdowns in the summary output.", )
    parser.add_argument(
        ARG_TESTS,
        nargs="+",
        choices=DEFAULT_TESTS,
        default=list(DEFAULT_TESTS),
        metavar="TEST",
        help=f"Space separated list of acquisition checks to run "
             f"(default: {' '.join(DEFAULT_TESTS)}).",
    )

    return parser.parse_args()


def validate_config(config: TestSequenceConfig) -> None:
    if config.request_interval <= 0:
        raise ValueError("request-interval must be positive.")
    if config.gpx_fix_timeout < 0 or config.apn_online_timeout < 0 or config.ping_timeout < 0:
        raise ValueError("timeout values must be non-negative.")
    if config.total_iterations <= 0:
        raise ValueError("total-iterations must be positive.")
    if config.wait_secs_after_each_iteration < 0:
        raise ValueError("wait-secs-after-each-iteration must be non-negative.")
    if not config.tests_to_run:
        raise ValueError("At least one test must be specified via --tests.")
    invalid_tests = [name for name in config.tests_to_run if name not in DEFAULT_TESTS]
    if invalid_tests:
        raise ValueError(f"Unknown tests requested: {', '.join(sorted(set(invalid_tests)))}")


def ensure_passwordless_ssh(host: str, user: str = SSM_USER) -> None:
    ssh_target = f"{user}@{host}"
    LOG(f"{LOG_PREFIX_MSG_INFO} Ensuring SSH key authentication to {ssh_target} ...")
    cmd = f'ssh -o BatchMode=yes -o ConnectTimeout=2 {ssh_target} true'
    result = run_shell(cmd, show_cmd=False, capture_output=True, timeout=10,
                       check_throw_exception_on_exit_code=False)
    if result.returncode == 0:
        LOG(f"{LOG_PREFIX_MSG_INFO} SSH key auth to {ssh_target} already works.")
        return

    LOG(f"{LOG_PREFIX_MSG_WARNING} SSH key auth to {ssh_target} failed, setting it up (may prompt once)...")
    exists, public_key_path = check_ssh_key_exists()
    if not exists and not generate_ssh_key():
        raise RuntimeError("Failed to generate SSH key for passwordless setup.")

    _, public_key_path = check_ssh_key_exists()
    if not setup_host_ssh_key(user, host, public_key_path):
        raise RuntimeError(f"Failed to copy SSH key to {ssh_target}.")

    verify = run_shell(cmd, show_cmd=False, capture_output=True, timeout=10,
                       check_throw_exception_on_exit_code=False)
    if verify.returncode != 0:
        raise RuntimeError(f"SSH key authentication still failing for {ssh_target}.")
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} SSH key successfully configured for {ssh_target}.")


def timestamp_str(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def check_ping_via_ssm(ssm_ip: str) -> bool:
    ssh_target = f"{SSM_USER}@{ssm_ip}"
    cmd = (
        f'ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout={PING_CMD_TIMEOUT} '
        f'{ssh_target} "ping -c 1 -W 2 {PING_TARGET} >/dev/null 2>&1"'
    )
    result = run_shell(cmd, show_cmd=False, capture_output=True, timeout=PING_CMD_TIMEOUT + 2,
                       check_throw_exception_on_exit_code=False)
    return result.returncode == 0


def should_run_test(config: TestSequenceConfig, name: str) -> bool:
    return name in config.tests_to_run


# --- Main Test Logic ---

def wait_for_system_up(client: SsmHttpClient, config: TestSequenceConfig,
                       start_count_time: Optional[float] = None) -> tuple[MetricRecord, float]:
    if start_count_time is None:
        start_count_time = time.time()
    deadline = start_count_time + config.ssm_reboot_timeout
    while True:
        now = time.time()
        if now > deadline:
            raise TimeoutError("Timed out waiting for SSM to respond after reboot.")
        try:
            # We don't strictly need to inspect the status code, just that it responds
            # but using response_type ensures we log clean "statecode: X" output.
            client.request("/api/system/status", response_type=SystemState)

            ssm_up_time = time.time()
            elapsed = int(ssm_up_time - start_count_time)
            record = MetricRecord(seconds=elapsed, timestamp=timestamp_str(ssm_up_time))
            return record, ssm_up_time
        except requests.RequestException:
            time.sleep(config.request_interval)


def wait_for_parallel_statuses(
    custom_client: SsmHttpClient,
    config: TestSequenceConfig,
    ssm_ip: str,
    reboot_start: float,
    ssm_up_time: float,
) -> tuple[Optional[MetricRecord], Optional[MetricRecord], Optional[MetricRecord]]:
    run_gps = should_run_test(config, TEST_GPS_FIX)
    run_ping = should_run_test(config, TEST_PING)
    run_aim = should_run_test(config, TEST_AIM_READY)
    if not any((run_gps, run_ping, run_aim)):
        return None, None, None

    gps_record: Optional[MetricRecord] = None
    ping_record: Optional[MetricRecord] = None
    aim_record: Optional[MetricRecord] = None
    deadline_components: List[int] = []
    if run_gps:
        deadline_components.append(config.gpx_fix_timeout)
    if run_aim:
        deadline_components.append(config.aim_status_timeout)
    parallel_deadline: Optional[float] = None
    if deadline_components:
        parallel_deadline = ssm_up_time + max(deadline_components)

    while (run_gps and not gps_record) or (run_ping and not ping_record) or (run_aim and not aim_record):
        if parallel_deadline and time.time() > parallel_deadline:
            raise TimeoutError("Timed out waiting for requested parallel statuses.")

        # --- Check GNSS ---
        if run_gps and not gps_record:
            try:
                gnss = custom_client.request("/api/gnss/gnssstats", response_type=GnssStatus)
                if gnss and gnss.has_3d_fix:
                    ts = time.time()
                    gps_record = MetricRecord(seconds=int(ts - reboot_start), timestamp=timestamp_str(ts))
                    LOG(f"{LOG_PREFIX_MSG_INFO} GPS 3D fix achieved after {gps_record.seconds} sec", highlight=True)
            except requests.RequestException:
                pass

        # --- Check Ping ---
        if run_ping and not ping_record:
            ping_elapsed = time.time() - reboot_start
            if ping_elapsed >= config.ping_timeout:
                raise TimeoutError(f"Timed out waiting for {PING_DISPLAY_NAME}.")
            if check_ping_via_ssm(ssm_ip):
                ts = time.time()
                ping_record = MetricRecord(seconds=int(ts - reboot_start), timestamp=timestamp_str(ts))
                LOG(f"{LOG_PREFIX_MSG_INFO} {PING_DISPLAY_NAME} succeeded after {ping_record.seconds} sec", highlight=True)

        # --- Check AIM ---
        if run_aim and not aim_record:
            try:
                antenna = custom_client.request("/api/antenna/antennainfo", response_type=AntennaStatus)
                if antenna and antenna.is_good:
                    ts = time.time()
                    aim_record = MetricRecord(seconds=int(ts - reboot_start), timestamp=timestamp_str(ts))
                    LOG(f"{LOG_PREFIX_MSG_INFO} Antenna status GOOD after {aim_record.seconds} sec", highlight=True)
            except requests.RequestException:
                pass

        time.sleep(config.request_interval)

    return gps_record, ping_record, aim_record


def wait_for_connected(client: SsmHttpClient, config: TestSequenceConfig, reboot_start: float) -> MetricRecord:
    deadline = reboot_start + config.apn_online_timeout
    while True:
        if time.time() > deadline:
            raise TimeoutError("Timed out waiting for APN connection status to report connected.")
        try:
            conn = client.request("/api/modem/modemstatus", response_type=ApnConnectionStatus)
            if conn and conn.is_connected:
                ts = time.time()
                record = MetricRecord(seconds=int(ts - reboot_start), timestamp=timestamp_str(ts))
                LOG(f"{LOG_PREFIX_MSG_INFO} APN connected after {record.seconds} sec", highlight=True)
                return record
        except requests.RequestException:
            pass

        time.sleep(config.request_interval)


def log_section(title: str) -> None:
    LOG("=" * 38)
    LOG(title)
    LOG("=" * 38)


def log_iteration_summaries(ssm_ip: str, metrics: List[IterationMetrics], tests_to_run: tuple[str, ...]) -> None:
    tests = set(tests_to_run)
    log_section(f"CYCLE RESULTS ON {ssm_ip}")
    for entry in metrics:
        LOG(f"Iteration {entry.iteration}:")
        LOG(f"  Total: {entry.total_time} sec")
        if TEST_SSM_UP in tests:
            LOG(f"  SSM up: {entry.server_up.seconds} sec" if entry.server_up else "  SSM up: skipped")
        if TEST_GPS_FIX in tests:
            LOG(f"  GPS 3D fix: {entry.gps_fix.seconds} sec" if entry.gps_fix else "  GPS 3D fix: skipped")
        if TEST_PING in tests:
            prefix = f"  {PING_DISPLAY_NAME}: "
            LOG(f"{prefix}{entry.ping_ready.seconds} sec" if entry.ping_ready else f"{prefix}skipped")
        if TEST_AIM_READY in tests:
            LOG(f"  AIM ready: {entry.aim_ready.seconds} sec" if entry.aim_ready else "  AIM ready: skipped")
        if TEST_CONNECTED in tests:
            LOG(f"  Connected: {entry.connected.seconds} sec" if entry.connected else "  Connected: skipped")
        LOG("--------------------------------------")


def log_metric_summary(label: str, values: List[int], timestamps: List[str], show_timestamps: bool) -> None:
    avg = sum(values) // len(values)
    LOG(f"{label}: avg={avg} sec, min={min(values)} sec, max={max(values)} sec")
    if show_timestamps and timestamps:
        LOG(f"{label} timestamps: {', '.join(timestamps)}")


def log_overall_summary(ssm_ip: str, metrics: List[IterationMetrics], total_iterations: int, show_timestamps: bool,
                        tests_to_run: tuple[str, ...]) -> None:
    tests = set(tests_to_run)

    log_section(f"SUMMARY ANALYSIS ON {ssm_ip} ({metrics[-1].iteration} of {total_iterations} iterations)")
    log_metric_summary("Total Time", [m.total_time for m in metrics], [
                       m.total_timestamp for m in metrics], show_timestamps)

    def summarize(label: str, attr: str) -> None:
        records = [getattr(m, attr) for m in metrics if getattr(m, attr) is not None]
        if not records:
            LOG(f"{label}: skipped")
            return
        log_metric_summary(label, [rec.seconds for rec in records], [rec.timestamp for rec in records],
                           show_timestamps)

    if TEST_SSM_UP in tests:
        summarize("SSM Up Time", "server_up")
    if TEST_GPS_FIX in tests:
        summarize("GPS 3D Fix Time", "gps_fix")
    if TEST_PING in tests:
        summarize(f"{PING_DISPLAY_NAME} Time", "ping_ready")
    if TEST_AIM_READY in tests:
        summarize("AIM Ready Time", "aim_ready")
    if TEST_CONNECTED in tests:
        summarize("Connected Time", "connected")


def wait_between_iterations(wait_secs: int) -> None:
    LOG(f"{LOG_PREFIX_MSG_INFO} Waiting {wait_secs} secs before next iteration...")
    renderer = StatusLineRenderer()
    start = time.time()
    elapsed = 0
    while elapsed < wait_secs:
        renderer.show(f"Wait {wait_secs} secs, elapsed: {elapsed} sec")
        time.sleep(1)
        elapsed = int(time.time() - start)
        elapsed = min(elapsed, wait_secs)
    renderer.show(f"Wait {wait_secs} secs, elapsed: {wait_secs} sec")
    sys.stderr.write("\n")
    sys.stderr.flush()
    renderer.clear()


def run_single_iteration(iteration: int, config: TestSequenceConfig, ssm_ip: str,
                         client: SsmHttpClient) -> IterationMetrics:
    log_section(f"STARTING ITERATION {iteration} of {config.total_iterations}")
    LOG(f"{LOG_PREFIX_MSG_INFO} Waiting for SSM to be up before iteration...")
    wait_for_system_up(client, config)
    random_offset = random.randint(TN_OFFSET_MIN, TN_OFFSET_MAX)
    set_tn_offset(client, random_offset)
    tn_settle_time = 3
    LOG(f"{LOG_PREFIX_MSG_INFO} Sleeping {tn_settle_time} seconds after TN offset update...", highlight=False)
    time.sleep(tn_settle_time)
    LOG(f"{LOG_PREFIX_MSG_INFO} Issuing reboot request to {config.ssm_ip}/api/system/reboot")
    client.request("/api/system/reboot", allow_read_timeout=True)
    sleep_time = 5
    LOG(f"{LOG_PREFIX_MSG_INFO} Sleeping {sleep_time} seconds before polling...")
    time.sleep(sleep_time)
    reboot_start_time = time.time()
    LOG(f"{LOG_PREFIX_MSG_INFO} Waiting for SSM to respond...")
    server_up, ssm_up_time = wait_for_system_up(client, config, reboot_start_time)
    LOG(f"{LOG_PREFIX_MSG_INFO} SSM up after {server_up.seconds} sec, checking parallel statuses...")

    gps_fix: Optional[MetricRecord] = None
    ping_ready: Optional[MetricRecord] = None
    aim_ready: Optional[MetricRecord] = None
    if any(should_run_test(config, name) for name in (TEST_GPS_FIX, TEST_PING, TEST_AIM_READY)):
        gps_fix, ping_ready, aim_ready = wait_for_parallel_statuses(
            client, config, ssm_ip, reboot_start_time, ssm_up_time)
        summary_components: List[str] = []
        if gps_fix:
            summary_components.append(f"GPS:{gps_fix.seconds}")
        if ping_ready:
            summary_components.append(f"{PING_DISPLAY_NAME}:{ping_ready.seconds}")
        if aim_ready:
            summary_components.append(f"AIM:{aim_ready.seconds}")
        if summary_components:
            LOG("")
            LOG(f"{LOG_PREFIX_MSG_INFO} All requested parallel checks completed! {' '.join(summary_components)}")
    else:
        LOG(f"{LOG_PREFIX_MSG_INFO} No parallel checks requested, skipping GPS/Ping/AIM polling.")
    current_offset = get_tn_offset(client)
    LOG(f"{LOG_PREFIX_MSG_INFO} TN offset currently {current_offset}", highlight=True)
    connected: Optional[MetricRecord] = None
    if should_run_test(config, TEST_CONNECTED):
        LOG(f"{LOG_PREFIX_MSG_INFO} Waiting for APN connection status with timeout = {config.apn_online_timeout}...")
        connected = wait_for_connected(client, config, reboot_start_time)
    else:
        LOG(f"{LOG_PREFIX_MSG_INFO} Connected status check skipped (not requested).")

    total_time = int(time.time() - reboot_start_time)
    total_timestamp = timestamp_str(time.time())

    return IterationMetrics(
        iteration=iteration,
        total_time=total_time,
        total_timestamp=total_timestamp,
        server_up=server_up if should_run_test(config, TEST_SSM_UP) else None,
        gps_fix=gps_fix if should_run_test(config, TEST_GPS_FIX) else None,
        ping_ready=ping_ready if should_run_test(config, TEST_PING) else None,
        aim_ready=aim_ready if should_run_test(config, TEST_AIM_READY) else None,
        connected=connected if should_run_test(config, TEST_CONNECTED) else None,
    )


def run_test_sequence(config: TestSequenceConfig) -> List[IterationMetrics]:
    validate_config(config)
    ensure_passwordless_ssh(config.ssm_ip)
    client = SsmHttpClient(config.ssm_ip)
    metrics: List[IterationMetrics] = []
    try:
        for iteration in range(1, config.total_iterations + 1):
            entry = run_single_iteration(iteration, config, config.ssm_ip, client)
            metrics.append(entry)
            log_iteration_summaries(config.ssm_ip, metrics, config.tests_to_run)
            log_overall_summary(config.ssm_ip, metrics, config.total_iterations, config.print_timestamp,
                                config.tests_to_run)
            if iteration < config.total_iterations and config.wait_secs_after_each_iteration > 0:
                wait_between_iterations(config.wait_secs_after_each_iteration)
        return metrics
    finally:
        client.close()


def main() -> None:
    args = parse_args()
    config = TestSequenceConfig.from_args(args)
    try:
        metrics = run_test_sequence(config)
    except (RuntimeError, TimeoutError, requests.RequestException) as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} {exc}")
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Interrupted by user.")
        raise SystemExit(130)

    LOG(f"{LOG_PREFIX_MSG_SUCCESS} All {len(metrics)} iterations completed successfully!")
    show_noti(title="UT acquisition test", message=f"All {len(metrics)} iterations on {config.ssm_ip} completed.")


if __name__ == "__main__":
    main()
