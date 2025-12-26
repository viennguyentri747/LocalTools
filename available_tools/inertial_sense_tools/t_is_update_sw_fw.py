#!/home/vien/local_tools/MyVenvFolder/bin/python
"""Unified tool to update Inertial Sense firmware seeds and SDK."""

import argparse
from pathlib import Path
from typing import List
from dev.dev_common import *
from available_tools.inertial_sense_tools.update_is_fws_utils import *
from available_tools.inertial_sense_tools.update_is_sdk_utils import *


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Update ONLY Firmware",
            args={
                ARG_NO_PROMPT: TRUE_STR_VALUE,
                ARG_UPDATE_FW: TRUE_STR_VALUE,
                ARG_VERSION_OR_FW_PATH: f"{DOWNLOADS_PATH}/IS-firmware_r2.6.0+2025-09-19-185429{GPX_EXTENSION}",
            },
            extra_description="For SDK: Go to branch on https://github.com/inertialsense/inertial-sense-sdk/branches -> Download inertial-sense-sdk-2.7.0-rc.zip via `< > Code` button -> Local Tab -> Download ZIP.",
            no_need_live_edit=True,
        ),
        ToolTemplate(
            name="Update ONLY SDK",
            args={
                ARG_NO_PROMPT: TRUE_STR_VALUE,
                ARG_UPDATE_SDK: TRUE_STR_VALUE,
                ARG_SDK_PATH: "~/downloads/inertial-sense-sdk-2.6.0.zip",
            },
            extra_description="For FW: Get FW (IMX + GPX or just GPX on newer version) from either:\n   1. Engineering build -> Check FW in IS gg chat.\n   2. Release build -> Check in `Assets` secition in releases Github. Ex: https://github.com/inertialsense/inertial-sense-sdk/releases/tag/2.5.1.",
        ),
        ToolTemplate(
            name="Update BOTH Firmware and SDK",
            args={
                ARG_NO_PROMPT: TRUE_STR_VALUE,
                ARG_UPDATE_FW: TRUE_STR_VALUE,
                ARG_UPDATE_SDK: TRUE_STR_VALUE,
                ARG_VERSION_OR_FW_PATH: f"{DOWNLOADS_PATH}/IS-firmware_r2.6.0+2025-09-19-185429{GPX_EXTENSION}",
                ARG_SDK_PATH: "~/downloads/inertial-sense-sdk-2.6.0.zip",
            },
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update Inertial Sense firmware packages and/or SDK from a single entry point.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument(ARG_UPDATE_FW, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Run firmware update workflow (true or false).", )
    parser.add_argument(ARG_UPDATE_SDK, type=lambda x: x.lower() == TRUE_STR_VALUE,
                        default=False, help="Run SDK update workflow (true or false).", )
    parser.add_argument("-v", ARG_VERSION_OR_FW_PATH, type=str, default=None,
                        help="Firmware .fpkg file path (e.g., ~/downloads/IS-firmware_r2.6.0+YYYY-MM-DD-HHMMSS.fpkg).", )
    parser.add_argument(ARG_SDK_PATH, ARG_PATH_SHORT, type=Path, default=None,
                        help="Path to the new SDK zip file (e.g., ~/downloads/inertial-sense-sdk-2.6.0.zip).", )
    parser.add_argument(ARG_NO_PROMPT, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="If true, run SDK workflow without confirmation prompts.", )

    args = parser.parse_args()

    if not args.update_fw and not args.update_sdk:
        parser.error("At least one of --update_fw or --update_sdk must be true.")

    if args.update_fw:
        fw_arg = get_arg_value(args, ARG_VERSION_OR_FW_PATH)
        if not fw_arg:
            parser.error("--version_or_fw_path is required when --update_fw is true.")
        fw_path = Path(fw_arg).expanduser()
        if fw_path.suffix != GPX_EXTENSION or not fw_path.is_file():
            parser.error("--version_or_fw_path must point to an existing .fpkg file.")
        run_fw_update(str(fw_path), no_prompt=args.no_prompt)

    if args.update_sdk:
        if args.sdk_path is None:
            parser.error("--sdk_path is required when --update_sdk is true.")
        run_sdk_update(args.sdk_path, no_prompt=args.no_prompt)


if __name__ == "__main__":
    main()
