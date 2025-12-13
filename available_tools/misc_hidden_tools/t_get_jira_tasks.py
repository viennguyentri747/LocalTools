from typing import Dict, List
from tabulate import tabulate

from dev.dev_common.constants import *
from dev.dev_common.core_utils import read_value_from_credential_file
from dev.dev_common.jira_utils import JiraTicket, JiraClient, get_company_jira_client

# ---- User config: Set your details here ----
# print("DEBUG: JIRA_URL read:", JIRA_URL)
# print("DEBUG: USERNAME read:", USERNAME)
# print("DEBUG: API_TOKEN read (first 10 chars):", API_TOKEN[:10] if API_TOKEN else 'None')

MY_TICKET_JQL = 'assignee=currentUser() AND resolution=Unresolved ORDER BY project, priority DESC, updated DESC'
MAX_RESULTS = 50  # Increase if needed

# --------------------------------------------


def print_tables_by_project(projects: Dict[str, List[JiraTicket]]):
    """Print tickets grouped by project in table format"""
    for project_name, tickets in projects.items():
        print(f"\n{'=' * 60}\n{project_name}\n{'=' * 60}")

        # Convert Ticket objects to table data (fallback method)
        table_data = []
        for ticket in tickets:
            # Use to_table_row() if available, otherwise create manually
            if hasattr(ticket, 'to_table_row'):
                table_data.append(ticket.to_table_row())
            else:
                # Fallback: create table row manually
                table_data.append({
                    "Key": ticket.key,
                    "Summary": ticket.title[:50] + "..." if len(ticket.title) > 50 else ticket.title,
                    "Status": ticket.status_name,
                    "Priority": ticket.priority_name,
                    "Resolution": ticket.resolution_name or "Unresolved"
                })

        print(tabulate(
            table_data,
            headers="keys",
            tablefmt="fancy_grid",
            showindex=True
        ))


def print_ticket_summary(tickets):
    """Print a summary of tickets"""
    print(f"\n📊 Ticket Summary:")
    print(f"Total tickets: {len(tickets)}")

    # Count by status
    status_counts = {}
    priority_counts = {}
    project_counts = {}

    for ticket in tickets:
        # Count by status
        status_counts[ticket.status_name] = status_counts.get(ticket.status_name, 0) + 1

        # Count by priority
        priority_counts[ticket.priority_name] = priority_counts.get(ticket.priority_name, 0) + 1

        # Count by project
        project_counts[ticket.project_name] = project_counts.get(ticket.project_name, 0) + 1

    print(f"\nBy Status:")
    for status, count in status_counts.items():
        print(f"  - {status}: {count}")

    print(f"\nBy Priority:")
    for priority, count in priority_counts.items():
        print(f"  - {priority}: {count}")

    print(f"\nBy Project:")
    for project, count in project_counts.items():
        print(f"  - {project}: {count}")


def analyze_resolution_status(all_tickets):
    """Analyze resolution status of tickets"""
    resolved_tickets = [ticket for ticket in all_tickets if ticket.is_resolved]
    unresolved_tickets = [ticket for ticket in all_tickets if ticket.is_unresolved]

    print(f"\n📈 Resolution Analysis:")
    print(f"Resolved tickets: {len(resolved_tickets)}")
    print(f"Unresolved tickets: {len(unresolved_tickets)}")

    if resolved_tickets:
        print(f"\nResolved by resolution type:")
        resolution_counts = {}
        for ticket in resolved_tickets:
            resolution_counts[ticket.resolution_name] = resolution_counts.get(ticket.resolution_name, 0) + 1

        for resolution, count in resolution_counts.items():
            print(f"  - {resolution}: {count}")

    return len(resolved_tickets), len(unresolved_tickets)


def main():
    jira_client: JiraClient = get_company_jira_client()

    # Step 1: Test connection and get user info
    account_id = jira_client.test_connection()
    if not account_id:
        print("❌ Connection test failed. Check your credentials and URL.")
        return

    # Step 2: Get all assigned tickets (no resolution filter)
    all_tickets = jira_client.get_all_assigned_tickets(max_results=MAX_RESULTS)
    print(f"\nℹ️  Total assigned tickets found: {len(all_tickets)}")

    if all_tickets:
        # Analyze all assigned tickets
        resolved_count, unresolved_count = analyze_resolution_status(all_tickets)

    # Step 3: Try original query
    print("\n=== Trying Original Query ===")
    try:
        tickets = jira_client.get_tickets(MY_TICKET_JQL, max_results=MAX_RESULTS)
        print(f"DEBUG: Total tickets fetched with original query: {len(tickets)}")

        if not tickets and all_tickets:
            print("\n⚠️  Original query returned 0 results, but you have assigned tickets.")
            print("This suggests the JQL filter is too restrictive.")

            if unresolved_count > 0:
                print(f"\n🤔 You have {unresolved_count} unresolved tickets, but the query returned 0.")
                print("Try using a simpler JQL query like: 'assignee=currentUser() AND resolution is EMPTY'")

                # Show some unresolved tickets as examples
                unresolved_tickets = [ticket for ticket in all_tickets if ticket.is_unresolved]
                if unresolved_tickets:
                    print(f"\nFirst few unresolved tickets:")
                    for i, ticket in enumerate(unresolved_tickets[:3]):
                        print(f"  {i+1}. {ticket.key}: {ticket.title[:50]}... [{ticket.status_name}]")

        elif tickets:
            print_ticket_summary(tickets)
            projects = jira_client.group_tickets_by_project(tickets)
            print_tables_by_project(projects)

            # # Additional analysis
            # print(f"\n🔍 Detailed Analysis:")
            # for project_name, project_tickets in projects.items():
            #     print(f"\n{project_name} ({len(project_tickets)} tickets):")
            #     for ticket in project_tickets[:3]:  # Show first 3 tickets per project
            #         print(f"  • {ticket.key}: {ticket.summary[:40]}...")
            #         print(f"    Status: {ticket.status_name}, Priority: {ticket.priority_name}")

            #     if len(project_tickets) > 3:
            #         print(f"  ... and {len(project_tickets) - 3} more tickets")

        else:
            print("No assigned tasks found!")

    except Exception as e:
        print(f"DEBUG: Exception occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
