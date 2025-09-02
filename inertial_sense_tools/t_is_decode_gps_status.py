#!/usr/bin/env python3.10

import argparse
from enum import IntEnum, Flag, auto
from typing import List

# --- Constants and Masks ---

GPS_STATUS_FIX_MASK: int = 0x00001F00
GPS_STATUS_FIX_BIT_OFFSET: int = 8

GPS_STATUS_FLAGS_MASK: int = 0xFFFFE000
GPS_STATUS_FLAGS_BIT_OFFSET: int = 16

# --- Fix Types ---

class GpsFixType(IntEnum):
    NONE = 0x00000000
    DEAD_RECKONING_ONLY = 0x00000100
    FIX_2D = 0x00000200
    FIX_3D = 0x00000300
    GPS_PLUS_DEAD_RECK = 0x00000400
    TIME_ONLY = 0x00000500
    UNUSED1 = 0x00000600
    UNUSED2 = 0x00000700
    DGPS = 0x00000800
    SBAS = 0x00000900
    RTK_SINGLE = 0x00000A00
    RTK_FLOAT = 0x00000B00
    RTK_FIX = 0x00000C00

# --- Flags ---

class GpsStatusFlags(Flag):
    FIX_OK = 0x00010000
    DGPS_USED = 0x00020000
    RTK_FIX_AND_HOLD = 0x00040000
    GPS1_RTK_POSITION_ENABLED = 0x00100000
    STATIC_MODE = 0x00200000
    GPS2_RTK_COMPASS_ENABLED = 0x00400000
    GPS1_RTK_RAW_GPS_DATA_ERROR = 0x00800000
    GPS1_RTK_BASE_DATA_MISSING = 0x01000000
    GPS1_RTK_BASE_POSITION_MOVING = 0x02000000
    GPS1_RTK_BASE_POSITION_INVALID = 0x03000000
    GPS1_RTK_POSITION_VALID = 0x04000000
    GPS2_RTK_COMPASS_VALID = 0x08000000
    GPS2_RTK_COMPASS_BASELINE_BAD = 0x00002000
    GPS2_RTK_COMPASS_BASELINE_UNSET = 0x00004000
    GPS_NMEA_DATA = 0x00008000
    GPS_PPS_TIMESYNC = 0x10000000

# --- Decoding Functions ---

def decode_fix_type(status: int) -> GpsFixType:
    fix_value = status & GPS_STATUS_FIX_MASK
    try:
        return GpsFixType(fix_value)
    except ValueError:
        return GpsFixType.NONE

def decode_flags(status: int) -> List[GpsStatusFlags]:
    flags_value = status & GPS_STATUS_FLAGS_MASK
    return [flag for flag in GpsStatusFlags if flag.value & flags_value]

def decode_gps_status(status: int) -> None:
    print(f"Raw Status: 0x{status:08X}")

    fix = decode_fix_type(status)
    print(f"Fix Type: {fix.name} (0x{fix.value:08X})")

    flags = decode_flags(status)
    print("Flags:")
    if not flags:
        print("  None")
    else:
        for flag in flags:
            print(f"  {flag.name} (0x{flag.value:08X})")

# --- Entry Point ---

def main() -> None:
    parser = argparse.ArgumentParser(description="Decode GPS status integer")
    parser.formatter_class = argparse.RawTextHelpFormatter
    parser.epilog = """Examples:

# Example 1
# Get the status using ins1 message: tail -F /var/log/ins_monitor_log | grep INS1Msg
#[2025-08-07 19:49:57.172], INS1Msg, TimeOfWeek[417015.167s], LLA[37.1202207, 127.0833099, 41.401], Roll[-179.35], Pitch[-0.08], Yaw[-85.79], Yaw (with offset)[-85.8], insStatus[0x1445026], hdwStatus[0x32080050], Velocity U,V,W[0.08, -0.05, -0.00, NED: 4164.98, -1377.12, 50.65]
python3 ~/local_tools/inertial_sense_tools/is_decode_gps_status.py --status "0x312"
"""
    parser.add_argument("-s", "--status", required=True, type=lambda x: int(x, 0), help="GPS status value (e.g. \"0x400312\" or \"785\")")
    args = parser.parse_args()

    decode_gps_status(args.status)

if __name__ == "__main__":
    main()
