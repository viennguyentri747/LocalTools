"""Utility helpers for decoding general fault status messages from Inertial Sense devices."""

from dataclasses import dataclass, field
from enum import IntFlag
from typing import Dict, Iterable, List, Optional, Union

from dev.dev_common.core_independent_utils import LOG
from dev.dev_iesa.iesa_repo_utils import (
    get_enum_declaration_from_path,
    get_path_to_inertial_sense_data_set_header,
)

ENUM_GEN_FAULT_CODES = "eGenFaultCodes"

_HEADER_PATH = get_path_to_inertial_sense_data_set_header()
_GEN_FAULT_VALUES = get_enum_declaration_from_path(ENUM_GEN_FAULT_CODES, _HEADER_PATH)


def _get(name: str) -> int:
    try:
        return _GEN_FAULT_VALUES[name]
    except KeyError as exc:
        raise KeyError(f"Missing {name} in {ENUM_GEN_FAULT_CODES}") from exc


class GeneralFaultCode(IntFlag):
    """Bit flags that compose the general fault status field."""

    INS_STATE_ORUN_UVW = _get("GFC_INS_STATE_ORUN_UVW")
    INS_STATE_ORUN_LAT = _get("GFC_INS_STATE_ORUN_LAT")
    INS_STATE_ORUN_ALT = _get("GFC_INS_STATE_ORUN_ALT")
    UNHANDLED_INTERRUPT = _get("GFC_UNHANDLED_INTERRUPT")
    GNSS_CRITICAL_FAULT = _get("GFC_GNSS_CRITICAL_FAULT")
    GNSS_TX_LIMITED = _get("GFC_GNSS_TX_LIMITED")
    GNSS_RX_OVERRUN = _get("GFC_GNSS_RX_OVERRUN")
    INIT_SENSORS = _get("GFC_INIT_SENSORS")
    INIT_SPI = _get("GFC_INIT_SPI")
    CONFIG_SPI = _get("GFC_CONFIG_SPI")
    GNSS1_INIT = _get("GFC_GNSS1_INIT")
    GNSS2_INIT = _get("GFC_GNSS2_INIT")
    FLASH_INVALID_VALUES = _get("GFC_FLASH_INVALID_VALUES")
    FLASH_CHECKSUM_FAILURE = _get("GFC_FLASH_CHECKSUM_FAILURE")
    FLASH_WRITE_FAILURE = _get("GFC_FLASH_WRITE_FAILURE")
    SYS_FAULT_GENERAL = _get("GFC_SYS_FAULT_GENERAL")
    SYS_FAULT_CRITICAL = _get("GFC_SYS_FAULT_CRITICAL")
    SENSOR_SATURATION = _get("GFC_SENSOR_SATURATION")
    INIT_IMU = _get("GFC_INIT_IMU")
    INIT_BAROMETER = _get("GFC_INIT_BAROMETER")
    INIT_MAGNETOMETER = _get("GFC_INIT_MAGNETOMETER")
    INIT_I2C = _get("GFC_INIT_I2C")
    CHIP_ERASE_INVALID = _get("GFC_CHIP_ERASE_INVALID")
    EKF_GNSS_TIME_FAULT = _get("GFC_EKF_GNSS_TIME_FAULT")
    GNSS_RECEIVER_TIME = _get("GFC_GNSS_RECEIVER_TIME")
    GNSS_GENERAL_FAULT = _get("GFC_GNSS_GENERAL_FAULT")


LOG(
    f"[IESA] Parsed {ENUM_GEN_FAULT_CODES}: "
    f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _GEN_FAULT_VALUES.items()} }"
)


FLAG_DESCRIPTIONS: Dict[GeneralFaultCode, str] = {
    GeneralFaultCode.INS_STATE_ORUN_UVW: "INS state limit overrun - body velocity (UVW)",
    GeneralFaultCode.INS_STATE_ORUN_LAT: "INS state limit overrun - latitude",
    GeneralFaultCode.INS_STATE_ORUN_ALT: "INS state limit overrun - altitude",
    GeneralFaultCode.UNHANDLED_INTERRUPT: "Unhandled interrupt",
    GeneralFaultCode.GNSS_CRITICAL_FAULT: "GNSS receiver critical fault (see GPS fatal mask)",
    GeneralFaultCode.GNSS_TX_LIMITED: "GNSS Tx limited",
    GeneralFaultCode.GNSS_RX_OVERRUN: "GNSS Rx overrun",
    GeneralFaultCode.INIT_SENSORS: "Sensor initialization failure",
    GeneralFaultCode.INIT_SPI: "SPI bus initialization failure",
    GeneralFaultCode.CONFIG_SPI: "SPI configuration failure",
    GeneralFaultCode.GNSS1_INIT: "GNSS1 initialization failure",
    GeneralFaultCode.GNSS2_INIT: "GNSS2 initialization failure",
    GeneralFaultCode.FLASH_INVALID_VALUES: "Flash failed to load valid values",
    GeneralFaultCode.FLASH_CHECKSUM_FAILURE: "Flash checksum failure",
    GeneralFaultCode.FLASH_WRITE_FAILURE: "Flash write failure",
    GeneralFaultCode.SYS_FAULT_GENERAL: "General system fault",
    GeneralFaultCode.SYS_FAULT_CRITICAL: "Critical system fault (see DID_SYS_FAULT)",
    GeneralFaultCode.SENSOR_SATURATION: "Sensor saturation detected",
    GeneralFaultCode.INIT_IMU: "IMU initialization failure",
    GeneralFaultCode.INIT_BAROMETER: "Barometer initialization failure",
    GeneralFaultCode.INIT_MAGNETOMETER: "Magnetometer initialization failure",
    GeneralFaultCode.INIT_I2C: "I2C initialization failure",
    GeneralFaultCode.CHIP_ERASE_INVALID: "Chip erase toggled but hold time not met (noise/transient)",
    GeneralFaultCode.EKF_GNSS_TIME_FAULT: "EKF GNSS time fault",
    GeneralFaultCode.GNSS_RECEIVER_TIME: "GNSS receiver time fault",
    GeneralFaultCode.GNSS_GENERAL_FAULT: "GNSS receiver general fault (see GPS general fault mask)",
}

