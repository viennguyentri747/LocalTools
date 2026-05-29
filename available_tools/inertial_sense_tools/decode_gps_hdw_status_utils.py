"""Utility helpers for decoding GPS hardware status messages from Inertial Sense devices."""

from dataclasses import dataclass
from enum import Flag, IntEnum
from typing import Dict, List, Union

from available_tools.inertial_sense_tools.common import IS_DATASET_ENUM_REPLACEMENTS
from dev.dev_common.core_independent_utils import ELogType, LOG
from dev.dev_common.math_utils import INT_FORMAT_HEX, parse_integer_value
from dev.dev_iesa.iesa_repo_utils import get_enum_declaration_from_path, get_path_to_inertial_sense_data_set_header

ENUM_EGPX_HDW_STATUS_FLAGS_NAME = "eGPXHdwStatusFlags"

_HEADER_PATH = get_path_to_inertial_sense_data_set_header()
_GPX_HDW_VALUES = get_enum_declaration_from_path(ENUM_EGPX_HDW_STATUS_FLAGS_NAME, _HEADER_PATH, enum_replacements=IS_DATASET_ENUM_REPLACEMENTS)


def _get(name: str) -> int:
    try:
        return _GPX_HDW_VALUES[name]
    except KeyError as exc:
        raise KeyError(f"Missing {name} in {ENUM_EGPX_HDW_STATUS_FLAGS_NAME}") from exc


GNSS1_RESET_COUNT_MASK: int = _get("GPX_HDW_STATUS_GNSS1_RESET_COUNT_MASK")
GNSS1_RESET_COUNT_OFFSET: int = _get("GPX_HDW_STATUS_GNSS1_RESET_COUNT_OFFSET")
GNSS2_RESET_COUNT_MASK: int = _get("GPX_HDW_STATUS_GNSS2_RESET_COUNT_MASK")
GNSS2_RESET_COUNT_OFFSET: int = _get("GPX_HDW_STATUS_GNSS2_RESET_COUNT_OFFSET")
GPS_HDW_STATUS_BIT_MASK: int = _get("GPX_HDW_STATUS_BIT_MASK")
GPS_HDW_STATUS_BIT_RUNNING: int = _get("GPX_HDW_STATUS_BIT_RUNNING")
GPS_HDW_STATUS_BIT_PASSED: int = _get("GPX_HDW_STATUS_BIT_PASSED")
GPS_HDW_STATUS_BIT_FAILED: int = _get("GPX_HDW_STATUS_BIT_FAULT")
GPS_HDW_STATUS_RESET_CAUSE_MASK: int = _get("GPX_HDW_STATUS_RESET_CAUSE_MASK")
GPS_HDW_STATUS_RESET_CAUSE_BACKUP_MODE: int = _get("GPX_HDW_STATUS_RESET_CAUSE_BACKUP_MODE")
GPS_HDW_STATUS_RESET_CAUSE_SOFT: int = _get("GPX_HDW_STATUS_RESET_CAUSE_SOFT")
GPS_HDW_STATUS_RESET_CAUSE_HDW: int = _get("GPX_HDW_STATUS_RESET_CAUSE_HDW")
GPS_HDW_STATUS_ERR_PPS_MASK: int = _get("GPX_HDW_STATUS_ERR_PPS_MASK")
GPS_HDW_STATUS_ERR_CNO_MASK: int = _get("GPX_HDW_STATUS_ERR_CNO_MASK")

LOG(f"[IESA] Parsed enum {ENUM_EGPX_HDW_STATUS_FLAGS_NAME}", log_type=ELogType.DEBUG)
LOG(f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _GPX_HDW_VALUES.items()} }", log_type=ELogType.DEBUG)


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


class GpsHdwBitStatus(IntEnum):
    NOT_RUN = 0
    RUNNING = GPS_HDW_STATUS_BIT_RUNNING
    PASSED = GPS_HDW_STATUS_BIT_PASSED
    FAILED = GPS_HDW_STATUS_BIT_FAILED


