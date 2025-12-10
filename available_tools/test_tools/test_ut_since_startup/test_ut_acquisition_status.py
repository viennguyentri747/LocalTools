#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

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
from available_tools.test_tools.test_ut_since_startup.common import *
from dev_common import *

SSM_USER = "root"
PING_TARGET = ACU_IP
PING_DISPLAY_NAME = "Ping ACU"
DEFAULT_HTTP_TIMEOUT = 10
DUPLICATE_THRESHOLD_SECS = 10
PING_CMD_TIMEOUT = 5
TN_OFFSET_FIELD = "dither_coarse_search_hypothesis0"
TN_OFFSET_MIN = -180
TN_OFFSET_MAX = 180
TN_CONFIG_ENDPOINT = "/aim/api/lui/data/config/antenna"


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
    reboot_time: MetricRecord = MetricRecord(seconds=-1, timestamp="")
    server_up: MetricRecord = MetricRecord(seconds=-1, timestamp="")
    gps_fix: MetricRecord = MetricRecord(seconds=-1, timestamp="")
    ping_ready: MetricRecord = MetricRecord(seconds=-1, timestamp="")
    aim_ready: MetricRecord = MetricRecord(seconds=-1, timestamp="")
    connected: MetricRecord = MetricRecord(seconds=-1, timestamp="")


@dataclass
class RequestLogEntry:
    last_value: str
    last_time: float
    duplicate_count: int = 0


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

    def __init__(self, threshold_secs: int = DUPLICATE_THRESHOLD_SECS) -> None:
        self._entries: Dict[str, RequestLogEntry] = {}
        self._log_dup_threshold_secs = threshold_secs
        self._status_line = StatusLineRenderer()

    def log(self, key: str, new_filtered_value: str) -> None:
        now = time.time()
        entry = self._entries.get(key)
        if entry and entry.last_value == new_filtered_value and (now - entry.last_time) <= self._log_dup_threshold_secs:
            entry.duplicate_count += 1
            return

        self._entries[key] = RequestLogEntry(new_filtered_value, now, 0)
        self._status_line.clear()
        LOG(f"{LOG_PREFIX_MSG_INFO} REQUEST: {key}")
        LOG(f"{LOG_PREFIX_MSG_INFO} RESPONSE: {new_filtered_value if new_filtered_value else '<empty>'}")

    def render_summary(self) -> None:
        duplicates = [
            f"{key} (x{entry.duplicate_count})"
            for key, entry in self._entries.items()
            if entry.duplicate_count > 0
        ]
        if duplicates:
            joined = ", ".join(duplicates)
            self._status_line.show(f"Duplicates ({len(duplicates)} cmds): {joined}")
        else:
            self._status_line.clear()

    def finish(self) -> None:
        self._status_line.clear()


# --- HTTP Client ---

T = TypeVar("T", bound=ApiResponse)

class SsmHttpClient:
    """HTTP helper that wraps requests.Session and logs calls with typed parsing."""

    def __init__(self, base_url: str, timeout: int = DEFAULT_HTTP_TIMEOUT, threshold_secs: int = DUPLICATE_THRESHOLD_SECS) -> None:
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

    def request(
        self, 
        path: str, 
        *, 
        method: str = "GET", 
        response_type: Optional[Type[T]] = None
    ) -> Union[T, str, None]:
        
        url = self._build_url(path)
        method = method.upper()
        key = f"{method} {url}"
        
        try:
            response = self.session.request(method=method, url=url, timeout=self.timeout)
            response.raise_for_status()
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

    def render_duplicate_summary(self) -> None:
        self.logger.render_summary()

    def close(self) -> None:
        self.logger.finish()
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
        ARG_SSM_IP: default_ssm,
        ARG_PRINT_TIMESTAMP: False,
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
    parser.add_argument(ARG_SSM_IP, required=True,
                        help="Base URL or IP for the SSM API (e.g. http://10.0.0.5 or 10.0.0.5:8080).", )
    parser.add_argument(ARG_REQUEST_INTERVAL, type=int, default=DEFAULT_REQUEST_INTERVAL,
                        help=f"Seconds between API requests (default: {DEFAULT_REQUEST_INTERVAL}).", )
    parser.add_argument(ARG_SSM_REBOOT_TIMEOUT, type=int, default=DEFAULT_SSM_REBOOT_TIMEOUT,
                        help=f"Seconds to wait for the SSM to respond after reboot (default: {DEFAULT_SSM_REBOOT_TIMEOUT}).", )
    parser.add_argument(ARG_GPX_FIX_TIMEOUT, type=int, default=DEFAULT_GPX_FIX_TIMEOUT,
                        help=f"Seconds to wait for the GNSS fix (default: {DEFAULT_GPX_FIX_TIMEOUT}).", )
    parser.add_argument(ARG_PING_TIMEOUT, type=int, default=DEFAULT_PING_TIMEOUT,
                        help=f"Seconds to wait for the UT ping to succeed (default: {DEFAULT_PING_TIMEOUT}).", )
    parser.add_argument(ARG_ONLINE_TIMEOUT, type=int, default=DEFAULT_ONLINE_TIMEOUT,
                        help=f"Seconds to wait for the CONNECTED status (default: {DEFAULT_ONLINE_TIMEOUT}).", )
    parser.add_argument(ARG_TOTAL_ITERATIONS, type=int, default=DEFAULT_TOTAL_ITERATIONS,
                        help=f"Number of test iterations to perform (default: {DEFAULT_TOTAL_ITERATIONS}).", )
    parser.add_argument(ARG_WAIT_SECS_AFTER_EACH_ITERATION, type=int, default=DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION,
                        help=f"Seconds to wait between iterations (default: {DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION}).", )
    parser.add_argument(ARG_PRINT_TIMESTAMP, action="store_true",
                        help="Include timestamp breakdowns in the summary output.", )

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


