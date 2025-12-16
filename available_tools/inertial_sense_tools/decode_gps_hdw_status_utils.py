"""Utility helpers for decoding GPS hardware status messages from Inertial Sense devices."""

from enum import Flag
from typing import Dict, Union
from dev.dev_common.constants import *

ENUM_EGPX_HDW_STATUS_FLAGS_NAME = "eGPXHdwStatusFlags"

# Reset count fields
GNSS1_RESET_COUNT_MASK: int = 0x00000070
GNSS1_RESET_COUNT_OFFSET: int = 4

GNSS2_RESET_COUNT_MASK: int = 0x00000700
GNSS2_RESET_COUNT_OFFSET: int = 8

# Built-in Test (BIT) Status Field
GPS_HDW_STATUS_BIT_MASK: int = 0x03000000
GPS_HDW_STATUS_BIT_RUNNING: int = 0x01000000
GPS_HDW_STATUS_BIT_PASSED: int = 0x02000000
GPS_HDW_STATUS_BIT_FAILED: int = 0x03000000

# System Reset Cause Field
GPS_HDW_STATUS_RESET_CAUSE_MASK: int = 0x70000000
GPS_HDW_STATUS_RESET_CAUSE_BACKUP_MODE: int = 0x10000000
GPS_HDW_STATUS_RESET_CAUSE_SOFT: int = 0x20000000
GPS_HDW_STATUS_RESET_CAUSE_HDW: int = 0x40000000

# Aggregate masks
GPS_HDW_STATUS_ERR_PPS_MASK: int = 0x000C0000
GPS_HDW_STATUS_ERR_CNO_MASK: int = 0x00F00000


class GpsHdwStatusFlags(Flag):
    """Bit flags associated with the GPS hardware status field."""

    GNSS1_SATELLITE_RX = 0x00000001
    GNSS2_SATELLITE_RX = 0x00000002
    GNSS1_TIME_OF_WEEK_VALID = 0x00000004
    GNSS2_TIME_OF_WEEK_VALID = 0x00000008
    FAULT_GNSS1_INIT = 0x00000080
    FAULT_GNSS2_INIT = 0x00000800
    GNSS_FW_UPDATE_REQUIRED = 0x00001000
    LED_ENABLED = 0x00002000
    SYSTEM_RESET_REQUIRED = 0x00004000
    FLASH_WRITE_PENDING = 0x00008000
    ERR_COM_TX_LIMITED = 0x00010000
    ERR_COM_RX_OVERRUN = 0x00020000
    ERR_NO_GPS1_PPS = 0x00040000
    ERR_NO_GPS2_PPS = 0x00080000
    ERR_LOW_CNO_GPS1 = 0x00100000
    ERR_LOW_CNO_GPS2 = 0x00200000
    ERR_CNO_GPS1_IRREGULAR = 0x00400000
    ERR_CNO_GPS2_IRREGULAR = 0x00800000
    ERR_TEMPERATURE = 0x04000000
    GPS_PPS_TIMESYNC = 0x08000000
    FAULT_SYS_CRITICAL = 0x80000000


def get_bit_status(status: int) -> str:
    """Decode the Built-in Test (BIT) status field."""
    bit_field = status & GPS_HDW_STATUS_BIT_MASK
    status_map = {
        GPS_HDW_STATUS_BIT_FAILED: "Failed",
        GPS_HDW_STATUS_BIT_PASSED: "Passed",
        GPS_HDW_STATUS_BIT_RUNNING: "Running",
    }
    return status_map.get(bit_field, "Not Run / N/A")


def get_reset_cause(status: int) -> str:
    """Decode the cause of the last system reset."""
    reset_field = status & GPS_HDW_STATUS_RESET_CAUSE_MASK
    cause_map = {
        GPS_HDW_STATUS_RESET_CAUSE_HDW: "Hardware (NRST pin)",
        GPS_HDW_STATUS_RESET_CAUSE_SOFT: "Software",
        GPS_HDW_STATUS_RESET_CAUSE_BACKUP_MODE: "Backup Mode (Low-power state)",
    }
    for cause, description in cause_map.items():
        if reset_field == cause:
            return description
    return "N/A"


def get_reset_count(status: int, mask: int, offset: int) -> int:
    """Extract a reset count value from the status field."""
    return (status & mask) >> offset


def is_set(status: int, flag: GpsHdwStatusFlags) -> bool:
    """Return True when the provided flag is set."""
    return (status & flag.value) != 0


