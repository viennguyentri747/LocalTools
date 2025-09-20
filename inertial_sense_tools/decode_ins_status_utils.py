"""Utility helpers for decoding INS status messages from Inertial Sense devices."""

from typing import Dict

# INS Status Flags Constants
INS_STATUS_HDG_ALIGN_COARSE = 0x00000001
INS_STATUS_VEL_ALIGN_COARSE = 0x00000002
INS_STATUS_POS_ALIGN_COARSE = 0x00000004
INS_STATUS_ALIGN_COARSE_MASK = 0x00000007
INS_STATUS_WHEEL_AIDING_VEL = 0x00000008
INS_STATUS_HDG_ALIGN_FINE = 0x00000010
INS_STATUS_VEL_ALIGN_FINE = 0x00000020
INS_STATUS_POS_ALIGN_FINE = 0x00000040
INS_STATUS_ALIGN_FINE_MASK = 0x00000070
INS_STATUS_GPS_AIDING_HEADING = 0x00000080
INS_STATUS_GPS_AIDING_POS = 0x00000100
INS_STATUS_GPS_UPDATE_IN_SOLUTION = 0x00000200
INS_STATUS_EKF_USING_REFERENCE_IMU = 0x00000400
INS_STATUS_MAG_AIDING_HEADING = 0x00000800
INS_STATUS_NAV_MODE = 0x00001000
INS_STATUS_STATIONARY_MODE = 0x00002000
INS_STATUS_GPS_AIDING_VEL = 0x00004000
INS_STATUS_KINEMATIC_CAL_GOOD = 0x00008000
INS_STATUS_SOLUTION_MASK = 0x000F0000
INS_STATUS_SOLUTION_OFFSET = 16

# Individual Solution Status Values
INS_STATUS_SOLUTION_OFF = 0
INS_STATUS_SOLUTION_ALIGNING = 1
INS_STATUS_SOLUTION_NAV = 3
INS_STATUS_SOLUTION_NAV_HIGH_VARIANCE = 4
INS_STATUS_SOLUTION_AHRS = 5
INS_STATUS_SOLUTION_AHRS_HIGH_VARIANCE = 6
INS_STATUS_SOLUTION_VRS = 7
INS_STATUS_SOLUTION_VRS_HIGH_VARIANCE = 8

INS_STATUS_RTK_COMPASSING_BASELINE_UNSET = 0x00100000
INS_STATUS_RTK_COMPASSING_BASELINE_BAD = 0x00200000
INS_STATUS_RTK_COMPASSING_MASK = (
    INS_STATUS_RTK_COMPASSING_BASELINE_UNSET | INS_STATUS_RTK_COMPASSING_BASELINE_BAD
)
INS_STATUS_MAG_RECALIBRATING = 0x00400000
INS_STATUS_MAG_INTERFERENCE_OR_BAD_CAL = 0x00800000
INS_STATUS_GPS_NAV_FIX_MASK = 0x03000000
INS_STATUS_GPS_NAV_FIX_OFFSET = 24
INS_STATUS_RTK_COMPASSING_VALID = 0x04000000
INS_STATUS_RTK_RAW_GPS_DATA_ERROR = 0x08000000
INS_STATUS_RTK_ERR_BASE_DATA_MISSING = 0x10000000
INS_STATUS_RTK_ERR_BASE_POSITION_MOVING = 0x20000000
INS_STATUS_RTK_ERR_BASE_POSITION_INVALID = 0x30000000
INS_STATUS_RTK_ERR_BASE_MASK = 0x30000000
INS_STATUS_RTK_ERROR_MASK = INS_STATUS_RTK_RAW_GPS_DATA_ERROR | INS_STATUS_RTK_ERR_BASE_MASK
INS_STATUS_RTOS_TASK_PERIOD_OVERRUN = 0x40000000
INS_STATUS_GENERAL_FAULT = 0x80000000


def decode_ins_status(ins_status: int) -> Dict[str, object]:
    """Decode a 32-bit INS status value into a structured mapping."""
    line_separator = f"\n{'=' * 60}\n"
    indent = " " * 4

    decoded_status: Dict[str, object] = {
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
        0: "None",  # NAV_FIX_STATUS_NONE
        1: "3D Fix",  # NAV_FIX_STATUS_3D
        2: "RTK Float",  # NAV_FIX_STATUS_RTK_FLOAT
        3: "RTK Fix",  # NAV_FIX_STATUS_RTK_FIX
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
