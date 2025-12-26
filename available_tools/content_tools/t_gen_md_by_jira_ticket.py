#!/home/vien/local_tools/MyVenvFolder/bin/python
import re
import argparse
from typing import Optional, List
from dev.dev_common import *
from dev.dev_iesa import *
# cmd.exe /c curl -X GET "http://127.0.0.1:27123/commands/" -H "accept: application/json" -H "Authorization: Bearer 647569e74ba327766ebee74be157d37cdeda23f6b8b4b8b36ff8011b90c56fb4"

PATH_TO_WORKING_NOTES = f"Notes/_Root/CurrentWorking/Intellian Working (Link, How to…)/Intellian Note working, diary (work log)/"


def get_tool_templates() -> List[ToolTemplate]:
    """Get tool templates."""
    return [
        ToolTemplate(
            name="Gen content by Company Jira Ticket",
            # extra_description="Generate coding task markdown from a Jira ticket URL.",
            args={
                ARG_VAULT_PATH: f"{Path.home()}/obsidian_work_vault/",
                ARG_NOTE_REL_PATH: f"{PATH_TO_WORKING_NOTES}",
                ARG_NOTE_REL_PATHS_TO_ADD_CONTENT: [f"{PATH_TO_WORKING_NOTES}/_Intellian Note working, diary (work log).md"],
                ARG_DEFAULT_OW_MANIFEST_BRANCH: BRANCH_MANPACK_MASTER,
                ARG_IS_GEN_CODING_TASK: False,
                ARG_TICKET_URL: f"{JIRA_COMPANY_URL}/browse/ESA1W-6816",
            },
        )
    ]


def extract_key_from_jira_url(url: str) -> Optional[str]:
    """Extracts a Jira ticket key from a full Jira URL. Ex: https://<company>.atlassian.net/browse/ESA1W-6816 -> ESA1W-6816"""
    match = re.search(r'/browse/([A-Z0-9]+-[0-9]+)', url, re.IGNORECASE)
    if match:
        return match.group(1).upper()  # Return the key, ensuring it's uppercase
    return None


class CodingTaskInfo:
    main_ow_branch: str

    def __init__(self, main_ow_branch: str) -> None:
        self.main_ow_branch = main_ow_branch


def gen_content_markdown(ticket: JiraTicket, coding_task_info: Optional[CodingTaskInfo]) -> str:
    """Generate the code task markdown content from Jira ticket data."""
    spacing_between_line_around_headers = "\n\n"
    spacing_between_lines = "\n"
    md_content_to_gen: str = (
        f"# Ticket Overview{spacing_between_line_around_headers}"
        f"- Title: {ticket.title}{spacing_between_lines}"
        f"- Link: {ticket.url}{spacing_between_line_around_headers}"
    )

    # has_body = False
    # if ticket.description:
    #     md_content_to_gen += (
    #         f"#### Description:{spacing_between_line_around_headers}"
    #         f"{ticket.description}{spacing_between_line_around_headers}"
    #     )
    #     has_body = True

    # if ticket.environment:
    #     md_content_to_gen += (
    #         f"#### Environment:{spacing_between_line_around_headers}"
    #         f"{ticket.environment}{spacing_between_line_around_headers}"
    #     )
    #     has_body = True

    # if not has_body:
    #     md_content_to_gen += f"*No additional ticket context provided.*{spacing_between_line_around_headers}"

    if coding_task_info:
        manifest: IesaManifest = get_repo_manifest_from_remote(coding_task_info.main_ow_branch)
        repo_names = manifest.get_all_repo_names(include_ow_sw_repos=True)
        # Generate the list of repos as a string
        repo_list_str = "".join([f"- [ ] {repo}\n" for repo in repo_names if (CORE_REPOS_PATH / repo).is_dir()])
        
        md_content_to_gen += (
            f"# Repos to make change:{spacing_between_line_around_headers}"
            f"{repo_list_str}{spacing_between_line_around_headers}"
            f"# Create branch command:{spacing_between_line_around_headers}"
            f"```bash{spacing_between_lines}"
            f"{gen_checkout_command(ticket, coding_task_info.main_ow_branch)}{spacing_between_lines}"
            f"```{spacing_between_line_around_headers}"
        )

    md_content_to_gen += f"# Notes{spacing_between_line_around_headers}"

    return md_content_to_gen


