"""Utility helpers for decoding INS status messages from Inertial Sense devices."""

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Callable, Dict, Optional, Tuple, Union

from available_tools.inertial_sense_tools.common import IS_DATASET_ENUM_REPLACEMENTS
from dev.dev_common.core_independent_utils import ELogType, LOG
from dev.dev_common.math_utils import INT_FORMAT_HEX, parse_integer_value
from dev.dev_iesa.iesa_repo_utils import get_enum_declaration_from_path, get_path_to_inertial_sense_data_set_header

ENUM_INS_STATUS_FLAGS = "eInsStatusFlags"
ENUM_GPS_NAV_FIX_STATUS = "eGpsNavFixStatus"

_HEADER_PATH = get_path_to_inertial_sense_data_set_header()
_INS_STATUS_VALUES = get_enum_declaration_from_path(ENUM_INS_STATUS_FLAGS, _HEADER_PATH, enum_replacements=IS_DATASET_ENUM_REPLACEMENTS)
_GPS_NAV_FIX_VALUES = get_enum_declaration_from_path(ENUM_GPS_NAV_FIX_STATUS, _HEADER_PATH, enum_replacements=IS_DATASET_ENUM_REPLACEMENTS)


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
INS_STATUS_GPS_UPDATE_IN_SOLUTION = _require(_INS_STATUS_VALUES, "INS_STATUS_GPS_UPDATE_IN_SOLUTION", ENUM_INS_STATUS_FLAGS)
INS_STATUS_EKF_USING_REFERENCE_IMU = _require(_INS_STATUS_VALUES, "INS_STATUS_EKF_USING_REFERENCE_IMU", ENUM_INS_STATUS_FLAGS)
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
INS_STATUS_SOLUTION_NAV_HIGH_VARIANCE = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_NAV_HIGH_VARIANCE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_AHRS = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_AHRS", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_AHRS_HIGH_VARIANCE = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_AHRS_HIGH_VARIANCE", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_VRS = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_VRS", ENUM_INS_STATUS_FLAGS)
INS_STATUS_SOLUTION_VRS_HIGH_VARIANCE = _require(_INS_STATUS_VALUES, "INS_STATUS_SOLUTION_VRS_HIGH_VARIANCE", ENUM_INS_STATUS_FLAGS)

INS_STATUS_RTK_COMPASSING_BASELINE_UNSET = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_COMPASSING_BASELINE_UNSET", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_COMPASSING_BASELINE_BAD = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_COMPASSING_BASELINE_BAD", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_COMPASSING_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_COMPASSING_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_MAG_RECALIBRATING = _require(_INS_STATUS_VALUES, "INS_STATUS_MAG_RECALIBRATING", ENUM_INS_STATUS_FLAGS)
INS_STATUS_MAG_INTERFERENCE_OR_BAD_CAL = _require(_INS_STATUS_VALUES, "INS_STATUS_MAG_INTERFERENCE_OR_BAD_CAL_OR_NO_CAL", ENUM_INS_STATUS_FLAGS)
INS_STATUS_GPS_NAV_FIX_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_GPS_NAV_FIX_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_GPS_NAV_FIX_OFFSET = _require(_INS_STATUS_VALUES, "INS_STATUS_GPS_NAV_FIX_OFFSET", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_COMPASSING_VALID = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_COMPASSING_VALID", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_RAW_GPS_DATA_ERROR = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_RAW_GPS_DATA_ERROR", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_ERR_BASE_DATA_MISSING = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_ERR_BASE_DATA_MISSING", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_ERR_BASE_POSITION_MOVING = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_ERR_BASE_POSITION_MOVING", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_ERR_BASE_POSITION_INVALID = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_ERR_BASE_POSITION_INVALID", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_ERR_BASE_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_ERR_BASE_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTK_ERROR_MASK = _require(_INS_STATUS_VALUES, "INS_STATUS_RTK_ERROR_MASK", ENUM_INS_STATUS_FLAGS)
INS_STATUS_RTOS_TASK_PERIOD_OVERRUN = _require(_INS_STATUS_VALUES, "INS_STATUS_RTOS_TASK_PERIOD_OVERRUN", ENUM_INS_STATUS_FLAGS)
INS_STATUS_GENERAL_FAULT = _require(_INS_STATUS_VALUES, "INS_STATUS_GENERAL_FAULT", ENUM_INS_STATUS_FLAGS)


LOG(f"[IESA] Parsed enum {ENUM_INS_STATUS_FLAGS}", log_type=ELogType.DEBUG)
LOG(f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _INS_STATUS_VALUES.items()} }", log_type=ELogType.DEBUG)
LOG(f"[IESA] Parsed enum {ENUM_GPS_NAV_FIX_STATUS}", log_type=ELogType.DEBUG)
LOG(f"{ {k: hex(v) if isinstance(v, int) else v for k, v in _GPS_NAV_FIX_VALUES.items()} }", log_type=ELogType.DEBUG)


