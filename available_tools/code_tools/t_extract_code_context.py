#!/home/vien/local_tools/MyVenvFolder/bin/python
from available_tools.code_tools.common_utils import *
from available_tools.code_tools.context_from_paths import *
from available_tools.code_tools.context_from_git_diff import *
from dev_common import *
from datetime import datetime
from typing import List, Tuple
from pathlib import Path
import sys
import argparse
script_dir = Path(__file__).resolve().parent
already_in_sys_path = str(script_dir) not in sys.path
if not already_in_sys_path:
    sys.path.insert(0, str(script_dir))


def get_tool_templates() -> List[ToolTemplate]:
    """Get tool templates for both extraction modes."""
    return get_diff_tool_templates() + get_paths_tool_templates()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Extract code context from file paths or a git diff.',
        formatter_class=argparse.RawTextHelpFormatter
    )

    # Mode selector
    parser.add_argument(ARG_EXTRACT_MODE, choices=AVAILABLE_EXTRACT_MODES, required=True,
                        help='The extraction mode to use.')

    # Common arguments
    parser.add_argument(ARG_OUTPUT_DIR_SHORT, ARG_OUTPUT_DIR_LONG, type=Path, default=Path.home() / DEFAULT_OUTPUT_BASE_DIR / DEFAULT_OUTPUT_SUBDIR,
                        help=f'The directory where the output will be saved. (default: ~/{DEFAULT_OUTPUT_BASE_DIR}/{DEFAULT_OUTPUT_SUBDIR})')
    parser.add_argument(ARG_NO_OPEN_EXPLORER, action='store_true',
                        help='Do not open Windows Explorer to highlight the output file(s) after completion.')
    parser.add_argument(ARG_MAX_FOLDERS, type=int, default=DEFAULT_MAX_FOLDERS,
                        help=f'Maximum number of context folders to keep (default: {DEFAULT_MAX_FOLDERS}).')

    # --- Arguments for 'paths' mode ---
    parser.add_argument(ARG_PATHS_SHORT, ARG_PATHS_LONG, nargs='+',
                        help='[paths mode] A list of file or directory paths to process with gitingest.')
    parser.add_argument(ARG_MAX_WORKERS, type=int, default=DEFAULT_MAX_WORKERS,
                        help='[paths mode] Maximum number of parallel threads to run.')
    parser.add_argument(ARG_INCLUDE_PATHS_PATTERN, nargs='*', default=[],
                        help='[paths mode] Additional patterns to include (e.g., "*.py" "*.md").')
    parser.add_argument(ARG_EXCLUDE_PATHS_PATTERN, nargs='*', default=[],
                        help='[paths mode] Additional patterns to exclude (e.g., "build" "*.log").')

    # --- Arguments for 'git_diff' mode ---
    parser.add_argument(ARG_PATH_LONG, type=Path, help='[git_diff mode] The path to the local git repository.')
    parser.add_argument(ARG_BASE_REF_LONG, help='[git_diff mode] The base git ref. (Ex: origin/master)')
    parser.add_argument(ARG_TARGET_REF_LONG,
                        help='[git_diff mode] The target git ref to compare against the base. Ex: origin/feat_branch)')

    # Build and set epilog with examples
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    return parser.parse_args()


def main() -> None:
    """Main function to orchestrate parallel execution."""
    args = parse_args()
    extract_mode = get_arg_value(args, ARG_EXTRACT_MODE)

    # Validate arguments based on mode
    if extract_mode == EXTRACT_MODE_PATHS:
        if not get_arg_value(args, ARG_PATHS_LONG):
            LOG(f"Error: --paths argument is required for '{EXTRACT_MODE_PATHS}' mode.", file=sys.stderr)
            sys.exit(1)
        main_paths(args)
    elif extract_mode == EXTRACT_MODE_GIT_DIFF:
        if not get_arg_value(args, ARG_PATH_LONG) or not get_arg_value(args, ARG_BASE_REF_LONG) or not get_arg_value(args, ARG_TARGET_REF_LONG):
            LOG(
                f"Error: --path, --base, and --target arguments are required for '{EXTRACT_MODE_GIT_DIFF}' mode.", file=sys.stderr)
            sys.exit(1)
        main_git_diff(args)
    else:
        LOG(f"Invalid extract mode: {extract_mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
