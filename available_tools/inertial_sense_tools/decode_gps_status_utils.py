"""Utility helpers for decoding GPS status messages from Inertial Sense devices."""

from enum import Flag, IntEnum
from typing import Dict, List, Union

# --- Constants and Masks ---

GPS_STATUS_FIX_MASK: int = 0x00001F00
GPS_STATUS_FIX_BIT_OFFSET: int = 8

GPS_STATUS_FLAGS_MASK: int = 0xFFFFE000
GPS_STATUS_FLAGS_BIT_OFFSET: int = 16


class GpsFixType(IntEnum):
    """Enumeration of supported GPS fix types."""

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


class GpsStatusFlags(Flag):
    """Bit flags associated with the GPS status field."""

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


def decode_fix_type(status: int) -> GpsFixType:
    """Return the fix type encoded within the status integer."""
    fix_value = status & GPS_STATUS_FIX_MASK
    try:
        return GpsFixType(fix_value)
    except ValueError:
        return GpsFixType.NONE


def decode_flags(status: int) -> List[GpsStatusFlags]:
    """Return the list of active status flags."""
    flags_value = status & GPS_STATUS_FLAGS_MASK
    return [flag for flag in GpsStatusFlags if flag.value & flags_value]


def decode_gps_status(status: Union[int, str]) -> Dict[str, object]:
    """Decode the GPS status integer into a structured mapping. This can be get from DID_GPS1_POS message"""
    if isinstance(status, str):
        status = int(status, 0)

    return {
        "raw_status": status,
        "fix_type": decode_fix_type(status),
        "flags": decode_flags(status),
    }


def print_gps_status_report(status: Union[int, str]) -> None:
    """Print a human readable summary of the GPS status."""
    decoded = decode_gps_status(status)

    raw_status = decoded["raw_status"]
    fix = decoded["fix_type"]
    flags = decoded["flags"]

    print(f"Raw Status: 0x{raw_status:08X}")
    print(f"Fix Type: {fix.name} (0x{fix.value:08X})")
    print("Flags:")
    if not flags:
        print("  None")
    else:
        for flag in flags:
            print(f"  {flag.name} (0x{flag.value:08X})")
