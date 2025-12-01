#!/home/vien/local_tools/MyVenvFolder/bin/python

import argparse  # Import the argparse module for named command-line arguments
import re  # Import regex for string pattern matching
from pathlib import Path
from typing import List
from dev_common.tools_utils import ToolTemplate, build_examples_epilog, convert_win_to_wsl_path, display_content_to_copy


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Standard C Drive",
            extra_description="Convert a standard C drive path to WSL",
            args={
                "--win_path": r"C:\Users\Vien\Documents\file.txt",
            }
        ),
        ToolTemplate(
            name="Secondary Drive with Spaces",
            extra_description="Convert a path on D drive containing spaces",
            args={
                "--win_path": r'"D:\Project Data\results.json"',
            }
        ),
    ]


# --- Example Usage ---
if __name__ == "__main__":
    # Create an ArgumentParser object
    parser = argparse.ArgumentParser(
        description="Convert Windows file paths to WSL (Windows Subsystem for Linux) format."
    )
    parser.formatter_class = argparse.RawTextHelpFormatter
    # Fill help epilog from templates
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    # Add argument for the Windows path
    parser.add_argument(
        "--win_path",
        type=str,
        required=True,
        help="The Windows path string (e.g., 'C:\\Users\\Name')."
    )

    # Parse the arguments provided by the user
    args = parser.parse_args()

    # Access the parsed arguments
    input_path = args.win_path

    print(f"Converting path: {input_path}\n")

    result_path: str = convert_win_to_wsl_path(input_path)

    display_content_to_copy(f"\"{result_path}\"")
