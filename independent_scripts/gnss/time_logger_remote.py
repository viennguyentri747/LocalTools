#!/usr/bin/env python3
"""
Print remote current time repeatedly at a fixed interval.

Fetches time from world-time-api3.p.rapidapi.com using the /ip.txt endpoint,
which returns plain-text key:value pairs (not JSON).

Usage:
  python3 time_logger_remote.py <log_rate_ms> [timezone] [--timeout SECS]

Examples:
  python3 time_logger_remote.py 200 utc
  python3 time_logger_remote.py 1000 est
  python3 time_logger_remote.py 500 Asia/Seoul
"""

import argparse
import datetime as dt
import signal
import sys
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests")

API_URL = "https://world-time-api3.p.rapidapi.com/ip.txt"
HEADERS = {
    "x-rapidapi-key":  "717f02b33cmsh2dc83d2f85c63b9p1cbba1jsncc8505cd7aca",
    "x-rapidapi-host": "world-time-api3.p.rapidapi.com",
    "Content-Type":    "application/json",
}

running = True


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

def _stop(*_):
    global running
    running = False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Print remote current time repeatedly at a fixed interval.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 time_logger_remote.py 200 utc\n"
            "  python3 time_logger_remote.py 1000 est\n"
            "  python3 time_logger_remote.py 500 Asia/Seoul"
        ),
    )
    p.add_argument("log_rate_ms", type=int, help="Log interval in milliseconds (must be > 0)")
    p.add_argument("timezone", type=str, nargs="?", default="utc",
                   help="Timezone alias/name (e.g., utc, est, cst, pst, kst)")
    p.add_argument("--timeout", type=float, default=5.0,
                   help="HTTP timeout in seconds (default: 5.0)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------

_ALIASES = {
    "utc": "UTC",              "z":   "UTC",
    "est": "America/New_York", "edt": "America/New_York",
    "cst": "America/Chicago",  "cdt": "America/Chicago",
    "mst": "America/Denver",   "mdt": "America/Denver",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
    "kst": "Asia/Seoul",
}


def normalize_tz_name(raw: str) -> str:
    return _ALIASES.get(raw.strip().lower(), raw.strip())


def validate_tz(tz_name: str, raw: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        valid = "utc, est, cst, mst, pst, kst, or a valid IANA name (e.g., Europe/London)"
        sys.exit(f"Invalid timezone '{raw}'. Use one of: {valid}")


def _fmt_offset(utcoffset) -> str:
    if utcoffset is None:
        return "+0000"
    total = int(utcoffset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}{(total % 3600) // 60:02d}"


# ---------------------------------------------------------------------------
# Parse plain-text key: value response
# ---------------------------------------------------------------------------

def parse_txt(text: str) -> dict:
    """
    Parse lines like:
        abbreviation: CDT
        utc_datetime: 2026-03-30T23:52:36.386+00:00
    into a dict. Values after the first ': ' are kept as-is.
    """
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if ": " in line:
            key, _, val = line.partition(": ")
            result[key.strip()] = val.strip()
    return result


# ---------------------------------------------------------------------------
# Remote time fetch
# ---------------------------------------------------------------------------

def fetch_remote_time(tz: ZoneInfo, timeout_sec: float) -> str:
    """
    GET /ip.txt  →  parse plain-text response  →  convert to requested tz
    Returns: YYYY-MM-DD HH:MM:SS.mmm ABBR±HHMM
    """
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=timeout_sec)
    except requests.exceptions.Timeout:
        sys.exit(f"Request timed out after {timeout_sec}s")
    except requests.exceptions.ConnectionError as e:
        sys.exit(f"Connection error: {e}")

    if resp.status_code == 429:
        sys.exit("Rate limited by API (HTTP 429) — reduce log_rate_ms")
    if resp.status_code == 401:
        sys.exit("Unauthorized (HTTP 401) — check the API key in HEADERS")
    if not resp.ok:
        sys.exit(f"API error HTTP {resp.status_code}: {resp.text[:200]}")

    payload = parse_txt(resp.text)

    dt_str = payload.get("utc_datetime") or payload.get("datetime")
    if not dt_str:
        sys.exit(f"Missing datetime in response:\n{resp.text[:300]}")

    try:
        parsed = dt.datetime.fromisoformat(dt_str)
    except ValueError:
        sys.exit(f"Unexpected datetime format: {dt_str!r}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)

    local_time = parsed.astimezone(tz)
    abbr   = payload.get("abbreviation") or local_time.strftime("%Z") or "UTC"
    offset = _fmt_offset(local_time.utcoffset())
    ms     = local_time.microsecond // 1000
    return local_time.strftime("%Y-%m-%d %H:%M:%S.") + f"{ms:03d} {abbr}{offset}"


def format_local_utc_now() -> str:
    now_utc = dt.datetime.now(dt.timezone.utc)
    ms = now_utc.microsecond // 1000
    return now_utc.strftime("%Y-%m-%d %H:%M:%S.") + f"{ms:03d} UTC"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    if args.log_rate_ms <= 0:
        sys.exit("log_rate_ms must be > 0")

    tz_name  = normalize_tz_name(args.timezone)
    tz       = validate_tz(tz_name, args.timezone)
    interval = args.log_rate_ms / 1000.0

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    next_tick = time.monotonic()
    while running:
        try:
            remote_time = fetch_remote_time(tz, args.timeout)
            print(f"[{format_local_utc_now()}] {remote_time}", flush=True)
        except BrokenPipeError:
            break
        next_tick += interval
        sleep_for = next_tick - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)
        else:
            next_tick = time.monotonic()


if __name__ == "__main__":
    main()
