#!/usr/local/bin/local_python
"""Check whether a target bit flag is enabled in a status value."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from dev.dev_common import *
from dev.dev_common.custom_structures import ToolData
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog

ARG_STATUS = "--status"
ARG_FLAG = "--flag"


def getToolData() -> ToolData:
    tool_templates = [
        ToolTemplate(
            name="Check GPX_STATUS_COM0_RX_TRAFFIC_NOT_DECTECTED",
            extra_description="status=0x70 includes flag=0x10, so result is enabled.",
            args={ARG_STATUS: "0x70", ARG_FLAG: "0x10"},
        ),
        ToolTemplate(
            name="Disabled case",
            extra_description="status=0x20 does not include flag=0x10, so result is disabled.",
            args={ARG_STATUS: "0x20", ARG_FLAG: "0x10"},
        ),
    ]
    return ToolData(tool_templates=tool_templates, tool_priority=EToolPriority.Level10_Last, hidden=False)



def parse_int(value: str) -> int:
    """Parse int from decimal/hex/octal/binary string (e.g. 112, 0x70, 0b1110000)."""
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid integer literal: {value}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test whether a flag bit is enabled in a status value.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().get_tool_templates(), Path(__file__))
    parser.add_argument(ARG_STATUS, required=True, type=parse_int, help="Status value (e.g. 0x70).")
    parser.add_argument(ARG_FLAG, required=True, type=parse_int, help="Flag value (e.g. 0x10).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    status: int = args.status
    flag: int = args.flag

    if status < 0 or flag < 0:
        raise SystemExit("status and flag must be non-negative integers")

    is_enabled = (status & flag) == flag
    print(f"status={status} ({status:#x})")
    print(f"flag={flag} ({flag:#x})")
    print(f"masked=(status & flag) = {(status & flag)} ({(status & flag):#x})")
    print(f"enabled={is_enabled}")


if __name__ == "__main__":
    main()
