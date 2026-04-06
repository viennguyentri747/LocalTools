#!/usr/bin/env python3
import subprocess
import re
import time
from datetime import datetime, timezone

def get_chrony_offset() -> float:
    out = subprocess.check_output(['chronyc', 'tracking'], text=True, timeout=2)
    for line in out.splitlines():
        if 'System time' in line:
            match = re.search(r'([\d.]+) seconds (fast|slow)', line)
            if match:
                offset = float(match.group(1))
                return -offset if match.group(2) == 'fast' else offset
    return 0.0

def now_utc(offset: float) -> str:
    ts = time.time() + offset
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z' + f'	Offset{offset}'

last_sync = 0
sync_interval_secs = 10
while True:
    if time.time() - last_sync > sync_interval_secs:
        offset = get_chrony_offset()
        last_sync = time.time()
    print(now_utc(offset))
    time.sleep(0.1)