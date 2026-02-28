#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

import requests

from available_tools.test_tools.test_ut_since_startup.t_test_ut_acquisition_status_tools import AntennaStatus, GnssStatus, MetricRecord, SsmHttpClient, StatusLineRenderer, timestamp_str, wait_for_system_up
from dev.dev_common import *
from dev.dev_common.constants import API_ANTENNA_INFO_ENDPOINT, API_GNSS_STATS_ENDPOINT, API_SYSTEM_REBOOT_ENDPOINT, ARGUMENT_LONG_PREFIX
from dev.dev_common.python_misc_utils import get_arg_value

DEFAULT_SSM_IP = "192.168.100.86"
DEFAULT_REQUEST_INTERVAL = 2
DEFAULT_SSM_REBOOT_TIMEOUT = 90
DEFAULT_FIX_TIMEOUT = 120
DEFAULT_WAIT_POST_FAIL = 30
DEFAULT_TOTAL_ITERATIONS = 0

ARG_SSM_IP = f"{ARGUMENT_LONG_PREFIX}ssm"
ARG_REQUEST_INTERVAL = f"{ARGUMENT_LONG_PREFIX}request-interval-secs"
ARG_SSM_REBOOT_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}ssm-reboot-timeout"
ARG_FIX_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}fix-timeout"
ARG_WAIT_POST_FAIL = f"{ARGUMENT_LONG_PREFIX}wait-post-fail"
ARG_TOTAL_ITERATIONS = f"{ARGUMENT_LONG_PREFIX}total-iterations"
ARG_PRINT_TIMESTAMP = f"{ARGUMENT_LONG_PREFIX}print-timestamp"


class Fix3DTimeoutError(TimeoutError):
    pass


@dataclass(frozen=True)
class Fix3DConfig:
    ssm_ip: str
    request_interval: int = DEFAULT_REQUEST_INTERVAL
    ssm_reboot_timeout: int = DEFAULT_SSM_REBOOT_TIMEOUT
    fix_timeout: int = DEFAULT_FIX_TIMEOUT
    wait_post_fail: int = DEFAULT_WAIT_POST_FAIL
    total_iterations: int = DEFAULT_TOTAL_ITERATIONS
    print_timestamp: bool = False

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Fix3DConfig":
        return cls(
            ssm_ip=get_arg_value(args, ARG_SSM_IP),
            request_interval=int(get_arg_value(args, ARG_REQUEST_INTERVAL)),
            ssm_reboot_timeout=int(get_arg_value(args, ARG_SSM_REBOOT_TIMEOUT)),
            fix_timeout=int(get_arg_value(args, ARG_FIX_TIMEOUT)),
            wait_post_fail=int(get_arg_value(args, ARG_WAIT_POST_FAIL)),
            total_iterations=int(get_arg_value(args, ARG_TOTAL_ITERATIONS)),
            print_timestamp=bool(get_arg_value(args, ARG_PRINT_TIMESTAMP)),
        )


@dataclass
class Fix3DIterationResult:
    iteration: int
    server_up: MetricRecord
    fix_record: MetricRecord


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Check UT 3D fix after reboot",
            extra_description="Wait for antenna GOOD, reboot the UT, then measure time to GNSS 3D fix.",
            args={
                ARG_REQUEST_INTERVAL: DEFAULT_REQUEST_INTERVAL,
                ARG_SSM_REBOOT_TIMEOUT: DEFAULT_SSM_REBOOT_TIMEOUT,
                ARG_FIX_TIMEOUT: DEFAULT_FIX_TIMEOUT,
                ARG_WAIT_POST_FAIL: DEFAULT_WAIT_POST_FAIL,
                ARG_TOTAL_ITERATIONS: DEFAULT_TOTAL_ITERATIONS,
                ARG_PRINT_TIMESTAMP: False,
                ARG_SSM_IP: DEFAULT_SSM_IP,
            },
        ),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wait for antenna GOOD, reboot a UT, and measure how long GNSS takes to reach 3D fix.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=build_examples_epilog(getToolData().tool_template, Path(__file__)),
    )
    add_arg_generic(parser, ARG_SSM_IP, required=True,
                    help_text="Base URL or IP for the SSM API (e.g. http://10.0.0.5 or 10.0.0.5:8080).", )
    add_arg_generic(parser, ARG_REQUEST_INTERVAL, arg_type=int, default=DEFAULT_REQUEST_INTERVAL,
                    help_text=f"Seconds between API requests (default: {DEFAULT_REQUEST_INTERVAL}).", )
    add_arg_generic(parser, ARG_SSM_REBOOT_TIMEOUT, arg_type=int, default=DEFAULT_SSM_REBOOT_TIMEOUT,
                    help_text=f"Seconds to wait for the SSM to respond after reboot (default: {DEFAULT_SSM_REBOOT_TIMEOUT}).", )
    add_arg_generic(parser, ARG_FIX_TIMEOUT, arg_type=int, default=DEFAULT_FIX_TIMEOUT,
                    help_text=f"Seconds to wait for GNSS 3D fix after reboot (default: {DEFAULT_FIX_TIMEOUT}).", )
    add_arg_generic(parser, ARG_WAIT_POST_FAIL, arg_type=int, default=DEFAULT_WAIT_POST_FAIL,
                    help_text=f"Seconds to wait after a failed iteration (default: {DEFAULT_WAIT_POST_FAIL}).", )
    add_arg_generic(parser, ARG_TOTAL_ITERATIONS, arg_type=int, default=DEFAULT_TOTAL_ITERATIONS,
                    help_text="Number of iterations to run; use 0 to continue forever.", )
    add_arg_bool(parser, ARG_PRINT_TIMESTAMP, default=False,
                 help_text="Include timestamps in per-iteration success logs.", )
    return parser.parse_args()