class GpsHdwResetCause(IntEnum):
    NOT_AVAILABLE = 0
    BACKUP_MODE = GPS_HDW_STATUS_RESET_CAUSE_BACKUP_MODE
    SOFTWARE = GPS_HDW_STATUS_RESET_CAUSE_SOFT
    HARDWARE = GPS_HDW_STATUS_RESET_CAUSE_HDW


_BIT_STATUS_LABEL = {
    GpsHdwBitStatus.NOT_RUN: "Not Run / N/A",
    GpsHdwBitStatus.RUNNING: "Running",
    GpsHdwBitStatus.PASSED: "Passed",
    GpsHdwBitStatus.FAILED: "Failed",
}
_RESET_CAUSE_LABEL = {
    GpsHdwResetCause.NOT_AVAILABLE: "N/A",
    GpsHdwResetCause.BACKUP_MODE: "Backup Mode (Low-power state)",
    GpsHdwResetCause.SOFTWARE: "Software",
    GpsHdwResetCause.HARDWARE: "Hardware (NRST pin)",
}


@dataclass(frozen=True)
class GpsReceiverState:
    gnss1_satellite_rx: bool
    gnss2_satellite_rx: bool
    gnss1_time_of_week_valid: bool
    gnss2_time_of_week_valid: bool
    fault_gnss1_init: bool
    fault_gnss2_init: bool


@dataclass(frozen=True)
class GpsResetCounts:
    gnss1_reset_count: int
    gnss2_reset_count: int


@dataclass(frozen=True)
class GpsPpsAndTiming:
    gps_pps_timesync: bool
    no_gps1_pps_signal: bool
    no_gps2_pps_signal: bool
    any_pps_related_error: bool


@dataclass(frozen=True)
class GpsSignalQuality:
    gps1_low_cno: bool
    gps2_low_cno: bool
    gps1_irregular_cno: bool
    gps2_irregular_cno: bool
    any_cno_related_error: bool


@dataclass(frozen=True)
class GpsSystemAndMaintenance:
    firmware_update_required: bool
    led_enabled: bool
    system_reset_required: bool
    flash_write_pending: bool
    bit_status: GpsHdwBitStatus
    reset_cause: GpsHdwResetCause


@dataclass(frozen=True)
class GpsCommunications:
    tx_buffer_limited: bool
    rx_overrun: bool


@dataclass(frozen=True)
class GpsFaultsAndWarnings:
    critical_system_fault: bool
    temperature_out_of_spec: bool


