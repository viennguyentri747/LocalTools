#!/home/vien/local_tools/MyVenvFolder/bin/python

import argparse
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
import shutil
import re
import tiktoken
import os
from datetime import datetime

from dev_common import *
from dev_common.python_misc_utils import get_arg_value
from dev_common.tools_utils import ToolTemplate

# --- Constants ---

# Processing modes
EXTRACT_MODE_PATHS = 'paths'
EXTRACT_MODE_GIT_DIFF = 'git_diff'
AVAILABLE_EXTRACT_MODES = [EXTRACT_MODE_PATHS, EXTRACT_MODE_GIT_DIFF]

# Default paths
DEFAULT_OUTPUT_BASE_DIR = 'testing'
DEFAULT_OUTPUT_SUBDIR = '.ai_context'

# Folder rotation settings
CONTEXT_FOLDER_PREFIX_PATHS = 'context_paths_'
CONTEXT_FOLDER_PREFIX_DIFF = 'context_diff_'
DEFAULT_MAX_FOLDERS = 5

# Commands
CMD_GITINGEST = 'gitingest'
CMD_GIT = 'git'
CMD_WSLPATH = 'wslpath'
CMD_EXPLORER = 'explorer.exe'

# File patterns
PATTERN_CMAKELISTS = 'CMakeLists.txt'

# Command line arguments
ARG_EXTRACT_MODE = '--extract-mode'
ARG_OUTPUT_DIR_SHORT = '-o'
ARG_OUTPUT_DIR_LONG = '--output_dir'
ARG_INCLUDE_PATHS_PATTERN = '--include-paths-pattern'
ARG_EXCLUDE_PATHS_PATTERN = '--exclude-paths-pattern'
ARG_MAX_WORKERS = '--max-workers'
ARG_NO_OPEN_EXPLORER = '--no-open-explorer'
ARG_MAX_FOLDERS = '--max-folders'
ARG_BASE_REF_LONG = '--base'
ARG_TARGET_REF_LONG = '--target'

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
MSG_GIT_NOT_FOUND = "The 'git' command was not found. Please ensure it is installed and in your system's PATH."
MSG_EXPLORER_WSL_ONLY = "Explorer integration only available in WSL environment!"
MSG_ALL_PROCESSED_SUCCESS = "🎉 All paths processed successfully."
MSG_CONTEXT_EXTRACTION_SUCCESS = "🎉 Context extraction completed successfully."

# Summary formatting
SUMMARY_SEPARATOR = "="*20 + " SUMMARY " + "="*20
SUCCESS_EMOJI = "✅"
FAILURE_EMOJI = "❌"
CELEBRATION_EMOJI = "🎉"


def get_tool_templates() -> List[ToolTemplate]:
    """Get tool templates for both extraction modes."""
    return [
        ToolTemplate(
            name="[paths] Multiple files with exclude GLOB patterns",
            args={
                ARG_EXTRACT_MODE: EXTRACT_MODE_PATHS,
                ARG_INCLUDE_PATHS_PATTERN: ["*"],
                ARG_EXCLUDE_PATHS_PATTERN: [".git", ".vscode"],
                ARG_PATHS_LONG: ["~/core_repos/intellian_pkg/", "~/ow_sw_tools/"],
            }
        ),
        ToolTemplate(
            name="[git_diff] Diff between 2 ref (commits, branchs, tags ...)",
            args={
                ARG_EXTRACT_MODE: EXTRACT_MODE_GIT_DIFF,
                ARG_PATH_LONG: "~/core_repos/intellian_pkg",
                ARG_BASE_REF_LONG: "<base-ref>(origin/manpack_master)",
                ARG_TARGET_REF_LONG: "<target-ref>(origin/feature_branch)",
            }
        ),
    ]


def build_mode_epilog(templates: List[ToolTemplate], script_path: Path, mode: str) -> str:
    """Build a help epilog string for a specific mode."""
    lines: List[str] = ["Examples:"]
    script_str = f"{str(script_path)} {mode}"

    mode_templates = [t for t in templates if mode in t.args]

    for i, t in enumerate(mode_templates, 1):
        # Build argument string
        arg_parts: List[str] = []
        for arg, value in t.args.items():
            if arg == mode:
                continue  # Skip the mode command itself
            if isinstance(value, list):
                part = " ".join([arg] + [str(v) for v in value])
                arg_parts.append(part)
            elif isinstance(value, bool):
                if value:
                    arg_parts.append(str(arg))
            elif value is not None:
                arg_parts.append(f"{arg} {value}")

        cmd = f"{script_str} {' '.join(arg_parts)}".rstrip()
        lines.append("")
        lines.append(f"# Example {i}: {t.name}")
        if t.extra_description:
            lines.append(f"# {t.extra_description}")
        lines.append(cmd)

    return "\n".join(lines)


