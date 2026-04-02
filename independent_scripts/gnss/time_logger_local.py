#!/usr/bin/env python3
import argparse, datetime as dt, signal, sys, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

running = True


def stop(*_):
    global running
    running = False


def parse_args():
    p = argparse.ArgumentParser(
        description="Print current time repeatedly at a fixed interval.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n  python3 time_logger.py 200 utc\n  python3 time_logger.py 1000 est\n  python3 time_logger.py 500 Asia/Seoul",
    )
    p.add_argument("log_rate_ms", type=int, help="Log interval in milliseconds (must be > 0)")
    p.add_argument("timezone", type=str, nargs="?", default="utc", help="Timezone alias/name (e.g., utc, est, cst, pst, kst)")
    return p.parse_args()


def resolve_tz(tz_input: str) -> ZoneInfo:
    aliases = {
        "utc": "UTC", "z": "UTC",
        "est": "America/New_York", "edt": "America/New_York",
        "cst": "America/Chicago", "cdt": "America/Chicago",
        "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
        "kst": "Asia/Seoul",
    }
    name = aliases.get(tz_input.strip().lower(), tz_input.strip())
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        valid = "utc, est, cst, pst, kst, or a valid IANA timezone (e.g., Europe/London)"
        sys.exit(f"Invalid timezone '{tz_input}'. Use one of: {valid}")


def fmt_now(tz: ZoneInfo) -> str:
    t = dt.datetime.now(tz)
    return t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d} " + t.strftime("%Z%z")


def main():
    args = parse_args()
    if args.log_rate_ms <= 0:
        sys.exit("log_rate_ms must be > 0")
    tz = resolve_tz(args.timezone)
    interval = args.log_rate_ms / 1000.0
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    next_tick = time.monotonic()
    while running:
        try:
            print(fmt_now(tz), flush=True)
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
