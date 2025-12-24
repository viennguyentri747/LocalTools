"""Utility helpers for decoding GPS hardware status messages from Inertial Sense devices."""

from dataclasses import dataclass, field
from enum import Flag
from typing import Dict, List, Union

from dev.dev_common.core_independent_utils import LOG
from dev.dev_iesa.iesa_repo_utils import (
    get_enum_declaration_from_path,
    get_path_to_inertial_sense_data_set_header,
)

ENUM_EGPX_HDW_STATUS_FLAGS_NAME = "eGPXHdwStatusFlags"

_HEADER_PATH = get_path_to_inertial_sense_data_set_header()
_GPX_HDW_VALUES = get_enum_declaration_from_path(ENUM_EGPX_HDW_STATUS_FLAGS_NAME, _HEADER_PATH)


def _get(name: str) -> int:
    try:
        return _GPX_HDW_VALUES[name]
    except KeyError as exc:
        raise KeyError(f"Missing {name} in {ENUM_EGPX_HDW_STATUS_FLAGS_NAME}") from exc


# Reset count fields
GNSS1_RESET_COUNT_MASK: int = _get("GPX_HDW_STATUS_GNSS1_RESET_COUNT_MASK")
GNSS1_RESET_COUNT_OFFSET: int = _get("GPX_HDW_STATUS_GNSS1_RESET_COUNT_OFFSET")

GNSS2_RESET_COUNT_MASK: int = _get("GPX_HDW_STATUS_GNSS2_RESET_COUNT_MASK")
GNSS2_RESET_COUNT_OFFSET: int = _get("GPX_HDW_STATUS_GNSS2_RESET_COUNT_OFFSET")

# Built-in Test (BIT) Status Field
GPS_HDW_STATUS_BIT_MASK: int = _get("GPX_HDW_STATUS_BIT_MASK")
GPS_HDW_STATUS_BIT_RUNNING: int = _get("GPX_HDW_STATUS_BIT_RUNNING")
GPS_HDW_STATUS_BIT_PASSED: int = _get("GPX_HDW_STATUS_BIT_PASSED")
GPS_HDW_STATUS_BIT_FAILED: int = _get("GPX_HDW_STATUS_BIT_FAULT")

# System Reset Cause Field
GPS_HDW_STATUS_RESET_CAUSE_MASK: int = _get("GPX_HDW_STATUS_RESET_CAUSE_MASK")
GPS_HDW_STATUS_RESET_CAUSE_BACKUP_MODE: int = _get("GPX_HDW_STATUS_RESET_CAUSE_BACKUP_MODE")
GPS_HDW_STATUS_RESET_CAUSE_SOFT: int = _get("GPX_HDW_STATUS_RESET_CAUSE_SOFT")
GPS_HDW_STATUS_RESET_CAUSE_HDW: int = _get("GPX_HDW_STATUS_RESET_CAUSE_HDW")

# Aggregate masks
GPS_HDW_STATUS_ERR_PPS_MASK: int = _get("GPX_HDW_STATUS_ERR_PPS_MASK")
GPS_HDW_STATUS_ERR_CNO_MASK: int = _get("GPX_HDW_STATUS_ERR_CNO_MASK")

LOG(
    f"[IESA] Parsed {ENUM_EGPX_HDW_STATUS_FLAGS_NAME}: "
    f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _GPX_HDW_VALUES.items()} }"
)


