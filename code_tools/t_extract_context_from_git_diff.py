#!/home/vien/local_tools/MyVenvFolder/bin/python

import argparse
from pathlib import Path
import shutil
import tiktoken
from datetime import datetime
import subprocess
import sys
import os

from dev_common import *
from dev_common.tools_utils import ToolTemplate
# Import the new centralized git functions

# --- Constants ---

# Default paths
DEFAULT_OUTPUT_BASE_DIR = 'testing'
DEFAULT_OUTPUT_SUBDIR = '.ai_context'

# Folder rotation settings
CONTEXT_FOLDER_PREFIX = 'context_diff_'
DEFAULT_MAX_FOLDERS = 5

# Commands
CMD_GIT = 'git'
CMD_WSLPATH = 'wslpath'
CMD_EXPLORER = 'explorer.exe'

# Command line arguments
ARG_BASE_REF_LONG = '--base'
ARG_TARGET_REF_LONG = '--target'
ARG_OUTPUT_DIR_SHORT = '-o'
ARG_OUTPUT_DIR_LONG = '--output-dir'
ARG_NO_OPEN_EXPLORER = '--no-open-explorer'
ARG_MAX_FOLDERS = '--max-folders'

# File extensions
TXT_EXTENSION = '.txt'

WSL_SELECT_FLAG = '/select,'

# Messages
MSG_GIT_NOT_FOUND = "The 'git' command was not found. Please ensure it is installed and in your system's PATH."
MSG_EXPLORER_WSL_ONLY = "Explorer integration only available in WSL environment"
MSG_ALL_PROCESSED_SUCCESS = "🎉 Context extraction completed successfully."

# Summary formatting
SUMMARY_SEPARATOR = "="*20 + " SUMMARY " + "="*20
SUCCESS_EMOJI = "✅"
FAILURE_EMOJI = "❌"
CELEBRATION_EMOJI = "🎉"


# Helper functions that don't call other functions in this file
def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Diff between 2 ref (commits, branchs, tags ...)",
            description="Extract diff between two refs with default settings",
            args={
                ARG_PATH_LONG: "~/core_repos/intellian_pkg",
                ARG_BASE_REF_LONG: "<base-ref>(origin/manpack_master)",
                ARG_TARGET_REF_LONG: "<target-ref>(origin/feature_branch)",
            }
        ),
        ToolTemplate(
            name="Diff between 2 branches",
            description="Extract diff between two refs with default settings",
            args={
                ARG_PATH_LONG: "~/core_repos/intellian_pkg",
                ARG_BASE_REF_LONG: "origin/master",
                ARG_TARGET_REF_LONG: "origin/feature_branch",
            }
        ),
    ]


def rotate_context_folders(output_dir: Path, max_folders: int) -> None:
    """
    Rotate context folders by keeping only the most recent n folders.

    Args:
        output_dir: Base directory containing context folders.
        max_folders: Maximum number of folders to keep.
    """
    if not output_dir.exists():
        return

    context_folders = [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith(CONTEXT_FOLDER_PREFIX)]

    # Sort by creation time (newest first)
    context_folders.sort(key=lambda x: x.stat().st_ctime, reverse=True)

    folders_to_remove = context_folders[max_folders:]

    if folders_to_remove:
        LOG(f"Rotating folders: keeping {min(len(context_folders), max_folders)} most recent.")
        for folder in folders_to_remove:
            try:
                shutil.rmtree(folder)
                LOG(f"Removed old context folder: {folder.name}")
            except Exception as e:
                LOG(f"Failed to remove folder {folder.name}: {e}")


def open_explorer_to_file(file_path: Path) -> None:
    """Opens Windows Explorer to highlight the specified file (WSL only)."""
    try:
        if shutil.which(CMD_WSLPATH) and shutil.which(CMD_EXPLORER):
            result = subprocess.run([CMD_WSLPATH, "-w", str(file_path)], capture_output=True, text=True, check=True)
            windows_path = result.stdout.strip()
            subprocess.run([CMD_EXPLORER, WSL_SELECT_FLAG, windows_path], check=True)
            LOG(f"Opened Explorer to highlight '{file_path}'")
        else:
            LOG(f"{MSG_EXPLORER_WSL_ONLY}")
    except Exception as e:
        LOG(f"Failed to open Explorer: {e}")


def save_base_ref_files(repo_path: Path, base: str, target: str, output_dir: Path) -> bool:
    """
    Saves the content of changed files from the base ref to a subdirectory,
    prefixing each filename with 'file_'.

    Args:
        repo_path: The path to the local git repository.
        base: The base git ref.
        target: The target git ref to compare against the base.
        output_dir: The directory to save the files.

    Returns:
        True if successful, False otherwise.
    """
    try:
        # Get the list of changed files
        diff_files_cmd = [CMD_GIT, '-C', str(repo_path), 'diff', '--name-only', base, target]
        result = subprocess.run(diff_files_cmd, capture_output=True, text=True, check=True, encoding='utf-8')
        changed_files = result.stdout.strip().split('\n')

        if not any(f.strip() for f in changed_files):
            LOG("No changed files found to save from base ref.")
            return True

        # The subdirectory for the files remains the same
        files_dir = output_dir / "base_ref_files"
        LOG(f"Saving base versions of changed files to '{files_dir}'...")

        for file_path_str in changed_files:
            file_path_str = file_path_str.strip()
            if not file_path_str:
                continue
            
            # Convert the string path to a Path object for easier manipulation
            original_path = Path(file_path_str)

            try:
                # Get the content of the file at the base ref
                show_cmd = [CMD_GIT, '-C', str(repo_path), 'show', f'{base}:{file_path_str}']
                content_result = subprocess.run(show_cmd, capture_output=True, text=True, check=True, encoding='utf-8')
                file_content = content_result.stdout

                # Create the new filename with the prefix
                prefixed_filename = f"{FILE_PREFIX}{original_path.name}"
                
                # Construct the full output path, preserving the parent directory structure
                output_file_path = files_dir / original_path.parent / prefixed_filename

                # Create the parent directories if they don't exist
                output_file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                LOG(f"  - Saved: {output_file_path}")

            except subprocess.CalledProcessError:
                # This often happens for new files (not in base) or deleted files.
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

