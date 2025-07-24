#!/usr/bin/env python3
"""
INS Status Decoder
Decodes INS (Inertial Navigation System) status flags into human-readable format.
"""

# INS Status Flag Definitions
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
INS_STATUS_RTK_COMPASSING_BASELINE_UNSET = 0x00100000
INS_STATUS_RTK_COMPASSING_BASELINE_BAD = 0x00200000
INS_STATUS_RTK_COMPASSING_MASK = (INS_STATUS_RTK_COMPASSING_BASELINE_UNSET | INS_STATUS_RTK_COMPASSING_BASELINE_BAD)
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
INS_STATUS_RTK_ERROR_MASK = (INS_STATUS_RTK_RAW_GPS_DATA_ERROR | INS_STATUS_RTK_ERR_BASE_MASK)
INS_STATUS_RTOS_TASK_PERIOD_OVERRUN = 0x40000000
INS_STATUS_GENERAL_FAULT = 0x80000000

# Solution Status Values
INS_STATUS_SOLUTION_OFF = 0
INS_STATUS_SOLUTION_ALIGNING = 1
INS_STATUS_SOLUTION_NAV = 3
INS_STATUS_SOLUTION_NAV_HIGH_VARIANCE = 4
INS_STATUS_SOLUTION_AHRS = 5
INS_STATUS_SOLUTION_AHRS_HIGH_VARIANCE = 6
INS_STATUS_SOLUTION_VRS = 7
INS_STATUS_SOLUTION_VRS_HIGH_VARIANCE = 8


def get_ins_solution_status(ins_status):
    """Get the INS solution status as a string."""
    if not (ins_status & INS_STATUS_SOLUTION_MASK):
        return "None"
    
    solution_status = (ins_status & INS_STATUS_SOLUTION_MASK) >> INS_STATUS_SOLUTION_OFFSET
    
    status_map = {
        0: "Off",
        1: "Aligning",
        3: "Nav",
        4: "Nav (High Variance)",
        5: "AHRS",
        6: "AHRS (High Variance)",
        7: "VRS",
        8: "VRS (High Variance)"
    }
    
    return status_map.get(solution_status, "N/A")


def get_ins_gps_nav_fix_status(ins_status):
    """Get the GPS navigation fix status."""
    gps_fix = (ins_status & INS_STATUS_GPS_NAV_FIX_MASK) >> INS_STATUS_GPS_NAV_FIX_OFFSET
    
    fix_map = {
        0: "No Fix",
        1: "Dead Reckoning",
        2: "2D Fix",
        3: "3D Fix"
    }
    
    return fix_map.get(gps_fix, "Unknown")


def get_ins_rtk_compassing(ins_status):
    """Get the RTK compassing status."""
    if ins_status & INS_STATUS_RTK_COMPASSING_BASELINE_UNSET:
        return "Baseline Unset"
    elif ins_status & INS_STATUS_RTK_COMPASSING_BASELINE_BAD:
        return "Baseline Bad"
    elif ins_status & INS_STATUS_RTK_COMPASSING_VALID:
        return "Valid"
    
    return "N/A"


def get_ins_rtk_base_errors(ins_status):
    """Get RTK base station error status."""
    errors = []
    
    if ins_status & INS_STATUS_RTK_ERR_BASE_DATA_MISSING:
        errors.append("Base Data Missing")
    if ins_status & INS_STATUS_RTK_ERR_BASE_POSITION_MOVING:
        errors.append("Base Position Moving")
    if ins_status & INS_STATUS_RTK_ERR_BASE_POSITION_INVALID:
        errors.append("Base Position Invalid")
    
    return errors if errors else ["None"]