class SolutionStatus(IntEnum):
    OFF = INS_STATUS_SOLUTION_OFF
    ALIGNING = INS_STATUS_SOLUTION_ALIGNING
    NAV = INS_STATUS_SOLUTION_NAV
    NAV_HIGH_VARIANCE = INS_STATUS_SOLUTION_NAV_HIGH_VARIANCE
    AHRS = INS_STATUS_SOLUTION_AHRS
    AHRS_HIGH_VARIANCE = INS_STATUS_SOLUTION_AHRS_HIGH_VARIANCE
    VRS = INS_STATUS_SOLUTION_VRS
    VRS_HIGH_VARIANCE = INS_STATUS_SOLUTION_VRS_HIGH_VARIANCE


class GpsNavFixStatus(IntEnum):
    NONE = _GPS_NAV_FIX_VALUES.get("GPS_NAV_FIX_NONE", 0)
    FIX_3D = _GPS_NAV_FIX_VALUES.get("GPS_NAV_FIX_POSITIONING_3D", 1)
    RTK_FLOAT = _GPS_NAV_FIX_VALUES.get("GPS_NAV_FIX_POSITIONING_RTK_FLOAT", 2)
    RTK_FIX = _GPS_NAV_FIX_VALUES.get("GPS_NAV_FIX_POSITIONING_RTK_FIX", 3)


class RtkCompassingStatus(IntEnum):
    NOT_AVAILABLE = 0
    BASELINE_UNSET = 1
    BASELINE_BAD = 2
    VALID = 3


_SOLUTION_LABEL = {
    SolutionStatus.OFF: "Off",
    SolutionStatus.ALIGNING: "Aligning",
    SolutionStatus.NAV: "Nav",
    SolutionStatus.NAV_HIGH_VARIANCE: "Nav (High Variance)",
    SolutionStatus.AHRS: "AHRS",
    SolutionStatus.AHRS_HIGH_VARIANCE: "AHRS (High Variance)",
    SolutionStatus.VRS: "VRS",
    SolutionStatus.VRS_HIGH_VARIANCE: "VRS (High Variance)",
}

_GPS_FIX_LABEL = {
    GpsNavFixStatus.NONE: "None",
    GpsNavFixStatus.FIX_3D: "3D Fix",
    GpsNavFixStatus.RTK_FLOAT: "RTK Float",
    GpsNavFixStatus.RTK_FIX: "RTK Fix",
}

_RTK_COMPASSING_LABEL = {
    RtkCompassingStatus.NOT_AVAILABLE: "N/A",
    RtkCompassingStatus.BASELINE_UNSET: "Baseline Unset",
    RtkCompassingStatus.BASELINE_BAD: "Baseline Bad",
    RtkCompassingStatus.VALID: "Valid",
}


@dataclass(frozen=True)
class InsAlignmentStatus:
    coarse_heading: bool
    coarse_velocity: bool
    coarse_position: bool
    fine_heading: bool
    fine_velocity: bool
    fine_position: bool


