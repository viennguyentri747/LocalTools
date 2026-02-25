#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
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
            name="Update BOTH Firmware and SDK",
            args={
                ARG_NO_PROMPT: TRUE_STR_VALUE,
                ARG_UPDATE_FW: TRUE_STR_VALUE,
                ARG_UPDATE_SDK: TRUE_STR_VALUE,
                ARG_FPKG_ONLY: FALSE_STR_VALUE,
                # ARG_SDK_PATH: "~/downloads/inertial-sense-sdk-2.6.0.zip",
                ARG_OW_SW_BASE_BRANCH: BRANCH_MANPACK_MASTER,
                ARG_INSENSE_CL_BASE_BRANCH: BRANCH_MANPACK_MASTER,
                ARG_VERSION_OR_FPKG_FW_PATH: f"{DOWNLOADS_PATH}/IS-firmware_r2.6.0+2025-09-19-185429{GPX_EXTENSION}",
                ARG_SDK_BRANCH: "2.7.0-rc",
            },
        ),
        ToolTemplate(
            name="Update ONLY Firmware",
            args={
                ARG_NO_PROMPT: TRUE_STR_VALUE,
                ARG_UPDATE_FW: TRUE_STR_VALUE,
                ARG_FPKG_ONLY: FALSE_STR_VALUE,
                ARG_OW_SW_BASE_BRANCH: BRANCH_MANPACK_MASTER,
                ARG_VERSION_OR_FPKG_FW_PATH: f"{DOWNLOADS_PATH}/IS-firmware_r2.6.0+2025-09-19-185429{GPX_EXTENSION}",
            },
            extra_description="For FW: Get FW (IMX + GPX or just GPX on newer version) from either:\n   1. Engineering build -> Check FW in IS gg chat.\n   2. Release build -> Check in `Assets` section in releases Github. Ex: https://github.com/inertialsense/inertial-sense-sdk/releases/tag/2.5.1.",
            no_need_live_edit=True,
        ),
        ToolTemplate(
            name="Update ONLY SDK via branch",
            args={
                ARG_NO_PROMPT: TRUE_STR_VALUE,
                ARG_UPDATE_SDK: TRUE_STR_VALUE,
                ARG_INSENSE_CL_BASE_BRANCH: BRANCH_MANPACK_MASTER,
                ARG_SDK_BRANCH: "2.7.0-rc",
            },
            extra_description="SDK branch-based update. Use --sdk_path if you prefer a zip. For SDK zip: Go to branch on https://github.com/inertialsense/inertial-sense-sdk/branches -> Download inertial-sense-sdk-2.7.0-rc.zip via `< > Code` button -> Local Tab -> Download ZIP.",
        ),
    ]



def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update Inertial Sense firmware packages and/or SDK from a single entry point.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_UPDATE_FW, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Run firmware update workflow (true or false).", )
    parser.add_argument(ARG_UPDATE_SDK, type=lambda x: x.lower() == TRUE_STR_VALUE,
                        default=False, help="Run SDK update workflow (true or false).", )
    parser.add_argument("-v", ARG_VERSION_OR_FPKG_FW_PATH, type=str, default=None,
                        help="Firmware .fpkg file path (e.g., ~/downloads/IS-firmware_r2.6.0+YYYY-MM-DD-HHMMSS.fpkg).", )
    parser.add_argument(ARG_SDK_PATH, ARG_PATH_SHORT, type=Path, default=None,
                        help="SDK zip path (optional; if omitted, --sdk_branch is used). Ex: ~/downloads/inertial-sense-sdk-2.6.0.zip.", )
    parser.add_argument(ARG_SDK_BRANCH, type=str, default=None,
                        help="SDK branch name to clone (optional; preferred if provided). Ex: 2.7.0-rc.", )
    parser.add_argument(ARG_FPKG_ONLY, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="If true, only update the .fpkg (skip IMX .hex extraction/update).", )
    parser.add_argument(ARG_NO_PROMPT, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="If true, run SDK workflow without confirmation prompts.", )
    parser.add_argument(ARG_OW_SW_BASE_BRANCH, type=str, default=None,
                        help="Base branch to use for OW SW firmware updates (optional).", )
    parser.add_argument(ARG_INSENSE_CL_BASE_BRANCH, type=str, default=None,
                        help="Base branch to use for insense_cl tool updates in the SDK repo (optional).", )

    args = parser.parse_args()

    if not args.update_fw and not args.update_sdk:
        parser.error("At least one of --update_fw or --update_sdk must be true.")

    if args.update_fw:
        fw_arg = get_arg_value(args, ARG_VERSION_OR_FPKG_FW_PATH)
        if not fw_arg:
            parser.error("--version_or_fw_path is required when --update_fw is true.")
        fw_path = Path(fw_arg).expanduser()
        if fw_path.suffix != GPX_EXTENSION or not fw_path.is_file():
            parser.error("--version_or_fw_path must point to an existing .fpkg file.")
        run_fw_update(str(fw_path), no_prompt=args.no_prompt, base_branch=args.ow_sw_base_branch, fpkg_only=args.fpkg_only)

    if args.update_sdk:
        sdk_branch = get_arg_value(args, ARG_SDK_BRANCH)
        if sdk_branch:
            run_sdk_update_with_branch(sdk_branch, no_prompt=args.no_prompt, base_branch=args.insense_cl_base_branch)
            return
        if args.sdk_path is not None:
            run_sdk_update_with_zip(args.sdk_path, no_prompt=args.no_prompt, base_branch=args.insense_cl_base_branch)
            return
        LOG_EXCEPTION(ValueError("Missing SDK branch/path"), msg="--sdk_branch or --sdk_path must be provided when --update_sdk is true.", exit=False)
        return


if __name__ == "__main__":
    main()
