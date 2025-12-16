"""Utility helpers for decoding hardware status messages from Inertial Sense devices."""

from enum import Flag
from typing import Dict, Union

# Built-in Test (BIT) Status Field
HDW_STATUS_BIT_MASK: int = 0x03000000
HDW_STATUS_BIT_RUNNING: int = 0x01000000
HDW_STATUS_BIT_PASSED: int = 0x02000000
HDW_STATUS_BIT_FAILED: int = 0x03000000

# Communications Parse Error Count Field
HDW_STATUS_COM_PARSE_ERR_COUNT_MASK: int = 0x00F00000
HDW_STATUS_COM_PARSE_ERR_COUNT_OFFSET: int = 20

# System Reset Cause Field
HDW_STATUS_RESET_CAUSE_MASK: int = 0x70000000
HDW_STATUS_RESET_CAUSE_BACKUP_MODE: int = 0x10000000
HDW_STATUS_RESET_CAUSE_WATCHDOG_FAULT: int = 0x20000000
HDW_STATUS_RESET_CAUSE_SOFT: int = 0x30000000
HDW_STATUS_RESET_CAUSE_HDW: int = 0x40000000


class HdwStatusFlags(Flag):
    """Bit flags associated with the hardware status field."""

    MOTION_GYR = 0x00000001
    MOTION_ACC = 0x00000002
    IMU_FAULT_REJECT_GYR = 0x00000004
    IMU_FAULT_REJECT_ACC = 0x00000008
    GPS_SATELLITE_RX_VALID = 0x00000010
    STROBE_IN_EVENT = 0x00000020
    GPS_TIME_OF_WEEK_VALID = 0x00000040
    REFERENCE_IMU_RX = 0x00000080
    SATURATION_GYR = 0x00000100
    SATURATION_ACC = 0x00000200
    SATURATION_MAG = 0x00000400
    SATURATION_BARO = 0x00000800
    SYSTEM_RESET_REQUIRED = 0x00001000
    ERR_GPS_PPS_NOISE = 0x00002000
    MAG_RECAL_COMPLETE = 0x00004000
    FLASH_WRITE_PENDING = 0x00008000
    ERR_COM_TX_LIMITED = 0x00010000
    ERR_COM_RX_OVERRUN = 0x00020000
    ERR_NO_GPS_PPS = 0x00040000
    GPS_PPS_TIMESYNC = 0x00080000
    ERR_TEMPERATURE = 0x04000000
    SPI_INTERFACE_ENABLED = 0x08000000
    FAULT_SYS_CRITICAL = 0x80000000


def get_bit_status(status: int) -> str:
    """Decode the Built-in Test (BIT) status field."""
    bit_field = status & HDW_STATUS_BIT_MASK
    status_map = {
        HDW_STATUS_BIT_FAILED: "Failed",
        HDW_STATUS_BIT_PASSED: "Passed",
        HDW_STATUS_BIT_RUNNING: "Running",
    }
    return status_map.get(bit_field, "Not Run / N/A")


def get_reset_cause(status: int) -> str:
    """Decode the cause of the last system reset."""
    reset_field = status & HDW_STATUS_RESET_CAUSE_MASK
    cause_map = {
        HDW_STATUS_RESET_CAUSE_HDW: "Hardware (NRST pin)",
        HDW_STATUS_RESET_CAUSE_SOFT: "Software",
        HDW_STATUS_RESET_CAUSE_WATCHDOG_FAULT: "Watchdog Fault",
        HDW_STATUS_RESET_CAUSE_BACKUP_MODE: "Backup Mode (Low-power state)",
    }
    for cause, description in cause_map.items():
        if reset_field == cause:
            return description
    return "N/A"


def get_com_parse_error_count(status: int) -> int:
    """Extract the communication parse error count."""
    return (status & HDW_STATUS_COM_PARSE_ERR_COUNT_MASK) >> HDW_STATUS_COM_PARSE_ERR_COUNT_OFFSET


