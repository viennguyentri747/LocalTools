#!/usr/bin/env python3.10

import argparse
from enum import Flag
from typing import Dict

# --- Constants, Masks, and Offsets ---

# Built-in Test (BIT) Status Field
HDW_STATUS_BIT_MASK: int = 0x03000000
HDW_STATUS_BIT_RUNNING: int = 0x01000000
HDW_STATUS_BIT_PASSED: int = 0x02000000
HDW_STATUS_BIT_FAILED: int = 0x03000000

# Communications Parse Error Count Field
HDW_STATUS_COM_PARSE_ERR_COUNT_MASK: int = 0x00F00000
HDW_STATUS_COM_PARSE_ERR_COUNT_OFFSET: int = 20

# System Reset Cause Field
HDW_STATUS_RESET_CAUSE_MASK: int = 0x70000000
HDW_STATUS_RESET_CAUSE_BACKUP_MODE: int = 0x10000000
HDW_STATUS_RESET_CAUSE_WATCHDOG_FAULT: int = 0x20000000
HDW_STATUS_RESET_CAUSE_SOFT: int = 0x30000000
HDW_STATUS_RESET_CAUSE_HDW: int = 0x40000000

# --- Hardware Status Flags Enum ---

class HdwStatusFlags(Flag):
    """Enum representing individual hardware status flags."""
    MOTION_GYR = 0x00000001
    MOTION_ACC = 0x00000002
    IMU_FAULT_REJECT_GYR = 0x00000004
    IMU_FAULT_REJECT_ACC = 0x00000008
    GPS_SATELLITE_RX_VALID = 0x00000010
    STROBE_IN_EVENT = 0x00000020
    GPS_TIME_OF_WEEK_VALID = 0x00000040
    REFERENCE_IMU_RX = 0x00000080
    SATURATION_GYR = 0x00000100
    SATURATION_ACC = 0x00000200
    SATURATION_MAG = 0x00000400
    SATURATION_BARO = 0x00000800
    SYSTEM_RESET_REQUIRED = 0x00001000
    ERR_GPS_PPS_NOISE = 0x00002000
    MAG_RECAL_COMPLETE = 0x00004000
    FLASH_WRITE_PENDING = 0x00008000
    ERR_COM_TX_LIMITED = 0x00010000
    ERR_COM_RX_OVERRUN = 0x00020000
    ERR_NO_GPS_PPS = 0x00040000
    GPS_PPS_TIMESYNC = 0x00080000
    ERR_TEMPERATURE = 0x04000000
    SPI_INTERFACE_ENABLED = 0x08000000
    FAULT_SYS_CRITICAL = 0x80000000

# --- Decoding Helper Functions ---

def get_bit_status(status: int) -> str:
    """Decodes the Built-in Test (BIT) status field."""
    bit_field = status & HDW_STATUS_BIT_MASK
    status_map = {
        HDW_STATUS_BIT_FAILED: "Failed",
        HDW_STATUS_BIT_PASSED: "Passed",
        HDW_STATUS_BIT_RUNNING: "Running",
    }
    return status_map.get(bit_field, "Not Run / N/A")

def get_reset_cause(status: int) -> str:
    """Decodes the cause of the last system reset."""
    reset_field = status & HDW_STATUS_RESET_CAUSE_MASK
    cause_map = {
        HDW_STATUS_RESET_CAUSE_HDW: "Hardware (NRST pin)",
        HDW_STATUS_RESET_CAUSE_SOFT: "Software",
        HDW_STATUS_RESET_CAUSE_WATCHDOG_FAULT: "Watchdog Fault",
        HDW_STATUS_RESET_CAUSE_BACKUP_MODE: "Backup Mode (Low-power state)",
    }
    # Order of checking matters if values overlap, though here they are distinct.
    for cause, description in cause_map.items():
        if reset_field == cause:
            return description
    return "N/A"

def get_com_parse_error_count(status: int) -> int:
    """Extracts the communication parse error count."""
    return (status & HDW_STATUS_COM_PARSE_ERR_COUNT_MASK) >> HDW_STATUS_COM_PARSE_ERR_COUNT_OFFSET

def is_set(hdw_status: int, flag: HdwStatusFlags) -> bool:
    """Checks if a specific flag is set in the status integer."""
    return (hdw_status & flag.value) != 0

# --- Main Decoding Function ---