@dataclass(frozen=True)
class InsAidingStatus:
    gps_aiding_heading: bool
    gps_aiding_position: bool
    gps_aiding_velocity: bool
    gps_update_in_solution: bool
    wheel_velocity_aiding: bool
    magnetometer_aiding_heading: bool


@dataclass(frozen=True)
class InsRtkStatus:
    compassing_status: RtkCompassingStatus
    raw_gps_data_error: bool
    base_data_missing: bool
    base_position_moving: bool


@dataclass(frozen=True)
class InsOperationalMode:
    navigation_mode: bool
    stationary_mode: bool
    ekf_using_reference_imu: bool


@dataclass(frozen=True)
class InsMagnetometerStatus:
    recalibrating: bool
    interference_or_bad_cal: bool


@dataclass(frozen=True)
class InsFaultsAndWarnings:
    general_fault: bool
    rtos_task_period_overrun: bool


@dataclass(frozen=True)
class InsStatus:
    """Structured representation of a decoded INS status value."""

    raw_value: int
    solution_status: SolutionStatus
    alignment_status: InsAlignmentStatus
    aiding_status: InsAidingStatus
    rtk_status: InsRtkStatus
    operational_mode: InsOperationalMode
    gps_fix: GpsNavFixStatus
    magnetometer_status: InsMagnetometerStatus
    faults_and_warnings: InsFaultsAndWarnings
    kinematic_calibration_good: bool

    @property
    def overall_status_hex(self) -> str:
        return f"0x{self.raw_value:08X}"

    @property
    def solution_status_label(self) -> str:
        return get_solution_status_label(self.solution_status)

    @property
    def gps_fix_label(self) -> str:
        return get_gps_nav_fix_status_label(self.gps_fix)

    @property
    def rtk_compassing_status_label(self) -> str:
        return get_rtk_compassing_status_label(self.rtk_status.compassing_status)

    def to_dict(self) -> Dict[str, object]:
        return {
            "raw_value": self.raw_value,
            "overall_status_hex": self.overall_status_hex,
            "solution_status": self.solution_status,
            "solution_status_label": self.solution_status_label,
            "alignment_status": self.alignment_status,
            "aiding_status": self.aiding_status,
            "rtk_status": self.rtk_status,
            "operational_mode": self.operational_mode,
            "gps_fix": self.gps_fix,
            "gps_fix_label": self.gps_fix_label,
            "magnetometer_status": self.magnetometer_status,
            "faults_and_warnings": self.faults_and_warnings,
            "kinematic_calibration_good": self.kinematic_calibration_good,
        }

    def __str__(self) -> str:
        lines = [f"INS Status: {self.overall_status_hex}", f"Solution Status: {self.solution_status_label}", ""]
        lines.append("Alignment Status")
        lines.extend(
            _format_section_lines(
                {
                    "Coarse Heading": self.alignment_status.coarse_heading,
                    "Coarse Velocity": self.alignment_status.coarse_velocity,
                    "Coarse Position": self.alignment_status.coarse_position,
                    "Fine Heading": self.alignment_status.fine_heading,
                    "Fine Velocity": self.alignment_status.fine_velocity,
                    "Fine Position": self.alignment_status.fine_position,
                }
            )
        )
        lines.append("Aiding Status")
        lines.extend(
            _format_section_lines(
                {
                    "GPS Aiding Heading": self.aiding_status.gps_aiding_heading,
                    "GPS Aiding Position": self.aiding_status.gps_aiding_position,
                    "GPS Aiding Velocity": self.aiding_status.gps_aiding_velocity,
                    "GPS Update in Solution": self.aiding_status.gps_update_in_solution,
                    "Wheel Velocity Aiding": self.aiding_status.wheel_velocity_aiding,
                    "Magnetometer Aiding Heading": self.aiding_status.magnetometer_aiding_heading,
                }
            )
        )
        lines.append("RTK Status")
        lines.extend(
            _format_section_lines(
                {
                    "Compassing Status": self.rtk_compassing_status_label,
                    "Raw GPS Data Error": self.rtk_status.raw_gps_data_error,
                    "Base Data Missing": self.rtk_status.base_data_missing,
                    "Base Position Moving": self.rtk_status.base_position_moving,
                }
            )
        )
        lines.append("Operational Mode")
        lines.extend(
            _format_section_lines(
                {
                    "Navigation Mode": self.operational_mode.navigation_mode,
                    "Stationary Mode": self.operational_mode.stationary_mode,
                    "EKF using Reference IMU": self.operational_mode.ekf_using_reference_imu,
                }
            )
        )
        lines.append(f"GPS Fix: {self.gps_fix_label}")
        lines.append("Magnetometer Status")
        lines.extend(
            _format_section_lines(
                {
                    "Recalibrating": self.magnetometer_status.recalibrating,
                    "Interference or Bad Cal": self.magnetometer_status.interference_or_bad_cal,
                }
            )
        )
        lines.append("Faults & Warnings")
        lines.extend(
            _format_section_lines(
                {
                    "General Fault": self.faults_and_warnings.general_fault,
                    "RTOS Task Period Overrun": self.faults_and_warnings.rtos_task_period_overrun,
                }
            )
        )
        lines.append(f"Kinematic Calibration Good: {self.kinematic_calibration_good}")
        return "\n".join(lines)

    def to_compact_str(self) -> str:
        fine_align = f"fineHeading={self.alignment_status.fine_heading}, fineVelocity={self.alignment_status.fine_velocity}, finePosition={self.alignment_status.fine_position}"
        aiding = f"gpsHeading={self.aiding_status.gps_aiding_heading}, gpsPosition={self.aiding_status.gps_aiding_position}, gpsVelocity={self.aiding_status.gps_aiding_velocity}, gpsUpdate={self.aiding_status.gps_update_in_solution}"
        faults = f"generalFault={self.faults_and_warnings.general_fault}, rtosOverrun={self.faults_and_warnings.rtos_task_period_overrun}"
        mag = f"magRecalibrating={self.magnetometer_status.recalibrating}, magBadCal={self.magnetometer_status.interference_or_bad_cal}"
        return (
            f"INS {self.overall_status_hex} ({self.raw_value}) | sol={self.solution_status_label} | gps={self.gps_fix_label} | "
            f"rtk={self.rtk_compassing_status_label} | fine={fine_align} | aid={aiding} | "
            f"mag={mag} | fault={faults} | kinematicCalGood={self.kinematic_calibration_good}"
        )


