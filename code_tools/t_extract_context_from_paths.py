#!/usr/bin/env python3.10

import argparse
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
import shutil
import re
import tiktoken
from dev_common import *

# Constants
# Processing modes
MODE_ALL_NON_IGNORE_FILES = 'default'
MODE_CMAKELISTS = 'cmake'
MODE_ALL_FILES = 'all'
AVAILABLE_MODES = [MODE_ALL_NON_IGNORE_FILES, MODE_CMAKELISTS, MODE_ALL_FILES]

# Default paths
DEFAULT_OUTPUT_BASE_DIR = 'testing'
DEFAULT_OUTPUT_SUBDIR = '.ai_context'

# Folder rotation settings
CONTEXT_FOLDER_PREFIX = 'context_paths_'
DEFAULT_MAX_FOLDERS = 5

# Commands
CMD_GITINGEST = 'gitingest'
CMD_WSLPATH = 'wslpath'
CMD_EXPLORER = 'explorer.exe'

# File patterns
PATTERN_CMAKELISTS = 'CMakeLists.txt'
EXCLUDE_PATTERNS_DEFAULT = [
    '.*', 'cmake*', 'build', 'Build', 'BUILD', '*.cmake',
    'node_modules', '__pycache__', '*.pyc', '*.pyo',
    '.git', '.svn', '.hg', '*.log', '*.tmp', "MyVenvFolder", "tmp_output"
]

# Command line arguments
ARG_OUTPUT_DIR_SHORT = '-o'
ARG_OUTPUT_DIR_LONG = '--output-dir'
ARG_MODE_SHORT = '-m'
ARG_MODE_LONG = '--mode'
ARG_INCLUDE_PATTERN = '--include-pattern'
ARG_EXCLUDE_PATTERN = '--exclude-pattern'
ARG_MAX_WORKERS = '--max-workers'
ARG_NO_OPEN_EXPLORER = '--no-open-explorer'
ARG_MAX_FOLDERS = '--max-folders'

GIT_INGEST_OUTPUT_FLAG = '--output'
GIT_INGEST_INCLUDE_FLAG = '--include-pattern'
GIT_INGEST_EXCLUDE_FLAG = '--exclude-pattern'

# Default values
DEFAULT_MAX_WORKERS = 10

# File extensions and suffixes
TXT_EXTENSION = '.txt'
UNDERSCORE = '_'
HYPHEN = '-'

# WSL specific
WSL_SELECT_FLAG = '/select,'

# Messages
MSG_INFO_PREFIX = '[INFO]'
MSG_SUCCESS_PREFIX = '[SUCCESS]'
MSG_ERROR_PREFIX = '[ERROR]'
MSG_WARNING_PREFIX = '[WARNING]'
MSG_FATAL_PREFIX = '[FATAL]'

MSG_GITINGEST_NOT_FOUND = "The 'gitingest' command was not found. Please ensure it is installed and in your system's PATH."
MSG_GITINGEST_NOT_AVAILABLE = "The 'gitingest' command is not available in your PATH. Please install it first."
MSG_EXPLORER_WSL_ONLY = "Explorer integration only available in WSL environment"
MSG_ALL_PROCESSED_SUCCESS = "🎉 All paths processed successfully."

# Summary formatting
SUMMARY_SEPARATOR = "="*20 + " SUMMARY " + "="*20
SUCCESS_EMOJI = "✅"
FAILURE_EMOJI = "❌"
CELEBRATION_EMOJI = "🎉"

# Mode descriptions
MODE_DESCRIPTIONS = {
    MODE_ALL_NON_IGNORE_FILES: "Exclude dotfiles and common build artifacts (default)",
    MODE_CMAKELISTS: "Include only CMakeLists.txt files",
    MODE_ALL_FILES: "Include all files (no excludes)"
}

def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Multiple Folder with Common Exclude Patterns",
            description="Process multiple repos with specific file patterns",
            args={
                ARG_MODE_LONG: MODE_ALL_FILES,
                ARG_EXCLUDE_PATTERN: [".git", ".vscode"],
                ARG_PATHS_LONG: ["~/core_repos/intellian_pkg/", "~/ow_sw_tools/"],
            }
        ),
        ToolTemplate(
            name="Multiple Folder with Include + Exclude Patterns",
            description="Process multiple repos with specific file patterns",
            args={
                ARG_MODE_LONG: MODE_ALL_FILES,
                ARG_EXCLUDE_PATTERN: [".git", ".vscode"],
                ARG_INCLUDE_PATTERN: ["*.py", "*.md", "*.cpp", "*.c", "*.h"],
                ARG_PATHS_LONG: ["~/core_repos/intellian_pkg/", "~/ow_sw_tools/"],
            }
        ),
    ]


