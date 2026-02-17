#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
# -*- coding: utf-8 -*-

"""
Remote script: Monitor ins_monitor logs for specific message names within a timeout window.

- Optionally restarts the ins_monitor service before monitoring.
- Supports multiple message names (comma-separated) and stops at the first match.
- Uses tail -F + grep -E -m 1 with timeout (mirrors known-good behavior).
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import List, Tuple, Dict, Optional


DEFAULT_LOG_FILE = "/var/log/ins_monitor_log"
DEFAULT_SERVICE_NAME = "ins_monitor"
DEFAULT_INS_CONFIG_PATH = "/usr/local/config/system_config/ins_config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor ins_monitor logs for specific messages.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--cfg_override_messages", type=str, required=False,
                        help="Comma-separated list of message names to detect, overriding the config file. Example: DID_GPS2_RTK_CMP_REL,DID_GPS1_POS", )
    parser.add_argument("--duration", "-d", type=int, default=15,
                        help="Duration in seconds to monitor for messages (default: 15).")
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


def load_messages_from_config(config_path: str) -> List[str]:
    """Loads enabled message names from the ins_config.json file."""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        if "messages" in config and isinstance(config["messages"], list):
            # Message names in config can be 'DID_INS_1' or 'DID_INS_1_MESSAGE'
            # The log format can be ',DID_INS_1,' or ',DID_INS_1_MESSAGE,'
            # We will strip _MESSAGE if it exists to normalize it.
            enabled_messages = [
                msg["name"].replace("_MESSAGE", "")
                for msg in config["messages"]
                if msg.get("enabled", False) and "name" in msg
            ]
            print(f"[{timestamp()}] Loaded {len(enabled_messages)} enabled messages from {config_path}")
            return enabled_messages
        else:
            print(f"[{timestamp()}] WARNING: 'messages' key not found or not a list in {config_path}")
            return []
    except FileNotFoundError:
        print(f"[{timestamp()}] ERROR: Configuration file not found at {config_path}")
        return []
    except json.JSONDecodeError:
        print(f"[{timestamp()}] ERROR: Failed to decode JSON from {config_path}")
        return []
    except Exception as e:
        print(f"[{timestamp()}] ERROR: An unexpected error occurred while reading {config_path}: {e}")
        return []


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
    """
    Builds a grep pattern to match message names.
    For a list of messages like ['DID_INS_1', 'DID_GPS1_POS'], the
    generated pattern for `grep -E` will be 'DID_INS_1|DID_GPS1_POS'.
    It handles both `DID_INS_1` and `DID_INS_1_MESSAGE` formats by searching
    for the base name.
    """
    if not messages:
        return ""

    # Just join the message names with a '|'
    return "|".join(re.escape(msg) for msg in messages if msg)


def parse_log_line(line: str) -> Optional[Tuple[datetime, str]]:
    """Parses a log line to extract the timestamp and the content."""
    # Match the exact log format from logMessage/time_to_string: [YYYY-MM-DD HH:MM:SS.mmm]
    match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.(\d{3})\](.*)", line)
    if match:
        try:
            ts_str = match.group(1)
            millisecs = int(match.group(2))
            # Parse the timestamp and add milliseconds
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            ts = ts.replace(microsecond=millisecs * 1000)  # Convert ms to microseconds
            content = match.group(3)
            return ts, content
        except (ValueError, IndexError):
            pass  # Return None if parsing fails

    return None, line  # Return raw line if parsing fails


def detect_single_message_in_line(line: str, messages_to_monitor: List[str]) -> Optional[str]:
    """Finds which message from the monitored list is in the given line."""
    for msg_name in messages_to_monitor:
        # The log format can be ',DID_INS_1,' or ',DID_INS_1_MESSAGE,'.
        # A simple substring check is sufficient and robust.
        if msg_name in line:
            return msg_name
    return None


def analyze_results(lines: List[str], target_messages: List[str]):
    """Analyzes log lines to calculate stats for each message type."""
    # Maps message name to a list of timestamps it occurred at
    results: Dict[str, List[datetime]] = defaultdict(list) # [message_name]: [timestamps]

    for line in lines:
        ts, content = parse_log_line(line)
        if not ts:
            print(f"[{timestamp()}] ERROR: Failed to parse timestamp from line: {line}")
        # else:
        #     print(f"[{timestamp()}] Parsed message ts: {ts}, content: {content}")
        msg_type = detect_single_message_in_line(content, target_messages)

        if msg_type and ts:
            results[msg_type].append(ts)

    if not results:
        print(f"[{timestamp()}] No enabled messages were found in the output.")
        return

    print(f"[{timestamp()}] Analytics per message type:")
    # Sort by message name for consistent output
    for msg_name in sorted(results.keys()):
        timestamps = sorted(results[msg_name])
        count = len(timestamps)

        if count > 1:
            secs_diffs = [(timestamps[i] - timestamps[i-1]).total_seconds() for i in range(1, count)]
            min_diff, max_diff = min(secs_diffs), max(secs_diffs)

            # If min and max are very close, show an approximate value
            if abs(max_diff - min_diff) < 0.01:
                time_range_str = f"~{min_diff:.2f}s"
            else:
                time_range_str = f"[{min_diff:.2f}s, {max_diff:.2f}s]"
        else:
            time_range_str = "[N/A]"  # Not enough data for differences

        print(f"  - {msg_name}:")
        print(f"    - Count: {count}")
        print(f"    - Time Difference Range: {time_range_str}")


def monitor_log(log_file: str, messages: List[str], duration_sec: int) -> Tuple[bool, int, float, List[str]]:
    """
    Monitor the given log file for any of the specified messages for a fixed duration.
    Returns: (success, total_found, duration_seconds, found_lines)
    """
    pattern = build_grep_pattern(messages)
    if not pattern:
        print(f"[{timestamp()}] ERROR: No valid messages provided to monitor.")
        return False, 0, 0.0, []

    # Build inner shell command to find all matches, using stdbuf -Ol for line-buffering -> Flush whenever encounter line-end (\n) instead of full buffer
    # The grep pattern is now more complex, so we pass it carefully.
    inner = f"tail -F {shlex.quote(log_file)} | stdbuf -oL grep -E {shlex.quote(pattern)}"
    # Run for a fixed duration
    cmd_list = ["timeout", str(int(duration_sec)), "bash", "-c", inner]
    messages_str = ", ".join(messages)
    print(f"[{timestamp()}] Monitoring logs for messages: {messages_str}")
    print(f"[{timestamp()}] Log file: {log_file}")
    print(f"[{timestamp()}] Monitoring duration: {duration_sec}s")
    start = time.time()

    found_lines = []
    try:
        print(f"[{timestamp()}] Running command: {' '.join(cmd_list)}")
        # We'll get a return code of 124 (timeout) which is the expected happy path.
        result = subprocess.run(cmd_list, capture_output=True, text=True, check=False, timeout=duration_sec + 5)
        duration = time.time() - start

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        total_found = 0
        if stdout:
            found_lines = stdout.split('\n')
            total_found = len(found_lines)
            print(f"[{timestamp()}] Found {total_found} total messages during monitoring.")

        # A return code of 124 is expected as `timeout` kills the process.
        if result.returncode not in [0, 1, 124]:  # grep returns 1 if no matches found
            print(f"[{timestamp()}] Process exited with unexpected code: {result.returncode}")
            if stderr:
                print(f"[{timestamp()}] stderr: {stderr}")

        print(f"[{timestamp()}] Monitoring finished in {duration:.1f}s")
        return total_found > 0, total_found, duration, found_lines

    except subprocess.TimeoutExpired:
        # This can happen if the subprocess.run timeout is hit, which is a safeguard.
        duration = time.time() - start
        print(f"[{timestamp()}] Monitoring subprocess timed out, which is unexpected.")
        print(f"[{timestamp()}] FAIL in {duration:.1f}s")
        return False, 0, duration, []
    except Exception as e:
        duration = time.time() - start
        print(f"[{timestamp()}] ERROR monitoring logs: {e}")
        print(f"[{timestamp()}] FAIL in {duration:.1f}s")
        return False, 0, duration, []


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    args = parse_args()

    # Determine which messages to monitor
    if args.cfg_override_messages:
        print(f"[{timestamp()}] Using message list from command line override.")
        # Normalize and split messages, removing _MESSAGE suffix if present
        target_messages = [m.strip().replace("_MESSAGE", "")
                           for m in args.cfg_override_messages.split(",") if m.strip()]
    else:
        print(f"[{timestamp()}] Loading enabled messages from config: {args.ins_config_path}")
        target_messages = load_messages_from_config(args.ins_config_path)

    if not target_messages:
        print(f"[{timestamp()}] No messages to monitor. Exiting.")
        return 1

    print("=" * 60)
    print("INS Monitor: Check Messages")
    print("=" * 60)
    print(f"Config:")
    print(f"  - messages to monitor: {target_messages}")
    print(f"  - duration           : {args.duration}s")
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

    success, total_found, duration, found_lines = monitor_log(
        log_file=args.log_file,
        messages=target_messages,
        duration_sec=args.duration,
    )

    print("=" * 60)
    if success:
        analyze_results(found_lines, target_messages)
        print("-" * 60)
        print(f"[{timestamp()}] RESULT: PASS")
        print(f"  - Total messages found: {total_found}")
        print(f"  - Monitored for: {duration:.1f}s")
        return 0
    else:
        print(f"[{timestamp()}] RESULT: FAIL (Found 0 matching messages)")
        print(f"  - Monitored for: {duration:.1f}s")
        return 1


if __name__ == "__main__":
    sys.exit(main())
