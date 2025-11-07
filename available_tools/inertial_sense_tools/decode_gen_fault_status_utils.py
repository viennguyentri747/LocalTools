"""Utility helpers for decoding general fault status messages from Inertial Sense devices."""

from enum import IntFlag
from typing import Dict, Iterable, List, Union


class GeneralFaultCode(IntFlag):
    """Bit flags that compose the general fault status field."""

    INS_STATE_ORUN_UVW = 0x00000001
    INS_STATE_ORUN_LAT = 0x00000002
    INS_STATE_ORUN_ALT = 0x00000004
    UNHANDLED_INTERRUPT = 0x00000010
    GNSS_CRITICAL_FAULT = 0x00000020
    GNSS_TX_LIMITED = 0x00000040
    GNSS_RX_OVERRUN = 0x00000080
    INIT_SENSORS = 0x00000100
    INIT_SPI = 0x00000200
    CONFIG_SPI = 0x00000400
    GNSS1_INIT = 0x00000800
    GNSS2_INIT = 0x00001000
    FLASH_INVALID_VALUES = 0x00002000
    FLASH_CHECKSUM_FAILURE = 0x00004000
    FLASH_WRITE_FAILURE = 0x00008000
    SYS_FAULT_GENERAL = 0x00010000
    SYS_FAULT_CRITICAL = 0x00020000
    SENSOR_SATURATION = 0x00040000
    INIT_IMU = 0x00100000
    INIT_BAROMETER = 0x00200000
    INIT_MAGNETOMETER = 0x00400000
    INIT_I2C = 0x00800000
    CHIP_ERASE_INVALID = 0x01000000
    EKF_GNSS_TIME_FAULT = 0x02000000
    GNSS_RECEIVER_TIME = 0x04000000
    GNSS_GENERAL_FAULT = 0x08000000


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
