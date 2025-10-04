#!/home/vien/local_tools/MyVenvFolder/bin/python
import argparse
import re
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Optional, List

from dev_common import *
from dev_common.gitlab_utils import get_gl_project, is_gl_branch_exists

JIRA_BASE_URL = "https://intelliantech.atlassian.net"


def get_tool_templates() -> List[ToolTemplate]:
    """Provide starter examples for CLI help output."""
    default_repo = IESA_OW_SW_TOOLS_REPO_NAME
    return [
        ToolTemplate(
            name="Generate GitLab MR for sample branch",
            args={
                ARG_REPO_NAME: default_repo,
                ARG_SOURCE_BRANCH: "ESA1W-6583_TEST_FIX_FTM_UPGRADE", #Branch name without remote prefix. Ex: feat, NOT origin/feat
                ARG_TARGET_BRANCH: "manpack_master",
            },
        )
    ]


def extract_ticket_tag(branch_name: str) -> Optional[str]:
    """Return the ticket key located at the start of the branch."""
    if not branch_name:
        return None
    final_segment = branch_name.split("/")[-1]
    match = re.match(r"([a-zA-Z][a-zA-Z0-9]+-\d+)", final_segment)
    if match:
        return match.group(1)
    return None


def build_mr_description(
    jira_ticket: JiraTicket = None,
) -> str:
    """Fill the Markdown template with contextual details."""

    # - Auto-generated MR for `{repo_name}` moving `{source_branch}` into `{target_branch}`.
    content = dedent(
        f"""
## Description / What this MR does
{jira_ticket.minimal_description}

## Associated Jira tasks
{f"- [{jira_ticket.key}]({jira_ticket.url})" if jira_ticket else "- None"}

## Testing done for this MR
- Tested ?

## Additional Information
"""
    ).strip()

    return content


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def ensure_temp_directory() -> Path:
    TEMP_FOLDER_PATH.mkdir(parents=True, exist_ok=True)
    return TEMP_FOLDER_PATH


def write_markdown_file(content: str, repo_name: str, ticket_tag: Optional[str], source_branch: str) -> Path:
    temp_dir = ensure_temp_directory()
    ticket_part = ticket_tag or "no_ticket"
    filename = f"mr_{sanitize_filename(ticket_part)}_{sanitize_filename(repo_name)}_{sanitize_filename(source_branch)}.md"
    path = temp_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate GitLab MR metadata and create the MR automatically.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=build_examples_epilog(get_tool_templates(), Path(__file__))
    )

    parser.add_argument(ARG_REPO_NAME, required=False, help="Repository name as defined in local mapping.")
    parser.add_argument(ARG_SOURCE_BRANCH, required=True, help="Source branch for the merge request.")
    parser.add_argument(ARG_TARGET_BRANCH, required=True, help="Target branch to merge into.")

    args = parser.parse_args()

    repo_name = get_arg_value(args, ARG_REPO_NAME)
    if not repo_name:
        options = [repo.repo_name for repo in LOCAL_REPO_MAPPING]
        repo_name = prompt_input_with_options("Select repository", options, default_input=options[0] if options else "")
        if not repo_name:
            LOG(f"{LOG_PREFIX_MSG_ERROR} Repository name is required.")
            return

    repo_info: IesaLocalRepoInfo = get_repo_info_by_name(repo_name)
    repo_gl_project: Project = get_gl_project(repo_info)

    source_branch = get_arg_value(args, ARG_SOURCE_BRANCH)
    target_branch = get_arg_value(args, ARG_TARGET_BRANCH)

    project_path = getattr(repo_gl_project, "path_with_namespace", repo_name)

    if not is_gl_branch_exists(repo_gl_project, source_branch):
        LOG( f"{LOG_PREFIX_MSG_ERROR} Source branch '{source_branch}' does not exist in '{project_path}'." )
        exit(1)

    if not is_gl_branch_exists(repo_gl_project, target_branch):
        LOG( f"{LOG_PREFIX_MSG_ERROR} Target branch '{target_branch}' does not exist in '{project_path}'." )
        exit(1)

    jira_client: JiraClient = get_company_jira_client()
    ticket_key = extract_ticket_tag(source_branch)
    ticket: Optional[JiraTicket] = jira_client.get_ticket_by_key(ticket_key) if ticket_key else None
    if not ticket:
        LOG(f"{LOG_PREFIX_MSG_INFO} No associated Jira ticket found for '{source_branch}'.")
        exit(1)

    mr_title = f"[{ticket.key}] {ticket.title}"
    LOG(f"{LOG_PREFIX_MSG_INFO} Preparing MR '{mr_title}' from '{source_branch}' to '{target_branch}' in repo '{repo_name}'")
    description = build_mr_description(
        jira_ticket=ticket,
    )

    markdown_path = write_markdown_file(description, repo_name, ticket_key, source_branch)
    LOG(f"{LOG_PREFIX_MSG_INFO} Markdown written to {markdown_path}")

    existing_open_mrs = get_gl_mrs_of_branch(
        gl_project=repo_gl_project,
        source_branch=source_branch,
        target_branch=target_branch,
        include_closed=False,
    )

    if existing_open_mrs:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Found existing open MR(s) for '{source_branch}':")
        for mr in existing_open_mrs:
            LOG(f"  !{mr.iid}: {mr.title} -> {mr.web_url}")
        if not prompt_confirmation("Proceed with creating another MR anyway?"):
            LOG(f"{LOG_PREFIX_MSG_INFO} Aborted by user due to existing MR.")
            return

    created_mr = create_gl_mr(
        gl_project=repo_gl_project,
        source_branch=source_branch,
        target_branch=target_branch,
        title=mr_title,
        description=description,
    )

    if not created_mr:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Merge request creation failed.")
        return

    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Created MR !{created_mr.iid}: {created_mr.web_url}")


if __name__ == "__main__":
    main()
