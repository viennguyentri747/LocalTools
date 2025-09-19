#!/home/vien/local_tools/MyVenvFolder/bin/python
import re
import argparse
from typing import Optional
from dev_common import *


def extract_key_from_jira_url(url: str) -> Optional[str]:
    """Extracts a Jira ticket key from a full Jira URL. Ex: https://<company>.atlassian.net/browse/FPA-3 -> FPA-3"""
    match = re.search(r'/browse/([A-Z0-9]+-[0-9]+)', url, re.IGNORECASE)
    if match:
        return match.group(1).upper()  # Return the key, ensuring it's uppercase
    return None


def gen_coding_task_markdown(ticket: JiraTicket, main_branch: str) -> str:
    """Generate the code task markdown content from Jira ticket data."""
    manifest: IesaManifest = parse_local_iesa_manifest()
    repos = manifest.get_all_repo_names()
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
        f"{gen_checkout_command(ticket, main_branch)}\n"
        f"```"
    )
    return template


def gen_checkout_command(ticket: JiraTicket, main_manifest_branch: str) -> str:
    """Generate the checkout command for a given Jira ticket and main branch."""
    feature_branch = f"feat/{ticket.key.lower()}-{str_to_slug(ticket.title)}"
    repo_manifest: IesaManifest = get_repo_manifest(main_manifest_branch)

    # Build the case statement for repo info resolution
    case_statement = "case $repo_name in "
    repo_names = repo_manifest.get_all_repo_names()
    for repo_name in repo_names:
        repo_path = CORE_REPOS_FOLDER_PATH / repo_name
        revision = repo_manifest.get_repo_revision(repo_name) or 'HEAD'  # Default to HEAD if no revision
        remote = 'origin'    # Hard code to origin instead of repo_manifest.get_repo_remote(repo_name)
        case_statement += f'"{repo_name}") repo_path="{repo_path}"; repo_revision="{revision}"; repo_remote="{remote}";; '
    case_statement += "*) repo_path=\"\"; repo_revision=\"\"; repo_remote=\"\" ;; esac"

    # Command with revision-based checkout (no fallback)
    repo_options = " ".join([f'"{name}"' for name in repo_names])
    command = (
        f"echo -e \"\\n🔎 Found below repo(s):\"; PS3='Enter your choice (number): '; "
        f"select repo_name in {repo_options}; do "
        f"    {case_statement}; "
        f"    git -C \"$repo_path\" fetch --all; "
        f"    if git -C \"$repo_path\" show-ref --verify --quiet refs/heads/{feature_branch}; then "
        f"        echo -e \"Use existing feature branch with command below:\\ngit -C \\\"$repo_path\\\" checkout {feature_branch}\"; "
        f"    else "
        f"        echo -e \"Create new feature branch with command below:\\ngit -C \\\"$repo_path\\\" checkout $repo_revision && git pull origin $repo_revision && git -C \\\"$repo_path\\\" checkout -b {feature_branch}\"; "
        f"    fi; "
        f"    break; "
        f"done"
    )

    return command


def get_repo_manifest(main_manifest_branch: str) -> IesaManifest:
    # Checkout + pull from main branch
    checkout_main_branch = f"git -C {OW_SW_PATH} checkout {main_manifest_branch}"
    run_shell(checkout_main_branch)
    remotes = get_git_remotes(OW_SW_PATH)
    if (len(remotes) == 1):
        remote = remotes[0]
    else:
        remote = prompt_input_with_options(f"Select remote", remotes)
    run_shell(f"git -C {OW_SW_PATH} pull {remote} {main_manifest_branch}")
    manifest: IesaManifest = parse_local_iesa_manifest()
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate coding task markdown from a Jira ticket.")
    parser.add_argument(ARG_TICKET_URL_LONG, type=str, required=False, help="The full URL of the Jira ticket.")
    parser.add_argument(ARG_OW_MANIFEST_BRANCH_LONG, type=str, required=False,
                        help="The manifest branch to use for generating checkout commands.")
    args = parser.parse_args()

    jira_url = get_arg_value(args, ARG_TICKET_URL_LONG)
    # Request user input for Jira URL
    if not jira_url:
        jira_url = input(f"Input jira url (Ex: \"{JIRA_COMPANY_URL}/browse/FPA-3\"): ").strip()

    # Validate and extract ticket key
    ticket_key = extract_key_from_jira_url(jira_url)
    if not ticket_key:
        print("Error: Invalid Jira URL format. Please provide a valid Jira URL.")
        exit(1)

    # Get Jira ticket data
    client = create_new_jira_client()
    ticket: JiraTicket = client.get_ticket_by_key(ticket_key)

    print(f"\nTicket info for {ticket_key}:")
    print(f"Summary: {ticket.title}")
    print(f"Description: {ticket.description}")

    main_branch = get_arg_value(args, ARG_OW_MANIFEST_BRANCH_LONG)
    if not main_branch:
        main_branch = prompt_input_with_options(
            "\nSelect the main branch for ow_sw_tools", OW_MAIN_BRANCHES, default_option=OW_MAIN_BRANCHES[0])

    # Generate and print the markdown content
    markdown_content = gen_coding_task_markdown(ticket, main_branch)
    print("\n" + "="*50)
    print("GENERATED CODE TASK MARKDOWN:")
    print("="*50)
    print(markdown_content)