@dataclass(frozen=True)
class InsStatusProgressSnapshot:
    solution_status: SolutionStatus
    solution_rank: int
    gps_fix: GpsNavFixStatus
    gps_fix_rank: int
    rtk_compassing_status: RtkCompassingStatus
    rtk_compassing_rank: int
    fine_heading: bool
    fine_velocity: bool
    fine_position: bool
    fine_alignment_score: int
    gps_update: bool
    general_fault: bool
    rtos_overrun: bool
    mag_bad_cal: bool
    kinematic_calibration_good: bool


class InsStatusCategory(Enum):
    SOLUTION = "solution"
    GPS_FIX = "gps_fix"
    RTK_COMPASSING = "rtk_compassing"
    FINE_ALIGNMENT = "fine_alignment"
    GPS_UPDATE = "gps_update"
    GENERAL_FAULT = "general_fault"
    RTOS_OVERRUN = "rtos_overrun"
    MAG_BAD_CAL = "mag_bad_cal"
    KINEMATIC_CALIBRATION_GOOD = "kinematic_calibration_good"


@dataclass(frozen=True)
class InsStatusCategorySpec:
    category: InsStatusCategory
    label: str
    value_getter: Callable[[InsStatusProgressSnapshot], object]
    rank_getter: Optional[Callable[[InsStatusProgressSnapshot], int]] = None
    label_getter: Optional[Callable[[InsStatusProgressSnapshot], str]] = None


