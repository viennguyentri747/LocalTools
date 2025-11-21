#!/home/vien/local_tools/MyVenvFolder/bin/python

import argparse  # Import the argparse module for named command-line arguments
import re  # Import regex for string pattern matching
from pathlib import Path
from typing import List
from dev_common.tools_utils import ToolTemplate, build_examples_epilog, display_content_to_copy


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


def convert_win_to_wsl_path(win_path: str) -> str:
    """
    Converts a Windows file path to a WSL (Windows Subsystem for Linux) path.
    """

    # 1. Clean input
    # Remove surrounding quotes if the user pasted them from "Copy as path"
    clean_path = win_path.strip('"').strip("'")

    # 2. Normalize slashes
    # Convert Windows backslashes to Linux forward slashes
    universal_path = clean_path.replace("\\", "/")

    wsl_path = universal_path

    # 3. Handle Drive Letters
    # Look for pattern like "C:/" or "d:/" at the start
    drive_match = re.match(r'^([a-zA-Z]):/(.*)', universal_path)

    if drive_match:
        drive_letter = drive_match.group(1).lower()  # Convert 'C' to 'c'
        rest_of_path = drive_match.group(2)

        # Construct standard WSL mount path: /mnt/<drive>/<path>
        wsl_path = f"/mnt/{drive_letter}/{rest_of_path}"

    return wsl_path


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