def ensure_passwordless_ssh(host: str, user: str = SSM_USER) -> None:
    ssh_target = f"{user}@{host}"
    LOG(f"{LOG_PREFIX_MSG_INFO} Ensuring SSH key authentication to {ssh_target}...")
    cmd = f'ssh -o BatchMode=yes -o ConnectTimeout=5 {ssh_target} true'
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


# --- Main Test Logic ---

def wait_for_system_up(client: SsmHttpClient, config: TestSequenceConfig,
                       reboot_start: float) -> tuple[MetricRecord, float]:
    deadline = reboot_start + config.ssm_reboot_timeout
    while True:
        now = time.time()
        if now > deadline:
            raise TimeoutError("Timed out waiting for SSM to respond after reboot.")
        try:
            # We don't strictly need to inspect the status code, just that it responds
            # but using response_type ensures we log clean "statecode: X" output.
            client.request("/api/system/status", response_type=SystemState)
            
            ssm_up_time = time.time()
            elapsed = int(ssm_up_time - reboot_start)
            record = MetricRecord(seconds=elapsed, timestamp=timestamp_str(ssm_up_time))
            return record, ssm_up_time
        except requests.RequestException:
            client.render_duplicate_summary()
            time.sleep(config.request_interval)


def wait_for_parallel_statuses(
    custom_client: SsmHttpClient,
    config: TestSequenceConfig,
    ssm_ip: str,
    reboot_start: float,
    ssm_up_time: float,
) -> tuple[MetricRecord, MetricRecord, MetricRecord]:
    gps_record: Optional[MetricRecord] = None
    ping_record: Optional[MetricRecord] = None
    aim_record: Optional[MetricRecord] = None
    parallel_deadline = ssm_up_time + max(config.gpx_fix_timeout, config.aim_status_timeout)

    while not (gps_record and ping_record and aim_record):
        if time.time() > parallel_deadline:
            raise TimeoutError("Timed out waiting for GPS, AIM, and ping readiness.")

        # --- Check GNSS ---
        if not gps_record:
            try:
                gnss = custom_client.request("/api/gnss/gnssstats", response_type=GnssStatus)
                if gnss and gnss.has_3d_fix:
                    ts = time.time()
                    gps_record = MetricRecord(seconds=int(ts - reboot_start), timestamp=timestamp_str(ts))
                    LOG(f"{LOG_PREFIX_MSG_INFO} GPS 3D fix achieved after {gps_record.seconds} sec", highlight=True)
            except requests.RequestException:
                pass

        # --- Check Ping ---
        if not ping_record:
            ping_elapsed = time.time() - reboot_start
            if ping_elapsed >= config.ping_timeout:
                raise TimeoutError(f"Timed out waiting for {PING_DISPLAY_NAME}.")
            if check_ping_via_ssm(ssm_ip):
                ts = time.time()
                ping_record = MetricRecord(seconds=int(ts - reboot_start), timestamp=timestamp_str(ts))
                LOG(f"{LOG_PREFIX_MSG_INFO} {PING_DISPLAY_NAME} succeeded after {ping_record.seconds} sec", highlight=True)

        # --- Check AIM ---
        if not aim_record:
            try:
                antenna = custom_client.request("/api/antenna/antennainfo", response_type=AntennaStatus)
                if antenna and antenna.is_good:
                    ts = time.time()
                    aim_record = MetricRecord(seconds=int(ts - reboot_start), timestamp=timestamp_str(ts))
                    LOG(f"{LOG_PREFIX_MSG_INFO} Antenna status GOOD after {aim_record.seconds} sec", highlight=True)
            except requests.RequestException:
                pass

        if gps_record and ping_record and aim_record:
            break
        custom_client.render_duplicate_summary()
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

        client.render_duplicate_summary()
        time.sleep(config.request_interval)


