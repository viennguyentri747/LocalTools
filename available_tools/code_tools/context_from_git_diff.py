import argparse
from pathlib import Path
import subprocess
import os
import shutil
import sys
from datetime import datetime

import tiktoken
from dev_common import *
from available_tools.code_tools.common_utils import *


def get_diff_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="[git_diff] Context from Git Diff between 2 refs (commits, branchs, tags ...)",
            args={
                ARG_EXTRACT_MODE: EXTRACT_MODE_GIT_DIFF,
                ARG_PATH_LONG: "~/core_repos/intellian_pkg",
                ARG_BASE_REF_LONG: "origin/manpack_master",
                ARG_TARGET_REF_LONG: "origin/feat_branch",
            }
        ),
    ]


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
                content_result = run_shell(show_cmd, capture_output=True, text=True, check=True, encoding='utf-8')
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
