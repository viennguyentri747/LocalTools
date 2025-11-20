import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import tiktoken
import platform
from pathlib import Path
from dev_common import *
import os
import sys
from typing import List, Tuple
from available_tools.code_tools.common_utils import *
from available_tools.code_tools.custom_gitingest import CustomGitingestResult, ingest_path

DEFAULT_MAX_WORKERS = 10
CONTEXT_FOLDER_PREFIX_PATHS = 'context_paths_'
HEADER_TITLE = "FILE(S) CONTEXT BELOW..."


def get_paths_tool_templates():
    return [
        ToolTemplate(
            name="[paths] Context from multiple PATHs",
            args={
                ARG_EXTRACT_MODE: EXTRACT_MODE_PATHS,
                ARG_INCLUDE_PATHS_PATTERN: ["*"],
                ARG_EXCLUDE_PATHS_PATTERN: [".git", ".vscode", "__pycache__", ".venv", "venv"],
                ARG_PATHS_LONG: ["path1", "path2"],
            }
        )
    ]


def main_paths(args: argparse.Namespace) -> None:
    """Main function for 'paths' extraction mode."""
    timestamp = get_time_stamp_now()
    paths = get_arg_value(args, ARG_PATHS_LONG)
    output_dir = get_arg_value(args, ARG_OUTPUT_DIR)
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
    original_abs_paths = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path: dict[Future[Tuple[bool, str, Path]], str] = {
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
                    # Store absolute path of the original input
                    original_abs_paths.append(str(Path(path).resolve()))
                else:
                    failures.append(path)
            except Exception as exc:
                LOG_EXCEPTION_STR(f"Path '{path}' generated an exception: {exc}", exit=True)

    LOG(f"\n{SUMMARY_SEPARATOR}")
    if successes:
        LOG(f"{SUCCESS_EMOJI} Successfully processed {len(successes)} paths: {', '.join(map(str, successes))}")
    if failures:
        LOG(f"{FAILURE_EMOJI} Failed to process {len(failures)} paths:", file=sys.stderr)
        for f in failures:
            LOG(f"  - {f}", file=sys.stderr)
        LOG_EXCEPTION_STR("Some paths failed to process...", exit=True)

    output_file_path = None
    LOG(f"Output files collected: {output_files}")
    for f in output_files:
        LOG(f"  - {f} (exists: {os.path.exists(f)})")

    # Always create a merged result file for consistency
    if output_files:
        output_file_path = merge_output_files(output_files, original_abs_paths, final_output_dir)

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


def merge_output_files(output_files: List[Path], original_abs_paths: List[str], output_dir: Path) -> Path:
    """
    Merge multiple output files into a single file with standardized format.
    Always creates a result file even for single files to ensure consistent format.
    Uses absolute paths of original input files in the headers.
    """
    merged_filename = f"file_merged_context{TXT_EXTENSION}"
    merged_path = output_dir / merged_filename

    LOG(f"Creating result file with {len(output_files)} source(s): '{merged_path}'")

    with open(merged_path, 'w', encoding='utf-8') as merged_file:
        # Write header
        merged_file.write(f"{HEADER_TITLE}\n")
        merged_file.write(f"{LINE_SEPARATOR}")
        
        for i, (file_path, abs_path) in enumerate(zip(output_files, original_abs_paths)):
            merged_file.write(f"{LINE_SEPARATOR}")
            postfix_count = f" {i+1}/{len(output_files)}" if len(output_files) > 1 else ""
            INPUT_TITLE = f"INPUT{postfix_count} (FOLDER)" if os.path.isdir(abs_path) else f"INPUT{postfix_count} (FILE)"
            merged_file.write(f"{INPUT_TITLE}: {abs_path}")
            merged_file.write(f"{LINE_SEPARATOR}")

            with open(file_path, 'r', encoding='utf-8') as input_file:
                merged_file.write(input_file.read())

    LOG(f"Created result file from {len(output_files)} file(s): '{merged_path}'")
    return merged_path


def run_gitingest(input_path: Path, output_dir: Path, include_pattern_list: List[str], exclude_pattern_list: List[str]) -> Tuple[bool, str, Path]:
    """
    Build a context file for the provided path using the local custom gitingest implementation.
    Returns: (success, message, output_path)
    """
    if input_path.is_dir():
        dir_name = input_path.name or input_path.resolve().name
        full_file_name = f"{FOLDER_PREFIX}{dir_name}{TXT_EXTENSION}"
    else:
        full_file_name = f"{FILE_PREFIX}{input_path.name}{TXT_EXTENSION}"

    output_path = output_dir / full_file_name

    LOG(f"Starting custom gitingest for '{input_path}'.")
    try:
        result: CustomGitingestResult = ingest_path( input_path, output_path, include_patterns=include_pattern_list, exclude_patterns=exclude_pattern_list, )
    except Exception as exc:
        error_msg = f"{LOG_PREFIX_MSG_ERROR} Failed to ingest '{input_path}': {exc}"
        return False, error_msg, output_path

    success_msg = (
        f"{LOG_PREFIX_MSG_SUCCESS} Finished gitingest for '{input_path}'. Output saved to '{output_path}'.\n"
        f"{result.summary_text(input_path)}"
    )
    return True, success_msg, output_path