INS_PROGRESSION_CATEGORY_SPECS: Tuple[InsStatusCategorySpec, ...] = (
    InsStatusCategorySpec(
        InsStatusCategory.SOLUTION, "Solution",
        value_getter=lambda s: s.solution_status,
        rank_getter=lambda s: s.solution_rank,
        label_getter=lambda s: get_solution_status_label(s.solution_status),
    ),
    InsStatusCategorySpec(
        InsStatusCategory.GPS_FIX, "GPS Fix",
        value_getter=lambda s: s.gps_fix,
        rank_getter=lambda s: s.gps_fix_rank,
        label_getter=lambda s: get_gps_nav_fix_status_label(s.gps_fix),
    ),
    InsStatusCategorySpec(
        InsStatusCategory.RTK_COMPASSING, "RTK Compassing",
        value_getter=lambda s: s.rtk_compassing_status,
        rank_getter=lambda s: s.rtk_compassing_rank,
        label_getter=lambda s: get_rtk_compassing_status_label(s.rtk_compassing_status),
    ),
    InsStatusCategorySpec(
        InsStatusCategory.FINE_ALIGNMENT, "Fine Alignment",
        value_getter=lambda s: (s.fine_heading, s.fine_velocity, s.fine_position),
        rank_getter=lambda s: s.fine_alignment_score,
        label_getter=lambda s: f"(Head:{int(s.fine_heading)} Vel:{int(s.fine_velocity)} Pos:{int(s.fine_position)})",
    ),
)

INS_FAULT_BOOL_CATEGORY_SPECS: Tuple[InsStatusCategorySpec, ...] = (
    InsStatusCategorySpec(InsStatusCategory.GENERAL_FAULT, "General Fault", value_getter=lambda s: s.general_fault),
    InsStatusCategorySpec(InsStatusCategory.RTOS_OVERRUN, "RTOS Task Period Overrun", value_getter=lambda s: s.rtos_overrun),
    InsStatusCategorySpec(InsStatusCategory.MAG_BAD_CAL, "Magnetometer Bad Cal", value_getter=lambda s: s.mag_bad_cal),
)


_SOLUTION_RANKS = {
    SolutionStatus.OFF: 0,
    SolutionStatus.ALIGNING: 1,
    SolutionStatus.AHRS_HIGH_VARIANCE: 2,
    SolutionStatus.AHRS: 3,
    SolutionStatus.VRS_HIGH_VARIANCE: 4,
    SolutionStatus.VRS: 5,
    SolutionStatus.NAV_HIGH_VARIANCE: 6,
    SolutionStatus.NAV: 7,
}
_GPS_FIX_RANKS = {GpsNavFixStatus.NONE: 0, GpsNavFixStatus.FIX_3D: 1, GpsNavFixStatus.RTK_FLOAT: 2, GpsNavFixStatus.RTK_FIX: 3}
_RTK_COMPASSING_RANKS = {
    RtkCompassingStatus.NOT_AVAILABLE: 0,
    RtkCompassingStatus.BASELINE_UNSET: 1,
    RtkCompassingStatus.BASELINE_BAD: 1,
    RtkCompassingStatus.VALID: 2,
}


def get_solution_status_label(solution_status: SolutionStatus) -> str:
    return _SOLUTION_LABEL.get(solution_status, "N/A")


def get_gps_nav_fix_status_label(gps_fix: GpsNavFixStatus) -> str:
    return _GPS_FIX_LABEL.get(gps_fix, "N/A")


def get_rtk_compassing_status_label(rtk_status: RtkCompassingStatus) -> str:
    return _RTK_COMPASSING_LABEL.get(rtk_status, "N/A")


def get_solution_rank(solution_status: SolutionStatus) -> int:
    return _SOLUTION_RANKS.get(solution_status, -1)


