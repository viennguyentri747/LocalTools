"""Utility helpers for decoding general fault status messages from Inertial Sense devices."""

from enum import IntFlag
from typing import Dict, Iterable, List, Union

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


def decode_gen_fault_status(status: Union[int, str]) -> Dict[str, object]:
    """Decode a general fault status integer into structured details."""
    if isinstance(status, str):
        status = int(status, 0)

    active_flags: List[Dict[str, object]] = list(_iter_active_flags(status))
    unknown_bits = status & ~ALL_KNOWN_FLAGS_MASK

    return {
        "Overall Status Value (Hex)": f"0x{status:08X}",
        "Active Flags": active_flags,
        "Unknown Bits": None if not unknown_bits else f"0x{unknown_bits:08X}",
    }


def _iter_active_flags(status: int) -> Iterable[Dict[str, object]]:
    """Yield decoded flags that are active in the provided status value."""
    for flag in GeneralFaultCode:
        if status & flag.value:
            yield {
                "flag": flag,
                "label": f"{flag.name} (0x{flag.value:08X})",
                "description": FLAG_DESCRIPTIONS.get(flag, flag.name.replace("_", " ").title()),
                "is_gpx_related": bool(flag & GPX_STATUS_RELATED_FLAGS),
            }


def print_decoded_status(decoded_status: Dict[str, object]) -> None:
    """Print a human readable summary of the general fault status."""
    status_hex = decoded_status["Overall Status Value (Hex)"]
    active_flags: List[Dict[str, object]] = decoded_status["Active Flags"]
    unknown_bits = decoded_status["Unknown Bits"]

    print(f"General Fault Status: {status_hex}")
    print("=" * 60)
    print("Active Flags:")
    if not active_flags:
        print("  None")
    else:
        for item in active_flags:
            label = item["label"]
            if item["is_gpx_related"]:
                label = f"{label} [GPX-related]"
            print(f"  - {label}")
            print(f"      {item['description']}")

    if unknown_bits:
        print("\nUnknown Bits:")
        print(f"  {unknown_bits}")