@dataclass(frozen=True)
class GpsHardwareStatus:
    """Structured representation of a decoded GPS hardware status value."""

    raw_value: int
    receiver_state: GpsReceiverState
    reset_counts: GpsResetCounts
    pps_and_timing: GpsPpsAndTiming
    signal_quality: GpsSignalQuality
    system_and_maintenance: GpsSystemAndMaintenance
    communications: GpsCommunications
    faults_and_warnings: GpsFaultsAndWarnings

    @property
    def overall_status_hex(self) -> str:
        return f"0x{self.raw_value:08X}"

    def to_dict(self) -> Dict[str, object]:
        return {
            "raw_value": self.raw_value,
            "overall_status_hex": self.overall_status_hex,
            "sections": {
                "GNSS Receiver State": {
                    "GNSS1 satellite signals received": self.receiver_state.gnss1_satellite_rx,
                    "GNSS2 satellite signals received": self.receiver_state.gnss2_satellite_rx,
                    "GNSS1 time-of-week valid": self.receiver_state.gnss1_time_of_week_valid,
                    "GNSS2 time-of-week valid": self.receiver_state.gnss2_time_of_week_valid,
                    "GNSS1 init fault": self.receiver_state.fault_gnss1_init,
                    "GNSS2 init fault": self.receiver_state.fault_gnss2_init,
                },
                "GNSS Reset Counts": {
                    "GNSS1 reset count": self.reset_counts.gnss1_reset_count,
                    "GNSS2 reset count": self.reset_counts.gnss2_reset_count,
                },
                "PPS & Timing": {
                    "GPS PPS time-synchronized": self.pps_and_timing.gps_pps_timesync,
                    "No GPS1 PPS signal": self.pps_and_timing.no_gps1_pps_signal,
                    "No GPS2 PPS signal": self.pps_and_timing.no_gps2_pps_signal,
                    "Any PPS-related error": self.pps_and_timing.any_pps_related_error,
                },
                "Signal Quality": {
                    "GPS1 low C/N0": self.signal_quality.gps1_low_cno,
                    "GPS2 low C/N0": self.signal_quality.gps2_low_cno,
                    "GPS1 irregular C/N0": self.signal_quality.gps1_irregular_cno,
                    "GPS2 irregular C/N0": self.signal_quality.gps2_irregular_cno,
                    "Any C/N0-related error": self.signal_quality.any_cno_related_error,
                },
                "System & Maintenance": {
                    "Firmware update required": self.system_and_maintenance.firmware_update_required,
                    "LED enabled (Manufacturing test)": self.system_and_maintenance.led_enabled,
                    "System reset required": self.system_and_maintenance.system_reset_required,
                    "Flash write pending": self.system_and_maintenance.flash_write_pending,
                    "Built-in Test (BIT) status": _BIT_STATUS_LABEL[self.system_and_maintenance.bit_status],
                    "Cause of last reset": _RESET_CAUSE_LABEL[self.system_and_maintenance.reset_cause],
                },
                "Communications": {
                    "Communications Tx buffer limited": self.communications.tx_buffer_limited,
                    "Communications Rx overrun": self.communications.rx_overrun,
                },
                "Faults & Warnings": {
                    "Critical system fault (CPU)": self.faults_and_warnings.critical_system_fault,
                    "Temperature out of spec": self.faults_and_warnings.temperature_out_of_spec,
                },
            },
        }

    def __str__(self) -> str:
        lines = [f"GPS Hardware Status: {self.overall_status_hex}"]
        for section, values in self.to_dict()["sections"].items():
            lines.append(section)
            lines.extend(_format_section_lines(values))
        return "\n".join(lines)


def get_bit_status(status: int) -> GpsHdwBitStatus:
    """Decode the Built-in Test (BIT) status field."""
    bit_field = status & GPS_HDW_STATUS_BIT_MASK
    try:
        return GpsHdwBitStatus(bit_field)
    except ValueError:
        return GpsHdwBitStatus.NOT_RUN


def get_reset_cause(status: int) -> GpsHdwResetCause:
    """Decode the cause of the last system reset."""
    reset_field = status & GPS_HDW_STATUS_RESET_CAUSE_MASK
    try:
        return GpsHdwResetCause(reset_field)
    except ValueError:
        return GpsHdwResetCause.NOT_AVAILABLE


def get_reset_count(status: int, mask: int, offset: int) -> int:
    """Extract a reset count value from the status field."""
    return (status & mask) >> offset


def is_set(status: int, flag: GpsHdwStatusFlags) -> bool:
    """Return True when the provided flag is set."""
    return (status & flag.value) != 0


