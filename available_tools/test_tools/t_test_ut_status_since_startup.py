#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

from dev_common import *

DEFAULT_SSM_REBOOT_TIMEOUT = 60  # seconds to wait for SSM to respond after reboot
DEFAULT_REQUEST_INTERVAL = 1  # seconds between url request attempts
DEFAULT_GPX_FIX_TIMEOUT = 120  # seconds to wait for gpx fix
DEFAULT_ONLINE_TIMEOUT = 800  # seconds to wait for the host to come back online

ARG_SSM_IP = f"{ARGUMENT_LONG_PREFIX}ssm"
ARG_REQUEST_INTERVAL = f"{ARGUMENT_LONG_PREFIX}request-interval"
ARG_GPX_FIX_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}gpx-fix-timeout"
ARG_ONLINE_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}online-timeout"


@dataclass(frozen=True)
class RebootSequenceConfig:
    """Configuration for constructing the reboot + status command."""

    ssm_ip: str
    request_interval: int = DEFAULT_REQUEST_INTERVAL
    ssm_reboot_timeout: int = DEFAULT_SSM_REBOOT_TIMEOUT
    gpx_fix_timeout: int = DEFAULT_GPX_FIX_TIMEOUT
    apn_online_timeout: int = DEFAULT_ONLINE_TIMEOUT

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "RebootSequenceConfig":
        return cls(
            ssm_ip=get_arg_value(args, ARG_SSM_IP),
            request_interval=int(get_arg_value(args, ARG_REQUEST_INTERVAL)),
            ssm_reboot_timeout=DEFAULT_SSM_REBOOT_TIMEOUT,
            gpx_fix_timeout=int(get_arg_value(args, ARG_GPX_FIX_TIMEOUT)),
            apn_online_timeout=int(get_arg_value(args, ARG_ONLINE_TIMEOUT)),
        )


