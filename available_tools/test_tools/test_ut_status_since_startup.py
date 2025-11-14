#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

from dev_common import *

DEFAULT_SSM_REBOOT_TIMEOUT = 90  # seconds to wait for SSM to respond after reboot
DEFAULT_REQUEST_INTERVAL = 1  # seconds between url request attempts
DEFAULT_GPX_FIX_TIMEOUT = 200  # seconds to wait for gpx fix
DEFAULT_ONLINE_TIMEOUT = 800  # seconds to wait for the host to come back online
DEFAULT_TOTAL_ITERATIONS = 10  # number of reboot cycles to execute

ARG_SSM_IP = f"{ARGUMENT_LONG_PREFIX}ssm"
ARG_SSM_REBOOT_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}ssm-reboot-timeout"
ARG_REQUEST_INTERVAL = f"{ARGUMENT_LONG_PREFIX}request-interval-secs"
ARG_GPX_FIX_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}gpx-fix-timeout"
ARG_ONLINE_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}online-timeout"    

ARG_TOTAL_ITERATIONS = f"{ARGUMENT_LONG_PREFIX}total-iterations"


@dataclass(frozen=True)
class RebootSequenceConfig:
    """Configuration for constructing the reboot + status command."""

    ssm_ip: str
    request_interval: int = DEFAULT_REQUEST_INTERVAL
    ssm_reboot_timeout: int = DEFAULT_SSM_REBOOT_TIMEOUT
    gpx_fix_timeout: int = DEFAULT_GPX_FIX_TIMEOUT
    aim_status_timeout: int = 200
    apn_online_timeout: int = DEFAULT_ONLINE_TIMEOUT
    total_iterations: int = DEFAULT_TOTAL_ITERATIONS

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "RebootSequenceConfig":
        return cls(
            ssm_ip=get_arg_value(args, ARG_SSM_IP),
            request_interval=int(get_arg_value(args, ARG_REQUEST_INTERVAL)),
            ssm_reboot_timeout=int(get_arg_value(args, ARG_SSM_REBOOT_TIMEOUT)),
            gpx_fix_timeout=int(get_arg_value(args, ARG_GPX_FIX_TIMEOUT)),
            apn_online_timeout=int(get_arg_value(args, ARG_ONLINE_TIMEOUT)),
            total_iterations=int(get_arg_value(args, ARG_TOTAL_ITERATIONS)),
        )