def rotate_context_folders(output_dir: Path, max_folders: int, prefix: str) -> None:
    """
    Rotate context folders by keeping only the most recent n folders.
    """
    if not output_dir.exists():
        return

    # Find all folders matching the context prefix pattern
    context_folders = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith(prefix)]

    # Sort by modification time (newest first)
    context_folders.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    # Remove excess folders
    folders_to_remove = context_folders[max_folders:]

    if folders_to_remove:
        LOG(f"Rotating folders: keeping {min(len(context_folders), max_folders)} most recent for prefix '{prefix}'")
        for folder in folders_to_remove:
            try:
                shutil.rmtree(folder)
                LOG(f"Removed old context folder: {folder.name}")
            except Exception as e:
                LOG(f"Failed to remove folder {folder.name}: {e}")


def open_explorer_to_file(file_path: Path) -> None:
    """
    Open Windows Explorer and highlight the specified file (WSL only).
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
            subprocess.run([CMD_EXPLORER, WSL_SELECT_FLAG, windows_path], check=False)
            LOG(f"Opened Explorer to highlight '{file_path}'")
        else:
            LOG(f"{MSG_EXPLORER_WSL_ONLY}")
    except Exception as e:
        LOG(f"Failed to open Explorer: {e}")


def run_gitingest(input_path: Path, output_dir: Path, include_pattern_list: List[str], exclude_pattern_list: List[str]) -> Tuple[bool, str, Path]:
    """
    Constructs and runs a single gitingest command for a given path.
    """
    # Construct a descriptive output filename
    if input_path.is_dir():
        parent = input_path.parent.name
        folder = input_path.name
        output_filename = f"{FILE_PREFIX}{parent}{HYPHEN}{folder}{TXT_EXTENSION}"
    else:
        output_filename = f"{FILE_PREFIX}{input_path.stem}{TXT_EXTENSION}"

    output_path = output_dir / output_filename

    # Build the command for subprocess
    command = [CMD_GITINGEST, str(input_path), GIT_INGEST_OUTPUT_FLAG, str(output_path)]

    for pattern in include_pattern_list:
        command.extend([GIT_INGEST_INCLUDE_FLAG, quote(pattern)])
    for pattern in exclude_pattern_list:
        command.extend([GIT_INGEST_EXCLUDE_FLAG, quote(pattern)])

    try:
        str_cmd = ' '.join(command)
        LOG(f"Starting gitingest for '{input_path}'.")
        process = run_shell(str_cmd, check_throw_exception_on_exit_code=True,
                            capture_output=True, text=True, encoding='utf-8', shell=True)
        success_msg = f"{MSG_SUCCESS_PREFIX} Finished gitingest for '{input_path}'. Output saved to '{output_path}'."
        if process.stdout:
            success_msg += f"\n{process.stdout.strip()}"
        return True, success_msg, output_path
    except FileNotFoundError:
        return False, f"{MSG_ERROR_PREFIX} {MSG_GITINGEST_NOT_FOUND}", output_path
    except subprocess.CalledProcessError as e:
        error_msg = (f"{MSG_ERROR_PREFIX} gitingest failed for '{input_path}' with exit code {e.returncode}.\n" f"  Command: {' '.join(command)}\n" f"  Stderr: {e.stderr.strip()}")
        return False, error_msg, output_path
    except Exception as e:
        return False, f"{MSG_ERROR_PREFIX} An unexpected error occurred while processing '{input_path}': {e}", output_path


def merge_output_files(output_files: List[Path], output_dir: Path) -> Path:
    """
    Merge multiple output files into a single file.
    """
    file_names = [f.name for f in output_files]
    LOG(f"Merging files {', '.join(file_names)} into a single file...")

    merged_filename = f"file_merged_context{TXT_EXTENSION}"
    merged_path = output_dir / merged_filename

    with open(merged_path, 'w', encoding='utf-8') as merged_file:
        for i, file_path in enumerate(output_files):
            merged_file.write(f"\n\n{'='*50}\n")
            merged_file.write(f"FILE {i+1}/{len(output_files)}: {file_path.name}\n")
            merged_file.write(f"{'='*50}\n\n")

            with open(file_path, 'r', encoding='utf-8') as input_file:
                merged_file.write(input_file.read())

    LOG(f"Merged {len(output_files)} files into '{merged_path}'")
    return merged_path


def create_log_file_paths(args: argparse.Namespace, output_dir: Path, timestamp: str) -> Path:
    """Create a log file with context information for 'paths' mode."""
    log_path = output_dir / "log.txt"
    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write(f"Extract Source Context Log (Paths Mode) - {timestamp}\n")
        log_file.write(f"{'='*50}\n\n")
        log_file.write("Arguments:\n")
        log_file.write(f"  Paths: {get_arg_value(args, ARG_PATHS_LONG)}\n")
        log_file.write(f"  Output directory: {get_arg_value(args, ARG_OUTPUT_DIR_LONG)}\n")
        log_file.write(f"  Include patterns: {get_arg_value(args, ARG_INCLUDE_PATHS_PATTERN)}\n")
        log_file.write(f"  Exclude patterns: {get_arg_value(args, ARG_EXCLUDE_PATHS_PATTERN)}\n")
        log_file.write(f"  Max workers: {get_arg_value(args, ARG_MAX_WORKERS)}\n")
        log_file.write(f"  Max folders: {get_arg_value(args, ARG_MAX_FOLDERS)}\n")
        log_file.write(f"  No open explorer: {get_arg_value(args, ARG_NO_OPEN_EXPLORER)}\n")
    return log_path


def main_paths(args: argparse.Namespace) -> None:
    """Main function for 'paths' extraction mode."""
    if not shutil.which(CMD_GITINGEST):
        LOG(f"{MSG_GITINGEST_NOT_AVAILABLE}", file=sys.stderr)
        sys.exit(1)

    timestamp = get_time_stamp_now()
    paths = get_arg_value(args, ARG_PATHS_LONG)
    output_dir = get_arg_value(args, ARG_OUTPUT_DIR_LONG)
    max_folders = get_arg_value(args, ARG_MAX_FOLDERS)
    max_workers = get_arg_value(args, ARG_MAX_WORKERS)
    include_paths_pattern = get_arg_value(args, ARG_INCLUDE_PATHS_PATTERN)
    exclude_paths_pattern = get_arg_value(args, ARG_EXCLUDE_PATHS_PATTERN)
    LOG(f"Include patterns: {include_paths_pattern}, Exclude patterns: {exclude_paths_pattern}")

    no_open_explorer = get_arg_value(args, ARG_NO_OPEN_EXPLORER)

    rotate_context_folders(output_dir, max_folders - 1, CONTEXT_FOLDER_PREFIX_PATHS)

    final_output_dir_name = f"{CONTEXT_FOLDER_PREFIX_PATHS}{timestamp}"
    final_output_dir = output_dir / final_output_dir_name
    final_output_dir.mkdir(parents=True, exist_ok=True)

    log_path = create_log_file_paths(args, final_output_dir, timestamp)
    LOG(f"Log file created at: {log_path}")
    LOG(f"Output directory: {final_output_dir}")

    successes = []
    failures = []
    output_files = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(run_gitingest, Path(p), final_output_dir, include_paths_pattern, exclude_paths_pattern): p
            for p in paths
        }

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

    LOG(f"\n{SUMMARY_SEPARATOR}")
    if successes:
        LOG(f"{SUCCESS_EMOJI} Successfully processed {len(successes)} paths: {', '.join(map(str, successes))}")
    if failures:
        LOG(f"{FAILURE_EMOJI} Failed to process {len(failures)} paths:", file=sys.stderr)
        for f in failures:
            LOG(f"  - {f}", file=sys.stderr)

    output_file_path = None
    LOG(f"Output files collected: {output_files}")
    for f in output_files:
        LOG(f"  - {f} (exists: {os.path.exists(f)})")

    if len(output_files) == 1:
        output_file_path = output_files[0]
    elif len(output_files) > 1:
        output_file_path = merge_output_files(output_files, final_output_dir)

    if output_file_path:
        with open(output_file_path, "r", encoding="utf-8") as f:
            file_contents = f.read()
            encoding = tiktoken.get_encoding("cl100k_base")
            token_count = len(encoding.encode(file_contents))
            filename = os.path.basename(output_file_path)
            LOG(f"{LINE_SEPARATOR}")
            LOG(f"Estimated token count for {filename}: {beautify_number(token_count)}")

        if not no_open_explorer:
            open_explorer_to_file(output_file_path)

    if failures:
        sys.exit(1)


# --- 'git_diff' mode functions ---
def save_base_ref_files(repo_path: Path, base: str, target: str, output_dir: Path) -> bool:
    """
    Saves the content of changed files from the base ref to a subdirectory.
    """
    try:
        diff_files_cmd = [CMD_GIT, '-C', str(repo_path), 'diff', '--name-only', base, target]
        result = run_shell(diff_files_cmd, capture_output=True, text=True,
                           check_throw_exception_on_exit_code=True, encoding='utf-8')
        changed_files = result.stdout.strip().split('\n')

        if not any(f.strip() for f in changed_files):
            LOG("No changed files found to save from base ref.")
            return True

        files_dir = output_dir / "base_ref_files"
        LOG(f"Saving base versions of changed files to '{files_dir}'...")

        for file_path_str in changed_files:
            file_path_str = file_path_str.strip()
            if not file_path_str:
                continue

            original_path = Path(file_path_str)

            try:
                show_cmd = [CMD_GIT, '-C', str(repo_path), 'show', f'{base}:{file_path_str}']
                content_result = subprocess.run(show_cmd, capture_output=True, text=True, check=True, encoding='utf-8')
                file_content = content_result.stdout

                prefixed_filename = f"{FILE_PREFIX}{original_path.name}"
                output_file_path = files_dir / original_path.parent / prefixed_filename
                output_file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                LOG(f"  - Saved: {output_file_path}")

            except subprocess.CalledProcessError:
                LOG(f"  - Skipping '{file_path_str}': could not retrieve from base ref (likely a new or binary file).")
            except Exception as e:
                LOG(f"  - An error occurred while processing '{file_path_str}': {e}", file=sys.stderr)

        return True
    except subprocess.CalledProcessError as e:
        LOG(f"Failed to get list of changed files: {e.stderr.strip()}", file=sys.stderr)
        return False
    except Exception as e:
        LOG(f"An unexpected error occurred in save_base_ref_files: {e}", file=sys.stderr)
        return False


def main_git_diff(args: argparse.Namespace) -> None:
    """Main function for 'git_diff' extraction mode."""
    repo_path = get_arg_value(args, ARG_PATH_LONG)
    base = get_arg_value(args, ARG_BASE_REF_LONG)
    target = get_arg_value(args, ARG_TARGET_REF_LONG)
    output_dir = get_arg_value(args, ARG_OUTPUT_DIR_LONG)
    no_open_explorer = get_arg_value(args, ARG_NO_OPEN_EXPLORER)
    max_folders = get_arg_value(args, ARG_MAX_FOLDERS)

    if not repo_path or not base or not target:
        LOG(f"Error: --path, --base, and --target arguments are required for 'git_diff' mode.", file=sys.stderr)
        sys.exit(1)

    if not shutil.which(CMD_GIT):
        LOG(f"{MSG_GIT_NOT_FOUND}", file=sys.stderr)
        sys.exit(1)

    is_fetch_success = git_fetch(repo_path)
    if not is_fetch_success:
        LOG(f"Aborting due to fetch failure.", file=sys.stderr)
        sys.exit(1)

    timestamp: str = get_time_stamp_now()
    rotate_context_folders(output_dir, max_folders - 1, CONTEXT_FOLDER_PREFIX_DIFF)

    final_output_dir_name = f"{CONTEXT_FOLDER_PREFIX_DIFF}{timestamp}"
    final_output_dir = output_dir / final_output_dir_name
    final_output_dir.mkdir(parents=True, exist_ok=True)

    LOG(f"Output directory: {final_output_dir}")
    LOG()

    diff_content = extract_git_diff(repo_path, base, target)
    is_success = diff_content is not None
    output_path = None

    if is_success:
        sanitized_base = sanitize_ref_for_filename(base)
        sanitized_target = sanitize_ref_for_filename(target)
        output_filename = f"diff_{sanitized_base}_vs_{sanitized_target}{TXT_EXTENSION}"
        output_path = final_output_dir / output_filename

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"# CONTEXT: Diff between {base} and {target}\n")
                f.write(f"# REPOSITORY: {repo_path.resolve().name}\n")
                f.write(f"# GENERATED AT: {datetime.now().isoformat()}\n")
                f.write(f"{'='*60}\n\n")
                f.write(diff_content)
            LOG(f"Diff content saved to '{output_path}'.")

            LOG()
            save_base_ref_files(repo_path, base, target, final_output_dir)

        except IOError as e:
            LOG(f"Failed to write to output file '{output_path}': {e}", file=sys.stderr)
            is_success = False

    LOG(f"\n{SUMMARY_SEPARATOR}")
    if is_success and output_path:
        LOG(f"{SUCCESS_EMOJI} Successfully processed '{repo_path}'.")
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                file_contents = f.read()
            encoding = tiktoken.get_encoding("cl100k_base")
            token_count = len(encoding.encode(file_contents))
            filename = os.path.basename(output_path)
            LOG(f"📄 Estimated token count for '{filename}': {beautify_number(token_count)}")
        except Exception as e:
            LOG(f"Could not estimate token count: {e}")

        if not no_open_explorer:
            open_explorer_to_file(output_path)

        LOG(f"{CELEBRATION_EMOJI} {MSG_CONTEXT_EXTRACTION_SUCCESS}")
    else:
        LOG(f"{FAILURE_EMOJI} Failed to process '{repo_path}'.", file=sys.stderr)
        try:
            shutil.rmtree(final_output_dir)
            LOG(f"Cleaned up empty output directory: {final_output_dir}")
        except Exception as e:
            LOG(f"Could not remove empty output directory: {e}")
        sys.exit(1)


# --- Main entry point ---

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