def gen_checkout_command(ticket: JiraTicket, main_manifest_branch: str) -> str:
    """Generate the checkout command for a given Jira ticket and main branch."""
    branch_name = f"{get_branch_prefix_from_ticket(ticket)}/{ticket.key}-{str_to_slug(ticket.title)}"
    repo_manifest: IesaManifest = get_repo_manifest_from_remote(main_manifest_branch)
    repo_names = repo_manifest.get_all_repo_names(include_ow_sw_repos=True)

    # Build the case statement for repo info resolution
    case_statement = "case $repo_name in "
    for repo_name in repo_names:
        if repo_name == IESA_OW_SW_TOOLS_REPO_NAME:
            revision = main_manifest_branch
        else:
            revision = repo_manifest.get_repo_revision(repo_name)

        case_statement += f'"{repo_name}") repo_revision="{revision}";; '
    case_statement += "*) repo_revision=\"\" ;; esac"

    # Command with revision-based checkout
    repo_options = " ".join([f'"{name}"' for name in repo_names])
    command = (
        f"repo_base_dir=\"{CORE_REPOS_PATH}\"; "
        f"echo -e \"\\n🔎 Found below repo(s):\"; PS3='Enter your choice (number): '; "
        f"select repo_name in {repo_options}; do "
        f"    {case_statement}; "
        f"    repo_path=\"$repo_base_dir/$repo_name\"; "
        f"    cd \"$repo_path\" && git fetch --all; "
        f"    if git show-ref --verify --quiet refs/heads/{branch_name}; then "
        f"        echo -e \"Use existing branch:\\n\\ncd \\\"$repo_path\\\" && git checkout {branch_name}\"; "
        f"    else "
        f"        echo -e \"Create new branch:\\n\\ncd \\\"$repo_path\\\" && git checkout $repo_revision && git pull origin $repo_revision && git checkout -b {branch_name}\"; "
        f"    fi; "
        f"    break; "
        f"done"
    )

    return command


def get_branch_prefix_from_ticket(ticket: JiraTicket) -> str:
    """Get the branch prefix based on the ticket type."""
    if ticket.issue_type == JiraIssueType.BUG:
        return "fix"
    elif ticket.issue_type == JiraIssueType.TASK or ticket.issue_type == JiraIssueType.STORY:
        return "feat"
    else:
        return "chore"  # Default prefix for other types