def get_gps_fix_rank(gps_fix: GpsNavFixStatus) -> int:
    return _GPS_FIX_RANKS.get(gps_fix, -1)


def get_rtk_compassing_rank(rtk_compassing_status: RtkCompassingStatus) -> int:
    return _RTK_COMPASSING_RANKS.get(rtk_compassing_status, -1)


def build_ins_status_progress_snapshot(decoded_status: Union[InsStatus, int, str]) -> InsStatusProgressSnapshot:
    decoded = decoded_status if isinstance(decoded_status, InsStatus) else decode_ins_status(decoded_status)
    fine_heading = decoded.alignment_status.fine_heading
    fine_velocity = decoded.alignment_status.fine_velocity
    fine_position = decoded.alignment_status.fine_position
    fine_alignment_score = int(fine_heading) + int(fine_velocity) + int(fine_position)
    return InsStatusProgressSnapshot(
        solution_status=decoded.solution_status,
        solution_rank=get_solution_rank(decoded.solution_status),
        gps_fix=decoded.gps_fix,
        gps_fix_rank=get_gps_fix_rank(decoded.gps_fix),
        rtk_compassing_status=decoded.rtk_status.compassing_status,
        rtk_compassing_rank=get_rtk_compassing_rank(decoded.rtk_status.compassing_status),
        fine_heading=fine_heading,
        fine_velocity=fine_velocity,
        fine_position=fine_position,
        fine_alignment_score=fine_alignment_score,
        gps_update=decoded.aiding_status.gps_update_in_solution,
        general_fault=decoded.faults_and_warnings.general_fault,
        rtos_overrun=decoded.faults_and_warnings.rtos_task_period_overrun,
        mag_bad_cal=decoded.magnetometer_status.interference_or_bad_cal,
        kinematic_calibration_good=decoded.kinematic_calibration_good,
    )


def get_category_value_from_snapshot(snapshot: InsStatusProgressSnapshot, category_spec: InsStatusCategorySpec) -> object:
    return category_spec.value_getter(snapshot)


def get_category_rank_from_snapshot(snapshot: InsStatusProgressSnapshot, category_spec: InsStatusCategorySpec) -> Optional[int]:
    if category_spec.rank_getter is None:
        return None
    return int(category_spec.rank_getter(snapshot))


def get_category_label_from_snapshot(snapshot: InsStatusProgressSnapshot, category_spec: InsStatusCategorySpec) -> str:
    if category_spec.label_getter is not None:
        return category_spec.label_getter(snapshot)
    return str(get_category_value_from_snapshot(snapshot, category_spec))


