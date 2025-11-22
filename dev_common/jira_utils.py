from enum import Enum
import re
import requests
from collections import defaultdict
from typing import List, Dict, Optional, Any
from datetime import datetime

from dev_common.constants import *
from dev_common.core_utils import LOG, LOG_EXCEPTION, read_value_from_credential_file
from dev_common.format_utils import get_stripped_paragraph
from dev_common.md_utils import *

JIRA_USERNAME = read_value_from_credential_file(CREDENTIALS_FILE_PATH, JIRA_USERNAME_KEY_NAME)
JIRA_COMPANY_URL = read_value_from_credential_file(CREDENTIALS_FILE_PATH, JIRA_COMPANY_URL_KEY_NAME)
API_TOKEN = read_value_from_credential_file(CREDENTIALS_FILE_PATH, JIRA_API_TOKEN_KEY_NAME)
jira_client: 'JiraClient' = None


def get_company_jira_client() -> 'JiraClient':
    global jira_client
    if jira_client is None:
        jira_client = JiraClient(JIRA_COMPANY_URL, JIRA_USERNAME, API_TOKEN)
    return jira_client


class JiraTicket:
    """A wrapper class for JIRA ticket data"""

    def __init__(self, base_jira_url: str, ticket_data: Dict[str, Any]):
        """
        Initialize Ticket from JIRA API response data

        Args:
            ticket_data: Raw ticket data from JIRA API
        """
        self.base_jira_url = base_jira_url.rstrip('/')  # Remove trailing slash if present
        # LOG(f"DEBUG: Creating JiraTicket for ticket data: {ticket_data}")
        self.raw_data = ticket_data
        self.key: str = ticket_data.get("key", "").upper()
        # self.internal_id: str = ticket_data.get("id", "")
        self.fields = ticket_data.get("fields", {})

        # Core properties
        self.title: str = self.fields.get("summary", "")

        # Project information
        project_data = self.fields.get("project", {})
        self.project_key = project_data.get("key", "")
        self.project_name = project_data.get("name", "")

        # Status and resolution
        status_data = self.fields.get("status", {})
        self.status_name = status_data.get("name", "")
        self.status_id = status_data.get("id", "")

        resolution_data = self.fields.get("resolution")
        self.resolution_name = resolution_data.get("name", "") if resolution_data else None
        self.resolution_id = resolution_data.get("id", "") if resolution_data else None

        # Priority
        priority_data = self.fields.get("priority", {})
        self.priority_name = priority_data.get("name", "")
        self.priority_id = priority_data.get("id", "")

        # Ticket type
        tickettype_data = self.fields.get("issuetype", {})
        ticket_type_name = tickettype_data.get("name", "")
        self.ticket_type_name = ticket_type_name
        self.ticket_type_id = tickettype_data.get("id", "")
        self.issue_type: JiraIssueType = JiraIssueType.from_string(ticket_type_name)

        # Assignee and reporter
        assignee_data = self.fields.get("assignee")
        self.assignee_name = assignee_data.get("displayName", "") if assignee_data else None
        self.assignee_email = assignee_data.get("emailAddress", "") if assignee_data else None

        reporter_data = self.fields.get("reporter")
        self.reporter_name = reporter_data.get("displayName", "") if reporter_data else None
        self.reporter_email = reporter_data.get("emailAddress", "") if reporter_data else None

        # Dates (these come as strings from JIRA)
        self.created = self.fields.get("created", "")
        self.updated = self.fields.get("updated", "")
        self.due_date = self.fields.get("duedate", "")

        # Description
        raw_description = self.fields.get("description")
        self.raw_description = raw_description
        self.description = self.parse_jira_description(raw_description) if raw_description else ""

        # Environment
        raw_environment = self.fields.get("environment")
        self.raw_environment = raw_environment
        # Usually a string or None
        self.environment = self.parse_jira_description(raw_environment) if raw_environment else ""

        # Labels and components
        self.labels = self.fields.get("labels", [])
        self.components = [comp.get("name", "") for comp in self.fields.get("components", [])]

        # self.development = self.fields.get("development", {})

    def parse_jira_description(self, description: dict) -> str:
        """
        Parses a Jira Atlassian Document Format (ADF) dictionary into a plain string.
        """
        if not isinstance(description, dict) or "content" not in description:
            return ""

        text_parts = []

        def _parse_node(node, list_level=0):
            """Recursively parses a single node."""
            node_type = node.get("type")

            # Handle text nodes
            if node_type == "text":
                text = node.get("text", "")
                marks = node.get("marks", [])
                text = get_md_apply_text_marks(text, marks)
                text_parts.append(text)

            # Handle line breaks
            elif node_type == "hardBreak":
                text_parts.append(MD_NEWLINE)

            # Handle inline cards (links to Confluence pages, Jira issues, etc.)
            elif node_type == "inlineCard":
                url = node.get("attrs", {}).get("url", "")
                if url:
                    text_parts.append(get_md_inline_link(url))

            # Handle regular links
            elif node_type == "link":
                url = node.get("attrs", {}).get("href", "")
                # Parse the link content first
                link_text = []
                if "content" in node:
                    old_parts = text_parts.copy()
                    text_parts.clear()
                    for child in node["content"]:
                        _parse_node(child, list_level)
                    link_text = "".join(text_parts)
                    text_parts.clear()
                    text_parts.extend(old_parts)

                text_parts.append(get_md_link_text(link_text, url))

            # Handle mentions
            elif node_type == "mention":
                mention_text = node.get("attrs", {}).get("text", "@user")
                text_parts.append(mention_text)

            # Handle emojis
            elif node_type == "emoji":
                shortName = node.get("attrs", {}).get("shortName", "")
                text_parts.append(shortName if shortName else "")

            # Handle code blocks
            elif node_type == "codeBlock":
                language = node.get("attrs", {}).get("language", "")
                text_parts.append(get_md_code_block_start(language))
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)
                text_parts.append(get_md_code_block_end())

            # Handle inline code
            elif node_type == "code":
                text_parts.append(get_md_wrap_text(node.get("text", ""), MD_CODE_WRAPPER))

            # Handle bullet lists
            elif node_type == "bulletList":
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)

            # Handle ordered lists
            elif node_type == "orderedList":
                if "content" in node:
                    for idx, child in enumerate(node["content"], 1):
                        if child.get("type") == "listItem":
                            text_parts.append(get_md_list_prefix(list_level, is_ordered=True, index=idx))
                            if "content" in child:
                                for subchild in child["content"]:
                                    _parse_node(subchild, list_level + 1)

            # Handle task lists (todos)
            elif node_type == "taskList":
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)

            elif node_type == "taskItem":
                state = node.get("attrs", {}).get("state", "TODO")
                is_done = state == "DONE"
                text_parts.append(get_md_todo_prefix(list_level, is_done))
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level + 1)

            # Handle list items
            elif node_type == "listItem":
                text_parts.append(get_md_list_prefix(list_level))
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level + 1)

            # Handle headings
            elif node_type == "heading":
                level = node.get("attrs", {}).get("level", 1)
                text_parts.append(get_md_heading_prefix(level))
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)
                text_parts.append(MD_NEWLINE)

            # Handle images/media
            elif node_type == "media":
                alt_text = node.get("attrs", {}).get("alt", "")
                url = node.get("attrs", {}).get("url", "")
                text_parts.append(get_md_media_text(alt_text, url))

            # Handle blockquotes
            elif node_type == "blockquote":
                text_parts.append(MD_BLOCKQUOTE_PREFIX)
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)
                text_parts.append(MD_NEWLINE)

            # Handle panels (info, note, warning, error, success)
            elif node_type == "panel":
                panel_type = node.get("attrs", {}).get("panelType", "info")
                text_parts.append(get_md_panel_prefix(panel_type))
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)
                text_parts.append(MD_NEWLINE)

            # Handle status (lozenge)
            elif node_type == "status":
                status_text = node.get("attrs", {}).get("text", "")
                text_parts.append(get_md_status_badge(status_text))

            # Handle dates
            elif node_type == "date":
                timestamp = node.get("attrs", {}).get("timestamp", "")
                if timestamp:
                    text_parts.append(get_md_date_text(timestamp))

            # Handle rules (horizontal lines)
            elif node_type == "rule":
                text_parts.append(MD_HORIZONTAL_RULE)

            # Handle expand/collapse sections
            elif node_type == "expand":
                title = node.get("attrs", {}).get("title", "")
                if title:
                    text_parts.append(get_md_expand_header(title))
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)

            # Handle decision nodes
            elif node_type == "decisionList":
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)

            elif node_type == "decisionItem":
                state = node.get("attrs", {}).get("state", "DECIDED")
                text_parts.append(get_md_decision_prefix(state))
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)

            # Handle tables
            elif node_type == "table":
                text_parts.append(MD_NEWLINE)
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)
                text_parts.append(MD_NEWLINE)

            elif node_type == "tableRow":
                text_parts.append(get_md_table_cell_separator())
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)
                text_parts.append(MD_NEWLINE)

            elif node_type == "tableHeader" or node_type == "tableCell":
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)
                text_parts.append(get_md_table_cell_separator())

            # Handle extension nodes (for apps/plugins)
            elif node_type == "extension":
                extension_key = node.get("attrs", {}).get("extensionKey", "")
                text_parts.append(get_md_extension_text(extension_key))

            # Handle layout sections
            elif node_type == "layoutSection":
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)

            elif node_type == "layoutColumn":
                if "content" in node:
                    for child in node["content"]:
                        _parse_node(child, list_level)

            # Handle paragraphs and other container nodes
            elif node_type == "paragraph":
                if "content" in node:
                    for child_node in node["content"]:
                        _parse_node(child_node, list_level)
                text_parts.append(MD_NEWLINE)

            # For any other container nodes, parse their children
            elif "content" in node and isinstance(node["content"], list):
                for child_node in node["content"]:
                    _parse_node(child_node, list_level)

        # Start parsing from the top-level content
        for content_node in description["content"]:
            _parse_node(content_node)

        # Clean up the final string for better readability
        result = "".join(text_parts).strip()
        # Replace multiple consecutive newlines with just two
        while MD_TRIPLE_NEWLINE in result:
            result = result.replace(MD_TRIPLE_NEWLINE, MD_DOUBLE_NEWLINE)

        return result

    @property
    def minimal_description(self) -> str:
        """Get a minimal Jiradescription without  extra lines, attachments (image), etc."""
        result = self.description
        # Remove patterns like [image - filename.png]
        result = re.sub(r'^\s*\[image\s*-\s*.*?\]\s*$', '', result, flags=re.MULTILINE)
        result = get_stripped_paragraph(result)
        return result

    @property
    def is_resolved(self) -> bool:
        """Check if the ticket is resolved"""
        return self.resolution_name is not None

    @property
    def is_unresolved(self) -> bool:
        """Check if the ticket is unresolved"""
        return self.resolution_name is None

    @property
    def url(self) -> str:
        """Get the JIRA URL for this ticket (requires base URL to be set externally)"""
        # This would need the base JIRA URL to construct the full URL
        return f"{self.base_jira_url}/browse/{self.key}"

    def get_field(self, field_name: str) -> Any:
        """
        Get a custom field value by name

        Args:
            field_name: The field name (e.g., 'customfield_10001')

        Returns:
            The field value or None if not found
        """
        return self.fields.get(field_name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert ticket to a simple dictionary for easy display"""
        return {
            "Key": self.key,
            "Summary": self.title,
            "Project": self.project_name,
            "Status": self.status_name,
            "Priority": self.priority_name,
            "Resolution": self.resolution_name or "Unresolved",
            "Assignee": self.assignee_name,
            "Reporter": self.reporter_name,
            "Ticket Type": self.ticket_type_name,
            "Created": self.created,
            "Updated": self.updated,
        }

    def __str__(self) -> str:
        """String representation of the ticket"""
        return f"{self.key}: {self.title} [{self.status_name}]"

    def __repr__(self) -> str:
        """Developer representation of the ticket"""
        return f"Ticket(key='{self.key}', summary='{self.title[:30]}...', status='{self.status_name}')"


class JiraClient:
    """A wrapper class for JIRA API operations"""

    def __init__(self, jira_url: str, username: str, api_token: str):
        """
        Initialize the JIRA client with credentials

        Args:
            jira_url: The base URL of your JIRA instance
            username: Your JIRA username
            api_token: Your JIRA API token
        """
        self.base_jira_url = jira_url.rstrip('/')  # Remove trailing slash if present
        self.username = username
        self.api_token = api_token
        self.auth = (username, api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def test_connection(self) -> Optional[str]:
        """
        Test the JIRA connection and return account ID if successful

        Returns:
            Account ID if connection successful, None otherwise
        """
        print("\n=== Testing JIRA Connection ===")

        url = f"{self.base_jira_url}/rest/api/3/myself"
        headers = {"Accept": "application/json"}

        try:
            response = requests.get(url, headers=headers, auth=self.auth)
            print(f"DEBUG: User info request status: {response.status_code}")

            if response.status_code == 200:
                user_data = response.json()
                print(f"DEBUG: Connected as: {user_data.get('displayName')} ({user_data.get('emailAddress')})")
                print(f"DEBUG: Account ID: {user_data.get('accountId')}")
                return user_data.get('accountId')
            else:
                print(f"DEBUG: Failed to get user info: {response.text}")
                return None
        except Exception as e:
            print(f"DEBUG: Connection test failed: {e}")
            return None

    def get_ticket_count(self, jql_query: str) -> int:
        """
        Get count of tickets for a JQL query

        Args:
            jql_query: The JQL query string

        Returns:
            Number of tickets matching the query, -1 on error
        """
        url = f"{self.base_jira_url}/rest/api/3/search/jql"
        payload = {
            "jql": jql_query,
            "maxResults": 0,  # Just get the count
            "fields": ["key"]
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, auth=self.auth)
            if response.status_code == 200:
                data = response.json()
                return data.get("total", 0)
            else:
                print(f"DEBUG: Query failed: {response.text}")
                return -1
        except Exception as e:
            print(f"DEBUG: Query exception: {e}")
            return -1

    def get_tickets(self, jql_query: str, max_results: int = 50,
                    fields: List[str] = None) -> List[JiraTicket]:
        """
        Search for tickets using JQL

        Args:
            jql_query: The JQL query string
            max_results: Maximum number of results to return
            fields: List of fields to include in the response

        Returns:
            List of Ticket objects
        """
        if fields is None:
            fields = [
                "key", "summary", "project", "priority", "status", "resolution",
                "issuetype", "assignee", "reporter", "created", "updated",
                "duedate", "description", "labels", "components"
            ]

        url = f"{self.base_jira_url}/rest/api/3/search/jql"
        payload = {
            "jql": jql_query,
            "maxResults": max_results,
            "fields": fields
        }

        print(f"DEBUG: Request URL: {url}")
        print(f"DEBUG: Payload JQL: {payload['jql']}")
        print(f"DEBUG: Auth username: {self.username}")

        try:
            response = requests.post(url, headers=self.headers, json=payload, auth=self.auth)
            print(f"DEBUG: Response status code: {response.status_code}")

            if response.status_code != 200:
                print(f"DEBUG: Response text: {response.text}")
                response.raise_for_status()

            data = response.json()

            # Debug: Print the response structure
            print(f"DEBUG: Response keys: {list(data.keys())}")

            # Get tickets from response and convert to Ticket objects
            tickets_data = data.get("issues", [])
            tickets = [JiraTicket(self.base_jira_url, ticket_data) for ticket_data in tickets_data]

            print(f"DEBUG: Number of tickets in response: {len(tickets)}")

            # Check if there's a total field and print it
            if "total" in data:
                print(f"DEBUG: Total tickets available: {data['total']}")
            else:
                print("DEBUG: No 'total' field in response")

            # Print first few ticket keys for verification
            if tickets:
                print("DEBUG: First few tickets:")
                for i, ticket in enumerate(tickets[:3]):
                    print(f"  {i+1}. {ticket.key}: {ticket.title[:60]}...")

            return tickets

        except Exception as e:
            print(f"DEBUG: Exception occurred: {e}")
            raise

    def get_all_assigned_tickets(self, max_results: int = 50) -> List[JiraTicket]:
        """
        Get all tickets assigned to current user (no filters)

        Args:
            max_results: Maximum number of results to return

        Returns:
            List of Ticket objects
        """
        print("\n=== Getting All Assigned Tickets ===")

        jql_query = "assignee=currentUser()"  # Simplest query

        print(f"DEBUG: Simplified JQL: {jql_query}")

        tickets = self.get_tickets(jql_query, max_results)

        # Print details about each ticket using the Ticket class
        for i, ticket in enumerate(tickets[:5]):  # Show first 5
            print(f"DEBUG: Ticket {i+1}: {ticket.key} - {ticket.title[:50]}...")
            print(f"       Project: {ticket.project_name}")
            print(f"       Status: {ticket.status_name}")
            print(f"       Resolution: {ticket.resolution_name or 'Unresolved'}")
            print()

        return tickets

    def group_tickets_by_project(self, tickets: List[JiraTicket]) -> Dict[str, List[JiraTicket]]:
        """
        Group tickets by project

        Args:
            tickets: List of Ticket objects

        Returns:
            Dictionary with project names as keys and lists of Ticket objects as values
        """
        projects = defaultdict(list)
        for ticket in tickets:
            projects[ticket.project_name].append(ticket)
        return dict(projects)

    def analyze_assigned_tickets(self, tickets: List[JiraTicket]) -> Dict[str, int]:
        """
        Analyze assigned tickets to get resolution statistics

        Args:
            tickets: List of Ticket objects

        Returns:
            Dictionary with 'resolved' and 'unresolved' counts
        """
        resolved_count = 0
        unresolved_count = 0

        for ticket in tickets:
            if ticket.is_resolved:
                resolved_count += 1
            else:
                unresolved_count += 1

        return {
            "resolved": resolved_count,
            "unresolved": unresolved_count
        }

    def get_ticket_by_key(self, ticket_key: str) -> Optional[JiraTicket]:
        """
        Get a single ticket by its key

        Args:
            ticket_key: The JIRA ticket key (e.g., 'PROJ-123')

        Returns:
            Ticket object if found, None otherwise
        """
        url = f"{self.base_jira_url}/rest/api/3/issue/{ticket_key}"

        try:
            response = requests.get(url, headers=self.headers, auth=self.auth)
            if response.status_code == 200:
                ticket_data = response.json()
                return JiraTicket(self.base_jira_url, ticket_data)
            else:
                print(f"DEBUG: Failed to get ticket {ticket_key}: {response.text}")
                return None
        except Exception as e:
            LOG_EXCEPTION(exception=e)
            return None


# Example usage:
if __name__ == "__main__":
    # Initialize client
    client = JiraClient("https://your-domain.atlassian.net", "your-email", "your-api-token")

    # Test connection
    account_id = client.test_connection()
    if not account_id:
        print("Failed to connect to JIRA")
        exit(1)

    # Get all assigned tickets
    tickets = client.get_all_assigned_tickets(max_results=10)

    # Now you can access ticket properties directly:
    for ticket in tickets:
        print(f"Key: {ticket.key}")
        print(f"Summary: {ticket.title}")
        print(f"Status: {ticket.status_name}")
        print(f"Is Resolved: {ticket.is_resolved}")
        print(f"Project: {ticket.project_name}")
        print("-" * 50)

    # Group by project
    grouped = client.group_tickets_by_project(tickets)
    for project_name, project_tickets in grouped.items():
        print(f"\nProject: {project_name}")
        for ticket in project_tickets:
            print(f"  - {ticket}")

    # Get statistics
    stats = client.analyze_assigned_tickets(tickets)
    print(f"\nStatistics:")
    print(f"Resolved: {stats['resolved']}")
    print(f"Unresolved: {stats['unresolved']}")


class JiraIssueType(Enum):
    """Enumeration of common JIRA issue types."""
    BUG = "Bug"
    TASK = "Task"
    STORY = "Story"
    EPIC = "Epic"
    SUBTASK = "Sub-task"
    IMPROVEMENT = "Improvement"
    INCIDENT = "Incident"
    CHANGE_REQUEST = "Change Request"
    TEST = "Test"
    UNKNOWN = "Unknown"

    @staticmethod
    def from_string(name: str) -> "JiraIssueType":
        """Convert string name to JiraIssueType, fallback to UNKNOWN."""
        normalized = (name or "").strip().lower()
        for issue_type in JiraIssueType:
            if issue_type.value.lower() == normalized:
                return issue_type
        return JiraIssueType.UNKNOWN
