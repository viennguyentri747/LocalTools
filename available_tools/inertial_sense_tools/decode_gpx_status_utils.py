"""Utility helpers for decoding GPX status messages from Inertial Sense devices."""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Union

from dev.dev_common.core_independent_utils import ELogType, LOG
from dev.dev_common.math_utils import INT_FORMAT_HEX, parse_integer_value
from dev.dev_iesa.iesa_repo_utils import get_enum_declaration_from_path, get_path_to_inertial_sense_data_set_header

ENUM_GPX_STATUS_NAME = "eGpxStatus"
_HEADER_PATH = get_path_to_inertial_sense_data_set_header()
_GPX_STATUS_VALUES = get_enum_declaration_from_path(ENUM_GPX_STATUS_NAME, _HEADER_PATH)


def _get(name: str) -> int:
    try:
        return _GPX_STATUS_VALUES[name]
    except KeyError as exc:
        raise KeyError(f"Missing {name} in {ENUM_GPX_STATUS_NAME}") from exc


GPX_STATUS_COM_PARSE_ERR_COUNT_MASK = _get("GPX_STATUS_COM_PARSE_ERR_COUNT_MASK")
GPX_STATUS_COM_PARSE_ERR_COUNT_OFFSET = _get("GPX_STATUS_COM_PARSE_ERR_COUNT_OFFSET")
GPX_STATUS_GENERAL_FAULT_MASK = _get("GPX_STATUS_GENERAL_FAULT_MASK")
GPX_STATUS_FATAL_MASK = _get("GPX_STATUS_FATAL_MASK")
GPX_STATUS_FATAL_OFFSET = _get("GPX_STATUS_FATAL_OFFSET")
GPX_STATUS_FAULT_UNUSED = _get("GPX_STATUS_FAULT_UNUSED")

_FLAG_NAMES = [
    "GPX_STATUS_COM0_RX_TRAFFIC_NOT_DECTECTED",
    "GPX_STATUS_COM1_RX_TRAFFIC_NOT_DECTECTED",
    "GPX_STATUS_COM2_RX_TRAFFIC_NOT_DECTECTED",
    "GPX_STATUS_USB_RX_TRAFFIC_NOT_DECTECTED",
    "GPX_STATUS_FAULT_RTK_QUEUE_LIMITED",
    "GPX_STATUS_FAULT_GNSS_RCVR_TIME",
    "GPX_STATUS_FAULT_DMA",
    "GPX_STATUS_FAULT_RP",
]

GPX_FLAG_VALUES: Dict[str, int] = {name: _get(name) for name in _FLAG_NAMES}


class GpxFatalCode(IntEnum):
    RESET_LOW_POW = _get("GPX_STATUS_FATAL_RESET_LOW_POW")
    RESET_BROWN = _get("GPX_STATUS_FATAL_RESET_BROWN")
    RESET_WATCHDOG = _get("GPX_STATUS_FATAL_RESET_WATCHDOG")
    CPU_EXCEPTION = _get("GPX_STATUS_FATAL_CPU_EXCEPTION")
    UNHANDLED_INTERRUPT = _get("GPX_STATUS_FATAL_UNHANDLED_INTERRUPT")
    STACK_OVERFLOW = _get("GPX_STATUS_FATAL_STACK_OVERFLOW")
    KERNEL_OOPS = _get("GPX_STATUS_FATAL_KERNEL_OOPS")
    KERNEL_PANIC = _get("GPX_STATUS_FATAL_KERNEL_PANIC")
    UNALIGNED_ACCESS = _get("GPX_STATUS_FATAL_UNALIGNED_ACCESS")
    MEMORY_ERROR = _get("GPX_STATUS_FATAL_MEMORY_ERROR")
    BUS_ERROR = _get("GPX_STATUS_FATAL_BUS_ERROR")
    USAGE_ERROR = _get("GPX_STATUS_FATAL_USAGE_ERROR")
    DIV_ZERO = _get("GPX_STATUS_FATAL_DIV_ZERO")
    SER0_REINIT = _get("GPX_STATUS_FATAL_SER0_REINIT")
    UNKNOWN = _get("GPX_STATUS_FATAL_UNKNOWN")


_FATAL_DESCRIPTIONS: Dict[int, str] = {
    GpxFatalCode.RESET_LOW_POW: "Reset from low power",
    GpxFatalCode.RESET_BROWN: "Reset from brown out",
    GpxFatalCode.RESET_WATCHDOG: "Reset from watchdog",
    GpxFatalCode.CPU_EXCEPTION: "CPU exception",
    GpxFatalCode.UNHANDLED_INTERRUPT: "Unhandled interrupt",
    GpxFatalCode.STACK_OVERFLOW: "Stack overflow",
    GpxFatalCode.KERNEL_OOPS: "Kernel oops",
    GpxFatalCode.KERNEL_PANIC: "Kernel panic",
    GpxFatalCode.UNALIGNED_ACCESS: "Unaligned access",
    GpxFatalCode.MEMORY_ERROR: "Memory error",
    GpxFatalCode.BUS_ERROR: "Bus error (bad pointer/malloc)",
    GpxFatalCode.USAGE_ERROR: "Usage error",
    GpxFatalCode.DIV_ZERO: "Division by zero",
    GpxFatalCode.SER0_REINIT: "Serial0 reinit",
    GpxFatalCode.UNKNOWN: "Unknown fatal",
}

