import argparse
import logging
import re
import sys
from typing import List, Union
from urllib.parse import urlparse

import tiktoken
from dev_common import *
from available_tools.code_tools.common_utils import *
from dev_common.constants import *
from dev_common.custom_structures import LOCAL_REPO_MAPPING
from dev_common.git_utils import git_fetch
from dev_common.gitlab_utils import get_mr_info_from_url
from dev_common.tools_utils import get_arg_value


def get_mr_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="[git_diff] Context from Git Diff between 2 refs (commits, branchs, tags ...)",
            args={
                ARG_GITLAB_MR_URL_LONG: "GitLab MR URL"
            }
        ),
    ]

    # """
    # Returns the tool template for the GitLab MR context tool.
    # """
    # return {
    #     CMD_CONTEXT_FROM_GIT_LAB_MR: {
    #         "args": {
                
    #         },
    #         "out_file": "mr_context.txt",
    #     },
    # }


def get_repo_name_from_mr_url(mr_url: str) -> Union[str, None]:
    """
    Extracts the repository path from a GitLab MR URL.
    """
    try:
        parsed_url = urlparse(mr_url)
        # Matches paths like /group/subgroup/repo/-/merge_requests/123
        match = re.search(r'/(.*?)/-/merge_requests/\d+', parsed_url.path)
        if match:
            return match.group(1)
        return None
    except Exception as e:
        print(f"Error parsing MR URL: {e}")
        return None


def main_git_mr(args: argparse.Namespace) -> None:
    """Main function for 'gitlab_mr' extraction mode."""
    mr_url = get_arg_value(args, ARG_GITLAB_MR_URL_LONG)

    output_dir = get_arg_value(args, ARG_OUTPUT_DIR_LONG)
    no_open_explorer = get_arg_value(args, ARG_NO_OPEN_EXPLORER)
    max_folders = get_arg_value(args, ARG_MAX_FOLDERS)

    if not mr_url:
        LOG(f"Error: --mr_url argument is required for '{EXTRACT_MODE_GIT_MR}' mode.", file=sys.stderr)
        sys.exit(1)

    # Get MR info
    mr_info = get_mr_info_from_url(mr_url)
    if not mr_info:
        LOG(f"Error: Could not retrieve MR info from URL '{mr_url}'.", file=sys.stderr)
        sys.exit(1)

    repo_name_from_url, source_branch, target_branch = mr_info
    LOG(f"Successfully retrieved MR info: {repo_name_from_url}, {source_branch}, {target_branch}")

    repo_info = LOCAL_REPO_MAPPING.get_by_name(repo_name_from_url)
    if not repo_info:
        LOG(f"Error: Could not find a local repository mapping for the provided MR URL: {mr_url}", file=sys.stderr)
        sys.exit(1)
    repo_local_path = repo_info.repo_local_path

    base = f"origin/{target_branch}"
    target = f"origin/{source_branch}"

    is_fetch_success = git_fetch(repo_local_path)
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

    diff_content = extract_git_diff(repo_local_path, base, target)
    is_success = diff_content is not None
    output_path = None

    if is_success:
        sanitized_base = sanitize_ref_for_filename(base)
        sanitized_target = sanitize_ref_for_filename(target)
        output_filename = f"diff_{sanitized_base}_vs_{sanitized_target}{TXT_EXTENSION}"
        output_path = final_output_dir / output_filename

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"# CONTEXT: Diff from MR '{mr_url}'\n")
                f.write(f"# BASE: {base}\n")
                f.write(f"# TARGET: {target}\n")
                f.write(f"# REPOSITORY: {repo_local_path.resolve().name}\n")
                f.write(f"# GENERATED AT: {datetime.now().isoformat()}\n")
                f.write(f"{'='*60}\n\n")
                f.write(diff_content)
            LOG(f"Diff content saved to '{output_path}'.")

            LOG()
            save_base_ref_files(repo_local_path, base, target, final_output_dir)

        except IOError as e:
            LOG(f"Failed to write to output file '{output_path}': {e}", file=sys.stderr)
            is_success = False

    LOG(f"\n{SUMMARY_SEPARATOR}")
    if is_success and output_path:
        LOG(f"{SUCCESS_EMOJI} Successfully processed '{repo_local_path}'.")
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
        LOG(f"{FAILURE_EMOJI} Failed to process '{repo_local_path}'.", file=sys.stderr)
        try:
            shutil.rmtree(final_output_dir)
            LOG(f"Cleaned up empty output directory: {final_output_dir}")
        except Exception as e:
            LOG(f"Could not remove empty output directory: {e}")
        sys.exit(1)