def decode_gps_hdw_status(status: Union[int, str], status_format: str = INT_FORMAT_HEX) -> GpsHardwareStatus:
    """Decode a 32-bit GPS hardware status value into a structured object."""
    status = parse_integer_value(status, parse_format=status_format, value_name="GPS hardware status")

    gps_hdw_status = GpsHardwareStatus(
        raw_value=status,
        receiver_state=GpsReceiverState(
            gnss1_satellite_rx=is_set(status, GpsHdwStatusFlags.GNSS1_SATELLITE_RX),
            gnss2_satellite_rx=is_set(status, GpsHdwStatusFlags.GNSS2_SATELLITE_RX),
            gnss1_time_of_week_valid=is_set(status, GpsHdwStatusFlags.GNSS1_TIME_OF_WEEK_VALID),
            gnss2_time_of_week_valid=is_set(status, GpsHdwStatusFlags.GNSS2_TIME_OF_WEEK_VALID),
            fault_gnss1_init=is_set(status, GpsHdwStatusFlags.FAULT_GNSS1_INIT),
            fault_gnss2_init=is_set(status, GpsHdwStatusFlags.FAULT_GNSS2_INIT),
        ),
        reset_counts=GpsResetCounts(
            gnss1_reset_count=get_reset_count(status, GNSS1_RESET_COUNT_MASK, GNSS1_RESET_COUNT_OFFSET),
            gnss2_reset_count=get_reset_count(status, GNSS2_RESET_COUNT_MASK, GNSS2_RESET_COUNT_OFFSET),
        ),
        pps_and_timing=GpsPpsAndTiming(
            gps_pps_timesync=is_set(status, GpsHdwStatusFlags.GPS_PPS_TIMESYNC),
            no_gps1_pps_signal=is_set(status, GpsHdwStatusFlags.ERR_NO_GPS1_PPS),
            no_gps2_pps_signal=is_set(status, GpsHdwStatusFlags.ERR_NO_GPS2_PPS),
            any_pps_related_error=bool(status & GPS_HDW_STATUS_ERR_PPS_MASK),
        ),
        signal_quality=GpsSignalQuality(
            gps1_low_cno=is_set(status, GpsHdwStatusFlags.ERR_LOW_CNO_GPS1),
            gps2_low_cno=is_set(status, GpsHdwStatusFlags.ERR_LOW_CNO_GPS2),
            gps1_irregular_cno=is_set(status, GpsHdwStatusFlags.ERR_CNO_GPS1_IRREGULAR),
            gps2_irregular_cno=is_set(status, GpsHdwStatusFlags.ERR_CNO_GPS2_IRREGULAR),
            any_cno_related_error=bool(status & GPS_HDW_STATUS_ERR_CNO_MASK),
        ),
        system_and_maintenance=GpsSystemAndMaintenance(
            firmware_update_required=is_set(status, GpsHdwStatusFlags.GNSS_FW_UPDATE_REQUIRED),
            led_enabled=is_set(status, GpsHdwStatusFlags.LED_ENABLED),
            system_reset_required=is_set(status, GpsHdwStatusFlags.SYSTEM_RESET_REQUIRED),
            flash_write_pending=is_set(status, GpsHdwStatusFlags.FLASH_WRITE_PENDING),
            bit_status=get_bit_status(status),
            reset_cause=get_reset_cause(status),
        ),
        communications=GpsCommunications(
            tx_buffer_limited=is_set(status, GpsHdwStatusFlags.ERR_COM_TX_LIMITED),
            rx_overrun=is_set(status, GpsHdwStatusFlags.ERR_COM_RX_OVERRUN),
        ),
        faults_and_warnings=GpsFaultsAndWarnings(
            critical_system_fault=is_set(status, GpsHdwStatusFlags.FAULT_SYS_CRITICAL),
            temperature_out_of_spec=is_set(status, GpsHdwStatusFlags.ERR_TEMPERATURE),
        ),
    )

    LOG(f"Decoded GPS hardware status: {gps_hdw_status}", highlight=True)
    return gps_hdw_status


def _format_section_lines(values: Dict[str, object], indent: int = 4) -> List[str]:
    """Format a mapping of values into indented strings."""
    prefix = " " * indent
    return [f"{prefix}{label}: {value}" for label, value in values.items()]


def print_decoded_status(decoded_status: Union[GpsHardwareStatus, int, str], status_format: str = INT_FORMAT_HEX) -> None:
    """Print a human readable summary of the GPS hardware status."""
    status_obj = decoded_status if isinstance(decoded_status, GpsHardwareStatus) else decode_gps_hdw_status(decoded_status, status_format=status_format)
    print(str(status_obj))
