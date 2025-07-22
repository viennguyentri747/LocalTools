#!/usr/bin/env python3
"""
Copy flash log files from 192.168.100.254 via one or more jump hosts.

Usage examples:
  # Single IP, T* logs
  python3 get_logs.py -t T -i 192.168.100.52

  # Multiple IPs, E* logs
  python3 get_logs.py --type E --ips 192.168.100.52 192.168.100.53

  # Multiple log types, multiple IPs
  python3 get_logs.py --type P T E --ips 192.168.100.52 192.168.100.53

  # Filter by date
  python3 get_logs.py --type T --ips 192.168.100.52 --date 20250625

  # Multiple log types, multiple IPs, filter by date
  python3 get_logs.py --type P T E --ips 192.168.100.52 192.168.100.53 --date 20250625

  # Multiple dates
  python3 get_logs.py --type T --ips 192.168.100.52 --date 20250625 20250626

  # Multiple log types, multiple IPs, multiple dates
  python3 get_logs.py --type P T E --ips 192.168.100.52 192.168.100.53 --date 20250625 20250626
Prerequisites:
  - Python 3.6+
  - SSH access (password or key) to jump host(s) and flash logs server
"""
import argparse
import subprocess
import datetime
import sys
import os
from typing import List, Tuple


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Pull flash log files via SSH jump hosts.'
    )
    parser.add_argument(
        '-t', '--type',
        nargs='+',
        choices=['P', 'T', 'E'],
        required=True,
        help='Log filename prefix(es) (P, T, or E).'
    )
    parser.add_argument(
        '-i', '--ips',
        nargs='+',
        required=True,
        help='UT IP address(es) to use as SSH jump host(s).'
    )
    parser.add_argument(
        '-u', '--user',
        default='root',
        help='SSH username (default: root).'
    )
    parser.add_argument(
        '-r', '--remote',
        default='192.168.100.254',
        help='Remote flash-logs server IP (default: 192.168.100.254).'
    )
    parser.add_argument(
        '-d', '--date',
        nargs='+',
        help='Date(s) to filter logs (YYYYMMDD format). If provided, only logs starting with these dates will be fetched.'
    )
    return parser.parse_args()


def build_scp_command(user: str, jump_ip: str, remote: str, log_type_prefix: str, dest: str, date_filter: str = None) -> List[str]:
    """
    Construct the scp command to fetch files matching log_type_prefix* from remote,
    using jump_ip as ProxyJump, saving into dest directory.
    If date_filter is provided, only logs starting with that date will be fetched.
    """
    if date_filter:
        remote_path = f"{user}@{remote}:/home/{user}/flash_logs/{log_type_prefix}_{date_filter}*"
    else:
        remote_path = f"{user}@{remote}:/home/{user}/flash_logs/{log_type_prefix}*"
    proxy = f"{user}@{jump_ip}"
    return [
        'scp', '-r',
        '-o', f'ProxyJump={proxy}',
        remote_path,
        dest
    ]


def fetch_logs_for_ip(user: str, remote: str, log_types: List[str], ip: str, timestamp: str, date_filters: List[str] = None) -> Tuple[bool, str]:
    """
    Create destination folder and invoke scp for each log type and date filter. Returns (success, ip).
    """
    all_ok = True
    subprocess.call("ssh-keygen -R 192.168.100.254", shell=True)
    dates_to_process = date_filters if date_filters else [None] # Process all dates or no date filter
    for log_type_prefix in log_types:
        for date_filter in dates_to_process:
            dest_dir_suffix = f"_{log_type_prefix}"
            if date_filter:
                dest_dir_suffix += f"_{date_filter}"
            dest_dir = f"{ip}_{timestamp}"

            try:
                os.makedirs(dest_dir, exist_ok=True)
            except OSError as e:
                print(f"[ERROR] Could not create directory '{dest_dir}': {e}", file=sys.stderr)
                all_ok = False
                continue

            cmd = build_scp_command(user, ip, remote, log_type_prefix, dest_dir, date_filter)
            print(f"[INFO] Fetching {log_type_prefix}* logs for {ip} into '{dest_dir}'...")
            try:
                subprocess.check_call(cmd)
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] scp failed for {ip} ({log_type_prefix}* logs, date {date_filter}): exit code {e.returncode}", file=sys.stderr)
                all_ok = False
    return all_ok, ip


def main() -> None:
    args = parse_args()
    # timestamp format YYYYMMDD_HHMMSS
    now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    failures = []
    for ip in args.ips:
        ok, this_ip = fetch_logs_for_ip(
            user=args.user,
            remote=args.remote,
            log_types=args.type,
            ip=ip,
            timestamp=now,
            date_filters=args.date # Pass date_filters
        )
        if not ok:
            failures.append(this_ip)

    if failures:
        print(f"\n[SUMMARY] Failed to fetch logs for: {', '.join(failures)}", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n[SUMMARY] All logs fetched successfully.")


if __name__ == '__main__':
    main()