def rotate_context_folders(output_dir: Path, max_folders: int) -> None:
    """
    Rotate context folders by keeping only the most recent n folders.

    Args:
        output_dir: Base directory containing context folders
        max_folders: Maximum number of folders to keep (default: 5)
    """
    if not output_dir.exists():
        return

    # Find all folders matching the context prefix pattern
    context_folders = []
    pattern = rf"^{re.escape(CONTEXT_FOLDER_PREFIX)}\d{{8}}_\d{{6}}$"

    for item in output_dir.iterdir():
        if item.is_dir() and re.match(pattern, item.name):
            context_folders.append(item)

    # Sort by modification time (newest first)
    context_folders.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    # Remove excess folders
    folders_to_remove = context_folders[max_folders:]

    if folders_to_remove:
        LOG(f"Rotating folders: keeping {min(len(context_folders), max_folders)} most recent context folders")
        for folder in folders_to_remove:
            try:
                shutil.rmtree(folder)
                LOG(f"Removed old context folder: {folder.name}")
            except Exception as e:
                LOG(f"Failed to remove folder {folder.name}: {e}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Run gitingest on multiple file or directory paths in parallel with different modes.',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.formatter_class = argparse.RawTextHelpFormatter
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument(ARG_PATHS_SHORT, ARG_PATHS_LONG, nargs='+', required=True,
                        help='A list of file or directory paths to process with gitingest.')
    parser.add_argument(ARG_OUTPUT_DIR_SHORT, ARG_OUTPUT_DIR_LONG, type=Path, default=Path.home() / DEFAULT_OUTPUT_BASE_DIR / DEFAULT_OUTPUT_SUBDIR,
                        help=f'The directory where the output text files will be saved. (default: ~/{DEFAULT_OUTPUT_BASE_DIR}/{DEFAULT_OUTPUT_SUBDIR})')
    parser.add_argument(ARG_MODE_SHORT, ARG_MODE_LONG, choices=AVAILABLE_MODES, default=MODE_ALL_NON_IGNORE_FILES, help=f'''Processing mode:
  {MODE_ALL_NON_IGNORE_FILES}: {MODE_DESCRIPTIONS[MODE_ALL_NON_IGNORE_FILES]}
  {MODE_CMAKELISTS}: {MODE_DESCRIPTIONS[MODE_CMAKELISTS]}
  {MODE_ALL_FILES}: {MODE_DESCRIPTIONS[MODE_ALL_FILES]}''')
    parser.add_argument(ARG_INCLUDE_PATTERN, nargs='*', default=[],
                        help='Additional patterns to include (e.g., "*.py" "*.md").')
    parser.add_argument(ARG_EXCLUDE_PATTERN, nargs='*', default=[],
                        help='Additional patterns to exclude (e.g., "build" "*.log").')
    parser.add_argument(ARG_MAX_WORKERS, type=int, default=DEFAULT_MAX_WORKERS,
                        help='Maximum number of parallel threads to run.')
    parser.add_argument(ARG_NO_OPEN_EXPLORER, action='store_true',
                        help='Do not open Windows Explorer to highlight the output file(s) after completion.')
    parser.add_argument(ARG_MAX_FOLDERS, type=int, default=DEFAULT_MAX_FOLDERS,
                        help=f'Maximum number of context folders to keep (default: {DEFAULT_MAX_FOLDERS}).')
    return parser.parse_args()


def get_mode_patterns(mode: str) -> Tuple[List[str], List[str]]:
    """
    Get the default include and exclude patterns for a given mode.

    Args:
        mode: The processing mode

    Returns:
        A tuple of (include_patterns, exclude_patterns)
    """
    if mode == MODE_CMAKELISTS:
        return [PATTERN_CMAKELISTS], []
    elif mode == MODE_ALL_FILES:
        return [], []
    elif mode == MODE_ALL_NON_IGNORE_FILES:
        return [], EXCLUDE_PATTERNS_DEFAULT
    else:
        return [], []


def run_gitingest(input_path: Path, output_dir: Path, include: List[str], exclude: List[str], mode: str) -> Tuple[bool, str, Path]:
    """
    Constructs and runs a single gitingest command for a given path.

    Args:
        input_path: The file or directory to be processed.
        output_dir: The directory to save the output file.
        include: A list of include patterns for gitingest.
        exclude: A list of exclude patterns for gitingest.
        mode: The processing mode for filename suffix.

    Returns:
        A tuple containing a success boolean, a message, and the output path.
    """
    # Construct a descriptive output filename with mode suffix
    if input_path.is_dir():
        parent = input_path.parent.name
        folder = input_path.name
        mode_suffix = mode.upper().replace(UNDERSCORE, '')
        output_filename = f"{parent}{HYPHEN}{folder}{UNDERSCORE}{mode_suffix}{TXT_EXTENSION}"
    else:
        mode_suffix = mode.upper().replace(UNDERSCORE, '')
        output_filename = f"{input_path.stem}{UNDERSCORE}{mode_suffix}{TXT_EXTENSION}"

    output_path = output_dir / output_filename

    # Build the command for subprocess
    command = [CMD_GITINGEST, str(input_path), GIT_INGEST_OUTPUT_FLAG, str(output_path)]

    for pattern in include:
        command.extend([GIT_INGEST_INCLUDE_FLAG, pattern])
    for pattern in exclude:
        command.extend([GIT_INGEST_EXCLUDE_FLAG, pattern])

    try:
        LOG(f"Starting gitingest for '{input_path}' in {mode} mode... Commmand:\n{' '.join(command)}")
        process = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        success_msg = f"{MSG_SUCCESS_PREFIX} Finished gitingest for '{input_path}'. Output saved to '{output_path}'."
        if process.stdout:
            success_msg += f"\n{process.stdout.strip()}"
        return True, success_msg, output_path
    except FileNotFoundError:
        return False, f"{MSG_ERROR_PREFIX} {MSG_GITINGEST_NOT_FOUND}", output_path
    except subprocess.CalledProcessError as e:
        error_msg = (
            f"{MSG_ERROR_PREFIX} gitingest failed for '{input_path}' with exit code {e.returncode}.\n"
            f"  Command: {' '.join(command)}\n"
            f"  Stderr: {e.stderr.strip()}"
        )
        return False, error_msg, output_path
    except Exception as e:
        return False, f"{MSG_ERROR_PREFIX} An unexpected error occurred while processing '{input_path}': {e}", output_path


def open_explorer_to_file(file_path: Path) -> None:
    """
    Open Windows Explorer and highlight the specified file (WSL only).

    Args:
        file_path: The file to highlight in Explorer
    """
    try:
        # Check if we're in WSL
        if shutil.which(CMD_WSLPATH) and shutil.which(CMD_EXPLORER):
            # Convert WSL path to Windows path
            result = subprocess.run(
                [CMD_WSLPATH, "-w", str(file_path)],
                capture_output=True,
                text=True,
                check=True
            )
            windows_path = result.stdout.strip()

            # Open Explorer with file selected
            subprocess.run(
                [CMD_EXPLORER, WSL_SELECT_FLAG, windows_path], check=True
            )
            LOG(f"Opened Explorer to highlight '{file_path}'")
        else:
            LOG(f"{MSG_EXPLORER_WSL_ONLY}")
    except Exception as e:
        LOG(f"Failed to open Explorer: {e}")


def merge_output_files(output_files: List[Path], output_dir: Path) -> Path:
    """
    Merge multiple output files into a single file.

    Args:
        output_files: List of output file paths to merge
        output_dir: Directory where the merged file will be saved

    Returns:
        Path to the merged file
    """
    file_names = [f.name for f in output_files]
    LOG(f"Merging files {', '.join(file_names)} into a single file...")

    # Create a descriptive filename for the merged file (no timestamp since already in timestamped folder)
    merged_filename = f"merged_context{TXT_EXTENSION}"
    merged_path = output_dir / merged_filename

    # Merge all files
    with open(merged_path, 'w', encoding='utf-8') as merged_file:
        for i, file_path in enumerate(output_files):
            merged_file.write(f"\n\n{'='*50}\n")
            merged_file.write(f"FILE {i+1}/{len(output_files)}: {file_path.name}\n")
            merged_file.write(f"{'='*50}\n\n")

            with open(file_path, 'r', encoding='utf-8') as input_file:
                merged_file.write(input_file.read())

    LOG(f"Merged {len(output_files)} files into '{merged_path}'")
    return merged_path


def create_log_file(args: argparse.Namespace, output_dir: Path, timestamp: str) -> Path:
    """
    Create a log file with context information.

    Args:
        args: Parsed command-line arguments
        output_dir: Directory where the log file will be saved
        timestamp: Timestamp string for the log entry

    Returns:
        Path to the created log file
    """
    log_path = output_dir / "log.txt"

    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write(f"Extract Source Context Log - {timestamp}\n")
        log_file.write(f"{'='*50}\n\n")

        log_file.write("Arguments:\n")
        log_file.write(f"  Paths: {args.paths}\n")
        log_file.write(f"  Output directory: {args.output_dir}\n")
        log_file.write(f"  Mode: {args.mode}\n")
        log_file.write(f"  Include patterns: {args.include_pattern}\n")
        log_file.write(f"  Exclude patterns: {args.exclude_pattern}\n")
        log_file.write(f"  Max workers: {args.max_workers}\n")
        log_file.write(f"  Max folders: {args.max_folders}\n")
        log_file.write(f"  No open explorer: {args.no_open_explorer}\n")

        # Get mode-specific patterns
        mode_include, mode_exclude = get_mode_patterns(args.mode)
        log_file.write(f"\nMode-specific patterns:\n")
        log_file.write(f"  Include: {mode_include}\n")
        log_file.write(f"  Exclude: {mode_exclude}\n")

        # Combined patterns
        final_include = mode_include + args.include_pattern
        final_exclude = mode_exclude + args.exclude_pattern
        log_file.write(f"\nFinal patterns:\n")
        log_file.write(f"  Include: {final_include}\n")
        log_file.write(f"  Exclude: {final_exclude}\n")

    return log_path


def main() -> None:
    """Main function to orchestrate parallel execution."""
    args = parse_args()

    # Verify gitingest command exists before starting threads
    if not shutil.which(CMD_GITINGEST):
        LOG(f"{MSG_GITINGEST_NOT_AVAILABLE}", file=sys.stderr)
        sys.exit(1)

    # Create timestamp for this run
    timestamp = subprocess.run(['date', '+%Y%m%d_%H%M%S'], capture_output=True, text=True).stdout.strip()

    # Rotate existing context folders before creating a new one
    rotate_context_folders(args.output_dir, args.max_folders - 1)  # Minus 1 because we will create a new one

    # Create timestamped output directory
    final_output_dir_name = f"{CONTEXT_FOLDER_PREFIX}{timestamp}"
    final_output_dir = args.output_dir / final_output_dir_name
    final_output_dir.mkdir(parents=True, exist_ok=True)

    # Create log file
    log_path = create_log_file(args, final_output_dir, timestamp)
    LOG(f"Log file created at: {log_path}")

    # Get mode-specific patterns
    mode_include, mode_exclude = get_mode_patterns(args.mode)

    # Combine mode patterns with user-specified patterns
    final_include = mode_include + args.include_pattern
    final_exclude = mode_exclude + args.exclude_pattern

    LOG(f"Running in '{args.mode}' mode")
    LOG(f"Output directory: {final_output_dir}")
    if final_include:
        LOG(f"Include patterns: {final_include}")
    if final_exclude:
        LOG(f"Exclude patterns: {final_exclude}")

    successes = []
    failures = []
    output_files = []

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit all jobs to the thread pool
        future_to_path = {
            executor.submit(run_gitingest, Path(p), final_output_dir, final_include, final_exclude, args.mode): p
            for p in args.paths
        }

        # Process results as they are completed
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                is_success, message, output_path = future.result()
                LOG(message)
                if is_success:
                    successes.append(path)
                    output_files.append(output_path)
                else:
                    failures.append(path)
            except Exception as exc:
                LOG(f"Path '{path}' generated an exception: {exc}")
                failures.append(path)

    # LOG a final summary of results
    LOG(f"\n{SUMMARY_SEPARATOR}")
    if successes:
        LOG(f"{SUCCESS_EMOJI} Successfully processed {len(successes)} paths in '{args.mode}' mode.")
    if failures:
        LOG(f"{FAILURE_EMOJI} Failed to process {len(failures)} paths:", file=sys.stderr)
        for f in failures:
            LOG(f"  - {f}", file=sys.stderr)
    output_file_path = None

    if len(output_files) == 1:
        output_file_path = output_files[0]
    else:
        output_file_path = merge_output_files(output_files, final_output_dir)
    with open(output_file_path, "r", encoding="utf-8") as f:
        file_contents = f.read()

        encoding = tiktoken.get_encoding("cl100k_base")
        token_count = len(encoding.encode(file_contents))
        filename = os.path.basename(output_file_path)
        LOG(f"{LINE_SEPARATOR}")
        LOG(f"Estimated token count for {filename}: {beautify_number(token_count)}")

    # Open explorer if requested
    if not args.no_open_explorer and output_file_path:
        if len(output_files) == 1:
            # Single file - open it directly
            open_explorer_to_file(output_file_path)
        else:
            # Multiple files - merge them first, then open the merged file
            open_explorer_to_file(output_file_path)

    if failures:
        sys.exit(1)
    else:
        LOG(f"{CELEBRATION_EMOJI} {MSG_ALL_PROCESSED_SUCCESS}")


if __name__ == '__main__':
    main()