LOG(f"[IESA] Parsed enum {ENUM_GPX_STATUS_NAME}", log_type=ELogType.DEBUG)
LOG(
    f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _GPX_STATUS_VALUES.items()} }",
    log_type=ELogType.DEBUG,
)


@dataclass
class GpxStatus:
    raw_value: int
    communication: Dict[str, Union[int, bool]] = field(default_factory=dict)
    faults: Dict[str, Union[str, bool, int]] = field(default_factory=dict)
    active_flags: List[str] = field(default_factory=list)
    unknown_bits: int = 0

    @property
    def overall_status_hex(self) -> str:
        return f"0x{self.raw_value:08X}"

    def __str__(self) -> str:
        lines = [f"GPX Status: {self.overall_status_hex}", "Communication"]
        lines.extend(_format_section_lines(self.communication))
        lines.append("Faults")
        lines.extend(_format_section_lines(self.faults))
        lines.append("Active Flags")
        lines.extend([f"    {name}" for name in self.active_flags] if self.active_flags else ["    None"])
        lines.append(f"Unknown Bits: 0x{self.unknown_bits:08X}")
        return "\n".join(lines)


def _format_section_lines(values: Dict[str, object], indent: int = 4) -> List[str]:
    prefix = " " * indent
    return [f"{prefix}{label}: {value}" for label, value in values.items()]


def _is_set(value: int, flag: int) -> bool:
    return (value & flag) != 0


def _fatal_description(fatal_code: int) -> str:
    return _FATAL_DESCRIPTIONS.get(fatal_code, "N/A")


def decode_gpx_status(status: Union[int, str], status_format: str = INT_FORMAT_HEX) -> GpxStatus:
    status = parse_integer_value(status, parse_format=status_format, value_name="GPX status")

    parse_err_count = (status & GPX_STATUS_COM_PARSE_ERR_COUNT_MASK) >> GPX_STATUS_COM_PARSE_ERR_COUNT_OFFSET
    fatal_code = (status & GPX_STATUS_FATAL_MASK) >> GPX_STATUS_FATAL_OFFSET
    active_flags = [name for name, value in GPX_FLAG_VALUES.items() if _is_set(status, value)]
    known_mask = GPX_STATUS_COM_PARSE_ERR_COUNT_MASK | GPX_STATUS_FATAL_MASK | GPX_STATUS_GENERAL_FAULT_MASK | GPX_STATUS_FAULT_UNUSED
    for value in GPX_FLAG_VALUES.values():
        known_mask |= value
    unknown_bits = status & ~known_mask

    gpx_status = GpxStatus(
        raw_value=status,
        communication={
            "COM Parse Error Count": parse_err_count,
            "COM0 Rx traffic not detected": _is_set(status, _get("GPX_STATUS_COM0_RX_TRAFFIC_NOT_DECTECTED")),
            "COM1 Rx traffic not detected": _is_set(status, _get("GPX_STATUS_COM1_RX_TRAFFIC_NOT_DECTECTED")),
            "COM2 Rx traffic not detected": _is_set(status, _get("GPX_STATUS_COM2_RX_TRAFFIC_NOT_DECTECTED")),
            "USB Rx traffic not detected": _is_set(status, _get("GPX_STATUS_USB_RX_TRAFFIC_NOT_DECTECTED")),
        },
        faults={
            "General Fault Mask Set": bool(status & GPX_STATUS_GENERAL_FAULT_MASK),
            "RTK queue limited": _is_set(status, _get("GPX_STATUS_FAULT_RTK_QUEUE_LIMITED")),
            "GNSS receiver time fault": _is_set(status, _get("GPX_STATUS_FAULT_GNSS_RCVR_TIME")),
            "DMA fault": _is_set(status, _get("GPX_STATUS_FAULT_DMA")),
            "Fatal Code": fatal_code,
            "Fatal Description": _fatal_description(fatal_code),
            "Internal RP fault": _is_set(status, _get("GPX_STATUS_FAULT_RP")),
        },
        active_flags=active_flags,
        unknown_bits=unknown_bits,
    )
    LOG(f"Decoded GPX status: {gpx_status}", highlight=True)
    return gpx_status


def print_decoded_status(decoded_status: Union[GpxStatus, int, str], status_format: str = INT_FORMAT_HEX) -> None:
    status_obj = decoded_status if isinstance(decoded_status, GpxStatus) else decode_gpx_status(decoded_status, status_format=status_format)
    print(str(status_obj))
