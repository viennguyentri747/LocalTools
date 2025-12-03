#!/home/vien/local_tools/MyVenvFolder/bin/python

import argparse
from pathlib import Path
from typing import Callable, Dict, List

from dev_common.constants import ARG_MODE, ARG_PATH_LONG
from dev_common.tools_utils import (
    ToolTemplate,
    build_examples_epilog,
    convert_win_to_wsl_path,
    convert_wsl_to_win_path,
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
                f"{ARG_PATH_LONG}": r"C:\Users\Vien\Documents\file.txt",
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
                f"{ARG_PATH_LONG}": "/mnt/c/Users/Vien/Documents/file.txt",
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

    print(f"Converting path ({conversion_mode}): {input_path}\n")

    if conversion_mode not in MODE_HANDLERS:
        raise ValueError(f"Unsupported mode: {conversion_mode}")

    result_path: str = MODE_HANDLERS[conversion_mode](input_path)

    display_content_to_copy(f'"{result_path}"')