def decode_hdw_status(hdw_status: int) -> Dict:
    """
    Decodes a 32-bit hardware status value into a dictionary of readable strings.
    """
    LINE_SEPARATOR = f"\n{'=' * 60}\n"
    INDENT = " " * 4
    
    decoded = {
        "Overall Status Value (Hex)": f"0x{hdw_status:08X}",
        f"{LINE_SEPARATOR}MOTION & IMU": {
            INDENT + "Gyro motion detected": is_set(hdw_status, HdwStatusFlags.MOTION_GYR),
            INDENT + "Accelerometer motion detected": is_set(hdw_status, HdwStatusFlags.MOTION_ACC),
            INDENT + "IMU gyro fault rejection": is_set(hdw_status, HdwStatusFlags.IMU_FAULT_REJECT_GYR),
            INDENT + "IMU accelerometer fault rejection": is_set(hdw_status, HdwStatusFlags.IMU_FAULT_REJECT_ACC),
        },
        f"{LINE_SEPARATOR}SENSOR SATURATION": {
            INDENT + "Gyro": is_set(hdw_status, HdwStatusFlags.SATURATION_GYR),
            INDENT + "Accelerometer": is_set(hdw_status, HdwStatusFlags.SATURATION_ACC),
            INDENT + "Magnetometer": is_set(hdw_status, HdwStatusFlags.SATURATION_MAG),
            INDENT + "Barometric Pressure": is_set(hdw_status, HdwStatusFlags.SATURATION_BARO),
        },
        f"{LINE_SEPARATOR}GENERAL STATUS & TIMING": {
            INDENT + "GPS Satellite RX Valid": is_set(hdw_status, HdwStatusFlags.GPS_SATELLITE_RX_VALID),
            INDENT + "GPS Time Of Week Valid": is_set(hdw_status, HdwStatusFlags.GPS_TIME_OF_WEEK_VALID),
            INDENT + "Time synchronized by GPS PPS": is_set(hdw_status, HdwStatusFlags.GPS_PPS_TIMESYNC),
            INDENT + "Reference IMU data received": is_set(hdw_status, HdwStatusFlags.REFERENCE_IMU_RX),
            INDENT + "Event on strobe input pin": is_set(hdw_status, HdwStatusFlags.STROBE_IN_EVENT),
        },
        f"{LINE_SEPARATOR}SYSTEM & INTERFACE": {
            INDENT + "Mag Recalibration Complete": is_set(hdw_status, HdwStatusFlags.MAG_RECAL_COMPLETE),
            INDENT + "Flash Write Pending": is_set(hdw_status, HdwStatusFlags.FLASH_WRITE_PENDING),
            INDENT + "SPI Interface Enabled": is_set(hdw_status, HdwStatusFlags.SPI_INTERFACE_ENABLED),
            INDENT + "Built-in Test (BIT) Status": get_bit_status(hdw_status),
            INDENT + "Cause of Last Reset": get_reset_cause(hdw_status),
        },
        f"{LINE_SEPARATOR}FAULTS & WARNINGS": {
            INDENT + "Critical System Fault (CPU)": is_set(hdw_status, HdwStatusFlags.FAULT_SYS_CRITICAL),
            INDENT + "System Reset Required": is_set(hdw_status, HdwStatusFlags.SYSTEM_RESET_REQUIRED),
            INDENT + "Temperature out of spec": is_set(hdw_status, HdwStatusFlags.ERR_TEMPERATURE),
            INDENT + "GPS PPS signal noise": is_set(hdw_status, HdwStatusFlags.ERR_GPS_PPS_NOISE),
            INDENT + "No GPS PPS signal": is_set(hdw_status, HdwStatusFlags.ERR_NO_GPS_PPS),
            INDENT + "Communications Tx buffer limited": is_set(hdw_status, HdwStatusFlags.ERR_COM_TX_LIMITED),
            INDENT + "Communications Rx buffer overrun": is_set(hdw_status, HdwStatusFlags.ERR_COM_RX_OVERRUN),
            INDENT + "Communications Parse Error Count": get_com_parse_error_count(hdw_status),
        },
    }
    return decoded

def print_decoded_status(decoded_status: Dict, indent: int = 0) -> None:
    """Prints the decoded status dictionary in a readable, nested format."""
    for key, value in decoded_status.items():
        prefix = " " * indent
        if isinstance(value, dict):
            print(f"{prefix}{key}")
            print_decoded_status(value, indent + 4)
        else:
            print(f"{prefix}{key}: {value}")

# --- Entry Point ---

def main() -> None:
    """Parses command-line arguments and initiates decoding."""
    parser = argparse.ArgumentParser(description="Decode a 32-bit hardware (HDW) status integer.")
    parser.add_argument(
        "-s", "--status", 
        required=True, 
        type=lambda x: int(x, 0), 
        help="Hardware status value (e.g., \"0x2088010\" or a decimal number)."
    )
    args = parser.parse_args()

    print(f"\nDecoding HDW Status: 0x{args.status:08X} ({args.status})")
    decoded_info = decode_hdw_status(args.status)
    print_decoded_status(decoded_info)
    print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    main()