def is_set(hdw_status: int, flag: HdwStatusFlags) -> bool:
    """Return True when the provided flag is set."""
    return (hdw_status & flag.value) != 0


def decode_system_hdw_status(hdw_status: Union[int, str]) -> Dict[str, object]:
    """Decode a 32-bit hardware status value into a structured mapping."""
    if isinstance(hdw_status, str):
        hdw_status = int(hdw_status, 0)

    line_separator = f"\n{'=' * 60}\n"
    indent = " " * 4

    return {
        "Overall Status Value (Hex)": f"0x{hdw_status:08X}",
        f"{line_separator}MOTION & IMU": {
            indent + "Gyro motion detected": is_set(hdw_status, HdwStatusFlags.MOTION_GYR),
            indent + "Accelerometer motion detected": is_set(hdw_status, HdwStatusFlags.MOTION_ACC),
            indent + "IMU gyro fault rejection": is_set(hdw_status, HdwStatusFlags.IMU_FAULT_REJECT_GYR),
            indent + "IMU accelerometer fault rejection": is_set(hdw_status, HdwStatusFlags.IMU_FAULT_REJECT_ACC),
        },
        f"{line_separator}SENSOR SATURATION": {
            indent + "Gyro": is_set(hdw_status, HdwStatusFlags.SATURATION_GYR),
            indent + "Accelerometer": is_set(hdw_status, HdwStatusFlags.SATURATION_ACC),
            indent + "Magnetometer": is_set(hdw_status, HdwStatusFlags.SATURATION_MAG),
            indent + "Barometric Pressure": is_set(hdw_status, HdwStatusFlags.SATURATION_BARO),
        },
        f"{line_separator}GENERAL STATUS & TIMING": {
            indent + "GPS Satellite RX Valid": is_set(hdw_status, HdwStatusFlags.GPS_SATELLITE_RX_VALID),
            indent + "GPS Time Of Week Valid": is_set(hdw_status, HdwStatusFlags.GPS_TIME_OF_WEEK_VALID),
            indent + "Time synchronized by GPS PPS": is_set(hdw_status, HdwStatusFlags.GPS_PPS_TIMESYNC),
            indent + "Reference IMU data received": is_set(hdw_status, HdwStatusFlags.REFERENCE_IMU_RX),
            indent + "Event on strobe input pin": is_set(hdw_status, HdwStatusFlags.STROBE_IN_EVENT),
        },
        f"{line_separator}SYSTEM & INTERFACE": {
            indent + "Mag Recalibration Complete": is_set(hdw_status, HdwStatusFlags.MAG_RECAL_COMPLETE),
            indent + "Flash Write Pending": is_set(hdw_status, HdwStatusFlags.FLASH_WRITE_PENDING),
            indent + "SPI Interface Enabled": is_set(hdw_status, HdwStatusFlags.SPI_INTERFACE_ENABLED),
            indent + "Built-in Test (BIT) Status": get_bit_status(hdw_status),
            indent + "Cause of Last Reset": get_reset_cause(hdw_status),
        },
        f"{line_separator}FAULTS & WARNINGS": {
            indent + "Critical System Fault (CPU)": is_set(hdw_status, HdwStatusFlags.FAULT_SYS_CRITICAL),
            indent + "System Reset Required": is_set(hdw_status, HdwStatusFlags.SYSTEM_RESET_REQUIRED),
            indent + "Temperature out of spec": is_set(hdw_status, HdwStatusFlags.ERR_TEMPERATURE),
            indent + "GPS PPS signal noise": is_set(hdw_status, HdwStatusFlags.ERR_GPS_PPS_NOISE),
            indent + "No GPS PPS signal": is_set(hdw_status, HdwStatusFlags.ERR_NO_GPS_PPS),
            indent + "Communications Tx buffer limited": is_set(hdw_status, HdwStatusFlags.ERR_COM_TX_LIMITED),
            indent + "Communications Rx buffer overrun": is_set(hdw_status, HdwStatusFlags.ERR_COM_RX_OVERRUN),
            indent + "Communications Parse Error Count": get_com_parse_error_count(hdw_status),
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