def log_section(title: str) -> None:
    LOG("=" * 38)
    LOG(title)
    LOG("=" * 38)


def log_iteration_summaries(ssm_ip: str, metrics: List[IterationMetrics]) -> None:
    log_section(f"CYCLE RESULTS ON {ssm_ip}")
    for entry in metrics:
        LOG(f"Iteration {entry.iteration}:")
        LOG(f"  Total: {entry.total_time} sec")
        LOG(f"  SSM up: {entry.server_up.seconds} sec")
        LOG(f"  GPS 3D fix: {entry.gps_fix.seconds} sec")
        LOG(f"  {PING_DISPLAY_NAME}: {entry.ping_ready.seconds} sec")
        LOG(f"  AIM ready: {entry.aim_ready.seconds} sec")
        LOG(f"  Connected: {entry.connected.seconds} sec")
        LOG("--------------------------------------")


def log_metric_summary(label: str, values: List[int], timestamps: List[str], show_timestamps: bool) -> None:
    avg = sum(values) // len(values)
    LOG(f"{label}: avg={avg} sec, min={min(values)} sec, max={max(values)} sec")
    if show_timestamps and timestamps:
        LOG(f"{label} timestamps: {', '.join(timestamps)}")


def log_overall_summary(ssm_ip: str, metrics: List[IterationMetrics], total_iterations: int, show_timestamps: bool) -> None:
    log_section(f"SUMMARY ANALYSIS ON {ssm_ip} ({metrics[-1].iteration} of {total_iterations} iterations)")
    log_metric_summary("Total Time", [m.total_time for m in metrics], [m.total_timestamp for m in metrics], show_timestamps)
    log_metric_summary("SSM Up Time", [m.server_up.seconds for m in metrics], [m.server_up.timestamp for m in metrics], show_timestamps)
    log_metric_summary("GPS 3D Fix Time", [m.gps_fix.seconds for m in metrics], [m.gps_fix.timestamp for m in metrics], show_timestamps)
    log_metric_summary(f"{PING_DISPLAY_NAME} Time", [m.ping_ready.seconds for m in metrics], [m.ping_ready.timestamp for m in metrics], show_timestamps)
    log_metric_summary("AIM Ready Time", [m.aim_ready.seconds for m in metrics], [m.aim_ready.timestamp for m in metrics], show_timestamps)
    log_metric_summary("Connected Time", [m.connected.seconds for m in metrics], [m.connected.timestamp for m in metrics], show_timestamps)


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
    random_offset = random.randint(TN_OFFSET_MIN, TN_OFFSET_MAX)
    set_tn_offset(client, random_offset)
    tn_settle_time = 3
    LOG(f"{LOG_PREFIX_MSG_INFO} Sleeping {tn_settle_time} seconds after TN offset update...", highlight=False)
    time.sleep(tn_settle_time)
    LOG(f"{LOG_PREFIX_MSG_INFO} Issuing reboot request to {config.ssm_ip}/api/system/reboot")
    client.request("/api/system/reboot")
    sleep_time = 5
    LOG(f"{LOG_PREFIX_MSG_INFO} Sleeping {sleep_time} seconds before polling...")
    time.sleep(sleep_time)
    reboot_start = time.time()
    LOG(f"{LOG_PREFIX_MSG_INFO} Waiting for SSM to respond...")
    server_up, ssm_up_time = wait_for_system_up(client, config, reboot_start)
    LOG(f"{LOG_PREFIX_MSG_INFO} SSM up after {server_up.seconds} sec, checking parallel statuses...")

    gps_fix, ping_ready, aim_ready = wait_for_parallel_statuses(
        client, config, ssm_ip, reboot_start, ssm_up_time)
    LOG("")
    LOG(f"{LOG_PREFIX_MSG_INFO} All parallel checks completed! GPS:{gps_fix.seconds} {PING_DISPLAY_NAME}:{ping_ready.seconds} AIM:{aim_ready.seconds}")
    current_offset = get_tn_offset(client)
    LOG(f"{LOG_PREFIX_MSG_INFO} TN offset currently {current_offset}", highlight=True)
    LOG(f"{LOG_PREFIX_MSG_INFO} Waiting for APN connection status with timeout = {config.apn_online_timeout}...")
    # connected=MetricRecord(seconds=-1, timestamp="N/A (commented out)")
    connected = wait_for_connected(client, config, reboot_start)

    total_time = int(time.time() - reboot_start)
    total_timestamp = timestamp_str(time.time())

    return IterationMetrics(
        iteration=iteration,
        total_time=total_time,
        total_timestamp=total_timestamp,
        server_up=server_up,
        gps_fix=gps_fix,
        ping_ready=ping_ready,
        aim_ready=aim_ready,
        connected=connected,
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
            log_iteration_summaries(config.ssm_ip, metrics)
            log_overall_summary(config.ssm_ip, metrics, config.total_iterations, config.print_timestamp)
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