class GpsHdwStatusFlags(Flag):
    """Bit flags associated with the GPS hardware status field."""

    GNSS1_SATELLITE_RX = _get("GPX_HDW_STATUS_GNSS1_SATELLITE_RX")
    GNSS2_SATELLITE_RX = _get("GPX_HDW_STATUS_GNSS2_SATELLITE_RX")
    GNSS1_TIME_OF_WEEK_VALID = _get("GPX_HDW_STATUS_GNSS1_TIME_OF_WEEK_VALID")
    GNSS2_TIME_OF_WEEK_VALID = _get("GPX_HDW_STATUS_GNSS2_TIME_OF_WEEK_VALID")
    FAULT_GNSS1_INIT = _get("GPX_HDW_STATUS_FAULT_GNSS1_INIT")
    FAULT_GNSS2_INIT = _get("GPX_HDW_STATUS_FAULT_GNSS2_INIT")
    GNSS_FW_UPDATE_REQUIRED = _get("GPX_HDW_STATUS_GNSS_FW_UPDATE_REQUIRED")
    LED_ENABLED = _get("GPX_HDW_STATUS_LED_ENABLED")
    SYSTEM_RESET_REQUIRED = _get("GPX_HDW_STATUS_SYSTEM_RESET_REQUIRED")
    FLASH_WRITE_PENDING = _get("GPX_HDW_STATUS_FLASH_WRITE_PENDING")
    ERR_COM_TX_LIMITED = _get("GPX_HDW_STATUS_ERR_COM_TX_LIMITED")
    ERR_COM_RX_OVERRUN = _get("GPX_HDW_STATUS_ERR_COM_RX_OVERRUN")
    ERR_NO_GPS1_PPS = _get("GPX_HDW_STATUS_ERR_NO_GPS1_PPS")
    ERR_NO_GPS2_PPS = _get("GPX_HDW_STATUS_ERR_NO_GPS2_PPS")
    ERR_LOW_CNO_GPS1 = _get("GPX_HDW_STATUS_ERR_LOW_CNO_GPS1")
    ERR_LOW_CNO_GPS2 = _get("GPX_HDW_STATUS_ERR_LOW_CNO_GPS2")
    ERR_CNO_GPS1_IRREGULAR = _get("GPX_HDW_STATUS_ERR_CNO_GPS1_IR")
    ERR_CNO_GPS2_IRREGULAR = _get("GPX_HDW_STATUS_ERR_CNO_GPS2_IR")
    ERR_TEMPERATURE = _get("GPX_HDW_STATUS_ERR_TEMPERATURE")
    GPS_PPS_TIMESYNC = _get("GPX_HDW_STATUS_GPS_PPS_TIMESYNC")
    FAULT_SYS_CRITICAL = _get("GPX_HDW_STATUS_FAULT_SYS_CRITICAL")


@dataclass
class GpsHardwareStatus:
    """Structured representation of a decoded GPS hardware status value."""

    raw_value: int
    receiver_state: Dict[str, bool] = field(default_factory=dict)
    reset_counts: Dict[str, int] = field(default_factory=dict)
    pps_and_timing: Dict[str, bool] = field(default_factory=dict)
    signal_quality: Dict[str, bool] = field(default_factory=dict)
    system_and_maintenance: Dict[str, object] = field(default_factory=dict)
    communications: Dict[str, bool] = field(default_factory=dict)
    faults_and_warnings: Dict[str, bool] = field(default_factory=dict)

    @property
    def overall_status_hex(self) -> str:
        return f"0x{self.raw_value:08X}"

    def to_dict(self) -> Dict[str, object]:
        return {
            "raw_value": self.raw_value,
            "overall_status_hex": self.overall_status_hex,
            "sections": {
                "GNSS Receiver State": self.receiver_state,
                "GNSS Reset Counts": self.reset_counts,
                "PPS & Timing": self.pps_and_timing,
                "Signal Quality": self.signal_quality,
                "System & Maintenance": self.system_and_maintenance,
                "Communications": self.communications,
                "Faults & Warnings": self.faults_and_warnings,
            },
        }

    def __str__(self) -> str:
        lines = [f"GPS Hardware Status: {self.overall_status_hex}"]
        for section, values in self.to_dict()["sections"].items():
            lines.append(section)
            lines.extend(_format_section_lines(values))
        return "\n".join(lines)


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


