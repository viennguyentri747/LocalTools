#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List
from available_tools.test_tools.test_ut_since_startup.t_test_ut_acquisition_status_tools import *
from dev.dev_common import *


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
    }

    return [
        ToolTemplate(
            name="Check UT statuses since startup (reboot)",
            extra_description="Generate the multi-step bash one-liner to reboot a UT and confirm services.",
            args=dict(base_args),
            hidden=True,
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
    parser.add_argument(ARG_PING_TIMEOUT, type=int, default=DEFAULT_PING_TIMEOUT,
                        help=f"Seconds to wait for the UT ping to succeed (default: {DEFAULT_PING_TIMEOUT}).", )
    parser.add_argument(ARG_ONLINE_TIMEOUT, type=int, default=DEFAULT_ONLINE_TIMEOUT,
                        help=f"Seconds to wait for the host to respond to ping again (default: {DEFAULT_ONLINE_TIMEOUT}).", )
    parser.add_argument(ARG_TOTAL_ITERATIONS, type=int, default=DEFAULT_TOTAL_ITERATIONS,
                        help=f"Number of test iterations to perform (default: {DEFAULT_TOTAL_ITERATIONS}).", )
    parser.add_argument(ARG_WAIT_SECS_AFTER_EACH_ITERATION, type=int, default=DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION,
                        help=f"Seconds to wait between iterations (default: {DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION}).", )

    return parser.parse_args()


def build_reboot_sequence_command(config: TestSequenceConfig) -> str:
    """
    Construct the bash command that:
    1. Issues a reboot via curl.
    2. Retrieves GNSS stats and connection status.
    """
    if config.request_interval <= 0:
        raise ValueError("ping-interval must be positive.")
    if config.gpx_fix_timeout < 0 or config.apn_online_timeout < 0 or config.ping_timeout < 0:
        raise ValueError("offline-timeout, online-timeout, and ping-timeout must be non-negative.")
    if config.total_iterations <= 0:
        raise ValueError("total-iterations must be positive.")
    if config.wait_secs_after_each_iteration < 0:
        raise ValueError("wait-secs-after-each-iteration must be non-negative.")

    curl_timeout_secs = 10

    command = (
        f'SSM_URL={config.ssm_ip} && '
        f'REQ_INTERVAL={config.request_interval} && '
        f'GPS_FIX_TIMEOUT={config.gpx_fix_timeout} && '
        f'PING_TIMEOUT={config.ping_timeout} && '
        f'APN_TIMEOUT={config.apn_online_timeout} && '
        f'AIM_STATUS_TIMEOUT={config.aim_status_timeout} && '
        f'TOTAL_ITERATIONS={config.total_iterations} && '
        f'WAIT_AFTER_ITERATION={config.wait_secs_after_each_iteration} && '
        f'THRESHOLD_DUP_SECS=10; '
        f'LAST_WAS_SAMELINE=0; '

        # f'log() {{ printf "[%s] %s\\n" "$(date \'+%Y-%m-%d %H:%M:%S\')" "$1" >&2; }}; '
        f'log() {{ [ "$LAST_WAS_SAMELINE" = "1" ] && printf "\\n" >&2; printf "[%s] %s\\n" "$(date \'+%Y-%m-%d %H:%M:%S\')" "$1" >&2; LAST_WAS_SAMELINE=0; }}; '

        # f'log_sameline() {{ printf "\\r[%s] %s" "$(date \'+%Y-%m-%d %H:%M:%S\')" "$1" >&2; }}; '
        f'log_sameline() {{ printf "\\r[%s] %s" "$(date \'+%Y-%m-%d %H:%M:%S\')" "$1" >&2; LAST_WAS_SAMELINE=1; }}; '

        f'SSH_TARGET="root@$SSM_URL"; '
        f'log "Ensuring SSH key authentication to $SSH_TARGET..."; '
        f'if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_TARGET" true </dev/null >/dev/null 2>&1; then '
        f'  log "SSH key auth not working, setting it up (may prompt for password once)..."; '
        f'  [ -f "$HOME/.ssh/id_rsa.pub" ] || ssh-keygen -t rsa -N "" -f "$HOME/.ssh/id_rsa" >&2; '
        f'  if command -v ssh-copy-id >/dev/null 2>&1; then '
        f'    ssh-copy-id -fi "$HOME/.ssh/id_rsa.pub" "$SSH_TARGET"; '
        f'  else '
        f'    cat "$HOME/.ssh/id_rsa.pub" | ssh "$SSH_TARGET" '
        f'      "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"; '
        f'  fi; '
        f'else '
        f'  log "SSH key auth to $SSH_TARGET already works."; '
        f'fi; '

        f'server_up_times="" && gps_fix_times="" && connect_times="" && total_times="" && '
        f'ping_times="" && antenna_ready_times="" && '
        f'server_up_timestamps="" && gps_fix_timestamps="" && connect_timestamps="" && '
        f'ping_timestamps="" && antenna_ready_timestamps="" && '

        f'for iteration in $(seq 1 $TOTAL_ITERATIONS); do '

        # --- Move declarations INSIDE the loop to reset counters per iteration ---
        f'  declare -A curl_count; declare -A curl_prev_resp_filtered; declare -A last_check_timestamps; CURL_RESPONSE=""; '

        f'  curl_with_log() {{ '
        f'    local url="$1"; '
        f'    local filter="$2"; '
        f'    local cmd_key="GET $url"; '
        f'    CURL_RESPONSE=$(curl -fsS --max-time {curl_timeout_secs} "$url" 2>&1); '
        f'    local exit_code=$?; '
        f'    local curr_resp="$CURL_RESPONSE"; '
        f'    local curr_resp_filtered=""; '
        f'    if [ -n "$filter" ]; then '
        f'      curr_resp_filtered=$(echo "$curr_resp" | eval "$filter" 2>/dev/null); '
        f'    else '
        f'      curr_resp_filtered="$curr_resp"; '
        f'    fi; '

        f'    local now=$(date +%s); '
        # --- Initialize timestamp to $now (not 0) to prevent 1.7 billion sec bug ---
        f'    [ -z "${{curl_count[$cmd_key]}}" ] && curl_count[$cmd_key]=0 && curl_prev_resp_filtered[$cmd_key]="" && last_check_timestamps[$cmd_key]=$now; '

        f'    if [ "$curr_resp_filtered" = "${{curl_prev_resp_filtered[$cmd_key]}}" ]; then '
        f'      curl_count[$cmd_key]=$((curl_count[$cmd_key] + 1)); '
        f'      local last_time_check=${{last_check_timestamps[$cmd_key]}}; '
        f'      local elapsed=$((now - last_time_check)); '
        f'      if [ $elapsed -le $THRESHOLD_DUP_SECS ]; then '
        f'        return $exit_code; '
        f'      fi; '
        f'    fi; '
        # Common logging path for both new responses and threshold-exceeded duplicates
        f'    [ ${{curl_count[$cmd_key]}} -gt 1 ] && printf "\\n" >&2; '
        f'    log "REQUEST: $cmd_key${{filter:+, FILTER: $filter}}${{elapsed:+ (Elapsed $elapsed s > threshold $THRESHOLD_DUP_SECS s)}}"; '
        f'    log "RESPONSE${{filter:+ WITH FILTER: $filter}}: $curr_resp_filtered"; '
        f'    curl_prev_resp_filtered[$cmd_key]="$curr_resp_filtered"; '
        f'    last_check_timestamps[$cmd_key]=$now; '
        f'    curl_count[$cmd_key]=0; '
        f'    return $exit_code; '
        f'  }}; '

        f'  print_dup_summary() {{ '
        f'    local dup_str=""; '
        f'    local cmds_count=0; '
        f'    for cmd_key in "${{!curl_count[@]}}"; do '
        f'      local count=${{curl_count[$cmd_key]}}; '
        f'      if [ $count -gt 0 ]; then '
        f'        [ -n "$dup_str" ] && dup_str="${{dup_str}}, "; '
        f'        dup_str="${{dup_str}}$cmd_key (x$count)"; '
        f'        cmds_count=$((cmds_count + 1)); '
        f'      fi; '
        f'    done; '

        # 2. Process output if duplicates exist
        f'    if [ $cmds_count -gt 0 ]; then '
        f'      local max_cols=$(tput cols 2>/dev/null || echo 80); '
        f'      local extra_margin=20; '
        #       Calculate Overhead:
        f'      local overhead=45;'  # [2025-11-26 23:22:24] Duplicates ($cmds_count cmds): "
        f'      local avail_width=$((max_cols - overhead - extra_margin)); '
        #       Safety: Ensure we always have at minimum 20 chars for printing
        f'      [ $avail_width -lt 20 ] && avail_width=20; '

        # 3. Truncate if too long (Bash string slicing: ${{var:start:length}})
        f'      if [ ${{#dup_str}} -gt $avail_width ]; then '
        f'        dup_str="${{dup_str:0:$avail_width}}..."; '
        f'      fi; '

        f'      log_sameline "Duplicates ($cmds_count cmds): $dup_str"; '
        f'    fi; '
        f'  }}; '

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
        f'  server_up_timestamp=$(date -d "@$ssm_start" \'+%Y-%m-%d %H:%M:%S\'); '
        f'  log "SSM up after $server_up_time sec, checking parallel statuses..."; '

        f'  gps_fixed=0 && ping_ok=0 && antenna_ready=0 && '
        f'  gps_fix_time=0 && ping_time=0 && antenna_ready_time=0; '
        f'  gps_fix_timestamp="" && ping_timestamp="" && antenna_ready_timestamp=""; '

        f'  until [ $gps_fixed -eq 1 ] && [ $ping_ok -eq 1 ] && [ $antenna_ready -eq 1 ]; do '
        f'    elapsed=$(( $(date +%s) - ssm_start )); '
        f'    [ $elapsed -ge "$GPS_FIX_TIMEOUT" ] && [ $elapsed -ge "$AIM_STATUS_TIMEOUT" ] && log "" && log "Timed out waiting for all statuses!" && exit 0; '

        f'    if [ $gps_fixed -eq 0 ]; then '
        f'      curl_with_log "$SSM_URL/api/gnss/gnssstats" "| jq -r \'.nmea_data.fix_type, .nmea_data.fix_quality\'"; '
        f'      GPS_DATA="$CURL_RESPONSE"; '
        f'      [ -n "$GPS_DATA" ] && '
        f'      GPS_FILTERED=$(echo "$GPS_DATA" | jq -r \'paths(scalars) as $p | ($p | join(".")) as $key | getpath($p) as $val | "\\($key): \\($val)"\' | grep -i "fix"); '
        f'      echo "$GPS_FILTERED" | grep -q "fix_quality: GPS fix (SPS)" && echo "$GPS_FILTERED" | grep -q "fix_type: 3D" && '
        f'      gps_fixed=1 && gps_fix_time=$(( $(date +%s) - reboot_start )) && '
        f'      gps_fix_timestamp=$(date \'+%Y-%m-%d %H:%M:%S\') && '
        f'      log "" && log "GPS 3D fix achieved after $gps_fix_time sec"; '
        f'    fi; '

        f'    if [ $ping_ok -eq 0 ]; then '
        f'      ping_elapsed=$(( $(date +%s) - reboot_start )); '
        f'      [ $ping_elapsed -ge "$PING_TIMEOUT" ] && log "Timed out waiting for 192.168.100.254 to respond to ping!" && exit 0; '
        f'      ssh "$SSH_TARGET" "ping -c 1 -W 2 192.168.100.254 >/dev/null 2>&1" >/dev/null 2>&1 && '
        f'      ping_ok=1 && ping_time=$(( $(date +%s) - reboot_start )) && '
        f'      ping_timestamp=$(date \'+%Y-%m-%d %H:%M:%S\') && '
        f'      log "" && log "192.168.100.254 pingable after $ping_time sec"; '
        f'    fi; '

        f'    curl_with_log "$SSM_URL/api/system/status" "| jq -r \'.amc\'"; '
        f'    STATUS_DATA="$CURL_RESPONSE"; '
        f'    [ -n "$STATUS_DATA" ] && '
        f'      if [ $antenna_ready -eq 0 ]; then '
        f'        echo "$STATUS_DATA" | grep -q \'"amc":"0.0.0"\' && '
        f'        antenna_ready=1 && antenna_ready_time=$(( $(date +%s) - reboot_start )) && '
        f'        antenna_ready_timestamp=$(date \'+%Y-%m-%d %H:%M:%S\') && '
        f'        log "" && log "AIM ready (0.0.0) after $antenna_ready_time sec"; '
        f'      fi; '
        f'    print_dup_summary; '
        f'    sleep "$REQ_INTERVAL"; '
        f'  done; '
        f'  printf "\\n" >&2; '
        f'  log "All parallel checks completed! GPS:$gps_fix_time PING:$ping_time AIM:$antenna_ready_time"; '
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
        f'  connect_timestamp=$(date \'+%Y-%m-%d %H:%M:%S\'); '
        f'  total_time=$(( $(date +%s) - reboot_start )); '

        f'  server_up_times="$server_up_times $server_up_time"; '
        f'  gps_fix_times="$gps_fix_times $gps_fix_time"; '
        f'  connect_times="$connect_times $connect_time"; '
        f'  total_times="$total_times $total_time"; '
        f'  ping_times="$ping_times $ping_time"; '
        f'  antenna_ready_times="$antenna_ready_times $antenna_ready_time"; '
        f'  server_up_timestamps="$server_up_timestamps,$server_up_timestamp"; '
        f'  gps_fix_timestamps="$gps_fix_timestamps,$gps_fix_timestamp"; '
        f'  connect_timestamps="$connect_timestamps,$connect_timestamp"; '
        f'  ping_timestamps="$ping_timestamps,$ping_timestamp"; '
        f'  antenna_ready_timestamps="$antenna_ready_timestamps,$antenna_ready_timestamp"; '

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
        f'    log "Iteration $i:"; '
        f'    log "  Total: $tot sec"; '
        f'    log "  SSM up: $sup sec"; '
        f'    log "  GPS 3D fix: $gfix sec"; '
        f'    log "  Ping 192.168.100.254: $ptime sec"; '
        f'    log "  AIM ready: $atime sec"; '
        f'    log "  Connected: $conn sec"; '
        f'    log "--------------------------------------"; '
        f'    i=$((i + 1)); '
        f'  done; '

        f'  log "======================================"; '
        f'  log "SUMMARY ANALYSIS ON {config.ssm_ip} ($iteration of $TOTAL_ITERATIONS iterations)"; '
        f'  log "======================================"; '
        f'  calc_stats() {{ '
        f'    local values="$1" label="$2" timestamps="$3"; '
        f'    local sum=0 count=0 min=999999 max=0; '
        f'    for val in $values; do '
        f'      sum=$((sum + val)); '
        f'      count=$((count + 1)); '
        f'      [ $val -lt $min ] && min=$val; '
        f'      [ $val -gt $max ] && max=$val; '
        f'    done; '
        f'    local avg=$((sum / count)); '
        f'    log "$label: avg=$avg sec, min=$min sec, max=$max sec"; '
        f'    log "$label timestamps: $timestamps"; '
        f'  }}; '
        f'  calc_stats "$total_times" "Total Time" "${{total_times// /,}}"; '
        f'  calc_stats "$server_up_times" "SSM Up Time" "${{server_up_timestamps#,}}"; '
        f'  calc_stats "$gps_fix_times" "GPS 3D Fix Time" "${{gps_fix_timestamps#,}}"; '
        f'  calc_stats "$ping_times" "Ping Time" "${{ping_timestamps#,}}"; '
        f'  calc_stats "$antenna_ready_times" "AIM Ready Time" "${{antenna_ready_timestamps#,}}"; '
        f'  calc_stats "$connect_times" "Connected Time" "${{connect_timestamps#,}}"; '
        f'  log "======================================"; '

        f'  if [ $iteration -lt $TOTAL_ITERATIONS ]; then '
        f'    log "Waiting $WAIT_AFTER_ITERATION secs before next iteration..."; '
        f'    wait_elapsed=0; '
        f'    while [ $wait_elapsed -lt $WAIT_AFTER_ITERATION ]; do '
        f'      log_sameline "Wait $WAIT_AFTER_ITERATION secs, elapsed: $wait_elapsed sec"; '
        f'      sleep 1; '
        f'      wait_elapsed=$((wait_elapsed + 1)); '
        f'    done; '
        f'    log_sameline "Wait $WAIT_AFTER_ITERATION secs, elapsed: $WAIT_AFTER_ITERATION sec"; '
        f'    printf "\n" >&2; LAST_WAS_SAMELINE=0; '
        f'  fi; '

        f'done; '
        f'log "All $TOTAL_ITERATIONS iterations completed successfully!"'
        f'noti "All $TOTAL_ITERATIONS iterations completed successfully!"; '
    )

    return command.strip()


def main() -> None:
    args = parse_args()
    config = TestSequenceConfig.from_args(args)

    try:
        command = build_reboot_sequence_command(config)
    except ValueError as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Input error: {exc}")
        raise SystemExit(1) from exc

    command = wrap_cmd_for_bash(command)
    display_content_to_copy(
        command,
        purpose="reboot UT and confirm status endpoints",
        is_copy_to_clipboard=True,
        post_actions={PostActionType.RUN_CONTENT_IN_SHELL},
    )


if __name__ == "__main__":
    main()
