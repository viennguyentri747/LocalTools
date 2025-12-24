"""Utility helpers for decoding GPS status messages from Inertial Sense devices."""

from dataclasses import dataclass, field
from enum import Flag, IntEnum
from typing import Dict, List, Union

from dev.dev_common.core_independent_utils import LOG
from dev.dev_iesa.iesa_repo_utils import (
    get_enum_declaration_from_path,
    get_path_to_inertial_sense_data_set_header,
)

ENUM_GPS_STATUS_NAME = "eGpsStatus"

_HEADER_PATH = get_path_to_inertial_sense_data_set_header()
_GPS_STATUS_VALUES = get_enum_declaration_from_path(ENUM_GPS_STATUS_NAME, _HEADER_PATH)


def _get(name: str) -> int:
    try:
        return _GPS_STATUS_VALUES[name]
    except KeyError as exc:
        raise KeyError(f"Missing {name} in {ENUM_GPS_STATUS_NAME}") from exc


# --- Constants and Masks ---

GPS_STATUS_FIX_MASK: int = _get("GPS_STATUS_FIX_MASK")
GPS_STATUS_FIX_BIT_OFFSET: int = _get("GPS_STATUS_FIX_BIT_OFFSET")


class GpsFixType(IntEnum):
    """Enumeration of supported GPS fix types."""

    NONE = _get("GPS_STATUS_FIX_NONE")
    DEAD_RECKONING_ONLY = _get("GPS_STATUS_FIX_DEAD_RECKONING_ONLY")
    FIX_2D = _get("GPS_STATUS_FIX_2D")
    FIX_3D = _get("GPS_STATUS_FIX_3D")
    GPS_PLUS_DEAD_RECK = _get("GPS_STATUS_FIX_GPS_PLUS_DEAD_RECK")
    TIME_ONLY = _get("GPS_STATUS_FIX_TIME_ONLY")
    UNUSED1 = _get("GPS_STATUS_FIX_UNUSED1")
    UNUSED2 = _get("GPS_STATUS_FIX_UNUSED2")
    DGPS = _get("GPS_STATUS_FIX_DGPS")
    SBAS = _get("GPS_STATUS_FIX_SBAS")
    RTK_SINGLE = _get("GPS_STATUS_FIX_RTK_SINGLE")
    RTK_FLOAT = _get("GPS_STATUS_FIX_RTK_FLOAT")
    RTK_FIX = _get("GPS_STATUS_FIX_RTK_FIX")


class GpsStatusFlags(Flag):
    """Bit flags associated with the GPS status field."""

    GPS2_RTK_COMPASS_BASELINE_BAD = _get("GPS_STATUS_FLAGS_GPS2_RTK_COMPASS_BASELINE_BAD")
    GPS2_RTK_COMPASS_BASELINE_UNSET = _get("GPS_STATUS_FLAGS_GPS2_RTK_COMPASS_BASELINE_UNSET")
    GPS_NMEA_DATA = _get("GPS_STATUS_FLAGS_GPS_NMEA_DATA")
    FIX_OK = _get("GPS_STATUS_FLAGS_FIX_OK")
    DGPS_USED = _get("GPS_STATUS_FLAGS_DGPS_USED")
    RTK_FIX_AND_HOLD = _get("GPS_STATUS_FLAGS_RTK_FIX_AND_HOLD")
    GPS1_RTK_POSITION_ENABLED = _get("GPS_STATUS_FLAGS_GPS1_RTK_POSITION_ENABLED")
    STATIC_MODE = _get("GPS_STATUS_FLAGS_STATIC_MODE")
    GPS2_RTK_COMPASS_ENABLED = _get("GPS_STATUS_FLAGS_GPS2_RTK_COMPASS_ENABLED")
    GPS1_RTK_RAW_GPS_DATA_ERROR = _get("GPS_STATUS_FLAGS_GPS1_RTK_RAW_GPS_DATA_ERROR")
    GPS1_RTK_BASE_DATA_MISSING = _get("GPS_STATUS_FLAGS_GPS1_RTK_BASE_DATA_MISSING")
    GPS1_RTK_BASE_POSITION_MOVING = _get("GPS_STATUS_FLAGS_GPS1_RTK_BASE_POSITION_MOVING")
    GPS1_RTK_BASE_POSITION_INVALID = _get("GPS_STATUS_FLAGS_GPS1_RTK_BASE_POSITION_INVALID")
    GPS1_RTK_POSITION_VALID = _get("GPS_STATUS_FLAGS_GPS1_RTK_POSITION_VALID")
    GPS2_RTK_COMPASS_VALID = _get("GPS_STATUS_FLAGS_GPS2_RTK_COMPASS_VALID")
    GPS_PPS_TIMESYNC = _get("GPS_STATUS_FLAGS_GPS_PPS_TIMESYNC")


GPS_STATUS_FLAGS_MASK: int = 0
for _flag in GpsStatusFlags:
    GPS_STATUS_FLAGS_MASK |= _flag.value

LOG(
    f"[IESA] Parsed {ENUM_GPS_STATUS_NAME}: "
    f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _GPS_STATUS_VALUES.items()} }"
)


@dataclass
class GpsStatusReport:
    """Structured representation of a decoded GPS status value."""

    raw_status: int
    fix_type: GpsFixType
    flags: List[GpsStatusFlags] = field(default_factory=list)

    @property
    def raw_status_hex(self) -> str:
        return f"0x{self.raw_status:08X}"

    def to_dict(self) -> Dict[str, object]:
        return {
            "raw_status": self.raw_status,
            "raw_status_hex": self.raw_status_hex,
            "fix_type": self.fix_type,
            "flags": self.flags,
        }

    def __str__(self) -> str:
        lines = [f"Raw Status: {self.raw_status_hex}", f"Fix Type: {self.fix_type.name} (0x{self.fix_type.value:08X})"]
        lines.append("Flags:")
        if not self.flags:
            lines.append("  None")
        else:
            for flag in self.flags:
                lines.append(f"  {flag.name} (0x{flag.value:08X})")
        return "\n".join(lines)


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


def decode_gps_status(status: Union[int, str]) -> GpsStatusReport:
    """Decode the GPS status integer into a structured mapping. This can be get from DID_GPS1_POS message."""
    if isinstance(status, str):
        status = int(status, 0)

    gps_status_data = GpsStatusReport(raw_status=status, fix_type=decode_fix_type(status), flags=decode_flags(status))
    LOG(f"Decoded GPS status: {gps_status_data}", highlight=True)
    return gps_status_data


def print_gps_status_report(status: Union[int, str, GpsStatusReport]) -> None:
    """Print a human readable summary of the GPS status."""
    report = status if isinstance(status, GpsStatusReport) else decode_gps_status(status)
    print(str(report))
