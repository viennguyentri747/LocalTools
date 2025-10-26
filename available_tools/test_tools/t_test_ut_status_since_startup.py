#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

from dev_common import *

DEFAULT_PING_INTERVAL = 5  # seconds between ping attempts
DEFAULT_GPX_FIX_TIMEOUT = 120  # seconds to wait for gpx fix
DEFAULT_ONLINE_TIMEOUT = 600  # seconds to wait for the host to come back online

ARG_SSM = f"{ARGUMENT_LONG_PREFIX}ssm"
ARG_PING_INTERVAL = f"{ARGUMENT_LONG_PREFIX}ping-interval"
ARG_GPX_FIX_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}gpx-fix-timeout"
ARG_ONLINE_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}online-timeout"


@dataclass(frozen=True)
class RebootSequenceConfig:
    """Configuration for constructing the reboot + status command."""

    ssm_target: str
    ping_interval: int = DEFAULT_PING_INTERVAL
    gpx_fix_timeout: int = DEFAULT_GPX_FIX_TIMEOUT
    online_timeout: int = DEFAULT_ONLINE_TIMEOUT

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "RebootSequenceConfig":
        return cls(
            ssm_target=get_arg_value(args, ARG_SSM),
            ping_interval=int(get_arg_value(args, ARG_PING_INTERVAL)),
            gpx_fix_timeout=int(get_arg_value(args, ARG_GPX_FIX_TIMEOUT)),
            online_timeout=int(get_arg_value(args, ARG_ONLINE_TIMEOUT)),
        )


def get_tool_templates() -> List[ToolTemplate]:
    """Provide ready-to-run templates for integration with main_tools."""
    default_ssm = f"{LIST_MP_IPS[0]}" if LIST_MP_IPS else "192.168.100.54"

    base_args = {
        ARG_SSM: default_ssm,
        ARG_PING_INTERVAL: DEFAULT_PING_INTERVAL,
        ARG_GPX_FIX_TIMEOUT: DEFAULT_GPX_FIX_TIMEOUT,
        ARG_ONLINE_TIMEOUT: DEFAULT_ONLINE_TIMEOUT,
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
    parser.add_argument(
        ARG_SSM,
        required=True,
        help="Base URL or IP for the SSM API (e.g. http://10.0.0.5 or 10.0.0.5:8080).",
    )
    parser.add_argument(
        ARG_PING_INTERVAL,
        type=int,
        default=DEFAULT_PING_INTERVAL,
        help=f"Seconds between ping attempts (default: {DEFAULT_PING_INTERVAL}).",
    )
    parser.add_argument(
        ARG_GPX_FIX_TIMEOUT,
        type=int,
        default=DEFAULT_GPX_FIX_TIMEOUT,
        help=f"Seconds to wait for the host to go offline (default: {DEFAULT_GPX_FIX_TIMEOUT}).",
    )
    parser.add_argument(
        ARG_ONLINE_TIMEOUT,
        type=int,
        default=DEFAULT_ONLINE_TIMEOUT,
        help=f"Seconds to wait for the host to respond to ping again (default: {DEFAULT_ONLINE_TIMEOUT}).",
    )

    return parser.parse_args()


def build_reboot_sequence_command(config: RebootSequenceConfig) -> str:
    """
    Construct the bash command that:
    1. Issues a reboot via curl.
    2. Waits for the host to drop off ping (optional timeout).
    3. Waits for ping to succeed again.
    4. Retrieves GNSS stats and connection status.
    """
    if config.ping_interval <= 0:
        raise ValueError("ping-interval must be positive.")
    if config.gpx_fix_timeout < 0 or config.online_timeout < 0:
        raise ValueError("offline-timeout and online-timeout must be non-negative.")

    command = (
        f'SSM_HOST={config.ssm_target} && '
        f'SSM_BASE_URL=$SSM_HOST && '
        f'PING_INTERVAL={config.ping_interval} && '
        f'GPS_FIX_TIMEOUT={config.gpx_fix_timeout} && '
        f'CONNECTION_TIMEOUT={config.online_timeout} && '
        f'log() {{ printf "[%s] %s\\n" "$(date \'+%Y-%m-%d %H:%M:%S\')" "$1"; }} && '
        f'log "Issuing reboot request to $SSM_BASE_URL/api/system/reboot" && '
        f'REBOOT_RESPONSE=$(curl -fsS "$SSM_BASE_URL/api/system/reboot") && '
        f'echo "$REBOOT_RESPONSE" | grep -q \'"status":"OK"\' && '
        f'log "Reboot request successful: $REBOOT_RESPONSE" && '
        f'log "Sleeping 5 seconds..." && '
        f'sleep 5 && '
        f'log "Waiting for GPS 3D fix..." && '
        f'gps_fix_check_start=$(date +%s) && '
        f'until GPS_DATA=$(curl -sS "$SSM_BASE_URL/api/gnss/gnssstats" 2>/dev/null | jq -r \'paths(scalars) as $p | ($p | join(".")) as $key | getpath($p) as $val | "\\($key): \\($val)"\' | grep -i "fix") && '
        f'echo "$GPS_DATA" | grep -q "fix_quality: GPS fix (SPS)" && '
        f'echo "$GPS_DATA" | grep -q "fix_type: 3D"; do '
        f'if [ $(( $(date +%s) - gps_fix_check_start )) -ge "$GPS_FIX_TIMEOUT" ]; then '
        f'log "Timed out waiting for GPS 3D fix"; '
        f'exit 1; '
        f'fi; '
        f'log "Waiting for GPS 3D fix... (retrying)"; '
        f'sleep "$PING_INTERVAL"; '
        f'done && '
        f'log "GPS 3D fix acquired! Fix details:" && '
        f'echo "$GPS_DATA" && '
        f'log "Waiting for connection status to be CONNECTED..." && '
        f'conn_start=$(date +%s) && '
        f'until CNX_STATUS=$(curl -sS "$SSM_BASE_URL/api/cnx/connection_status" 2>/dev/null) && '
        f'echo "$CNX_STATUS" | grep -q "CONNECTED"; do '
        f'if [ $(( $(date +%s) - conn_start )) -ge "$CONNECTION_TIMEOUT" ]; then '
        f'log "Timed out waiting for CONNECTED status"; '
        f'exit 1; '
        f'fi; '
        f'log "Waiting for CONNECTED status... (retrying)"; '
        f'sleep "$PING_INTERVAL"; '
        f'done && '
        f'log "Connection status: $CNX_STATUS" && '
        f'log "Reboot cycle completed successfully!"'
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
    )


if __name__ == "__main__":
    main()
