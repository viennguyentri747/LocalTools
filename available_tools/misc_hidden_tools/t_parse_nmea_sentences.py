#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
"""Parse one NMEA sentence using pynmea2 and print a structured view."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List

from dev.dev_common.custom_structures import ToolData
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog

try:
    import pynmea2
except ImportError as exc:  # pragma: no cover - depends on environment
    pynmea2 = None
    PYNMEA2_IMPORT_ERROR = exc
else:
    PYNMEA2_IMPORT_ERROR = None

ARG_SENTENCE = "--sentence"
ARG_CHECKSUM = "--check-checksum"


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Parse GGA sentence",
            extra_description="Parse a standard GPS fix data sentence.",
            args={ARG_SENTENCE: "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"},
        ),
        ToolTemplate(
            name="Parse RMC sentence with checksum validation",
            extra_description="RMC sentence with strict checksum checking.",
            args={
                ARG_SENTENCE: "$GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191194,020.3,E*68",
                ARG_CHECKSUM: True,
            },
        ),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse one NMEA sentence and print parsed fields as JSON.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_SENTENCE, required=True, help="Full NMEA sentence (with or without checksum).")
    parser.add_argument(ARG_CHECKSUM, action="store_true", help="Validate checksum strictly while parsing.")
    return parser.parse_args()


def nmea_message_to_dict(msg: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "raw": str(msg).strip(),
        "talker": getattr(msg, "talker", ""),
        "sentence_type": getattr(msg, "sentence_type", ""),
        "parser_class": type(msg).__name__,
    }
    for field in getattr(msg, "fields", []):
        if isinstance(field, tuple):
            field_key = field[1] if len(field) >= 2 else None
        else:
            field_key = str(field)
        if not field_key:
            continue
        payload[field_key] = getattr(msg, field_key, None)
    return payload


def main() -> None:
    if pynmea2 is None:
        print(f"Missing dependency: pynmea2 ({PYNMEA2_IMPORT_ERROR})", file=sys.stderr)
        print("Install with: pip install pynmea2", file=sys.stderr)
        raise SystemExit(2)

    args = parse_args()
    try:
        msg = pynmea2.parse(args.sentence.strip(), check=args.check_checksum)
    except pynmea2.ParseError as exc:
        print(f"Failed to parse NMEA sentence: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(json.dumps(nmea_message_to_dict(msg), indent=2, default=str))


if __name__ == "__main__":
    main()