def get_tool_templates() -> List[ToolTemplate]:
    """Provide ready-to-run templates for integration with main_tools."""
    default_ssm = f"{LIST_MP_IPS[0]}" if LIST_MP_IPS else "192.168.100.54"

    base_args = {
        ARG_REQUEST_INTERVAL: DEFAULT_REQUEST_INTERVAL,
        ARG_SSM_REBOOT_TIMEOUT: DEFAULT_SSM_REBOOT_TIMEOUT,
        ARG_GPX_FIX_TIMEOUT: DEFAULT_GPX_FIX_TIMEOUT,
        ARG_ONLINE_TIMEOUT: DEFAULT_ONLINE_TIMEOUT,
        ARG_TOTAL_ITERATIONS: DEFAULT_TOTAL_ITERATIONS,
        ARG_SSM_IP: default_ssm,
    }

    return [
        ToolTemplate(
            name="Check UT statuses since startup (reboot)",
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
    parser.add_argument(ARG_SSM_REBOOT_TIMEOUT, type=int, default=DEFAULT_SSM_REBOOT_TIMEOUT,
                        help=f"Seconds to wait for the SSM to respond after reboot (default: {DEFAULT_SSM_REBOOT_TIMEOUT}).", )
    parser.add_argument(ARG_GPX_FIX_TIMEOUT, type=int, default=DEFAULT_GPX_FIX_TIMEOUT,
                        help=f"Seconds to wait for the host to go offline (default: {DEFAULT_GPX_FIX_TIMEOUT}).", )
    parser.add_argument(ARG_ONLINE_TIMEOUT, type=int, default=DEFAULT_ONLINE_TIMEOUT,
                        help=f"Seconds to wait for the host to respond to ping again (default: {DEFAULT_ONLINE_TIMEOUT}).", )
    parser.add_argument(ARG_TOTAL_ITERATIONS, type=int, default=DEFAULT_TOTAL_ITERATIONS,
                        help=f"Number of reboot iterations to perform (default: {DEFAULT_TOTAL_ITERATIONS}).", )

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
    if config.total_iterations <= 0:
        raise ValueError("total-iterations must be positive.")

    curl_timeout_secs = 10

    command = (
    f'SSM_URL={config.ssm_ip} && '
    f'REQ_INTERVAL={config.request_interval} && '
    f'GPS_FIX_TIMEOUT={config.gpx_fix_timeout} && '
    f'APN_TIMEOUT={config.apn_online_timeout} && '
    f'AIM_STATUS_TIMEOUT={config.aim_status_timeout} && '
    f'TOTAL_ITERATIONS={config.total_iterations} && '
    # New time-based threshold in seconds
    f'THRESHOLD_DUP_SECS=5; '

    # All functions defined using semicolon at the end (no && between them)
    f'log() {{ printf "[%s] %s\\n" "$(date \'+%Y-%m-%d %H:%M:%S\')" "$1" >&2; }}; '
    f'log_sameline() {{ printf "\\r[%s] %s" "$(date \'+%Y-%m-%d %H:%M:%S\')" "$1" >&2; }}; '

    f'SSH_TARGET="root@$SSM_URL"; '
    f'log "Ensuring SSH key authentication to $SSH_TARGET..."; '
    f'if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_TARGET" true </dev/null >/dev/null 2>&1; then '
    f'  log "SSH key auth not working, setting it up (may prompt for password once)..."; '
    f'  [ -f "$HOME/.ssh/id_rsa.pub" ] || ssh-keygen -t rsa -N "" -f "$HOME/.ssh/id_rsa" >&2; '
    f'  if command -v ssh-copy-id >/dev/null 2>&1; then '
    f'    ssh-copy-id -i "$HOME/.ssh/id_rsa.pub" "$SSH_TARGET"; '
    f'  else '
    f'    cat "$HOME/.ssh/id_rsa.pub" | ssh "$SSH_TARGET" '
    f'      "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"; '
    f'  fi; '
    f'else '
    f'  log "SSH key auth to $SSH_TARGET already works."; '
    f'fi; '

    f'declare -A curl_count; declare -A curl_prev_resp_filtered; declare -A last_check_timestamps; CURL_RESPONSE=""; '
    f'curl_with_log() {{ '
    f'  local url="$1"; '
    f'  local filter="$2"; '
    f'  local cmd_key="GET $url"; '
    f'  CURL_RESPONSE=$(curl -fsS --max-time {curl_timeout_secs} "$url" 2>&1); '
    f'  local exit_code=$?; '
    f'  local curr_resp="$CURL_RESPONSE"; '
    f'  local curr_resp_filtered=""; '
    f'  if [ -n "$filter" ]; then '
    f'    curr_resp_filtered=$(echo "$curr_resp" | eval "$filter" 2>/dev/null); '
    f'  else '
    f'    curr_resp_filtered="$curr_resp"; '
    f'  fi; '

    f'  local now=$(date +%s); '
    f'  [ -z "${{curl_count[$cmd_key]}}" ] && curl_count[$cmd_key]=0 && curl_prev_resp_filtered[$cmd_key]="" && last_check_timestamps[$cmd_key]=0; '
    f'  if [ "$curr_resp_filtered" = "${{curl_prev_resp_filtered[$cmd_key]}}" ]; then '
    f'    curl_count[$cmd_key]=$((curl_count[$cmd_key] + 1)); '
    f'    local last_time_check=${{last_check_timestamps[$cmd_key]}}; '
    f'    local elapsed=$((now - last_time_check)); '
    f'    if [ $elapsed -gt $THRESHOLD_DUP_SECS ]; then '
    f'      [ ${{curl_count[$cmd_key]}} -gt 1 ] && printf "\\n" >&2; '
    f'      log "REQUEST: $cmd_key (Elapsed $elapsed s > threshold $THRESHOLD_DUP_SECS s)"; '
    f'      log "RESPONSE: $curr_resp"; '
    f'      curl_count[$cmd_key]=0; '
    f'    fi; '
    f'    last_check_timestamps[$cmd_key]=$now; '
    f'  else '
    f'    [ ${{curl_count[$cmd_key]}} -gt 0 ] && printf "\\n" >&2; '
    f'    log "REQUEST: $cmd_key", FILTER: "$filter"; '
    f'    log "RESPONSE: $curr_resp"; '
    f'    curl_prev_resp_filtered[$cmd_key]="$curr_resp_filtered"; '
    f'    last_check_timestamps[$cmd_key]=$now; '
    f'    curl_count[$cmd_key]=0; '
    f'  fi; '
    f'  return $exit_code; '
    f'}}; '

    f'print_dup_summary() {{ '
    f'  local dup_str=""; '
    f'  local now=$(date +%s); '
    f'  for cmd_key in "${{!curl_count[@]}}"; do '
    f'    local count=${{curl_count[$cmd_key]}}; '
    f'    if [ $count -gt 0 ]; then '
    f'      [ -n "$dup_str" ] && dup_str="${{dup_str}}, "; '
    f'      dup_str="${{dup_str}}$cmd_key (x$count)"; '
    f'    fi; '
    f'  done; '
    f'  [ -n "$dup_str" ] && log_sameline "Duplicates: $dup_str"; '
    f'}}; '

    # Ordinary shell assignments and procedural logic can safely use &&
    f'server_up_times="" && gps_fix_times="" && connect_times="" && total_times="" && '
    f'ping_times="" && antenna_ready_times="" && mdm_ready_times="" && '

    f'for iteration in $(seq 1 $TOTAL_ITERATIONS); do '
    f'  log "======================================"; '
    f'  log "STARTING ITERATION $iteration of $TOTAL_ITERATIONS"; '
    f'  log "======================================"; '
    f'  log "Issuing reboot request to $SSM_URL/api/system/reboot"; '
    f'  curl_with_log "$SSM_URL/api/system/reboot"; '
    f'  REBOOT_RESPONSE="$CURL_RESPONSE"; '
    f'  echo "$REBOOT_RESPONSE" | grep -q \'"status":"OK"\' && log "Reboot request successful: $REBOOT_RESPONSE"; '
    f'  sleep_time=5 && log "Sleeping $sleep_time seconds..." && sleep $sleep_time; '
    f'  reboot_start=$(date +%s); log "Waiting for SSM to respond..."; '

    f'  until curl_with_log "$SSM_URL/api/system/status" "| jq -r \'.statecode\'"; do '
    f'    elapsed=$(( $(date +%s) - reboot_start )); '
    f'    [ $elapsed -ge {config.ssm_reboot_timeout} ] && log "Timed out waiting for SSM!" && exit 0; '
    f'    print_dup_summary; '
    f'    sleep "$REQ_INTERVAL"; '
    f'  done; '
    f'  printf "\\n" >&2; '

    f'  ssm_start=$(date +%s); '
    f'  server_up_time=$(( ssm_start - reboot_start )); '
    f'  log "SSM up after $server_up_time sec, checking parallel statuses..."; '

    f'  gps_fixed=0 && ping_ok=0 && antenna_ready=0 && modem_ready=0 && '
    f'  gps_fix_time=0 && ping_time=0 && antenna_ready_time=0 && mdm_ready_time=0; '

    f'  until [ $gps_fixed -eq 1 ] && [ $ping_ok -eq 1 ] && [ $antenna_ready -eq 1 ] && [ $modem_ready -eq 1 ]; do '
    f'    elapsed=$(( $(date +%s) - ssm_start )); '
    f'    [ $elapsed -ge "$GPS_FIX_TIMEOUT" ] && [ $elapsed -ge "$AIM_STATUS_TIMEOUT" ] && log "Timed out waiting for all statuses!" && exit 0; '

    f'    if [ $gps_fixed -eq 0 ]; then '
    f'      curl_with_log "$SSM_URL/api/gnss/gnssstats" "| jq -r \'.nmea_data.fix_type, .nmea_data.fix_quality\'"; '
    f'      GPS_DATA="$CURL_RESPONSE"; '
    f'      [ -n "$GPS_DATA" ] && '
    f'      GPS_FILTERED=$(echo "$GPS_DATA" | jq -r \'paths(scalars) as $p | ($p | join(".")) as $key | getpath($p) as $val | "\\($key): \\($val)"\' | grep -i "fix"); '
    f'      echo "$GPS_FILTERED" | grep -q "fix_quality: GPS fix (SPS)" && echo "$GPS_FILTERED" | grep -q "fix_type: 3D" && '
    f'      gps_fixed=1 && gps_fix_time=$(( $(date +%s) - reboot_start )) && log "GPS 3D fix achieved after $gps_fix_time sec"; '
    f'    fi; '

    # --- UPDATED PING BLOCK: reuse SSH_TARGET, no weird -J call ---
    f'    if [ $ping_ok -eq 0 ]; then '
    f'      ssh "$SSH_TARGET" "ping -c 1 -W 2 192.168.100.254 >/dev/null 2>&1" >/dev/null 2>&1 && '
    f'      ping_ok=1 && ping_time=$(( $(date +%s) - reboot_start )) && log "192.168.100.254 pingable after $ping_time sec"; '
    f'    fi; '

    f'    if [ $ping_ok -eq 0 ]; then '
    f'      ssh -J root@$SSM_URL "ping -c 1 -W 2 192.168.100.254 >/dev/null 2>&1" >/dev/null 2>&1 && '
    f'      ping_ok=1 && ping_time=$(( $(date +%s) - reboot_start )) && log "192.168.100.254 pingable after $ping_time sec"; '
    f'    fi; '

    f'    curl_with_log "$SSM_URL/api/system/status" "| jq -r \'.aim, .modem\'"; '
    f'    STATUS_DATA="$CURL_RESPONSE"; '
    f'    [ -n "$STATUS_DATA" ] && '
    f'      if [ $antenna_ready -eq 0 ]; then '
    f'        echo "$STATUS_DATA" | grep -q \'"amc":"0.0.0"\' && '
    f'        antenna_ready=1 && antenna_ready_time=$(( $(date +%s) - reboot_start )) && log "AIM ready (0.0.0) after $antenna_ready_time sec"; '
    f'      fi; '
    f'      if [ $modem_ready -eq 0 ]; then '
    f'        echo "$STATUS_DATA" | grep -q \'"modem":"4.3.2"\' && '
    f'        modem_ready=1 && mdm_ready_time=$(( $(date +%s) - reboot_start )) && log "Modem ready (4.3.2) after $mdm_ready_time sec"; '
    f'      fi; '
    f'    print_dup_summary; '
    f'    sleep "$REQ_INTERVAL"; '
    f'  done; '
    f'  printf "\\n" >&2; '
    f'  log "All parallel checks completed! GPS:$gps_fix_time PING:$ping_time AIM:$antenna_ready_time MODEM:$mdm_ready_time"; '
    f'  log "Waiting for CONNECTED status with timeout = $APN_TIMEOUT..."; '

    f'  until curl_with_log "$SSM_URL/api/cnx/connection_status" "| jq -r \'.connection_status\'" && '
    f'    CNX_STATUS="$CURL_RESPONSE" && echo "$CNX_STATUS" | grep -q \'"connection_status":"CONNECTED"\'; do '
    f'    elapsed=$(( $(date +%s) - ssm_start )); '
    f'    [ $elapsed -ge "$APN_TIMEOUT" ] && log "Timed out waiting for CONNECTED!" && exit 0; '
    f'    print_dup_summary; '
    f'    sleep "$REQ_INTERVAL"; '
    f'  done; '
    f'  printf "\\n" >&2; '

    f'  connect_time=$(( $(date +%s) - ssm_start )); '
    f'  total_time=$(( $(date +%s) - reboot_start )); '

    f'  server_up_times="$server_up_times $server_up_time"; '
    f'  gps_fix_times="$gps_fix_times $gps_fix_time"; '
    f'  connect_times="$connect_times $connect_time"; '
    f'  total_times="$total_times $total_time"; '
    f'  ping_times="$ping_times $ping_time"; '
    f'  antenna_ready_times="$antenna_ready_times $antenna_ready_time"; '
    f'  mdm_ready_times="$mdm_ready_times $mdm_ready_time"; '

    f'  log "======================================"; '
    f'  log "CYCLE RESULTS ON {config.ssm_ip}"; '
    f'  log "======================================"; '
    f'  i=1; '
    f'  for sup in $server_up_times; do '
    f'    gfix=$(echo $gps_fix_times | cut -d" " -f$i); '
    f'    conn=$(echo $connect_times | cut -d" " -f$i); '
    f'    tot=$(echo $total_times | cut -d" " -f$i); '
    f'    ptime=$(echo $ping_times | cut -d" " -f$i); '
    f'    atime=$(echo $antenna_ready_times | cut -d" " -f$i); '
    f'    mtime=$(echo $mdm_ready_times | cut -d" " -f$i); '
    f'    log "Iteration $i:"; '
    f'    log "  Total: $tot sec"; '
    f'    log "  SSM up: $sup sec"; '
    f'    log "  GPS 3D fix: $gfix sec"; '
    f'    log "  Ping 192.168.100.254: $ptime sec"; '
    f'    log "  AIM ready: $atime sec"; '
    f'    log "  Modem ready: $mtime sec"; '
    f'    log "  Connected: $conn sec"; '
    f'    log "--------------------------------------"; '
    f'    i=$((i + 1)); '
    f'  done; '

    f'  log "======================================"; '
    f'  log "SUMMARY ANALYSIS ($iteration of $TOTAL_ITERATIONS iterations)"; '
    f'  log "======================================"; '
    f'  calc_stats() {{ '
    f'    local values="$1" label="$2"; '
    f'    local sum=0 count=0 min=999999 max=0; '
    f'    for val in $values; do '
    f'      sum=$((sum + val)); '
    f'      count=$((count + 1)); '
    f'      [ $val -lt $min ] && min=$val; '
    f'      [ $val -gt $max ] && max=$val; '
    f'    done; '
    f'    local avg=$((sum / count)); '
    f'    log "$label: avg=$avg sec, min=$min sec, max=$max sec"; '
    f'  }}; '  # <--- semicolon
    f'  calc_stats "$total_times" "Total Time"; '
    f'  calc_stats "$server_up_times" "SSM Up Time"; '
    f'  calc_stats "$gps_fix_times" "GPS 3D Fix Time"; '
    f'  calc_stats "$ping_times" "Ping Time"; '
    f'  calc_stats "$antenna_ready_times" "AIM Ready Time"; '
    f'  calc_stats "$mdm_ready_times" "Modem Ready Time"; '
    f'  calc_stats "$connect_times" "Connected Time"; '
    f'  log "======================================"; '
    f'done; '
    f'log "All $TOTAL_ITERATIONS iterations completed successfully!"'
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
        post_actions={PostActionType.RUN_CONTENT_IN_SHELL},
    )


if __name__ == "__main__":
    main()
