#!/usr/bin/env python3.10

import argparse
from pathlib import Path
from dev_common.tools_utils import ToolTemplate, build_examples_epilog

# ------------------------------
# Hardware Status Bit Definitions
# ------------------------------

HDW_STATUS_FLAGS = {
    0x00000001: "Gyro motion detected",
    0x00000002: "Accelerometer motion detected",
    0x00000004: "IMU gyro fault rejection",
    0x00000008: "IMU accelerometer fault rejection",
    0x00000010: "GPS satellite signals received",
    0x00000020: "Strobe input event",
    0x00000040: "GPS time of week valid",
    0x00000080: "Reference IMU data received",
    0x00000100: "Gyro saturation",
    0x00000200: "Accelerometer saturation",
    0x00000400: "Magnetometer saturation",
    0x00000800: "Barometric sensor saturation",
    0x00001000: "System reset required",
    0x00002000: "GPS PPS signal noise",
    0x00004000: "Magnetometer recalibration complete",
    0x00008000: "Flash write pending",
    0x00010000: "Communication TX limited",
    0x00020000: "Communication RX overrun",
    0x00040000: "No GPS PPS signal",
    0x00080000: "GPS PPS time sync",
    0x01000000: "BIT running",
    0x02000000: "BIT passed",
    0x03000000: "BIT failed",
    0x04000000: "Temperature error",
    0x08000000: "SPI interface enabled",
    0x10000000: "Reset from backup mode",
    0x20000000: "Reset from watchdog fault",
    0x30000000: "Reset from software",
    0x40000000: "Reset from hardware",
    0x80000000: "Critical system fault",
}

# Masks and Offsets
SATURATION_MASK = 0x00000F00
SATURATION_OFFSET = 8

BIT_MASK = 0x03000000
RESET_CAUSE_MASK = 0x70000000
COM_PARSE_ERR_MASK = 0x00F00000
COM_PARSE_ERR_OFFSET = 20

# ------------------------------
# Decoder Function
# ------------------------------

def decode_hdw_status(status: int):
    print(f"Raw Status: 0x{status:08X}")

    # Decode individual flags
    print("\nFlags Set:")
    found = False
    for flag_val, description in HDW_STATUS_FLAGS.items():
        if (status & flag_val) == flag_val:
            print(f"  {description} (0x{flag_val:08X})")
            found = True
    if not found:
        print("  None")

    # Decode Saturation
    saturation = (status & SATURATION_MASK) >> SATURATION_OFFSET
    if saturation:
        print(f"\nSaturation Bits: 0x{saturation:01X}")

    # Decode BIT
    bit_status = status & BIT_MASK
    if bit_status == 0x01000000:
        print("\nBIT Status: Running")
    elif bit_status == 0x02000000:
        print("\nBIT Status: Passed")
    elif bit_status == 0x03000000:
        print("\nBIT Status: Failed")

    # Decode Reset Cause
    reset_cause = status & RESET_CAUSE_MASK
    if reset_cause:
        print("\nReset Cause:", end=" ")
        if reset_cause == 0x10000000:
            print("Backup Mode")
        elif reset_cause == 0x20000000:
            print("Watchdog Fault")
        elif reset_cause == 0x30000000:
            print("Software Reset")
        elif reset_cause == 0x40000000:
            print("Hardware Reset")
        else:
            print(f"Unknown (0x{reset_cause:08X})")

    # Decode Communication Parse Error Count
    com_parse_err = (status & COM_PARSE_ERR_MASK) >> COM_PARSE_ERR_OFFSET
    if com_parse_err:
        print(f"\nCommunication Parse Error Count: {com_parse_err}")

# ------------------------------
# Main CLI Entry
# ------------------------------

def main():
    parser = argparse.ArgumentParser(description="Decode a 32-bit Hardware status flag.")
    # Fill help epilog from templates
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument("-s", "--status", required=True, type=lambda x: int(x, 0),
                        help="Hardware status value (e.g. \"0x40000001\" or \"1073741825\")")
    args = parser.parse_args()

    decode_hdw_status(args.status)


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Decode HDW Status",
            description="Decode hardware status integer",
            args={
                "--status": "0x40000001",
            }
        ),
    ]


if __name__ == "__main__":
    main()
