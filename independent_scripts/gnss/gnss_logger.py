#!/usr/bin/env python3
import sys, datetime, time, signal, os
sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", errors="replace", closefd=False)
if len(sys.argv) < 4:
    sys.exit("Usage: python3 gnss_logger.py <device> <output> <max_seconds>\n  Ex: python3 gnss_logger.py /dev/ttymxc0.bak gnss_out.txt 3600")
DEVICE, OUTPUT, TIMEOUT = sys.argv[1], sys.argv[2], int(sys.argv[3])
running = True
signal.signal(signal.SIGINT,  lambda s, f: globals().update(running=False))
signal.signal(signal.SIGTERM, lambda s, f: globals().update(running=False))
def ts():
    t = datetime.datetime.now()
    return t.strftime("[%Y-%m-%d %H:%M:%S.") + "{:03d}]".format(t.microsecond // 1000)
deadline = time.monotonic() + TIMEOUT
buf = b""
fd = os.open(DEVICE, os.O_RDONLY | os.O_NOCTTY)
dev = os.fdopen(fd, "rb", buffering=0)
with dev, open(OUTPUT, "w", buffering=1, encoding="utf-8") as out:
    out.write("{} Source: {}\n".format(ts(), DEVICE))
    while running and time.monotonic() < deadline:
        byte = dev.read(1)
        if not byte:
            continue
        if byte == b"\n":
            line = buf.decode("ascii", errors="replace").rstrip("\r")
            buf = b""
            if line:
                entry = "{} {}\n".format(ts(), line)
                out.write(entry)
                print(entry, end="")
        else:
            buf += byte