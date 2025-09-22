import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import tiktoken
import platform
from pathlib import Path
from dev_common import *
import os
import sys
from typing import List, Tuple
from available_tools.code_tools.common_code_tools_utils import *

DEFAULT_MAX_WORKERS = 10
CONTEXT_FOLDER_PREFIX_PATHS = 'context_paths_'


def main_paths(args: argparse.Namespace) -> None:
    """Main function for 'paths' extraction mode."""
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
            if platform.system() == "Windows":
                open_explorer_to_file(output_file_path)
            else:
                LOG(f"Skipping opening file explorer on non-Windows OS.")

    if failures:
        sys.exit(1)


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

    gitingest_cmd = [CMD_GITINGEST, str(input_path), GIT_INGEST_OUTPUT_FLAG, str(output_path)]
    for pattern in include_pattern_list:
        gitingest_cmd.extend([GIT_INGEST_INCLUDE_FLAG, quote(pattern)])
    for pattern in exclude_pattern_list:
        gitingest_cmd.extend([GIT_INGEST_EXCLUDE_FLAG, quote(pattern)])

    try:
        str_cmd = ' '.join(gitingest_cmd)
        LOG(f"Starting gitingest for '{input_path}'.")
        process = run_shell(str_cmd, check_throw_exception_on_exit_code=True,
                            capture_output=True, text=True, encoding='utf-8', shell=True)
        success_msg = f"{LOG_PREFIX_MSG_SUCCESS} Finished gitingest for '{input_path}'. Output saved to '{output_path}'."
        if process.stdout:
            success_msg += f"\n{process.stdout.strip()}"
        return True, success_msg, output_path
    except Exception as e:
        return False, f"{LOG_PREFIX_MSG_ERROR} An unexpected error occurred while processing '{input_path}': {e}", output_path
