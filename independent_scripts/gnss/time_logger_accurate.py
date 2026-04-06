#!/usr/bin/env python3
import ntplib
from datetime import datetime, timezone

def get_ntp_utc():
    c = ntplib.NTPClient()
    response = c.request('time.cloudflare.com', version=3)
    utc_time = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
    offset = response.offset  # How far your system clock is off (seconds)
    return utc_time, offset

while True:
    utc, offset = get_ntp_utc()
    print(f"UTC: {utc.strftime('%Y-%m-%dT%H:%M:%S.%f')}Z")
    #print(f"System clock offset: {offset:.6f}s")