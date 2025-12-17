"""Utility helpers for decoding hardware status messages from Inertial Sense devices."""

from enum import Flag
from typing import Dict, Union

from dev.dev_common.core_independent_utils import LOG
from dev.dev_iesa.iesa_repo_utils import (
    get_enum_declaration_from_path,
    get_path_to_inertial_sense_data_set_header,
)

ENUM_HDW_STATUS_FLAGS_NAME = "eHdwStatusFlags"

_HEADER_PATH = get_path_to_inertial_sense_data_set_header()
_HDW_STATUS_VALUES = get_enum_declaration_from_path(ENUM_HDW_STATUS_FLAGS_NAME, _HEADER_PATH)


def _get(name: str) -> int:
    try:
        return _HDW_STATUS_VALUES[name]
    except KeyError as exc:
        raise KeyError(f"Missing {name} in {ENUM_HDW_STATUS_FLAGS_NAME}") from exc


# Built-in Test (BIT) Status Field
HDW_STATUS_BIT_MASK: int = _get("HDW_STATUS_BIT_MASK")
HDW_STATUS_BIT_RUNNING: int = _get("HDW_STATUS_BIT_RUNNING")
HDW_STATUS_BIT_PASSED: int = _get("HDW_STATUS_BIT_PASSED")
HDW_STATUS_BIT_FAILED: int = _get("HDW_STATUS_BIT_FAILED")

# Communications Parse Error Count Field
HDW_STATUS_COM_PARSE_ERR_COUNT_MASK: int = _get("HDW_STATUS_COM_PARSE_ERR_COUNT_MASK")
HDW_STATUS_COM_PARSE_ERR_COUNT_OFFSET: int = _get("HDW_STATUS_COM_PARSE_ERR_COUNT_OFFSET")

# System Reset Cause Field
HDW_STATUS_RESET_CAUSE_MASK: int = _get("HDW_STATUS_RESET_CAUSE_MASK")
HDW_STATUS_RESET_CAUSE_BACKUP_MODE: int = _get("HDW_STATUS_RESET_CAUSE_BACKUP_MODE")
HDW_STATUS_RESET_CAUSE_WATCHDOG_FAULT: int = _get("HDW_STATUS_RESET_CAUSE_WATCHDOG_FAULT")
HDW_STATUS_RESET_CAUSE_SOFT: int = _get("HDW_STATUS_RESET_CAUSE_SOFT")
HDW_STATUS_RESET_CAUSE_HDW: int = _get("HDW_STATUS_RESET_CAUSE_HDW")

LOG(
    f"[IESA] Parsed {ENUM_HDW_STATUS_FLAGS_NAME}: "
    f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _HDW_STATUS_VALUES.items()} }"
)


class HdwStatusFlags(Flag):
    """Bit flags associated with the hardware status field."""

    MOTION_GYR = _get("HDW_STATUS_MOTION_GYR")
    MOTION_ACC = _get("HDW_STATUS_MOTION_ACC")
    IMU_FAULT_REJECT_GYR = _get("HDW_STATUS_IMU_FAULT_REJECT_GYR")
    IMU_FAULT_REJECT_ACC = _get("HDW_STATUS_IMU_FAULT_REJECT_ACC")
    GPS_SATELLITE_RX_VALID = _get("HDW_STATUS_GPS_SATELLITE_RX_VALID")
    STROBE_IN_EVENT = _get("HDW_STATUS_STROBE_IN_EVENT")
    GPS_TIME_OF_WEEK_VALID = _get("HDW_STATUS_GPS_TIME_OF_WEEK_VALID")
    REFERENCE_IMU_RX = _get("HDW_STATUS_REFERENCE_IMU_RX")
    SATURATION_GYR = _get("HDW_STATUS_SATURATION_GYR")
    SATURATION_ACC = _get("HDW_STATUS_SATURATION_ACC")
    SATURATION_MAG = _get("HDW_STATUS_SATURATION_MAG")
    SATURATION_BARO = _get("HDW_STATUS_SATURATION_BARO")
    SYSTEM_RESET_REQUIRED = _get("HDW_STATUS_SYSTEM_RESET_REQUIRED")
    ERR_GPS_PPS_NOISE = _get("HDW_STATUS_ERR_GPS_PPS_NOISE")
    MAG_RECAL_COMPLETE = _get("HDW_STATUS_MAG_RECAL_COMPLETE")
    FLASH_WRITE_PENDING = _get("HDW_STATUS_FLASH_WRITE_PENDING")
    ERR_COM_TX_LIMITED = _get("HDW_STATUS_ERR_COM_TX_LIMITED")
    ERR_COM_RX_OVERRUN = _get("HDW_STATUS_ERR_COM_RX_OVERRUN")
    ERR_NO_GPS_PPS = _get("HDW_STATUS_ERR_NO_GPS_PPS")
    GPS_PPS_TIMESYNC = _get("HDW_STATUS_GPS_PPS_TIMESYNC")
    ERR_TEMPERATURE = _get("HDW_STATUS_ERR_TEMPERATURE")
    SPI_INTERFACE_ENABLED = _get("HDW_STATUS_SPI_INTERFACE_ENABLED")
    FAULT_SYS_CRITICAL = _get("HDW_STATUS_FAULT_SYS_CRITICAL")


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