def validate_config(config: Fix3DConfig) -> None:
    if config.request_interval <= 0:
        raise ValueError("request-interval must be positive.")
    if config.ssm_reboot_timeout <= 0 or config.fix_timeout <= 0:
        raise ValueError("ssm-reboot-timeout and fix-timeout must be positive.")
    if config.wait_post_fail < 0:
        raise ValueError("wait-post-fail must be non-negative.")
    if config.total_iterations < 0:
        raise ValueError("total-iterations must be zero or positive.")


def iter_numbers(total_iterations: int) -> Iterator[int]:
    iteration = 1
    while total_iterations == 0 or iteration <= total_iterations:
        yield iteration
        iteration += 1


def format_metric(value: Optional[int]) -> str:
    return f"{value}s" if value is not None else "N/A"


def _brief_request_error(exc: requests.RequestException) -> str:
    if isinstance(exc, requests.ConnectTimeout):
        return "connect timeout, retrying"
    if isinstance(exc, requests.ReadTimeout):
        return "read timeout, retrying"
    if isinstance(exc, requests.ConnectionError):
        return "not reachable yet, retrying"
    response = getattr(exc, "response", None)
    return f"http error {response.status_code}, retrying" if response is not None else "request failed, retrying"


def wait_with_status(wait_secs: int, reason: str) -> None:
    if wait_secs <= 0:
        return
    LOG(f"{LOG_PREFIX_MSG_INFO} Waiting {wait_secs} sec ({reason})...")
    renderer = StatusLineRenderer()
    start = time.time()
    elapsed = 0
    while elapsed < wait_secs:
        renderer.show(f"{reason}: {elapsed}/{wait_secs} sec")
        time.sleep(1)
        elapsed = min(int(time.time() - start), wait_secs)
    renderer.clear()


def wait_for_antenna_good(client: SsmHttpClient, config: Fix3DConfig) -> MetricRecord:
    renderer = StatusLineRenderer()
    start = time.time()
    retry_count = 0
    while True:
        elapsed = int(time.time() - start)
        try:
            antenna = client.request(API_ANTENNA_INFO_ENDPOINT, response_type=AntennaStatus)
            status = antenna.status if antenna else "UNKNOWN"
            renderer.show(f"Waiting for antenna GOOD before reboot [{elapsed}s | retries:{retry_count}]: {status}")
            if antenna and antenna.is_good:
                renderer.clear()
                ts = time.time()
                record = MetricRecord(seconds=int(ts - start), timestamp=timestamp_str(ts))
                LOG(f"{LOG_PREFIX_MSG_INFO} Antenna status GOOD after {record.seconds} sec", highlight=True)
                return record
        except requests.RequestException as exc:
            retry_count += 1
            renderer.show(f"Waiting for antenna GOOD before reboot [{elapsed}s | retries:{retry_count}]: {_brief_request_error(exc)}")
        time.sleep(config.request_interval)


def wait_for_3d_fix(client: SsmHttpClient, config: Fix3DConfig, reboot_start: float) -> MetricRecord:
    renderer = StatusLineRenderer()
    deadline = reboot_start + config.fix_timeout
    retry_count = 0
    while True:
        now = time.time()
        if now > deadline:
            renderer.clear()
            raise Fix3DTimeoutError(f"Timed out waiting for GNSS 3D fix after {config.fix_timeout} sec.")
        elapsed = int(now - reboot_start)
        try:
            gnss = client.request(API_GNSS_STATS_ENDPOINT, response_type=GnssStatus)
            renderer.show(f"Waiting for GNSS 3D fix [{elapsed}s/{config.fix_timeout}s | retries:{retry_count}]: {gnss if gnss else '<empty>'}")
            if gnss and gnss.has_3d_fix:
                renderer.clear()
                ts = time.time()
                record = MetricRecord(seconds=int(ts - reboot_start), timestamp=timestamp_str(ts))
                LOG(f"{LOG_PREFIX_MSG_INFO} GNSS 3D fix achieved after {record.seconds} sec", highlight=True)
                return record
        except requests.RequestException as exc:
            retry_count += 1
            renderer.show(f"Waiting for GNSS 3D fix [{elapsed}s/{config.fix_timeout}s | retries:{retry_count}]: {_brief_request_error(exc)}")
        time.sleep(config.request_interval)


