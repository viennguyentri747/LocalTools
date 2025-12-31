import argparse
from dev.dev_common import *

# Default paths
DEFAULT_OUTPUT_BASE_DIR = 'testing'
DEFAULT_OUTPUT_SUBDIR = '.ai_context'

# Folder rotation settings
CONTEXT_FOLDER_PREFIX_DIFF = 'context_diff_'
DEFAULT_MAX_FOLDERS = 5

ARG_EXTRACT_MODE = '--extract-mode'
ARG_BASE_REF_LONG = '--base'
ARG_TARGET_REF_LONG = '--target'
ARG_GITLAB_MR_URL_LONG = '--mr-url'
ARG_INCLUDE_PATHS_PATTERN = '--include-paths-pattern'
ARG_EXCLUDE_PATHS_PATTERN = '--exclude-paths-pattern'
ARG_MAX_WORKERS = '--max-workers'

GIT_INGEST_OUTPUT_FLAG = '--output'
GIT_INGEST_INCLUDE_FLAG = '--include-pattern'
GIT_INGEST_EXCLUDE_FLAG = '--exclude-pattern'
EXTRACT_MODE_PATHS = 'paths'
EXTRACT_MODE_GIT_DIFF = 'git_diff'
EXTRACT_MODE_GIT_MR = 'gitlab_mr'
AVAILABLE_EXTRACT_MODES = [EXTRACT_MODE_PATHS, EXTRACT_MODE_GIT_DIFF, EXTRACT_MODE_GIT_MR]
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
        log_file.write(f"  Output directory: {get_arg_value(args, ARG_OUTPUT_DIR)}\n")
        log_file.write(f"  Include patterns: {get_arg_value(args, ARG_INCLUDE_PATHS_PATTERN)}\n")
        log_file.write(f"  Exclude patterns: {get_arg_value(args, ARG_EXCLUDE_PATHS_PATTERN)}\n")
        log_file.write(f"  Max workers: {get_arg_value(args, ARG_MAX_WORKERS)}\n")
        log_file.write(f"  Max folders: {get_arg_value(args, ARG_MAX_FOLDERS)}\n")
        log_file.write(f"  No open explorer: {get_arg_value(args, ARG_NO_OPEN_EXPLORER)}\n")
    return log_path


def save_changed_files(repo_path: Path, base: str, target: str, output_dir: Path) -> bool:
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
                show_cmd = f"{CMD_GIT} -C {str(repo_path)} show {base}:{file_path_str}"
                content_result = run_shell(show_cmd, capture_output=True, text=True,
                                           check_throw_exception_on_exit_code=True, encoding='utf-8')
                file_content = content_result.stdout

                prefixed_filename = f"{FILE_PREFIX}{original_path.name}"
                output_file_path = files_dir / original_path.parent / prefixed_filename
                output_file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                # LOG(f"  - Saved: {output_file_path}")

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
