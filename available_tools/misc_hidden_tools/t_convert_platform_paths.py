#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python

import argparse
from pathlib import Path
from typing import Callable, Dict, List

from dev.dev_common.constants import ARG_MODE, ARG_PATH_LONG
from dev.dev_common.core_independent_utils import LOG, is_platform_windows
from dev.dev_common.core_utils import convert_wsl_to_win_path
from dev.dev_common.tools_utils import (
    ToolTemplate,
    build_examples_epilog,
    convert_win_to_wsl_path,
    display_content_to_copy,
)

MODE_WIN_TO_WSL = "win_to_wsl"
MODE_WSL_TO_WIN = "wsl_to_win"
MODE_CHOICES = (MODE_WIN_TO_WSL, MODE_WSL_TO_WIN)
DEFAULT_MODE = MODE_WIN_TO_WSL

MODE_HANDLERS: Dict[str, Callable[[str], str]] = {
    MODE_WIN_TO_WSL: convert_win_to_wsl_path,
    MODE_WSL_TO_WIN: lambda user_path: convert_wsl_to_win_path(Path(user_path)),
}


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Window path -> WSL path: Standard C Drive",
            extra_description="Convert a standard C drive path to WSL",
            args={
                f"{ARG_PATH_LONG}": r"C:\Users\Vien.Nguyen\.wslconfig",
            },
        ),
        ToolTemplate(
            name="Secondary Drive with Spaces",
            extra_description="Convert a path on D drive containing spaces",
            args={
                f"{ARG_PATH_LONG}": r'"D:\Project Data\results.json"',
            },
            hidden=True,
        ),
        ToolTemplate(
            name="WSL path -> Windows",
            extra_description="Convert a /mnt path into a Windows Explorer path",
            args={
                ARG_MODE: MODE_WSL_TO_WIN,
                f"{ARG_PATH_LONG}": "/mnt/c/Users/Vien.Nguyen/.wslconfig",
            },
        ),
    ]


# --- Example Usage ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert file paths between Windows and WSL formats."
    )
    parser.formatter_class = argparse.RawTextHelpFormatter
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument(
        ARG_MODE,
        choices=MODE_CHOICES,
        default=DEFAULT_MODE,
        help=(
            "Conversion direction. "
            f"'{MODE_WIN_TO_WSL}' expects a Windows path; '{MODE_WSL_TO_WIN}' expects a WSL/Linux path."
        ),
    )
    parser.add_argument(
        f"{ARG_PATH_LONG}",
        type=str,
        required=True,
        help="Input path to convert.",
    )

    args = parser.parse_args()

    input_path = args.path
    conversion_mode: str = args.mode
    if conversion_mode not in MODE_HANDLERS:
        raise ValueError(f"Unsupported mode: {conversion_mode}")

    LOG(f"Converting path ({conversion_mode}): {input_path}")
    result_path: str = MODE_HANDLERS[conversion_mode](input_path)
    # Determine which path to verify based on platform and conversion mode
    verify_original = (conversion_mode == MODE_WIN_TO_WSL and is_platform_windows()) or (conversion_mode == MODE_WSL_TO_WIN and not is_platform_windows())

    path_to_check = input_path if verify_original else result_path
    path_type = "original" if verify_original else "converted"
    if not Path(path_to_check).exists():
        LOG(f"Warning: The {path_type} path does not exist: {path_to_check}")
    else:
        LOG(f"The {path_type} path exists: {path_to_check}")

    display_content_to_copy(f'"{result_path}"')