# Functions that call other functions
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Extracts a git diff between two references to create an AI context file.',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(ARG_PATH_SHORT, ARG_PATH_LONG, required=True, type=Path, help='The path to the local git repository.')
    parser.add_argument(ARG_BASE_REF_LONG, required=True, help='The base git ref. (Ex: origin/master)')
    parser.add_argument(ARG_TARGET_REF_LONG, required=True,
                        help='The target git ref to compare against the base. Ex: origin/feat_branch)')
    parser.add_argument(ARG_OUTPUT_DIR_SHORT, ARG_OUTPUT_DIR_LONG, type=Path, default=Path.home() / DEFAULT_OUTPUT_BASE_DIR /
                        DEFAULT_OUTPUT_SUBDIR, help=f'The base directory for output. (default: ~/{DEFAULT_OUTPUT_BASE_DIR}/{DEFAULT_OUTPUT_SUBDIR})')
    parser.add_argument(ARG_NO_OPEN_EXPLORER, action='store_true',
                        help='Do not open Windows Explorer to highlight the output file after completion.')
    parser.add_argument(ARG_MAX_FOLDERS, type=int, default=DEFAULT_MAX_FOLDERS,
                        help=f'Maximum number of context folders to keep (default: {DEFAULT_MAX_FOLDERS}).')
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    return parser.parse_args()


# Main functions
def main() -> None:
    """Main function to orchestrate context extraction."""
    args = parse_args()

    # Store attributes in variables immediately after parsing args
    repo_path = getattr(args, ARG_PATH_LONG.lstrip('-').replace('-', '_'))
    base = getattr(args, ARG_BASE_REF_LONG.lstrip('-').replace('-', '_'))
    target = getattr(args, ARG_TARGET_REF_LONG.lstrip('-').replace('-', '_'))
    output_dir = getattr(args, ARG_OUTPUT_DIR_LONG.lstrip('-').replace('-', '_'))
    no_open_explorer = getattr(args, ARG_NO_OPEN_EXPLORER.lstrip('-').replace('-', '_'))
    max_folders = getattr(args, ARG_MAX_FOLDERS.lstrip('-').replace('-', '_'))

    if not shutil.which(CMD_GIT):
        LOG(f"{MSG_GIT_NOT_FOUND}", file=sys.stderr)
        sys.exit(1)

    # --- Step 1: Fetch latest changes to ensure diff is accurate ---
    is_fetch_success = git_fetch(repo_path)
    if not is_fetch_success:
        LOG(f"Aborting due to fetch failure.", file=sys.stderr)
        sys.exit(1)
    # -----------------------------------------------------------------

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Rotate existing folders before creating a new one
    rotate_context_folders(output_dir, max_folders - 1)

    # Create a new timestamped directory for this run
    final_output_dir_name = f"{CONTEXT_FOLDER_PREFIX}{timestamp}"
    final_output_dir = output_dir / final_output_dir_name
    final_output_dir.mkdir(parents=True, exist_ok=True)

    LOG(f"Output directory: {final_output_dir}")
    LOG()

    # --- Step 2: Run the main logic ---
    diff_content = extract_git_diff(repo_path, base, target)
    # ----------------------------------

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

            # --- Step 3: Save the base version of changed files ---
            LOG() # Add a newline for readability
            save_base_ref_files(repo_path, base, target, final_output_dir)
            # --------------------------------------------------------

        except IOError as e:
            LOG(f"Failed to write to output file '{output_path}': {e}", file=sys.stderr)
            is_success = False

    LOG(f"\n{SUMMARY_SEPARATOR}")
    if is_success and output_path:
        LOG(f"{SUCCESS_EMOJI} Successfully processed '{repo_path}'.")

        # Estimate token count
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                file_contents = f.read()
            encoding = tiktoken.get_encoding("cl100k_base")
            token_count = len(encoding.encode(file_contents))
            filename = os.path.basename(output_path)
            LOG(f"📄 Estimated token count for '{filename}': {beautify_number(token_count)}")
        except Exception as e:
            LOG(f"Could not estimate token count: {e}")

        # Open explorer if requested
        if not no_open_explorer:
            open_explorer_to_file(output_path)

        LOG(f"{CELEBRATION_EMOJI} {MSG_ALL_PROCESSED_SUCCESS}")
    else:
        LOG(f"{FAILURE_EMOJI} Failed to process '{repo_path}'.", file=sys.stderr)
        # If the process failed, the output dir is empty and can be removed
        try:
            shutil.rmtree(final_output_dir)
            LOG(f"Cleaned up empty output directory: {final_output_dir}")
        except Exception as e:
            LOG(f"Could not remove empty output directory: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()