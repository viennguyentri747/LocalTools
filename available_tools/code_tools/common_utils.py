import argparse
from dev_common import *

# Default paths
DEFAULT_OUTPUT_BASE_DIR = 'testing'
DEFAULT_OUTPUT_SUBDIR = '.ai_context'

# Folder rotation settings
CONTEXT_FOLDER_PREFIX_DIFF = 'context_diff_'
DEFAULT_MAX_FOLDERS = 5

ARG_EXTRACT_MODE = '--extract-mode'
ARG_BASE_REF_LONG = '--base'
ARG_TARGET_REF_LONG = '--target'
ARG_INCLUDE_PATHS_PATTERN = '--include-paths-pattern'
ARG_EXCLUDE_PATHS_PATTERN = '--exclude-paths-pattern'
ARG_MAX_WORKERS = '--max-workers'

GIT_INGEST_OUTPUT_FLAG = '--output'
GIT_INGEST_INCLUDE_FLAG = '--include-pattern'
GIT_INGEST_EXCLUDE_FLAG = '--exclude-pattern'
EXTRACT_MODE_PATHS = 'paths'
EXTRACT_MODE_GIT_DIFF = 'git_diff'
AVAILABLE_EXTRACT_MODES = [EXTRACT_MODE_PATHS, EXTRACT_MODE_GIT_DIFF]
# Summary formatting
SUMMARY_SEPARATOR = "="*20 + " SUMMARY " + "="*20


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
