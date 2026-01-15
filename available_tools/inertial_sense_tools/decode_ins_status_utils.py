"""Utility helpers for decoding INS status messages from Inertial Sense devices."""

from dataclasses import dataclass, field
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


@dataclass
class InsStatus:
    """Structured representation of a decoded INS status value."""

    raw_value: int
    solution_status: str
    alignment_status: Dict[str, bool] = field(default_factory=dict)
    aiding_status: Dict[str, bool] = field(default_factory=dict)
    rtk_status: Dict[str, Union[str, bool]] = field(default_factory=dict)
    operational_mode: Dict[str, bool] = field(default_factory=dict)
    gps_fix: str = ""
    magnetometer_status: Dict[str, bool] = field(default_factory=dict)
    faults_and_warnings: Dict[str, bool] = field(default_factory=dict)
    kinematic_calibration_good: bool = False

    @property
    def overall_status_hex(self) -> str:
        return f"0x{self.raw_value:08X}"

    def to_dict(self) -> Dict[str, object]:
        return {
            "raw_value": self.raw_value,
            "overall_status_hex": self.overall_status_hex,
            "solution_status": self.solution_status,
            "alignment_status": self.alignment_status,
            "aiding_status": self.aiding_status,
            "rtk_status": self.rtk_status,
            "operational_mode": self.operational_mode,
            "gps_fix": self.gps_fix,
            "magnetometer_status": self.magnetometer_status,
            "faults_and_warnings": self.faults_and_warnings,
            "kinematic_calibration_good": self.kinematic_calibration_good,
        }

    def __str__(self) -> str:
        lines = [f"INS Status: {self.overall_status_hex}", f"Solution Status: {self.solution_status}", ""]
        lines.append("Alignment Status")
        lines.extend(_format_section_lines(self.alignment_status))
        lines.append("Aiding Status")
        lines.extend(_format_section_lines(self.aiding_status))
        lines.append("RTK Status")
        lines.extend(_format_section_lines(self.rtk_status))
        lines.append("Operational Mode")
        lines.extend(_format_section_lines(self.operational_mode))
        lines.append(f"GPS Fix: {self.gps_fix}")
        lines.append("Magnetometer Status")
        lines.extend(_format_section_lines(self.magnetometer_status))
        lines.append("Faults & Warnings")
        lines.extend(_format_section_lines(self.faults_and_warnings))
        lines.append(f"Kinematic Calibration Good: {self.kinematic_calibration_good}")
        return "\n".join(lines)


def decode_ins_status(ins_status: Union[int, str]) -> InsStatus:
    """Decode a 32-bit INS status value into a structured object."""
    if isinstance(ins_status, str):
        ins_status = int(ins_status, 0)

    alignment_status = {
        "Coarse Heading": is_set(ins_status, INS_STATUS_HDG_ALIGN_COARSE),
        "Coarse Velocity": is_set(ins_status, INS_STATUS_VEL_ALIGN_COARSE),
        "Coarse Position": is_set(ins_status, INS_STATUS_POS_ALIGN_COARSE),
        "Fine Heading": is_set(ins_status, INS_STATUS_HDG_ALIGN_FINE),
        "Fine Velocity": is_set(ins_status, INS_STATUS_VEL_ALIGN_FINE),
        "Fine Position": is_set(ins_status, INS_STATUS_POS_ALIGN_FINE),
    }

    aiding_status = {
        "GPS Aiding Heading": is_set(ins_status, INS_STATUS_GPS_AIDING_HEADING),
        "GPS Aiding Position": is_set(ins_status, INS_STATUS_GPS_AIDING_POS),
        "GPS Aiding Velocity": is_set(ins_status, INS_STATUS_GPS_AIDING_VEL),
        "GPS Update in Solution": is_set(ins_status, INS_STATUS_GPS_UPDATE_IN_SOLUTION),
        "Wheel Velocity Aiding": is_set(ins_status, INS_STATUS_WHEEL_AIDING_VEL),
        "Magnetometer Aiding Heading": is_set(ins_status, INS_STATUS_MAG_AIDING_HEADING),
    }

    rtk_status = {
        "Compassing Status": get_rtk_compassing_status(ins_status),
        "Raw GPS Data Error": is_set(ins_status, INS_STATUS_RTK_RAW_GPS_DATA_ERROR),
        "Base Data Missing": is_set(ins_status, INS_STATUS_RTK_ERR_BASE_DATA_MISSING),
        "Base Position Moving": is_set(ins_status, INS_STATUS_RTK_ERR_BASE_POSITION_MOVING),
    }

    operational_mode = {
        "Navigation Mode": is_set(ins_status, INS_STATUS_NAV_MODE),
        "Stationary Mode": is_set(ins_status, INS_STATUS_STATIONARY_MODE),
        "EKF using Reference IMU": is_set(ins_status, INS_STATUS_EKF_USING_REFERENCE_IMU),
    }

    magnetometer_status = {
        "Recalibrating": is_set(ins_status, INS_STATUS_MAG_RECALIBRATING),
        "Interference or Bad Cal": is_set(ins_status, INS_STATUS_MAG_INTERFERENCE_OR_BAD_CAL),
    }

    faults_and_warnings = {
        "General Fault": is_set(ins_status, INS_STATUS_GENERAL_FAULT),
        "RTOS Task Period Overrun": is_set(ins_status, INS_STATUS_RTOS_TASK_PERIOD_OVERRUN),
    }

    ins_status_data = InsStatus(
        raw_value=ins_status,
        solution_status=get_solution_status(ins_status),
        alignment_status=alignment_status,
        aiding_status=aiding_status,
        rtk_status=rtk_status,
        operational_mode=operational_mode,
        gps_fix=get_gps_nav_fix_status(ins_status),
        magnetometer_status=magnetometer_status,
        faults_and_warnings=faults_and_warnings,
        kinematic_calibration_good=is_set(ins_status, INS_STATUS_KINEMATIC_CAL_GOOD),
    )

    #LOG(f"Decoded INS status: {ins_status_data}", highlight=True)
    return ins_status_data


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


def _format_section_lines(values: Dict[str, object], indent: int = 4) -> list:
    """Format a mapping into indented key/value lines."""
    prefix = " " * indent
    return [f"{prefix}{label}: {value}" for label, value in values.items()]


def print_decoded_status(decoded_status: Union[InsStatus, int, str]) -> None:
    """Print a human readable summary of the INS status."""
    status_obj = decoded_status if isinstance(decoded_status, InsStatus) else decode_ins_status(decoded_status)
    LOG(str(status_obj), highlight=True)
