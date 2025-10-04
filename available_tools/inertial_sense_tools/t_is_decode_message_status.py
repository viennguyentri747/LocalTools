#!/home/vien/local_tools/MyVenvFolder/bin/python

import argparse
from pathlib import Path
from typing import List, Tuple

from dev_common.tools_utils import ToolTemplate, build_examples_epilog
from inertial_sense_tools.decode_gps_status_utils import print_gps_status_report
from inertial_sense_tools.decode_hdw_status_utils import (
    decode_hdw_status,
    print_decoded_status as print_hdw_status,
)
from inertial_sense_tools.decode_ins_status_utils import (
    decode_ins_status,
    print_decoded_status as print_ins_status,
)

SUPPORTED_TYPES: Tuple[str, ...] = ("gps", "hdw", "ins")

def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Decode INS Status",
            extra_description="Decode INS status integer",
            args={
                "--type": "ins",
                "--status": "0x00031000",
            },
        ),
        ToolTemplate(
            name="Decode GPS Status",
            extra_description="Decode GPS status integer",
            args={
                "--type": "gps",
                "--status": "0x312",
            },
        ),
        ToolTemplate(
            name="Decode HDW Status",
            extra_description="Decode hardware status integer",
            args={
                "--type": "hdw",
                "--status": "0x2088010",
            },
        ),
    ]

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decode an Inertial Sense status value for multiple message types.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument(
        "-t",
        "--type",
        required=True,
        choices=sorted(SUPPORTED_TYPES),
        help="Message type to decode (e.g. gps, ins, hdw).",
    )
    parser.add_argument(
        "-s",
        "--status",
        required=True,
        help="Status value to decode (accepts decimal or hex such as 0x1234).",
    )
    args = parser.parse_args()

    try:
        status_value = int(args.status, 0)
    except ValueError as exc:
        raise SystemExit(f"Failed to parse status value '{args.status}': {exc}") from exc

    decode_message(args.type, args.status, status_value)


def decode_message(message_type: str, raw_status: str, status_value: int) -> None:
    """Route decoding to the appropriate helper for the given message type."""
    if message_type == "gps":
        print(f"Decoding GPS Status: {raw_status} (0x{status_value:08X})")
        print_gps_status_report(status_value)
        return

    if message_type == "ins":
        print(f"Decoding INS Status: {raw_status} (0x{status_value:08X})...")
        decoded = decode_ins_status(status_value)
        print_ins_status(decoded)
        print("\n" + "=" * 40 + "\n")
        return

    if message_type == "hdw":
        print(f"\nDecoding HDW Status: 0x{status_value:08X} ({status_value})")
        decoded = decode_hdw_status(status_value)
        print_hdw_status(decoded)
        print("\n" + "=" * 60 + "\n")
        return

    raise SystemExit(f"Unsupported message type: {message_type}")


if __name__ == "__main__":
    main()
