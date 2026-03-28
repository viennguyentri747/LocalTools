___
%% START page_tmpl_default %%
```dataviewjs
// Constants from external object
const LINKED_FROM_HEADER = "Backlinks";
const NO_BACKLINKS_MESSAGE = "No backlinks";

// Get backlinks to current page
const currentPage = dv.current().file.path;
const backlinks = dv.pages()
  .filter(p => p.file.outlinks.includes(dv.current().file.link))
  .sort(p => p.file.name, 'asc');

// Create a table to display the backlinks
if (backlinks.length > 0) {
  dv.table(
    [LINKED_FROM_HEADER],
    backlinks.map(p => [
      dv.fileLink(p.file.path)
    ])
  );
} else {
  dv.paragraph(NO_BACKLINKS_MESSAGE);
}
```
**Created:** 2025-04-17
%% END page_tmpl_default %%
___
[https://intelliantech.atlassian.net/wiki/spaces/IADC/pages/457212051/IESA+FTM+KIM+Debugging](https://intelliantech.atlassian.net/wiki/spaces/IADC/pages/457212051/IESA+FTM+KIM+Debugging)

[[_Intellian KIM-FTM-ACU-SSM communication (KIM focus), communication interfaces (flow chart dev ttyS2, ttyS1 ...)]]

[[_Intellian FTM - Communicate with FTM (via serial port on ACU, SSM) using Available SCPI Commands How to (set passthrough, configure ftm ...)]]

# What it does

It tells FTM to **NOT absorb the original KIM NMEA sentences**, this mean it will let those sentences passthrough FTM **and go to the SSM** directly.

> [!important] This mean **NMEA sentences seen** on the FTM-ACU interface (PRG) are the exact messages **received by the FTM from the KIM**

# Steps to-do it via ACU (SSM-FTM)

[[Intellian FTM - (EXTENDED) Put FTM into GNSS passthrough on ACU]]

# Steps to-do it via SSM (SSM-FTM) - work but need test mode!!!

[[_Intellian SSM Software, Applications Overview, What it does on operation, … (sysmon, gnssmon …)]]

- **PUT FTM IN TEST MODE**: DO THIS or else gnssmon will interrupt or cause missing sentences ~~-> Via testing still missing ...~~
	- Note: THIS MAY NOT WORK in some case (like FTM not respond and require certain configuration beside FTM scpis since startup?)

```Bash
touch /misc/ssm_test.dat && sync && reboot
```

- Some times require `ftmreset` on FD/HD
- Then do any of below to stop gnssmon interrupting `/dev/ttymxc0`
	- Way1: Change egr device path. What this does is it move the device node to a different name and thus gnssmon will not be able to use it. After reboot kernel recreates `/dev/ttymxc0` fresh from devtmpfs/udev so it should be fine

```Bash
# Stop gnssmon + Access the serial port to FTM (SSM-FTM interface)
EGR_DEV=/dev/ttymxc0; mv $EGR_DEV $EGR_DEV.bak; killall gnssmon; minicom -D $EGR_DEV.bak -b 115200;
```

- Way2: Put ssm in test mode (require reboot) →

[[minicom overview + how to (commands, .. for working with serial port comm)]]

- SCPI Commands to **disable NMEA messages from FTM → SSM.** Notes: can run all at once.
[[_Intellian FTM - Communicate with FTM (via serial port on ACU, SSM) using Available SCPI Commands How to (set passthrough, configure ftm ...)]]

```Bash
#Below Still work but show 'Command errors'
GPS:GPGGA 0;GPS:GPGSA 0;GPS:GPGLL 0;GPS:GPZDA 0;GPS:GPGSV 0;GPS:GPVTG 0;GPS:PJLTV 0;GPS:PJLTS 0; GPS:POWGPS 0; GPS:POWTLV 0;
#To enable them back
GPS:GPGGA 1;GPS:GPGSA 1;GPS:GPGLL 1;GPS:GPZDA 1;GPS:GPGSV 1;GPS:GPVTG 1;GPS:PJLTV 1;GPS:PJLTS 1; GPS:POWGPS 1; GPS:POWTLV 1;
```

Note: NMEA Messages can also be disabled by setting broadcast interval in diagnostics > configuration. Ex: `gga_interval_ms`

![[image 118.png|800]]

- Put the **FTM into GNSS Passthrough mode**

```Bash
SYST:GNSSPASS 1
# To disable (later):
SYST:GNSSPASS 0
```

### Note:

- For now the easiest way to know if it is actually in pass through mode or not is by looking at the **GNGGA NMEA** sentence, if the first field (UTC in hhmmss) have **3 decimal point then it is from the KIM (passthrough)**, but if **it has 2 then it is formatted from FTM**

```Bash
# From KIM -> have 3 number after time. (000 after 021752.)
$GNGGA,021752.000,3903.81498,N,07709.27921,W,1,21,0.90,110.65,M,-33.80,M,,*4C
```

- For new version of the KIM, NMEA sentences still coming through irrelevant of SSM running or not
- Single script

```Bash
minicom -D /dev/ttymxc0 -C minicom.log
#Then `tail -F minicom.log` on the side (current will be interactive)
```

- When we use the passthrough mode we will missing the $ sign in the message.

# Extra

### Get gnss log with timestamp

- `cat | while read`, the data goes through a shell pipe. Pipes in Linux are block-buffered (usually 4KB to 64KB) by default. Furthermore, the `read` command waits for the whole line to be buffered before passing it.

```Bash
#Get passthrough sentences WITH TIMESTAMP
MAX_SECS=3600; EGR_DEV=/dev/ttymxc0; mv $EGR_DEV $EGR_DEV.bak; killall gnssmon; sleep 3; date > test_gnss.txt; echo "Source: $EGR_DEV.bak" >> test_gnss.txt; nohup timeout $MAX_SECS sh -c "cat $EGR_DEV.bak | while read -r l; do echo \"\$(date +[%Y-%m-%d\ %H:%M:%S.%3N]) \$l\"; done" >> test_gnss.txt & tail -F test_gnss.txt
```

#### Or with python

Note on performance:
- You explicitly opened the device unbuffered (`buffering=0`) and read it byte-by-byte. The timestamp is generated the exact microsecond the `\n` byte crosses the serial interface into Python.
- **Shell:** When you use `cat | while read`, the data goes through a shell pipe. Pipes in Linux are block-buffered (usually 4KB to 64KB) by default. Furthermore, the `read` command waits for the whole line to be buffered before passing it. By the time the `date` command runs, the actual arrival time of that NMEA sentence has already passed, introducing unpredictable timing jitter (latency).

```Bash
cat > gnss_logger.py << 'EOF'
#!/usr/bin/env python3
import sys, datetime, time, signal
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
with open(DEVICE, "rb", buffering=0) as dev, open(OUTPUT, "w", buffering=1) as out:
    out.write("{} Source: {}\n".format(ts(), DEVICE))
    while running and time.monotonic() < deadline:
        byte = dev.read(1)
        if not byte:
            break
        if byte in (b"\n", b"\r"):
            line = buf.decode("ascii", errors="replace").rstrip("")
            buf = b""
            if line:
                entry = "{} {}\n".format(ts(), line)
                out.write(entry)
                print(entry, end="")
        else:
            buf += byte
EOF

python3 gnss_logger.py /dev/ttymxc0.bak gnss_out.txt 3600
```

### Set pass through mode without minicom (DOES NOT WORK ...)

```Bash
killall gnssmon
(echo "SYST:GNSSPASS 1") > /dev/ttymxc0 && cat /dev/ttymxc0
```