def decode_gps_hdw_status(status: Union[int, str]) -> Dict[str, object]:
    """Decode a 32-bit GPS hardware status value into a structured mapping."""
    if isinstance(status, str):
        status = int(status, 0)

    line_separator = f"\n{'=' * 60}\n"
    indent = " " * 4

    return {
        "Overall Status Value (Hex)": f"0x{status:08X}",
        f"{line_separator}GNSS RECEIVER STATE": {
            indent + "GNSS1 satellite signals received": is_set(status, GpsHdwStatusFlags.GNSS1_SATELLITE_RX),
            indent + "GNSS2 satellite signals received": is_set(status, GpsHdwStatusFlags.GNSS2_SATELLITE_RX),
            indent + "GNSS1 time-of-week valid": is_set(status, GpsHdwStatusFlags.GNSS1_TIME_OF_WEEK_VALID),
            indent + "GNSS2 time-of-week valid": is_set(status, GpsHdwStatusFlags.GNSS2_TIME_OF_WEEK_VALID),
            indent + "GNSS1 init fault": is_set(status, GpsHdwStatusFlags.FAULT_GNSS1_INIT),
            indent + "GNSS2 init fault": is_set(status, GpsHdwStatusFlags.FAULT_GNSS2_INIT),
        },
        f"{line_separator}GNSS RESET COUNTS": {
            indent + "GNSS1 reset count": get_reset_count(status, GNSS1_RESET_COUNT_MASK, GNSS1_RESET_COUNT_OFFSET),
            indent + "GNSS2 reset count": get_reset_count(status, GNSS2_RESET_COUNT_MASK, GNSS2_RESET_COUNT_OFFSET),
        },
        f"{line_separator}PPS & TIMING": {
            indent + "GPS PPS time-synchronized": is_set(status, GpsHdwStatusFlags.GPS_PPS_TIMESYNC),
            indent + "No GPS1 PPS signal": is_set(status, GpsHdwStatusFlags.ERR_NO_GPS1_PPS),
            indent + "No GPS2 PPS signal": is_set(status, GpsHdwStatusFlags.ERR_NO_GPS2_PPS),
            indent + "Any PPS-related error": bool(status & GPS_HDW_STATUS_ERR_PPS_MASK),
        },
        f"{line_separator}SIGNAL QUALITY": {
            indent + "GPS1 low C/N0": is_set(status, GpsHdwStatusFlags.ERR_LOW_CNO_GPS1),
            indent + "GPS2 low C/N0": is_set(status, GpsHdwStatusFlags.ERR_LOW_CNO_GPS2),
            indent + "GPS1 irregular C/N0": is_set(status, GpsHdwStatusFlags.ERR_CNO_GPS1_IRREGULAR),
            indent + "GPS2 irregular C/N0": is_set(status, GpsHdwStatusFlags.ERR_CNO_GPS2_IRREGULAR),
            indent + "Any C/N0-related error": bool(status & GPS_HDW_STATUS_ERR_CNO_MASK),
        },
        f"{line_separator}SYSTEM & MAINTENANCE": {
            indent + "Firmware update required": is_set(status, GpsHdwStatusFlags.GNSS_FW_UPDATE_REQUIRED),
            indent + "LED enabled (Manufacturing test)": is_set(status, GpsHdwStatusFlags.LED_ENABLED),
            indent + "System reset required": is_set(status, GpsHdwStatusFlags.SYSTEM_RESET_REQUIRED),
            indent + "Flash write pending": is_set(status, GpsHdwStatusFlags.FLASH_WRITE_PENDING),
            indent + "Built-in Test (BIT) status": get_bit_status(status),
            indent + "Cause of last reset": get_reset_cause(status),
        },
        f"{line_separator}COMMUNICATIONS": {
            indent + "Communications Tx buffer limited": is_set(status, GpsHdwStatusFlags.ERR_COM_TX_LIMITED),
            indent + "Communications Rx overrun": is_set(status, GpsHdwStatusFlags.ERR_COM_RX_OVERRUN),
        },
        f"{line_separator}FAULTS & WARNINGS": {
            indent + "Critical system fault (CPU)": is_set(status, GpsHdwStatusFlags.FAULT_SYS_CRITICAL),
            indent + "Temperature out of spec": is_set(status, GpsHdwStatusFlags.ERR_TEMPERATURE),
        },
    }


def print_decoded_status(decoded_status: Dict[str, object], indent: int = 0) -> None:
    """Recursively print the decoded status dictionary."""
    for key, value in decoded_status.items():
        prefix = " " * indent
        if isinstance(value, dict):
            print(f"{prefix}{key}")
            print_decoded_status(value, indent + 4)
        else:
            print(f"{prefix}{key}: {value}")