def get_repo_manifest_from_remote(main_manifest_branch: str) -> IesaManifest:
    """Gets the repo manifest from the remote GitLab repository."""
    # Use get_gl_project to get the manifest project object
    # token = read_value_from_credential_file(CREDENTIALS_FILE_PATH, GL_OW_SW_TOOLS_TOKEN_KEY_NAME)
    gl_repo_info: IesaLocalRepoInfo = get_repo_info_by_name(IESA_OW_SW_TOOLS_REPO_NAME)
    ow_sw_tools_project = get_gl_project(gl_repo_info)

    LOG(f"Fetching manifest from branch '{main_manifest_branch}' of project '{ gl_repo_info.gl_project_path}', path '{IESA_MANIFEST_FILE_PATH_LOCAL}'...")
    # Use get_file_from_remote to fetch the manifest content
    manifest_content = get_file_from_remote(ow_sw_tools_project, str(IESA_MANIFEST_RELATIVE_PATH), main_manifest_branch)

    # Use parse_remote_iesa_manifest to parse the content
    manifest: IesaManifest = parse_remote_gl_iesa_manifest(manifest_content)

    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate coding task markdown from a Jira ticket.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=build_examples_epilog(get_tool_templates(), Path(__file__))
    )

    parser.add_argument(ARG_TICKET_URL, type=str, required=False, help="The full URL of the Jira ticket.")
    parser.add_argument(ARG_DEFAULT_OW_MANIFEST_BRANCH, type=str, required=False,
                        help="The manifest branch to use for generating checkout commands.")
    parser.add_argument(f"{ARG_IS_GEN_CODING_TASK}", type=lambda x: x.lower() == TRUE_STR_VALUE, required=True,
                        help="Is generating coding task content.")
    parser.add_argument(ARG_VAULT_PATH, type=str, required=False, default=None,
                        help="The destination directory for the generated file.")
    parser.add_argument(ARG_NOTE_REL_PATH, type=str, required=False, default=None,
                        help="The relative path (vs vault) to note that need to fill with content.")
    parser.add_argument(ARG_NOTE_REL_PATHS_TO_ADD_CONTENT, nargs='+', default=[], required=False,
                        help="The relative paths (vs vault) to add note (with filled content)'s link.")

    args = parser.parse_args()

    jira_url = get_arg_value(args, ARG_TICKET_URL)
    rel_note_dir = get_arg_value(args, ARG_NOTE_REL_PATH)
    vault_dir_str = get_arg_value(args, ARG_VAULT_PATH)
    rel_paths_to_add_link = get_arg_value(args, ARG_NOTE_REL_PATHS_TO_ADD_CONTENT)

    # Request user input for Jira URL
    if not jira_url:
        jira_url = input(f"Input jira url (Ex: \"{JIRA_COMPANY_URL}/browse/FPA-3\"): ").strip()

    # Validate and extract ticket key
    ticket_key = extract_key_from_jira_url(jira_url)
    if not ticket_key:
        LOG("Error: Invalid Jira URL format. Please provide a valid Jira URL.")
        exit(1)

    # Get Jira ticket data
    client = get_company_jira_client()
    ticket: JiraTicket = client.get_ticket_by_key(ticket_key)

    is_gen_coding_task = get_arg_value(args, ARG_IS_GEN_CODING_TASK)
    if is_gen_coding_task:
        main_branch = get_arg_value(args, ARG_DEFAULT_OW_MANIFEST_BRANCH)
        if not main_branch:
            main_branch = prompt_input_with_options(
                "\nSelect the main branch for ow_sw_tools", OW_MAIN_BRANCHES, default_input=OW_MAIN_BRANCHES[0])
        coding_task_content = CodingTaskInfo(main_ow_branch=main_branch)
    else:
        coding_task_content = None

    # Generate and LOG the markdown content
    markdown_content = gen_content_markdown(ticket, coding_task_content)

    # Save the generated markdown content to a file
    file_prefix = f"{ticket.key} "
    file_name = f"{sanitize_str_to_file_name(file_prefix + ticket.title)}.md"
    file_path = PERSISTENT_TEMP_PATH / file_name
    if vault_dir_str and rel_note_dir:
        should_create_note = True
        destination_dir_path = Path(strip_quotes(vault_dir_str)) / strip_quotes(rel_note_dir)  # Clean the path first
        # breakpoint()
        if not destination_dir_path.exists():
            LOG(f"{LOG_PREFIX_MSG_ERROR} Destination directory does not exist: {destination_dir_path}")
            should_create_note = False
        else:
            # 1. Check if exact file already exists
            destination_path = destination_dir_path / file_name
            if destination_path.exists():
                if prompt_confirmation(f"Warning: File '{file_name}' already exists in destination. Overwrite?"):
                    backup_path = PERSISTENT_TEMP_PATH / f"{file_name}.backup"
                    copy_file(destination_path, backup_path)
                    LOG(f"Backed up existing file to {backup_path}")
                else:
                    LOG(f"Copy operation cancelled by user.")
                    should_create_note = False
            # 2. Check for files with same prefix (only if exact file doesn't exist)
            else:
                existing_files_with_prefix = list(destination_dir_path.glob(f"{file_prefix}*"))
                if existing_files_with_prefix:
                    file_list_str = "\n".join([f"- {f.name}" for f in existing_files_with_prefix])
                    if not prompt_confirmation(f"Found existing file(s) with prefix '{file_prefix}' in destination:\n{file_list_str}\n\nCreate new file anyway?"):
                        LOG(f"Copy operation cancelled by user.")
                        should_create_note = False

        # 3. Create note
        if should_create_note:
            # Optional alias: use the JIRA key prefix (e.g., "MANP-268")
            # alias = file_prefix.rstrip("_")
            # Build the wikilink list item
            wikilink_line = f"\n- [ ] {to_wikilink(Path(file_name))}\n"
            # Regex to match the exact heading line
            heading_regex = r"^#\s*Common\s*\+\s*Log daily\s*$"
            for path_to_add_link_str in rel_paths_to_add_link:
                # Call YOUR helper (pass vault_path explicitly)
                insert_success = insert_content_after_regex(
                    note_vault_rel_path=Path(path_to_add_link_str),
                    prefix_regex=heading_regex,
                    content_to_insert=wikilink_line,
                    vault_path=Path(vault_dir_str),
                    flags=re.MULTILINE,
                    insert_all=False,
                    prevent_duplicate=True,
                )

                if insert_success:
                    LOG(f"Successfully inserted link to {path_to_add_link_str}")
                else:
                    LOG(f"Failed to insert link to {path_to_add_link_str}")
            # output_dir_path = get_arg_value(args, ARG_DIR_TO_COPY_TO, for_shell=True)
            rel_destination_path = Path(strip_quotes(rel_note_dir)) / file_name
            success = create_obsidian_note_with_template(note_vault_rel_path=str(
                rel_destination_path), markdown_content=markdown_content)
            if success:
                LOG(f"Successfully created note at {destination_path}")
            else:
                LOG(f"❌ Failed to create note at {destination_path}")
    else:
        display_content_to_copy(markdown_content, purpose="Use for markdown content", is_copy_to_clipboard=True)
