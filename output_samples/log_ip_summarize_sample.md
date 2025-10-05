# Sample: ACU E-log Summary Output

```
[2025-10-04 16:00:54] Log Analysis Summary for IPs [192.168.100.54, 192.168.100.60]
[2025-10-04 16:00:54] 
======================================================================

[2025-10-04 16:00:55] IP:192.168.100.54
[2025-10-04 16:00:55] Log Directory: /home/vien/local_tools/temp/acu_elogs/192.168.100.54
[2025-10-04 16:00:55] Log Files Status:
[2025-10-04 16:00:55] - ✓ Found: ['E_20251003_000000.txt', 'E_20251004_000000.txt']
[2025-10-04 16:00:55] - ✗ Missing: None
[2025-10-04 16:00:55] 
[2025-10-04 16:00:55] Pattern Analysis:
[2025-10-04 16:00:55] Pattern: `MOTION DETECT`
[2025-10-04 16:00:55] - Matches: 2
[2025-10-04 16:00:55] - Lines:
[2025-10-04 16:00:55]   - [2025-10-04 15:08:17.404][F] [CRI] TN-CAL-STOP Occurred Master [169.03->0.00] [MOTION DETECT]
[2025-10-04 16:00:55]   - [2025-10-03 20:29:48.366][F] [CRI] TN-CAL-STOP Occurred Master [166.56->0.00] [MOTION DETECT]
[2025-10-04 16:00:55] Pattern: `INS-READY`
[2025-10-04 16:00:55] - Matches: 0
[2025-10-04 16:00:55] - Lines: None

======================================================================

[2025-10-04 16:00:55] IP:192.168.100.60
[2025-10-04 16:00:55] Log Directory: /home/vien/local_tools/temp/acu_elogs/192.168.100.60
[2025-10-04 16:00:55] Log Files Status:
[2025-10-04 16:00:55] - ✓ Found: None
[2025-10-04 16:00:55] - ✗ Missing: ['E_20251004*', 'E_20251003*']
[2025-10-04 16:00:55] Pattern check skipped since no log files found

======================================================================
```

Use this as a reference for how the tool formats its high-level summary.