GPX_STATUS_RELATED_FLAGS = (
    GeneralFaultCode.GNSS1_INIT
    | GeneralFaultCode.GNSS2_INIT
    | GeneralFaultCode.GNSS_TX_LIMITED
    | GeneralFaultCode.GNSS_RX_OVERRUN
    | GeneralFaultCode.GNSS_CRITICAL_FAULT
    | GeneralFaultCode.GNSS_RECEIVER_TIME
    | GeneralFaultCode.GNSS_GENERAL_FAULT
)

ALL_KNOWN_FLAGS_MASK = 0
for _flag in GeneralFaultCode:
    ALL_KNOWN_FLAGS_MASK |= _flag.value


@dataclass
class GeneralFaultFlagInfo:
    """Details for an individual general fault flag."""

    code: GeneralFaultCode
    description: str
    is_gpx_related: bool

    @property
    def label(self) -> str:
        return f"{self.code.name} (0x{self.code.value:08X})"


@dataclass
class GeneralFaultStatus:
    """Structured representation of a general fault status value."""

    raw_value: int
    active_flags: List[GeneralFaultFlagInfo] = field(default_factory=list)
    unknown_bits: Optional[int] = None

    @property
    def overall_status_hex(self) -> str:
        return f"0x{self.raw_value:08X}"

    def to_dict(self) -> Dict[str, object]:
        return {
            "overall_status_hex": self.overall_status_hex,
            "active_flags": [
                {
                    "flag": flag.code,
                    "label": flag.label,
                    "description": flag.description,
                    "is_gpx_related": flag.is_gpx_related,
                }
                for flag in self.active_flags
            ],
            "unknown_bits": None if self.unknown_bits is None else f"0x{self.unknown_bits:08X}",
        }

    def __str__(self) -> str:
        lines = [f"General Fault Status: {self.overall_status_hex}", "=" * 60, "Active Flags:"]
        if not self.active_flags:
            lines.append("  None")
        else:
            for flag in self.active_flags:
                label = flag.label
                if flag.is_gpx_related:
                    label = f"{label} [GPX-related]"
                lines.append(f"  - {label}")
                lines.append(f"      {flag.description}")

        if self.unknown_bits:
            lines.extend(["", "Unknown Bits:", f"  0x{self.unknown_bits:08X}"])

        return "\n".join(lines)


def decode_gen_fault_status(status: Union[int, str]) -> GeneralFaultStatus:
    """Decode a general fault status integer into a structured object."""
    if isinstance(status, str):
        status = int(status, 0)

    active_flags = list(_iter_active_flags(status))
    unknown_bits = status & ~ALL_KNOWN_FLAGS_MASK

    general_fault_status = GeneralFaultStatus(raw_value=status, active_flags=active_flags, unknown_bits=unknown_bits or None)

    LOG(f"Decoded general fault status: {general_fault_status}", highlight=True)
    return general_fault_status


def _iter_active_flags(status: int) -> Iterable[GeneralFaultFlagInfo]:
    """Yield decoded flags that are active in the provided status value."""
    for flag in GeneralFaultCode:
        if status & flag.value:
            yield GeneralFaultFlagInfo(
                code=flag,
                description=FLAG_DESCRIPTIONS.get(flag, flag.name.replace("_", " ").title()),
                is_gpx_related=bool(flag & GPX_STATUS_RELATED_FLAGS),
            )


def print_decoded_status(decoded_status: Union[GeneralFaultStatus, int, str]) -> None:
    """Print a human readable summary of the general fault status."""
    status_obj = decoded_status if isinstance(decoded_status, GeneralFaultStatus) else decode_gen_fault_status(decoded_status)
    print(str(status_obj))