def decode_ins_status(ins_status: Union[int, str], status_format: str = INT_FORMAT_HEX) -> InsStatus:
    """Decode a 32-bit INS status value into a structured object."""
    ins_status = parse_integer_value(ins_status, parse_format=status_format, value_name="INS status")

    alignment_status = InsAlignmentStatus(
        coarse_heading=is_set(ins_status, INS_STATUS_HDG_ALIGN_COARSE),
        coarse_velocity=is_set(ins_status, INS_STATUS_VEL_ALIGN_COARSE),
        coarse_position=is_set(ins_status, INS_STATUS_POS_ALIGN_COARSE),
        fine_heading=is_set(ins_status, INS_STATUS_HDG_ALIGN_FINE),
        fine_velocity=is_set(ins_status, INS_STATUS_VEL_ALIGN_FINE),
        fine_position=is_set(ins_status, INS_STATUS_POS_ALIGN_FINE),
    )

    aiding_status = InsAidingStatus(
        gps_aiding_heading=is_set(ins_status, INS_STATUS_GPS_AIDING_HEADING),
        gps_aiding_position=is_set(ins_status, INS_STATUS_GPS_AIDING_POS),
        gps_aiding_velocity=is_set(ins_status, INS_STATUS_GPS_AIDING_VEL),
        gps_update_in_solution=is_set(ins_status, INS_STATUS_GPS_UPDATE_IN_SOLUTION),
        wheel_velocity_aiding=is_set(ins_status, INS_STATUS_WHEEL_AIDING_VEL),
        magnetometer_aiding_heading=is_set(ins_status, INS_STATUS_MAG_AIDING_HEADING),
    )

    rtk_status = InsRtkStatus(
        compassing_status=get_rtk_compassing_status(ins_status),
        raw_gps_data_error=is_set(ins_status, INS_STATUS_RTK_RAW_GPS_DATA_ERROR),
        base_data_missing=is_set(ins_status, INS_STATUS_RTK_ERR_BASE_DATA_MISSING),
        base_position_moving=is_set(ins_status, INS_STATUS_RTK_ERR_BASE_POSITION_MOVING),
    )

    operational_mode = InsOperationalMode(
        navigation_mode=is_set(ins_status, INS_STATUS_NAV_MODE),
        stationary_mode=is_set(ins_status, INS_STATUS_STATIONARY_MODE),
        ekf_using_reference_imu=is_set(ins_status, INS_STATUS_EKF_USING_REFERENCE_IMU),
    )

    magnetometer_status = InsMagnetometerStatus(
        recalibrating=is_set(ins_status, INS_STATUS_MAG_RECALIBRATING),
        interference_or_bad_cal=is_set(ins_status, INS_STATUS_MAG_INTERFERENCE_OR_BAD_CAL),
    )

    faults_and_warnings = InsFaultsAndWarnings(
        general_fault=is_set(ins_status, INS_STATUS_GENERAL_FAULT),
        rtos_task_period_overrun=is_set(ins_status, INS_STATUS_RTOS_TASK_PERIOD_OVERRUN),
    )

    return InsStatus(
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


def get_solution_status(ins_status: int) -> SolutionStatus:
    """Decode the solution status field."""
    solution_val = (ins_status & INS_STATUS_SOLUTION_MASK) >> INS_STATUS_SOLUTION_OFFSET
    try:
        return SolutionStatus(solution_val)
    except ValueError:
        return SolutionStatus.OFF


def get_rtk_compassing_status(ins_status: int) -> RtkCompassingStatus:
    """Decode the RTK compassing status."""
    if ins_status & INS_STATUS_RTK_COMPASSING_BASELINE_UNSET:
        return RtkCompassingStatus.BASELINE_UNSET
    if ins_status & INS_STATUS_RTK_COMPASSING_BASELINE_BAD:
        return RtkCompassingStatus.BASELINE_BAD
    if ins_status & INS_STATUS_RTK_COMPASSING_VALID:
        return RtkCompassingStatus.VALID
    return RtkCompassingStatus.NOT_AVAILABLE


def get_gps_nav_fix_status(ins_status: int) -> GpsNavFixStatus:
    """Decode the GPS Nav Fix status."""
    fix_val = (ins_status & INS_STATUS_GPS_NAV_FIX_MASK) >> INS_STATUS_GPS_NAV_FIX_OFFSET
    try:
        return GpsNavFixStatus(fix_val)
    except ValueError:
        return GpsNavFixStatus.NONE


def is_set(ins_status: int, flag: int) -> bool:
    """Return True when the specified flag bit is set."""
    return (ins_status & flag) != 0


def _format_section_lines(values: Dict[str, object], indent: int = 4) -> list:
    """Format a mapping into indented key/value lines."""
    prefix = " " * indent
    return [f"{prefix}{label}: {value}" for label, value in values.items()]


def print_decoded_status(decoded_status: Union[InsStatus, int, str], is_compact: bool = False, status_format: str = INT_FORMAT_HEX) -> None:
    """Print a human readable summary of the INS status."""
    status_obj = decoded_status if isinstance(decoded_status, InsStatus) else decode_ins_status(decoded_status, status_format=status_format)
    LOG(status_obj.to_compact_str() if is_compact else str(status_obj), highlight=True)
