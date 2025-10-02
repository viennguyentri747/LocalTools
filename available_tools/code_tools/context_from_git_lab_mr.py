import argparse
import sys
from typing import List, Union
import tiktoken
from available_tools.code_tools.common_utils import *
from dev_common import *

ARG_SHOULD_INCLUDE_FILE_CONTENT = f"{ARGUMENT_LONG_PREFIX}should_include_file_content"


def get_mr_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="[git_mr_diff] Context from Git Diff of a GitLab MR",
            args={
                ARG_EXTRACT_MODE: EXTRACT_MODE_GIT_MR,
                ARG_SHOULD_INCLUDE_FILE_CONTENT: True,
                ARG_GITLAB_MR_URL_LONG: f"{GL_BASE_URL}/intellian_adc/gerrit_mirror/oneweb/intellian_pkg/-/merge_requests/324"
            }
        ),
    ]


def main_git_mr(args: argparse.Namespace) -> None:
    """Main function for 'gitlab_mr' extraction mode."""
    mr_url = get_arg_value(args, ARG_GITLAB_MR_URL_LONG)
    output_dir = get_arg_value(args, ARG_OUTPUT_DIR_LONG)
    no_open_explorer = get_arg_value(args, ARG_NO_OPEN_EXPLORER)
    max_folders = get_arg_value(args, ARG_MAX_FOLDERS)
    should_include_file_content: bool = get_arg_value(args, ARG_SHOULD_INCLUDE_FILE_CONTENT)

    if not mr_url:
        LOG(f"Error: --mr_url argument is required for '{EXTRACT_MODE_GIT_MR}' mode.", file=sys.stderr)
        sys.exit(1)

    file_changes: List[MrFileChange] | None = get_file_changes_from_url(mr_url)
    mr_diff: str | None = get_diff_from_mr_file_changes(file_changes)
    if not mr_diff:
        LOG(f"Error: Could not retrieve MR diff from URL '{mr_url}'.", file=sys.stderr)
        sys.exit(1)
    LOG(f"Successfully retrieved MR diff from: {mr_url}")

    timestamp: str = get_time_stamp_now()
    rotate_context_folders(output_dir, max_folders - 1, CONTEXT_FOLDER_PREFIX_DIFF)

    final_output_dir_name = f"{CONTEXT_FOLDER_PREFIX_DIFF}{timestamp}"
    final_output_dir = output_dir / final_output_dir_name
    final_output_dir.mkdir(parents=True, exist_ok=True)

    LOG(f"Output directory: {final_output_dir}")
    LOG()
    # Create output filename based on MR URL
    mr_id = mr_url.rstrip('/').split('/')[-1]
    info: InfoFromMrUrl = get_info_from_mr_url(mr_url)
    gl_project_path: str = info.gl_project_path
    project_name = gl_project_path.split('/')[-1]
    output_filename = f"mr_diff_{project_name}_{mr_id}{TXT_EXTENSION}"
    output_path = final_output_dir / output_filename

    is_success = True
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            # --- Part 1: Writing the MR Diff ---
            f.write(f"# CONTEXT: Diff from MR '{mr_url}'\n")
            f.write(f"# MR ID: {mr_id}\n")
            f.write(f"# GENERATED AT: {datetime.now().isoformat()}\n")
            f.write(f"{'='*60}\n\n")
            f.write(mr_diff)

            if should_include_file_content:
                # --- Part 2: Writing the full file contents ---
                f.write("\n\n")  # Add some spacing for readability
                f.write(f"# CONTEXT: Files after diff from MR '{mr_url}'\n")
                f.write(f"# CONTEXT: Full content of all changed files from MR '{mr_url}'\n")
                f.write(f"{'='*60}\n\n")

                # Iterate through each file change object to write its content
                for change in file_changes:
                    content = change.GetFileContent()
                    # if content is not None:
                    f.write(f"{'-'*20} START OF FILE: {change.filePath} {'-'*20}\n")
                    f.write(content)
                    f.write(f"\n{'-'*20} END OF FILE: {change.filePath} {'-'*20}\n\n")

        LOG(f"Diff content saved to '{output_path}'.")
    except IOError as e:
        LOG(f"Failed to write to output file '{output_path}': {e}", file=sys.stderr)
        is_success = False

    LOG(f"\n{SUMMARY_SEPARATOR}")
    if is_success and output_path:
        LOG(f"{SUCCESS_EMOJI} Successfully processed MR diff.")
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
        LOG(f"{FAILURE_EMOJI} Failed to process MR diff.", file=sys.stderr)
        try:
            shutil.rmtree(final_output_dir)
            LOG(f"Cleaned up empty output directory: {final_output_dir}")
        except Exception as e:
            LOG(f"Could not remove empty output directory: {e}")
        sys.exit(1)
