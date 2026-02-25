#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python

import argparse
from pathlib import Path
from typing import List, Tuple

from dev.dev_common.custom_structures import ToolData
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog
from available_tools.inertial_sense_tools.decode_gen_fault_status_utils import (
    decode_gen_fault_status,
    print_decoded_status as print_gen_fault_status,
)
from available_tools.inertial_sense_tools.decode_gps_status_utils import print_gps_status_report
from available_tools.inertial_sense_tools.decode_system_hdw_status_utils import (
    decode_system_hdw_status,
    print_decoded_status as print_hdw_status,
)
from available_tools.inertial_sense_tools.decode_gps_hdw_status_utils import (
    decode_gps_hdw_status,
    print_decoded_status as print_gps_hdw_status,
)
from available_tools.inertial_sense_tools.decode_ins_status_utils import (
    decode_ins_status,
    print_decoded_status as print_ins_status,
)

SUPPORTED_TYPES: Tuple[str, ...] = ("gen_fault", "gps", "gps_hdw", "system_hdw", "ins")

def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Decode INS Status Integer",
            extra_description="Check it in `insStatus` in ``tail -F /var/log/ins_monitor_log | grep -i INS1Msg`",
            args={
                "--type": "ins",
                "--status": "0x50351f7",
            },
        ),
        ToolTemplate(
            name="Decode GPS Status Integer",
            extra_description="Check it in `status` in `tail -F /var/log/ins_monitor_log | grep -i DID_GPS1_POS`",
            args={
                "--type": "gps",
                "--status": "0x312",
            },
        ),
        ToolTemplate(
            name="Decode GPS Hardware Status Integer",
            extra_description="Check it in `status` in DID_GPX_HDW_STATUS.",
            args={
                "--type": "gps_hdw",
                "--status": "0x80010001",
            },
        ),
        ToolTemplate(
            name="Decode SYSTEM HDW Status Integer",
            extra_description="Decode SYSTEM hardware status integer, `hdwStatus` in `tail -F /var/log/ins_monitor_log | grep -i INS1Msg` or via DID_SYS_PARAMS.hdwStatus",
            args={
                "--type": "system_hdw",
                "--status": "0x2088010",
            },
        ),
        ToolTemplate(
            name="Decode General Fault Status",
            extra_description="Use enum eGenFaultCodes, check it with `tail -F /var/log/ins_monitor_log | grep -i DID_SYS_PARAMS`",
            args={
                "--type": "gen_fault",
                "--status": "0x800",
            },
        ),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decode an Inertial Sense status value for multiple message types.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
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
        help="Status value to decode (accepts decimal or hex such as 0x1234).",
    )
    args = parser.parse_args()

    status_value = int(args.status, 0)
    decode_message(args.type, status_value)


def decode_message(message_type: str, status_value: str) -> None:
    """Route decoding to the appropriate helper for the given message type."""
    if message_type == "gps":
        print(f"Decoding GPS Status: {status_value}")
        print_gps_status_report(status_value)
        return

    if message_type == "ins":
        print(f"Decoding INS Status: {status_value}...")
        decoded = decode_ins_status(status_value)
        print_ins_status(decoded)
        print("\n" + "=" * 40 + "\n")
        return

    if message_type == "gps_hdw":
        print(f"\nDecoding GPS HDW Status: 0x{status_value:08X} ({status_value})")
        decoded = decode_gps_hdw_status(status_value)
        print_gps_hdw_status(decoded)
        print("\n" + "=" * 60 + "\n")
        return

    if message_type == "system_hdw":
        print(f"\nDecoding HDW Status: 0x{status_value:08X} ({status_value})")
        decoded = decode_system_hdw_status(status_value)
        print_hdw_status(decoded)
        print("\n" + "=" * 60 + "\n")
        return

    if message_type == "gen_fault":
        print(f"\nDecoding General Fault Status: 0x{status_value:08X} ({status_value})")
        decoded = decode_gen_fault_status(status_value)
        print_gen_fault_status(decoded)
        print("\n" + "=" * 60 + "\n")
        return

    raise SystemExit(f"Unsupported message type: {message_type}")


if __name__ == "__main__":
    main()
