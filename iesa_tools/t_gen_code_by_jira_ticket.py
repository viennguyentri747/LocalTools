#!/usr/bin/env python3
import re
from typing import Optional
from dev_common.jira_utils import JIRA_COMPANY_URL, JiraIssue, create_new_jira_client


def extract_key_from_jira_url(url: str) -> Optional[str]:
    """Extracts a Jira issue key from a full Jira URL. Ex: https://<company>.atlassian.net/browse/FPA-3 -> FPA-3"""
    match = re.search(r'/browse/([A-Z0-9]+-[0-9]+)', url, re.IGNORECASE)
    if match:
        return match.group(1).upper()  # Return the key, ensuring it's uppercase
    return None


def generate_code_task_markdown(issue: JiraIssue) -> str:
    """Generate the code task markdown content from Jira issue data."""
    template = f"""# Jira Ticket reference

- Jira Link: {issue.issue_url}
- Jira Description: {issue.description if issue.description else 'No Jira description available'}
# Repos to make change:

- [ ] intellian_pkg
- [ ] submodule_spibeam
- [ ] insensesdk
- [ ] adc_lib
- [ ] upgrade

# Branch
"""
    
    return template


if __name__ == "__main__":
    # Request user input for Jira URL
    jira_url = input(f"Input jira url (Ex: \"{JIRA_COMPANY_URL}/browse/FPA-3\"): ").strip()
    
    # Validate and extract issue key
    issue_key = extract_key_from_jira_url(jira_url)
    if not issue_key:
        print("Error: Invalid Jira URL format. Please provide a valid Jira URL.")
        exit(1)
    
    try:
        # Get Jira issue data
        client = create_new_jira_client()
        issue: JiraIssue = client.get_issue_by_key(issue_key)
        
        print(f"\nIssue info for {issue_key}:")
        print(f"Summary: {issue.summary}")
        print(f"Description: {issue.description}")
        
        # Generate and print the markdown content
        markdown_content = generate_code_task_markdown(issue)
        print("\n" + "="*50)
        print("GENERATED CODE TASK MARKDOWN:")
        print("="*50)
        print(markdown_content)
        
    except Exception as e:
        print(f"Error retrieving Jira issue: {e}")
        exit(1)