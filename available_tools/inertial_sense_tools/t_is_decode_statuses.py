#!/usr/local/bin/local_python

import argparse
import os
from pathlib import Path
from typing import List, Tuple

from dev.dev_common import *
from dev.dev_common.math_utils import INT_FORMAT_DEC, INT_FORMAT_HEX, SUPPORTED_INT_FORMATS, format_integer_value, parse_integer_value
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from dev.dev_iesa.iesa_repo_utils import IS_DATASET_HEADER_PATH_ENV, get_path_to_inertial_sense_data_set_header

SUPPORTED_TYPES: Tuple[str, ...] = ("gen_fault", "gps", "gps_hdw", "gpx", "system_hdw", "ins")
DEFAULT_DATASET_HEADER_PATH = get_path_to_inertial_sense_data_set_header(log_usage=False)


def _format_status_pair(status_value: int) -> str:
    return f"{format_integer_value(status_value, output_format=INT_FORMAT_HEX, width=8)} ({format_integer_value(status_value, output_format=INT_FORMAT_DEC)})"


def getToolData() -> ToolData:
    tool_templates = [
        ToolTemplate(
            name="Decode INS Status Integer",
            extra_description="Check it in `insStatus` in ``tail -F /var/log/ins_monitor_log | grep -i INS1Msg`",
            args={
                "--type": "ins",
                "--dataset-header-path": str(DEFAULT_DATASET_HEADER_PATH),
                "--status-format": "hex",
                "--status": "0x50351f7",
            },
        ),
        ToolTemplate(
            name="Decode INS Status from P-log decimal value",
            extra_description="Use this when P-log prints status as decimal (example: `92492279`).",
            args={
                "--type": "ins",
                "--dataset-header-path": str(DEFAULT_DATASET_HEADER_PATH),
                "--status-format": "dec",
                "--status": "92492279",
            },
        ),
        ToolTemplate(
            name="Decode GPS Status Integer",
            extra_description="Check it in `status` in `tail -F /var/log/ins_monitor_log | grep -i DID_GPS1_POS`",
            args={
                "--type": "gps",
                "--dataset-header-path": str(DEFAULT_DATASET_HEADER_PATH),
                "--status-format": "hex",
                "--status": "0x312",
            },
        ),
        ToolTemplate(
            name="Decode GPX Status Integer",
            extra_description="Check it in `status` in `tail -F /var/log/ins_monitor_log | grep -i DID_GPX_STATUS`",
            args={
                "--type": "gpx",
                "--dataset-header-path": str(DEFAULT_DATASET_HEADER_PATH),
                "--status-format": "hex",
                "--status": "0x60",
            },
        ),
        ToolTemplate(
            name="Decode GPS Hardware Status Integer",
            extra_description="Check it in `status` in DID_GPX_HDW_STATUS.",
            args={
                "--type": "gps_hdw",
                "--dataset-header-path": str(DEFAULT_DATASET_HEADER_PATH),
                "--status-format": "hex",
                "--status": "0x80010001",
            },
        ),
        ToolTemplate(
            name="Decode SYSTEM HDW Status Integer",
            extra_description="Decode SYSTEM hardware status integer, `hdwStatus` in `tail -F /var/log/ins_monitor_log | grep -i INS1Msg` or via DID_SYS_PARAMS.hdwStatus",
            args={
                "--type": "system_hdw",
                "--dataset-header-path": str(DEFAULT_DATASET_HEADER_PATH),
                "--status-format": "hex",
                "--status": "0x2088010",
            },
        ),
        ToolTemplate(
            name="Decode General Fault Status",
            extra_description="Use enum eGenFaultCodes, check it with `tail -F /var/log/ins_monitor_log | grep -i DID_SYS_PARAMS`",
            args={
                "--type": "gen_fault",
                "--dataset-header-path": str(DEFAULT_DATASET_HEADER_PATH),
                "--status-format": "hex",
                "--status": "0x800",
            },
        ),
    ]
    return ToolData(tool_templates=tool_templates, tool_priority=EToolPriority.Level10_Last, hidden=False)



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decode an Inertial Sense status value for multiple message types.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))
    parser.add_argument(
        "-t",
        "--type",
        required=True,
        choices=sorted(SUPPORTED_TYPES),
        help="Message type to decode (e.g. gps, ins, hdw, gen_fault).",
    )
    parser.add_argument(
        "-s",
        "--status",
        required=True,
        help="Status value to decode.",
    )
    parser.add_argument(
        "--status-format",
        default=INT_FORMAT_HEX,
        choices=SUPPORTED_INT_FORMATS,
        help="Input format for --status. Use 'hex' (default), 'dec' for P-log decimal values, or 'bin'.",
    )
    parser.add_argument(
        "--dataset-header-path",
        default=str(DEFAULT_DATASET_HEADER_PATH),
        help="Path to data_sets.h, or a directory containing it. Defaults to the highest repo-local is_dataset_files/KIM_* header.",
    )
    args = parser.parse_args()

    os.environ[IS_DATASET_HEADER_PATH_ENV] = str(get_path_to_inertial_sense_data_set_header(args.dataset_header_path, log_usage=False))
    status_value = parse_integer_value(args.status, parse_format=args.status_format, value_name="status")
    decode_message(args.type, status_value, input_status_format=args.status_format)


