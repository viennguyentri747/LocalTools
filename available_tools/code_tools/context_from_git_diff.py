import argparse
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


def main_git_diff(args: argparse.Namespace) -> None:
    """Main function for 'git_diff' extraction mode."""
    repo_path = get_arg_value(args, ARG_PATH_LONG)
    base = get_arg_value(args, ARG_BASE_REF_LONG)
    target = get_arg_value(args, ARG_TARGET_REF_LONG)
    output_dir = get_arg_value(args, ARG_OUTPUT_DIR)
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
            save_changed_files(repo_path, base, target, final_output_dir)

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

        LOG(f"{CELEBRATION_EMOJI} Extraction complete! Output directory: {final_output_dir}")
    else:
        LOG(f"{FAILURE_EMOJI} Failed to process '{repo_path}'.", file=sys.stderr)
        try:
            shutil.rmtree(final_output_dir)
            LOG(f"Cleaned up empty output directory: {final_output_dir}")
        except Exception as e:
            LOG(f"Could not remove empty output directory: {e}")
        sys.exit(1)