def get_tool_templates() -> List[ToolTemplate]:
    """Provide ready-to-run templates for integration with main_tools."""
    default_ssm = f"{LIST_MP_IPS[0]}" if LIST_MP_IPS else "192.168.100.54"

    base_args = {
        ARG_REQUEST_INTERVAL: DEFAULT_REQUEST_INTERVAL,
        ARG_GPX_FIX_TIMEOUT: DEFAULT_GPX_FIX_TIMEOUT,
        ARG_ONLINE_TIMEOUT: DEFAULT_ONLINE_TIMEOUT,
        ARG_SSM_IP: default_ssm,
    }

    return [
        ToolTemplate(
            name="Build UT reboot + status command",
            extra_description="Generate the multi-step bash one-liner to reboot a UT and confirm services.",
            args=dict(base_args),
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a bash command that reboots a UT, waits for it to come back online, and checks key statuses.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=build_examples_epilog(get_tool_templates(), Path(__file__)),
    )
    parser.add_argument(ARG_SSM_IP, required=True,
                        help="Base URL or IP for the SSM API (e.g. http://10.0.0.5 or 10.0.0.5:8080).", )
    parser.add_argument(ARG_REQUEST_INTERVAL, type=int, default=DEFAULT_REQUEST_INTERVAL,
                        help=f"Seconds between ping attempts (default: {DEFAULT_REQUEST_INTERVAL}).", )
    parser.add_argument(ARG_GPX_FIX_TIMEOUT, type=int, default=DEFAULT_GPX_FIX_TIMEOUT,
                        help=f"Seconds to wait for the host to go offline (default: {DEFAULT_GPX_FIX_TIMEOUT}).", )
    parser.add_argument(ARG_ONLINE_TIMEOUT, type=int, default=DEFAULT_ONLINE_TIMEOUT,
                        help=f"Seconds to wait for the host to respond to ping again (default: {DEFAULT_ONLINE_TIMEOUT}).", )

    return parser.parse_args()


def build_reboot_sequence_command(config: RebootSequenceConfig) -> str:
    """
    Construct the bash command that:
    1. Issues a reboot via curl.
    2. Waits for the host to drop off ping (optional timeout).
    3. Waits for ping to succeed again.
    4. Retrieves GNSS stats and connection status.
    """
    if config.request_interval <= 0:
        raise ValueError("ping-interval must be positive.")
    if config.gpx_fix_timeout < 0 or config.apn_online_timeout < 0:
        raise ValueError("offline-timeout and online-timeout must be non-negative.")

    curl_timeout_secs = 10
    command = (
        f'BASE_URL={config.ssm_ip} && REQ_INTERVAL={config.request_interval} && '
        f'GPS_FIX_TIMEOUT={config.gpx_fix_timeout} && APN_TIMEOUT={config.apn_online_timeout} && '
        # log to stderr instead of stdout to avoid interfering with command output capture (from stdout)
        f'log() {{ printf "[%s] %s\\n" "$(date \'+%Y-%m-%d %H:%M:%S\')" "$1" >&2; }} && '
        f'curl_with_log() {{ local url="$1"; log "REQUEST: GET $url"; response=$(curl -fsS --max-time {curl_timeout_secs} "$url" 2>&1); exit_code=$?; log "RESPONSE: $response"; [ $exit_code -eq 0 ] && echo "$response"; return $exit_code; }} && '
        f'log "Issuing reboot request to $BASE_URL/api/system/reboot" && '
        f'REBOOT_RESPONSE=$(curl_with_log "$BASE_URL/api/system/reboot") && '
        f'echo "$REBOOT_RESPONSE" | grep -q \'"status":"OK"\' && '
        f'log "Reboot request successful: $REBOOT_RESPONSE" && '
        f'sleep_time=5 && log "Sleeping $sleep_time seconds..." && sleep $sleep_time && '
        f'reboot_start=$(date +%s) && log "Waiting for SSM to respond..." && '
        f'until curl_with_log "$BASE_URL/api/system/status"; do '
        f'elapsed=$(( $(date +%s) - reboot_start )); '
        f'[ $elapsed -ge {config.ssm_reboot_timeout} ] && log "Timed out waiting for SSM" && exit 1; '
        f'log "Waiting for SSM to respond (elapsed=${{elapsed}}s)"; '
        f'sleep "$REQ_INTERVAL"; done && '
        f'ssm_start=$(date +%s) && server_up_time=$(( ssm_start - reboot_start )) && log "Server up after $server_up_time sec, checking GPX fix status..." && '
        f'until GPS_DATA=$(curl_with_log "$BASE_URL/api/gnss/gnssstats") && [ -n "$GPS_DATA" ] && '
        f'GPS_FILTERED=$(echo "$GPS_DATA" | jq -r \'paths(scalars) as $p | ($p | join(".")) as $key | getpath($p) as $val | "\\($key): \\($val)"\' | grep -i "fix") && echo "$GPS_FILTERED" | grep -q "fix_quality: GPS fix (SPS)" && echo "$GPS_FILTERED" | grep -q "fix_type: 3D"; do '
        f'elapsed=$(( $(date +%s) - ssm_start )); '
        f'[ $elapsed -ge "$GPS_FIX_TIMEOUT" ] && log "Timed out waiting for GPS 3D fix" && exit 1; '
        f'log "Waiting for GPS 3D fix (elapsed=${{elapsed}}s)"; '
        f'sleep "$REQ_INTERVAL"; done && '
        f'gps_fix_time=$(( $(date +%s) - ssm_start )) && '
        f'log "GPS Fix status ok after $gps_fix_time sec, waiting for CONNECTED status with timeout = $APN_TIMEOUT..." && '
        f'until CNX_STATUS=$(curl_with_log "$BASE_URL/api/cnx/connection_status") && '
        f'echo "$CNX_STATUS" | grep -q \'"connection_status":"CONNECTED"\'; do '
        f'elapsed=$(( $(date +%s) - ssm_start )); '
        f'[ $elapsed -ge "$APN_TIMEOUT" ] && log "Timed out waiting for CONNECTED" && exit 1; '
        f'log "Waiting for CONNECTED (elapsed=${{elapsed}}s)"; '
        f'sleep "$REQ_INTERVAL"; done && '
        f'connect_time=$(( $(date +%s) - ssm_start )) && total_time=$(( $(date +%s) - reboot_start )) && '
        f'log "======================================" && log "REBOOT CYCLE RESULTS" && log "======================================" &&'
        f'log "Server up: $server_up_time sec" && log "GPS 3D fix: $gps_fix_time sec" && '
        f'log "Connected: $connect_time sec" && log "Total time: $total_time sec" && '
        f'log "======================================" && log "Reboot cycle completed successfully!"'
    )
    return command.strip()


def main() -> None:
    args = parse_args()
    config = RebootSequenceConfig.from_args(args)

    try:
        command = build_reboot_sequence_command(config)
    except ValueError as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Input error: {exc}")
        raise SystemExit(1) from exc

    display_content_to_copy(
        command,
        purpose="reboot UT and confirm status endpoints",
        is_copy_to_clipboard=True,
        is_run_content_in_shell=True,
    )


if __name__ == "__main__":
    main()
