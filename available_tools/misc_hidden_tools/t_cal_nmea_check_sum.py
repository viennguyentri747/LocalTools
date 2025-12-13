#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Calculate the NMEA ASCE checksum for a provided sentence.

This tool normalizes the provided sentence (removing any leading '$' and trailing
checksum markers), computes its checksum, and prints the formatted NMEA sentence.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from dev.dev_common import *

ARG_SENTENCE = f"{ARGUMENT_LONG_PREFIX}sentence"


def get_tool_templates() -> List[ToolTemplate]:
    """Return ready-to-run examples for this tool."""
    return [
        ToolTemplate(
            name="Checksum for INS Monitor Feed",
            extra_description="Typical INS monitor sentence with multiple GNSS messages.",
            args={
                ARG_SENTENCE: "ASCE,0,PPIMU,1,PINS2,10,GNGGA,1" #Output: 26
            },
        ),
        ToolTemplate(
            name="Checksum for IMU/INS Snapshot",
            extra_description="Minimal sentence containing IMU and INS fields.",
            args={ARG_SENTENCE: "ASCE,0,PPIMU,1,PINS2,10,GNGGA,1"},
        ),
        ToolTemplate(
            name="Checksum for GNSS Idle State",
            extra_description="Example GNSS sentence when GNSS updates are disabled.",
            args={ARG_SENTENCE: "ASCE,0,GNGGA,0,GNRMC,0,GNVTG,0"},
        ),
    ]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Calculate the NMEA checksum for an ASCE-formatted sentence.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument(
        ARG_SENTENCE,
        required=True,
        help="NMEA sentence fields without leading '$' or trailing checksum (e.g. ASCE,0,PPIMU,1,...).",
    )
    return parser.parse_args()


def calculate_nmea_checksum(sentence: str) -> str:
    """Calculate NMEA checksum using XOR of all characters."""
    checksum = 0
    for char in sentence:
        checksum ^= ord(char)
    return f"{checksum:02X}"


def format_nmea_sentence(sentence: str) -> str:
    """Format complete NMEA sentence with checksum."""
    checksum = calculate_nmea_checksum(sentence)
    return f"${sentence}*{checksum}\r\n"


def normalize_sentence(raw_sentence: str) -> str:
    """Strip delimiters like '$' prefix or '*XX' suffix from a sentence."""
    stripped = raw_sentence.strip()
    if stripped.startswith("$"):
        stripped = stripped[1:]
    return stripped.split("*")[0]


def main() -> None:
    args = parse_args()
    sentence = get_arg_value(args, ARG_SENTENCE)
    normalized_sentence = normalize_sentence(sentence)
    checksum = calculate_nmea_checksum(normalized_sentence)
    # full_sentence = format_nmea_sentence(normalized_sentence)

    print("NMEA ASCE Checksum Calculator")
    print(f"Sentence: {normalized_sentence}")
    print(f"Checksum: {checksum}")
    # print(f"Full Sentence: {full_sentence}", end="")

    #Test:
    s1 = "ASCE,4,GXGGA,0,GXGLL,0,GXGSA,0,GXZDA,0,GXVTG,0,GXRMC,0,PASHR,0,INTEL,0,GPGSV_1,0,GAGSV_1,0,GLGSV_1,0"
    s2 = "ASCE,4,GXGGA,2,GXGLL,2,GXGSA,2,GXZDA,2,GXVTG,2,GXRMC,2,PASHR,2,INTEL,2,GPGSV_1,2,GAGSV_1,2,GLGSV_1,0"

    print(f"Sentence 1 '{s1}' checksum: {calculate_nmea_checksum(s1)}")
    print(f"Sentence 2 '{s2}' checksum: {calculate_nmea_checksum(s2)}")


if __name__ == "__main__":
    main()