def decode_ins_status(ins_status):
    """
    Decode INS status flags into a comprehensive dictionary.
    
    Args:
        ins_status (int): The INS status value to decode
        
    Returns:
        dict: Dictionary containing all decoded status information
    """
    status_info = {
        "raw_value": f"0x{ins_status:08X}",
        "solution_status": get_ins_solution_status(ins_status),
        "gps_nav_fix": get_ins_gps_nav_fix_status(ins_status),
        "rtk_compassing": get_ins_rtk_compassing(ins_status),
        "rtk_base_errors": get_ins_rtk_base_errors(ins_status),
        "alignment": {
            "coarse": {
                "heading": bool(ins_status & INS_STATUS_HDG_ALIGN_COARSE),
                "velocity": bool(ins_status & INS_STATUS_VEL_ALIGN_COARSE),
                "position": bool(ins_status & INS_STATUS_POS_ALIGN_COARSE)
            },
            "fine": {
                "heading": bool(ins_status & INS_STATUS_HDG_ALIGN_FINE),
                "velocity": bool(ins_status & INS_STATUS_VEL_ALIGN_FINE),
                "position": bool(ins_status & INS_STATUS_POS_ALIGN_FINE)
            }
        },
        "aiding": {
            "wheel_velocity": bool(ins_status & INS_STATUS_WHEEL_AIDING_VEL),
            "gps_heading": bool(ins_status & INS_STATUS_GPS_AIDING_HEADING),
            "gps_position": bool(ins_status & INS_STATUS_GPS_AIDING_POS),
            "gps_velocity": bool(ins_status & INS_STATUS_GPS_AIDING_VEL),
            "mag_heading": bool(ins_status & INS_STATUS_MAG_AIDING_HEADING),
            "gps_update_in_solution": bool(ins_status & INS_STATUS_GPS_UPDATE_IN_SOLUTION)
        },
        "modes": {
            "nav_mode": bool(ins_status & INS_STATUS_NAV_MODE),
            "stationary_mode": bool(ins_status & INS_STATUS_STATIONARY_MODE)
        },
        "system_status": {
            "ekf_using_reference_imu": bool(ins_status & INS_STATUS_EKF_USING_REFERENCE_IMU),
            "kinematic_cal_good": bool(ins_status & INS_STATUS_KINEMATIC_CAL_GOOD),
            "mag_recalibrating": bool(ins_status & INS_STATUS_MAG_RECALIBRATING),
            "mag_interference_or_bad_cal": bool(ins_status & INS_STATUS_MAG_INTERFERENCE_OR_BAD_CAL),
            "rtk_raw_gps_data_error": bool(ins_status & INS_STATUS_RTK_RAW_GPS_DATA_ERROR),
            "rtos_task_period_overrun": bool(ins_status & INS_STATUS_RTOS_TASK_PERIOD_OVERRUN),
            "general_fault": bool(ins_status & INS_STATUS_GENERAL_FAULT)
        }
    }
    
    return status_info


def print_ins_status(ins_status):
    """
    Print a formatted report of the INS status.
    
    Args:
        ins_status (int): The INS status value to decode
    """
    info = decode_ins_status(ins_status)
    
    print(f"INS Status Report")
    print(f"=" * 50)
    print(f"Raw Value: {info['raw_value']}")
    print(f"Solution Status: {info['solution_status']}")
    print(f"GPS Nav Fix: {info['gps_nav_fix']}")
    print(f"RTK Compassing: {info['rtk_compassing']}")
    print(f"RTK Base Errors: {', '.join(info['rtk_base_errors'])}")
    
    print(f"\nAlignment Status:")
    print(f"  Coarse Alignment:")
    print(f"    Heading: {info['alignment']['coarse']['heading']}")
    print(f"    Velocity: {info['alignment']['coarse']['velocity']}")
    print(f"    Position: {info['alignment']['coarse']['position']}")
    print(f"  Fine Alignment:")
    print(f"    Heading: {info['alignment']['fine']['heading']}")
    print(f"    Velocity: {info['alignment']['fine']['velocity']}")
    print(f"    Position: {info['alignment']['fine']['position']}")
    
    print(f"\nAiding Sources:")
    print(f"  Wheel Velocity: {info['aiding']['wheel_velocity']}")
    print(f"  GPS Heading: {info['aiding']['gps_heading']}")
    print(f"  GPS Position: {info['aiding']['gps_position']}")
    print(f"  GPS Velocity: {info['aiding']['gps_velocity']}")
    print(f"  Magnetometer Heading: {info['aiding']['mag_heading']}")
    print(f"  GPS Update in Solution: {info['aiding']['gps_update_in_solution']}")
    
    print(f"\nOperating Modes:")
    print(f"  Navigation Mode: {info['modes']['nav_mode']}")
    print(f"  Stationary Mode: {info['modes']['stationary_mode']}")
    
    print(f"\nSystem Status:")
    print(f"  EKF Using Reference IMU: {info['system_status']['ekf_using_reference_imu']}")
    print(f"  Kinematic Calibration Good: {info['system_status']['kinematic_cal_good']}")
    print(f"  Magnetometer Recalibrating: {info['system_status']['mag_recalibrating']}")
    print(f"  Mag Interference/Bad Cal: {info['system_status']['mag_interference_or_bad_cal']}")
    print(f"  RTK Raw GPS Data Error: {info['system_status']['rtk_raw_gps_data_error']}")
    print(f"  RTOS Task Period Overrun: {info['system_status']['rtos_task_period_overrun']}")
    print(f"  General Fault: {info['system_status']['general_fault']}")


def main():
    """Main function for testing the decoder."""
    # Example usage
    test_values = [
        88297975,  # Example: Nav mode with some alignment flags
        -2059185673,  # General fault
        # 0x40000000,  # RTOS task period overrun
        # 0x04000000,  # RTK compassing valid
        # 0x00100000,  # RTK baseline unset
    ]
    
    for value in test_values:
        print_ins_status(value)
        print("\n" + "="*50 + "\n")


if __name__ == "__main__":
    main()