def run_single_iteration(iteration: int, fail_count: int, min_fix: Optional[int], max_fix: Optional[int], config: Fix3DConfig,
                         client: SsmHttpClient) -> Fix3DIterationResult:
    LOG("=" * 38)
    LOG(f"Iteration {iteration} (fix3d_fails: {fail_count} | min: {format_metric(min_fix)} | max: {format_metric(max_fix)})")
    LOG("=" * 38)
    wait_for_antenna_good(client, config)
    LOG(f"{LOG_PREFIX_MSG_INFO} Issuing reboot request to {config.ssm_ip}{API_SYSTEM_REBOOT_ENDPOINT}")
    client.request(API_SYSTEM_REBOOT_ENDPOINT, allow_read_timeout=True)
    sleep_time = 5
    LOG(f"{LOG_PREFIX_MSG_INFO} Sleeping {sleep_time} seconds before polling...")
    time.sleep(sleep_time)
    reboot_start = time.time()
    LOG(f"{LOG_PREFIX_MSG_INFO} Waiting for SSM to respond...")
    server_up, _ = wait_for_system_up(client, config, reboot_start)
    LOG(f"{LOG_PREFIX_MSG_INFO} SSM up after {server_up.seconds} sec, checking GNSS 3D fix...")
    fix_record = wait_for_3d_fix(client, config, reboot_start)
    return Fix3DIterationResult(iteration=iteration, server_up=server_up, fix_record=fix_record)


def log_success_summary(results: List[Fix3DIterationResult], print_timestamp: bool) -> None:
    if not results:
        return
    fix_values = [entry.fix_record.seconds for entry in results]
    server_values = [entry.server_up.seconds for entry in results]
    LOG("======================================")
    LOG("3D FIX SUMMARY")
    LOG("======================================")
    LOG(f"Successful iterations: {len(results)}")
    LOG(f"SSM up: avg={sum(server_values) // len(server_values)} sec, min={min(server_values)} sec, max={max(server_values)} sec")
    LOG(f"3D fix: avg={sum(fix_values) // len(fix_values)} sec, min={min(fix_values)} sec, max={max(fix_values)} sec")
    if print_timestamp:
        LOG(f"3D fix timestamps: {', '.join(entry.fix_record.timestamp for entry in results)}")


def run_fix_sequence(config: Fix3DConfig) -> List[Fix3DIterationResult]:
    validate_config(config)
    client = SsmHttpClient(config.ssm_ip)
    results: List[Fix3DIterationResult] = []
    fail_count = 0
    try:
        for iteration in iter_numbers(config.total_iterations):
            min_fix = min((entry.fix_record.seconds for entry in results), default=None)
            max_fix = max((entry.fix_record.seconds for entry in results), default=None)
            try:
                result = run_single_iteration(iteration, fail_count, min_fix, max_fix, config, client)
                results.append(result)
                LOG(f"{LOG_PREFIX_MSG_SUCCESS} Iteration {iteration}: 3D fix after {result.fix_record.seconds} sec")
                if config.print_timestamp:
                    LOG(f"{LOG_PREFIX_MSG_INFO} Iteration {iteration} timestamps: server_up={result.server_up.timestamp}, fix={result.fix_record.timestamp}")
                log_success_summary(results, config.print_timestamp)
            except Fix3DTimeoutError as exc:
                fail_count += 1
                LOG(f"{LOG_PREFIX_MSG_ERROR} {exc}")
                show_noti(title="3D FIX timeout", message=f"{config.ssm_ip}: iteration {iteration} timed out after {config.fix_timeout} sec")
                wait_with_status(config.wait_post_fail, "post-failure wait")
            except (TimeoutError, requests.RequestException) as exc:
                LOG(f"{LOG_PREFIX_MSG_WARNING} Iteration {iteration} failed before 3D fix: {exc}")
                wait_with_status(config.wait_post_fail, "post-failure wait")
    finally:
        client.close()
    return results


def main() -> None:
    args = parse_args()
    config = Fix3DConfig.from_args(args)
    try:
        results = run_fix_sequence(config)
    except ValueError as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} {exc}")
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Interrupted by user.")
        raise SystemExit(130)

    if config.total_iterations != 0:
        LOG(f"{LOG_PREFIX_MSG_SUCCESS} Completed {len(results)} successful iterations.")
    else:
        LOG(f"{LOG_PREFIX_MSG_INFO} Exiting after {len(results)} successful iterations.")


if __name__ == "__main__":
    main()