def decode_message(message_type: str, status_value: int, input_status_format: str = INT_FORMAT_HEX) -> None:
    """Route decoding to the appropriate helper for the given message type."""
    formatted_status = _format_status_pair(status_value)
    if message_type == "gps":
        from available_tools.inertial_sense_tools.decode_gps_status_utils import print_gps_status_report

        print(f"Decoding GPS Status: {formatted_status}")
        print_gps_status_report(status_value, status_format=input_status_format)
        return

    if message_type == "ins":
        from available_tools.inertial_sense_tools.decode_ins_status_utils import decode_ins_status, print_decoded_status as print_ins_status

        print(f"Decoding INS Status: {formatted_status}...")
        decoded = decode_ins_status(status_value, status_format=input_status_format)
        print_ins_status(decoded)
        print("\n" + "=" * 40 + "\n")
        return

    if message_type == "gps_hdw":
        from available_tools.inertial_sense_tools.decode_gps_hdw_status_utils import decode_gps_hdw_status, print_decoded_status as print_gps_hdw_status

        print(f"\nDecoding GPS HDW Status: {formatted_status}")
        decoded = decode_gps_hdw_status(status_value, status_format=input_status_format)
        print_gps_hdw_status(decoded)
        print("\n" + "=" * 60 + "\n")
        return

    if message_type == "gpx":
        from available_tools.inertial_sense_tools.decode_gpx_status_utils import decode_gpx_status, print_decoded_status as print_gpx_status

        print(f"\nDecoding GPX Status: {formatted_status}")
        decoded = decode_gpx_status(status_value, status_format=input_status_format)
        print_gpx_status(decoded)
        print("\n" + "=" * 60 + "\n")
        return

    if message_type == "system_hdw":
        from available_tools.inertial_sense_tools.decode_system_hdw_status_utils import decode_system_hdw_status, print_decoded_status as print_hdw_status

        print(f"\nDecoding HDW Status: {formatted_status}")
        decoded = decode_system_hdw_status(status_value, status_format=input_status_format)
        print_hdw_status(decoded)
        print("\n" + "=" * 60 + "\n")
        return

    if message_type == "gen_fault":
        from available_tools.inertial_sense_tools.decode_gen_fault_status_utils import decode_gen_fault_status, print_decoded_status as print_gen_fault_status

        print(f"\nDecoding General Fault Status: {formatted_status}")
        decoded = decode_gen_fault_status(status_value, status_format=input_status_format)
        print_gen_fault_status(decoded)
        print("\n" + "=" * 60 + "\n")
        return

    raise SystemExit(f"Unsupported message type: {message_type}")


if __name__ == "__main__":
    main()
