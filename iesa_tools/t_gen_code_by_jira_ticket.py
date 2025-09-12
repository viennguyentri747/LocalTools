#!/usr/bin/env python3
import re
from typing import Optional
from dev_common.iesa_utils import IesaManifest, parse_local_iesa_manifest
from dev_common.jira_utils import JIRA_COMPANY_URL, JiraTicket, create_new_jira_client
from dev_common.format_utils import str_to_slug
from dev_common.input_utils import prompt_input_with_options
from dev_common.constants import OW_MAIN_BRANCHES, CORE_REPOS_FOLDER_PATH


def extract_key_from_jira_url(url: str) -> Optional[str]:
    """Extracts a Jira ticket key from a full Jira URL. Ex: https://<company>.atlassian.net/browse/FPA-3 -> FPA-3"""
    match = re.search(r'/browse/([A-Z0-9]+-[0-9]+)', url, re.IGNORECASE)
    if match:
        return match.group(1).upper()  # Return the key, ensuring it's uppercase
    return None


def gen_coding_task_markdown(ticket: JiraTicket, main_branch: str) -> str:
    """Generate the code task markdown content from Jira ticket data."""
    feature_branch = f"feature/{ticket.key.lower()}-{str_to_slug(ticket.title)}"

    manifest: IesaManifest = parse_local_iesa_manifest()
    repos = manifest.get_all_repo_names()

    repo_paths = [str(CORE_REPOS_FOLDER_PATH / repo) for repo in repos if (CORE_REPOS_FOLDER_PATH / repo).is_dir()]

    # Create a bash script for interactive repo selection
    script_lines = [
        "#!/bin/bash",
        "# This script allows you to select a repository and create a new feature branch in it.",
        "",
        "# Define the list of repositories",
        "REPOS=("
    ]
    script_lines.extend([f'    "{path}"' for path in repo_paths])
    script_lines.extend([
        ")",
        "",
        "# Display the menu and get user's choice",
        "PS3='Please enter your choice: '",
        "select repo_path in \"${REPOS[@]}\"",
        "do",
        "    if [[ -n \"$repo_path\" ]]; then",
        "        echo \"You chose $repo_path\"",
        "        break",
        "    else",
        "        echo \"Invalid selection. Please try again.\"",
        "    fi",
        "done",
        "",
        "# Generate and display the git commands",
        "echo 'Run the following commands to create the branch:'",
        "echo \"cd $repo_path\"",
        f"echo \"git checkout {main_branch}\"",
        "echo \"git pull\"",
        f"echo \"git checkout -b {feature_branch}\"",
    ])

    checkout_script = "\n".join(script_lines)

    # 1. Generate the list of repos as a string first
    repo_list_str = "".join([f"- [ ] {repo}\n" for repo in repos if (CORE_REPOS_FOLDER_PATH / repo).is_dir()])

    # 2. Now, create the template using that variable
    template = (
        f"# Jira Ticket reference\n\n"
        f"- Ticket Link: {ticket.ticket_url}\n"
        f"- Ticket Title: {ticket.title}\n"
        f"- Ticket Description:\n"
        f"{ticket.description if ticket.description else 'No Jira description available'}\n\n"
        f"# Repos to make change:\n\n"
        f"{repo_list_str}\n\n"
        f"# Create branch command:\n"
        f"```bash\n"
        f"{checkout_script}\n"
        f"```"
    )

    return template


if __name__ == "__main__":
    # Request user input for Jira URL
    jira_url = input(f"Input jira url (Ex: \"{JIRA_COMPANY_URL}/browse/FPA-3\"): ").strip()

    # Validate and extract ticket key
    ticket_key = extract_key_from_jira_url(jira_url)
    if not ticket_key:
        print("Error: Invalid Jira URL format. Please provide a valid Jira URL.")
        exit(1)

    try:
        # Get Jira ticket data
        client = create_new_jira_client()
        ticket: JiraTicket = client.get_ticket_by_key(ticket_key)

        print(f"\nTicket info for {ticket_key}:")
        print(f"Summary: {ticket.title}")
        print(f"Description: {ticket.description}")

        main_branch = prompt_input_with_options("\nSelect the main branch for ow_sw_tools", OW_MAIN_BRANCHES)

        # Generate and print the markdown content
        markdown_content = gen_coding_task_markdown(ticket, main_branch)
        print("\n" + "="*50)
        print("GENERATED CODE TASK MARKDOWN:")
        print("="*50)
        print(markdown_content)

    except Exception as e:
        print(f"Error retrieving Jira ticket: {e}")
        exit(1)
