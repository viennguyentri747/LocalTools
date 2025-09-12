#!/usr/bin/env python3
import re
from typing import Optional
from dev_common.jira_utils import JIRA_COMPANY_URL, JiraTicket, create_new_jira_client
from dev_common.format_utils import str_to_slug


def extract_key_from_jira_url(url: str) -> Optional[str]:
    """Extracts a Jira ticket key from a full Jira URL. Ex: https://<company>.atlassian.net/browse/FPA-3 -> FPA-3"""
    match = re.search(r'/browse/([A-Z0-9]+-[0-9]+)', url, re.IGNORECASE)
    if match:
        return match.group(1).upper()  # Return the key, ensuring it's uppercase
    return None


def generate_code_task_markdown(ticket: JiraTicket) -> str:
    """Generate the code task markdown content from Jira ticket data."""
    branch_name = f"feature/{ticket.key}-{str_to_slug(ticket.title)}"
    template = f"""# Jira Ticket reference

- Ticket Link: {ticket.ticket_url}
- Ticket Title: {ticket.title}
- Ticket Description:\n {ticket.description if ticket.description else 'No Jira description available'}
# Repos to make change:

- [ ] intellian_pkg
- [ ] submodule_spibeam
- [ ] insensesdk
- [ ] adc_lib
- [ ] upgrade

# Create branch command:
```
git checkout -b {branch_name}
```
"""
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
        
        # Generate and print the markdown content
        markdown_content = generate_code_task_markdown(ticket)
        print("\n" + "="*50)
        print("GENERATED CODE TASK MARKDOWN:")
        print("="*50)
        print(markdown_content)
        
    except Exception as e:
        print(f"Error retrieving Jira ticket: {e}")
        exit(1)