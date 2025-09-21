#!/home/vien/local_tools/MyVenvFolder/bin/python
# -*- coding: utf-8 -*-

"""
Remote script: Monitor ins_monitor logs for specific message names within a timeout window.

- Optionally restarts the ins_monitor service before monitoring.
- Supports multiple message names (comma-separated) and stops at the first match.
- Uses tail -F + grep -E -m 1 with timeout (mirrors known-good behavior).
"""

import argparse
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
from typing import List, Tuple


DEFAULT_LOG_FILE = "/var/log/ins_monitor_log"
DEFAULT_SERVICE_NAME = "ins_monitor"
DEFAULT_INS_CONFIG_PATH = "/usr/local/config/system_config/ins_config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor ins_monitor logs for specific messages.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--messages", "-m", type=str, required=True, help="Comma-separated list of message names to detect. Example: DID_GPS2_RTK_CMP_REL_MESSAGE,DID_GPS1_POS_MESSAGE", )
    parser.add_argument("--timeout", "-t", type=int, default=15, help="Timeout in seconds to wait for a matching log entry (default: 15).", )
    parser.add_argument("--log_file", type=str, default=DEFAULT_LOG_FILE,
                        help=f"Log file to monitor (default: {DEFAULT_LOG_FILE})", )
    parser.add_argument("--service", type=str, default=DEFAULT_SERVICE_NAME,
                        help=f"Systemd service name to optionally restart (default: {DEFAULT_SERVICE_NAME})", )
    parser.add_argument("--restart", action="store_true", help="If set, restart the service before monitoring.", )
    parser.add_argument("--restart_delay", type=float, default=2.0,
                        help="Seconds to wait after restart before monitoring (default: 2.0)", )
    parser.add_argument("--ins_config_path", type=str, default=DEFAULT_INS_CONFIG_PATH,
                        help=f"Path to ins_config.json (default: {DEFAULT_INS_CONFIG_PATH})", )
    return parser.parse_args()


def restart_service(service_name: str, delay_seconds: float) -> bool:
    try:
        print(f"[{timestamp()}] Restarting service '{service_name}'...")
        res = subprocess.run(
            ["systemctl", "restart", service_name],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if res.returncode != 0:
            print(f"[{timestamp()}] Service restart failed: {res.stderr.strip()}")
            return False
        print(f"[{timestamp()}] Service restart successful. Sleeping {delay_seconds:.1f}s...")
        time.sleep(delay_seconds)
        return True
    except Exception as e:
        print(f"[{timestamp()}] Error restarting service: {e}")
        return False


def build_grep_pattern(messages: List[str]) -> str:
    # Use alternation for grep -E, escaping each message safely for regex context
    escaped = [re.escape(m) for m in messages if m]
    return "|".join(escaped)


def monitor_logs(log_file: str, messages: List[str], timeout_sec: int) -> Tuple[bool, str, float]:
    """
    Monitor the given log file for any of the specified messages.
    Returns: (success, matched_message, duration_seconds)
    """
    pattern = build_grep_pattern(messages)
    if not pattern:
        print(f"[{timestamp()}] ERROR: No valid messages provided after parsing.")
        return False, "", 0.0

    # Build inner shell command safely with quoted args
    inner = f"tail -F {shlex.quote(log_file)} | grep -E -m 1 {shlex.quote(pattern)}"
    # Run as: timeout <T> bash -lc "<inner>"
    cmd_list = ["timeout", str(int(timeout_sec)), "bash", "-lc", inner]

    print(f"[{timestamp()}] Monitoring logs for messages: {', '.join(messages)}")
    print(f"[{timestamp()}] Log file: {log_file}")
    print(f"[{timestamp()}] Timeout: {timeout_sec}s")
    start = time.time()
    try:
        print(f"[{timestamp()}] Running command: {' '.join(cmd_list)}")
        result = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout_sec + 5,)
        duration = time.time() - start

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        if stdout:
            print(f"[{timestamp()}] stdout: {stdout}")
            matched_message = detect_single_message_in_line(stdout, messages)
            if matched_message:
                print(f"[{timestamp()}] ✓ Found target message: {matched_message or 'NOT FOUND'}")
                print(f"[{timestamp()}] Matched line: {stdout}")
                print(f"[{timestamp()}] PASS in {duration:.1f}s")
                return True, matched_message or "", duration
            else:
                print(f"[{timestamp()}] FAIL in {duration:.1f}s")
                return False, "", duration
        else:
            if result.returncode == 124:  # timeout command returns 124 on timeout
                print(f"[{timestamp()}] Monitoring timed out (no messages found).")
            else:
                # Could be other errors (e.g., log file missing)
                if stderr:
                    print(f"[{timestamp()}] stderr: {stderr}")
                print(f"[{timestamp()}] No matching output. Return code: {result.returncode}")
            print(f"[{timestamp()}] FAIL in {duration:.1f}s")
            return False, "", duration
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        print(f"[{timestamp()}] Monitoring subprocess.TimeoutExpired (no messages found).")
        print(f"[{timestamp()}] FAIL in {duration:.1f}s")
        return False, "", duration
    except Exception as e:
        duration = time.time() - start
        print(f"[{timestamp()}] ERROR monitoring logs: {e}")
        print(f"[{timestamp()}] FAIL in {duration:.1f}s")
        return False, "", duration


def detect_single_message_in_line(line: str, messages: List[str]) -> str:
    # Return the first message name that appears in the line
    for m in messages:
        if m and m in line:
            return m
    return ""


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    args = parse_args()

    # Normalize and split messages
    messages = [m.strip() for m in args.messages.split(",") if m.strip()]

    print("=" * 60)
    print("INS Monitor: Check Messages")
    print("=" * 60)
    print(f"Config:")
    print(f"  - messages           : {messages}")
    print(f"  - timeout            : {args.timeout}s")
    print(f"  - log_file           : {args.log_file}")
    print(f"  - service            : {args.service}")
    print(f"  - restart            : {args.restart}")
    print(f"  - restart_delay      : {args.restart_delay}s")
    print(f"  - ins_config_path    : {args.ins_config_path}")
    print("=" * 60)

    if args.restart:
        ok = restart_service(args.service, args.restart_delay)
        if not ok:
            # Continue to monitor anyway, but note the restart failed
            print(f"[{timestamp()}] WARNING: Proceeding to monitor despite restart failure.")

    success, matched_message, duration = monitor_logs(
        log_file=args.log_file,
        messages=messages,
        timeout_sec=args.timeout,
    )

    if success:
        print(f"[{timestamp()}] RESULT: PASS (matched: {matched_message})")
        return 0
    else:
        print(f"[{timestamp()}] RESULT: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