def decode_gps_hdw_status(status: Union[int, str]) -> GpsHardwareStatus:
    """Decode a 32-bit GPS hardware status value into a structured object."""
    if isinstance(status, str):
        status = int(status, 0)

    receiver_state = {
        "GNSS1 satellite signals received": is_set(status, GpsHdwStatusFlags.GNSS1_SATELLITE_RX),
        "GNSS2 satellite signals received": is_set(status, GpsHdwStatusFlags.GNSS2_SATELLITE_RX),
        "GNSS1 time-of-week valid": is_set(status, GpsHdwStatusFlags.GNSS1_TIME_OF_WEEK_VALID),
        "GNSS2 time-of-week valid": is_set(status, GpsHdwStatusFlags.GNSS2_TIME_OF_WEEK_VALID),
        "GNSS1 init fault": is_set(status, GpsHdwStatusFlags.FAULT_GNSS1_INIT),
        "GNSS2 init fault": is_set(status, GpsHdwStatusFlags.FAULT_GNSS2_INIT),
    }

    reset_counts = {
        "GNSS1 reset count": get_reset_count(status, GNSS1_RESET_COUNT_MASK, GNSS1_RESET_COUNT_OFFSET),
        "GNSS2 reset count": get_reset_count(status, GNSS2_RESET_COUNT_MASK, GNSS2_RESET_COUNT_OFFSET),
    }

    pps_and_timing = {
        "GPS PPS time-synchronized": is_set(status, GpsHdwStatusFlags.GPS_PPS_TIMESYNC),
        "No GPS1 PPS signal": is_set(status, GpsHdwStatusFlags.ERR_NO_GPS1_PPS),
        "No GPS2 PPS signal": is_set(status, GpsHdwStatusFlags.ERR_NO_GPS2_PPS),
        "Any PPS-related error": bool(status & GPS_HDW_STATUS_ERR_PPS_MASK),
    }

    signal_quality = {
        "GPS1 low C/N0": is_set(status, GpsHdwStatusFlags.ERR_LOW_CNO_GPS1),
        "GPS2 low C/N0": is_set(status, GpsHdwStatusFlags.ERR_LOW_CNO_GPS2),
        "GPS1 irregular C/N0": is_set(status, GpsHdwStatusFlags.ERR_CNO_GPS1_IRREGULAR),
        "GPS2 irregular C/N0": is_set(status, GpsHdwStatusFlags.ERR_CNO_GPS2_IRREGULAR),
        "Any C/N0-related error": bool(status & GPS_HDW_STATUS_ERR_CNO_MASK),
    }

    system_and_maintenance = {
        "Firmware update required": is_set(status, GpsHdwStatusFlags.GNSS_FW_UPDATE_REQUIRED),
        "LED enabled (Manufacturing test)": is_set(status, GpsHdwStatusFlags.LED_ENABLED),
        "System reset required": is_set(status, GpsHdwStatusFlags.SYSTEM_RESET_REQUIRED),
        "Flash write pending": is_set(status, GpsHdwStatusFlags.FLASH_WRITE_PENDING),
        "Built-in Test (BIT) status": get_bit_status(status),
        "Cause of last reset": get_reset_cause(status),
    }

    communications = {
        "Communications Tx buffer limited": is_set(status, GpsHdwStatusFlags.ERR_COM_TX_LIMITED),
        "Communications Rx overrun": is_set(status, GpsHdwStatusFlags.ERR_COM_RX_OVERRUN),
    }

    faults_and_warnings = {
        "Critical system fault (CPU)": is_set(status, GpsHdwStatusFlags.FAULT_SYS_CRITICAL),
        "Temperature out of spec": is_set(status, GpsHdwStatusFlags.ERR_TEMPERATURE),
    }

    gpx_hdw_status = GpsHardwareStatus(
        raw_value=status,
        receiver_state=receiver_state,
        reset_counts=reset_counts,
        pps_and_timing=pps_and_timing,
        signal_quality=signal_quality,
        system_and_maintenance=system_and_maintenance,
        communications=communications,
        faults_and_warnings=faults_and_warnings,
    )

    LOG(f"Decoded GPS hardware status: {gpx_hdw_status}", highlight=True)
    return gpx_hdw_status


def _format_section_lines(values: Dict[str, object], indent: int = 4) -> List[str]:
    """Format a mapping of values into indented strings."""
    prefix = " " * indent
    return [f"{prefix}{label}: {value}" for label, value in values.items()]


def print_decoded_status(decoded_status: Union[GpsHardwareStatus, int, str]) -> None:
    """Print a human readable summary of the GPS hardware status."""
    status_obj = decoded_status if isinstance(decoded_status, GpsHardwareStatus) else decode_gps_hdw_status(decoded_status)
    print(str(status_obj))
