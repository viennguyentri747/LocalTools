"""Utility helpers for decoding INS status messages from Inertial Sense devices."""

from typing import Dict, Union

from dev.dev_common.core_independent_utils import LOG
from dev.dev_iesa.iesa_repo_utils import (
    get_enum_declaration_from_path,
    get_path_to_inertial_sense_data_set_header,
)

ENUM_INS_STATUS_FLAGS = "eInsStatusFlags"
ENUM_GPS_NAV_FIX_STATUS = "eGpsNavFixStatus"

_HEADER_PATH = get_path_to_inertial_sense_data_set_header()
_INS_STATUS_VALUES = get_enum_declaration_from_path(ENUM_INS_STATUS_FLAGS, _HEADER_PATH)
_GPS_NAV_FIX_VALUES = get_enum_declaration_from_path(ENUM_GPS_NAV_FIX_STATUS, _HEADER_PATH)


def _require(enum_dict: Dict[str, int], name: str, enum_name: str) -> int:
    try:
        return enum_dict[name]
    except KeyError as exc:
        raise KeyError(f"Missing {name} in {enum_name}") from exc


INS_STATUS_HDG_ALIGN_COARSE = _require(_INS_STATUS_VALUES, "INS_STATUS_HDG_ALIGN_COARSE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_VEL_ALIGN_COARSE = _require(_INS_STATUS_VALUES, "INS_STATUS_VEL_ALIGN_COARSE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_POS_ALIGN_COARSE = _require(_INS_STATUS_VALUES, "INS_STATUS_POS_ALIGN_COARSE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_ALIGN_COARSE_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_ALIGN_COARSE_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_WHEEL_AIDING_VEL = _require(_INS_STATUS_VALUES, "INS_STATUS_WHEEL_AIDING_VEL", ENUM_INS_STATUS_FLAGS)
INS_STATUS_HDG_ALIGN_FINE = _require(_INS_STATUS_VALUES, "INS_STATUS_HDG_ALIGN_FINE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_VEL_ALIGN_FINE = _require(_INS_STATUS_VALUES, "INS_STATUS_VEL_ALIGN_FINE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_POS_ALIGN_FINE = _require(_INS_STATUS_VALUES, "INS_STATUS_POS_ALIGN_FINE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_ALIGN_FINE_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_ALIGN_FINE_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_GPS_AIDING_HEADING = _require(_INS_STATUS_VALUES, "INS_STATUS_GPS_AIDING_HEADING", ENUM_INS_STATUS_FLAGS)
INS_STATUS_GPS_AIDING_POS = _require(_INS_STATUS_VALUES, "INS_STATUS_GPS_AIDING_POS", ENUM_INS_STATUS_FLAGS)
INS_STATUS_GPS_UPDATE_IN_SOLUTION = _require(
    _INS_STATUS_VALUES, "INS_STATUS_GPS_UPDATE_IN_SOLUTION", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_EKF_USING_REFERENCE_IMU = _require(
    _INS_STATUS_VALUES, "INS_STATUS_EKF_USING_REFERENCE_IMU", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_MAG_AIDING_HEADING = _require(_INS_STATUS_VALUES, "INS_STATUS_MAG_AIDING_HEADING", ENUM_INS_STATUS_FLAGS)
INS_STATUS_NAV_MODE = _require(_INS_STATUS_VALUES, "INS_STATUS_NAV_MODE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_STATIONARY_MODE = _require(_INS_STATUS_VALUES, "INS_STATUS_STATIONARY_MODE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_GPS_AIDING_VEL = _require(_INS_STATUS_VALUES, "INS_STATUS_GPS_AIDING_VEL", ENUM_INS_STATUS_FLAGS)
INS_STATUS_KINEMATIC_CAL_GOOD = _require(_INS_STATUS_VALUES, "INS_STATUS_KINEMATIC_CAL_GOOD", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_OFFSET = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_OFFSET", ENUM_INS_STATUS_FLAGS)

INS_STATUS_SOLUTION_OFF = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_OFF", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_ALIGNING = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_ALIGNING", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_NAV = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_NAV", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_NAV_HIGH_VARIANCE = _require(
    _INS_STATUS_VALUES, "INS_STATUS_SOLUTION_NAV_HIGH_VARIANCE", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_SOLUTION_AHRS = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_AHRS", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_AHRS_HIGH_VARIANCE = _require(
    _INS_STATUS_VALUES, "INS_STATUS_SOLUTION_AHRS_HIGH_VARIANCE", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_SOLUTION_VRS = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_VRS", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_VRS_HIGH_VARIANCE = _require(
    _INS_STATUS_VALUES, "INS_STATUS_SOLUTION_VRS_HIGH_VARIANCE", ENUM_INS_STATUS_FLAGS
)

INS_STATUS_RTK_COMPASSING_BASELINE_UNSET = _require(
    _INS_STATUS_VALUES, "INS_STATUS_RTK_COMPASSING_BASELINE_UNSET", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_RTK_COMPASSING_BASELINE_BAD = _require(
    _INS_STATUS_VALUES, "INS_STATUS_RTK_COMPASSING_BASELINE_BAD", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_RTK_COMPASSING_MASK = _require(
    _INS_STATUS_VALUES, "INS_STATUS_RTK_COMPASSING_MASK", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_MAG_RECALIBRATING = _require(_INS_STATUS_VALUES, "INS_STATUS_MAG_RECALIBRATING", ENUM_INS_STATUS_FLAGS)
INS_STATUS_MAG_INTERFERENCE_OR_BAD_CAL = _require(
    _INS_STATUS_VALUES, "INS_STATUS_MAG_INTERFERENCE_OR_BAD_CAL_OR_NO_CAL", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_GPS_NAV_FIX_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_GPS_NAV_FIX_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_GPS_NAV_FIX_OFFSET = _require(_INS_STATUS_VALUES, "INS_STATUS_GPS_NAV_FIX_OFFSET", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_COMPASSING_VALID = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_COMPASSING_VALID", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_RAW_GPS_DATA_ERROR = _require(
    _INS_STATUS_VALUES, "INS_STATUS_RTK_RAW_GPS_DATA_ERROR", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_RTK_ERR_BASE_DATA_MISSING = _require(
    _INS_STATUS_VALUES, "INS_STATUS_RTK_ERR_BASE_DATA_MISSING", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_RTK_ERR_BASE_POSITION_MOVING = _require(
    _INS_STATUS_VALUES, "INS_STATUS_RTK_ERR_BASE_POSITION_MOVING", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_RTK_ERR_BASE_POSITION_INVALID = _require(
    _INS_STATUS_VALUES, "INS_STATUS_RTK_ERR_BASE_POSITION_INVALID", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_RTK_ERR_BASE_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_ERR_BASE_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_ERROR_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_ERROR_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTOS_TASK_PERIOD_OVERRUN = _require(
    _INS_STATUS_VALUES, "INS_STATUS_RTOS_TASK_PERIOD_OVERRUN", ENUM_INS_STATUS_FLAGS
)
INS_STATUS_GENERAL_FAULT = _require(_INS_STATUS_VALUES, "INS_STATUS_GENERAL_FAULT", ENUM_INS_STATUS_FLAGS)


LOG(
    f"[IESA] Parsed {ENUM_INS_STATUS_FLAGS}: "
    f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _INS_STATUS_VALUES.items()} }"
)
LOG(
    f"[IESA] Parsed {ENUM_GPS_NAV_FIX_STATUS}: "
    f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _GPS_NAV_FIX_VALUES.items()} }"
)


def decode_ins_status(ins_status: Union[int, str]) -> Dict[str, Union[str, Dict[str, Union[str, bool]]]]:
    """Decode a 32-bit INS status value into a structured mapping. Keys are CATEGORICAL heading (for example SOLUTION STATUS) and values corresponding str (corresponding value)/dict(of title: value)."""
    if isinstance(ins_status, str):
        ins_status = int(ins_status, 0)

    line_separator = f"\n{'=' * 60}\n"
    indent = " " * 4

    decoded_status: Dict[str, Union[str, Dict[str, object]]] = {
        "Overall Status Value (Hex)": f"0x{ins_status:08X}",
        f"{line_separator}SOLUTION STATUS": get_solution_status(ins_status),
        f"{line_separator}ALIGNMENT STATUS": {
            indent + "Coarse Heading": is_set(ins_status, INS_STATUS_HDG_ALIGN_COARSE),
            indent + "Coarse Velocity": is_set(ins_status, INS_STATUS_VEL_ALIGN_COARSE),
            indent + "Coarse Position": is_set(ins_status, INS_STATUS_POS_ALIGN_COARSE),
            indent + "Fine Heading": is_set(ins_status, INS_STATUS_HDG_ALIGN_FINE),
            indent + "Fine Velocity": is_set(ins_status, INS_STATUS_VEL_ALIGN_FINE),
            indent + "Fine Position": is_set(ins_status, INS_STATUS_POS_ALIGN_FINE),
        },
        f"{line_separator}AIDING STATUS": {
            indent + "GPS Aiding Heading": is_set(ins_status, INS_STATUS_GPS_AIDING_HEADING),
            indent + "GPS Aiding Position": is_set(ins_status, INS_STATUS_GPS_AIDING_POS),
            indent + "GPS Aiding Velocity": is_set(ins_status, INS_STATUS_GPS_AIDING_VEL),
            indent + "GPS Update in Solution": is_set(ins_status, INS_STATUS_GPS_UPDATE_IN_SOLUTION),
            indent + "Wheel Velocity Aiding": is_set(ins_status, INS_STATUS_WHEEL_AIDING_VEL),
            indent + "Magnetometer Aiding Heading": is_set(ins_status, INS_STATUS_MAG_AIDING_HEADING),
        },
        f"{line_separator}RTK STATUS": {
            indent + "Compassing Status": get_rtk_compassing_status(ins_status),
            indent + "Raw GPS Data Error": is_set(ins_status, INS_STATUS_RTK_RAW_GPS_DATA_ERROR),
            indent + "Base Data Missing": is_set(ins_status, INS_STATUS_RTK_ERR_BASE_DATA_MISSING),
            indent + "Base Position Moving": is_set(ins_status, INS_STATUS_RTK_ERR_BASE_POSITION_MOVING),
        },
        f"{line_separator}OPERATIONAL MODE": {
            indent + "Navigation Mode": is_set(ins_status, INS_STATUS_NAV_MODE),
            indent + "Stationary Mode": is_set(ins_status, INS_STATUS_STATIONARY_MODE),
            indent + "EKF using Reference IMU": is_set(ins_status, INS_STATUS_EKF_USING_REFERENCE_IMU),
        },
        f"{line_separator}GPS FIX": get_gps_nav_fix_status(ins_status),
        f"{line_separator}MAGNETOMETER STATUS": {
            indent + "Recalibrating": is_set(ins_status, INS_STATUS_MAG_RECALIBRATING),
            indent + "Interference or Bad Cal": is_set(ins_status, INS_STATUS_MAG_INTERFERENCE_OR_BAD_CAL),
        },
        f"{line_separator}FAULTS & WARNINGS": {
            indent + "General Fault": is_set(ins_status, INS_STATUS_GENERAL_FAULT),
            indent + "RTOS Task Period Overrun": is_set(ins_status, INS_STATUS_RTOS_TASK_PERIOD_OVERRUN),
        },
        f"{line_separator}Kinematic Calibration Good": is_set(ins_status, INS_STATUS_KINEMATIC_CAL_GOOD),
    }

    return decoded_status


def get_solution_status(ins_status: int) -> str:
    """Decode the solution status field."""
    solution_map = {
        INS_STATUS_SOLUTION_OFF: "Off",
        INS_STATUS_SOLUTION_ALIGNING: "Aligning",
        INS_STATUS_SOLUTION_NAV: "Nav",
        INS_STATUS_SOLUTION_NAV_HIGH_VARIANCE: "Nav (High Variance)",
        INS_STATUS_SOLUTION_AHRS: "AHRS",
        INS_STATUS_SOLUTION_AHRS_HIGH_VARIANCE: "AHRS (High Variance)",
        INS_STATUS_SOLUTION_VRS: "VRS",
        INS_STATUS_SOLUTION_VRS_HIGH_VARIANCE: "VRS (High Variance)",
    }
    solution_val = (ins_status & INS_STATUS_SOLUTION_MASK) >> INS_STATUS_SOLUTION_OFFSET
    return solution_map.get(solution_val, "N/A")


def get_rtk_compassing_status(ins_status: int) -> str:
    """Decode the RTK compassing status."""
    if ins_status & INS_STATUS_RTK_COMPASSING_BASELINE_UNSET:
        return "Baseline Unset"
    if ins_status & INS_STATUS_RTK_COMPASSING_BASELINE_BAD:
        return "Baseline Bad"
    if ins_status & INS_STATUS_RTK_COMPASSING_VALID:
        return "Valid"
    return "N/A"


def get_gps_nav_fix_status(ins_status: int) -> str:
    """Decode the GPS Nav Fix status."""
    fix_map = {
        _GPS_NAV_FIX_VALUES.get("GPS_NAV_FIX_NONE", 0): "None",
        _GPS_NAV_FIX_VALUES.get("GPS_NAV_FIX_POSITIONING_3D", 1): "3D Fix",
        _GPS_NAV_FIX_VALUES.get("GPS_NAV_FIX_POSITIONING_RTK_FLOAT", 2): "RTK Float",
        _GPS_NAV_FIX_VALUES.get("GPS_NAV_FIX_POSITIONING_RTK_FIX", 3): "RTK Fix",
    }
    fix_val = (ins_status & INS_STATUS_GPS_NAV_FIX_MASK) >> INS_STATUS_GPS_NAV_FIX_OFFSET
    return fix_map.get(fix_val, "N/A")


def is_set(ins_status: int, flag: int) -> bool:
    """Return True when the specified flag bit is set."""
    return (ins_status & flag) != 0


def print_decoded_status(decoded_status: Dict[str, object], indent: int = 0) -> None:
    """Recursively print the decoded status dictionary."""
    for key, value in decoded_status.items():
        prefix = " " * indent
        if isinstance(value, dict):
            print(f"{prefix}{key}")
            print_decoded_status(value, indent + 4)
        else:
            print(f"{prefix}{key}: {value}")
