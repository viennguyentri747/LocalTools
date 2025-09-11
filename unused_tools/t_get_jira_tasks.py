from typing import Dict, List
from tabulate import tabulate

from dev_common.constants import *
from dev_common.core_utils import read_value_from_credential_file
from dev_common.jira_utils import JiraIssue, JiraClient, create_new_jira_client

# ---- User config: Set your details here ----
# print("DEBUG: JIRA_URL read:", JIRA_URL)
# print("DEBUG: USERNAME read:", USERNAME)
# print("DEBUG: API_TOKEN read (first 10 chars):", API_TOKEN[:10] if API_TOKEN else 'None')

MY_ISSUE_JQL = 'assignee=currentUser() AND resolution=Unresolved ORDER BY project, priority DESC, updated DESC'
MAX_RESULTS = 50  # Increase if needed

# --------------------------------------------


def print_tables_by_project(projects: Dict[str, List[JiraIssue]]):
    """Print issues grouped by project in table format"""
    for project_name, issues in projects.items():
        print(f"\n{'=' * 60}\n{project_name}\n{'=' * 60}")

        # Convert Issue objects to table data (fallback method)
        table_data = []
        for issue in issues:
            # Use to_table_row() if available, otherwise create manually
            if hasattr(issue, 'to_table_row'):
                table_data.append(issue.to_table_row())
            else:
                # Fallback: create table row manually
                table_data.append({
                    "Key": issue.key,
                    "Summary": issue.summary[:50] + "..." if len(issue.summary) > 50 else issue.summary,
                    "Status": issue.status_name,
                    "Priority": issue.priority_name,
                    "Resolution": issue.resolution_name or "Unresolved"
                })

        print(tabulate(
            table_data,
            headers="keys",
            tablefmt="fancy_grid",
            showindex=True
        ))


def print_issue_summary(issues):
    """Print a summary of issues"""
    print(f"\n📊 Issue Summary:")
    print(f"Total issues: {len(issues)}")

    # Count by status
    status_counts = {}
    priority_counts = {}
    project_counts = {}

    for issue in issues:
        # Count by status
        status_counts[issue.status_name] = status_counts.get(issue.status_name, 0) + 1

        # Count by priority
        priority_counts[issue.priority_name] = priority_counts.get(issue.priority_name, 0) + 1

        # Count by project
        project_counts[issue.project_name] = project_counts.get(issue.project_name, 0) + 1

    print(f"\nBy Status:")
    for status, count in status_counts.items():
        print(f"  - {status}: {count}")

    print(f"\nBy Priority:")
    for priority, count in priority_counts.items():
        print(f"  - {priority}: {count}")

    print(f"\nBy Project:")
    for project, count in project_counts.items():
        print(f"  - {project}: {count}")


def analyze_resolution_status(all_issues):
    """Analyze resolution status of issues"""
    resolved_issues = [issue for issue in all_issues if issue.is_resolved]
    unresolved_issues = [issue for issue in all_issues if issue.is_unresolved]

    print(f"\n📈 Resolution Analysis:")
    print(f"Resolved issues: {len(resolved_issues)}")
    print(f"Unresolved issues: {len(unresolved_issues)}")

    if resolved_issues:
        print(f"\nResolved by resolution type:")
        resolution_counts = {}
        for issue in resolved_issues:
            resolution_counts[issue.resolution_name] = resolution_counts.get(issue.resolution_name, 0) + 1

        for resolution, count in resolution_counts.items():
            print(f"  - {resolution}: {count}")

    return len(resolved_issues), len(unresolved_issues)


def main():
    # Initialize JIRA client
    jira_client = create_new_jira_client()

    # Step 1: Test connection and get user info
    account_id = jira_client.test_connection()
    if not account_id:
        print("❌ Connection test failed. Check your credentials and URL.")
        return

    # Step 2: Get all assigned issues (no resolution filter)
    all_issues = jira_client.get_all_assigned_issues(max_results=MAX_RESULTS)
    print(f"\nℹ️  Total assigned issues found: {len(all_issues)}")

    if all_issues:
        # Analyze all assigned issues
        resolved_count, unresolved_count = analyze_resolution_status(all_issues)

    # Step 3: Try original query
    print("\n=== Trying Original Query ===")
    try:
        issues = jira_client.get_issues(MY_ISSUE_JQL, max_results=MAX_RESULTS)
        print(f"DEBUG: Total issues fetched with original query: {len(issues)}")

        if not issues and all_issues:
            print("\n⚠️  Original query returned 0 results, but you have assigned issues.")
            print("This suggests the JQL filter is too restrictive.")

            if unresolved_count > 0:
                print(f"\n🤔 You have {unresolved_count} unresolved issues, but the query returned 0.")
                print("Try using a simpler JQL query like: 'assignee=currentUser() AND resolution is EMPTY'")

                # Show some unresolved issues as examples
                unresolved_issues = [issue for issue in all_issues if issue.is_unresolved]
                if unresolved_issues:
                    print(f"\nFirst few unresolved issues:")
                    for i, issue in enumerate(unresolved_issues[:3]):
                        print(f"  {i+1}. {issue.key}: {issue.summary[:50]}... [{issue.status_name}]")

        elif issues:
            print_issue_summary(issues)
            projects = jira_client.group_issues_by_project(issues)
            print_tables_by_project(projects)

            # # Additional analysis
            # print(f"\n🔍 Detailed Analysis:")
            # for project_name, project_issues in projects.items():
            #     print(f"\n{project_name} ({len(project_issues)} issues):")
            #     for issue in project_issues[:3]:  # Show first 3 issues per project
            #         print(f"  • {issue.key}: {issue.summary[:40]}...")
            #         print(f"    Status: {issue.status_name}, Priority: {issue.priority_name}")

            #     if len(project_issues) > 3:
            #         print(f"  ... and {len(project_issues) - 3} more issues")

        else:
            print("No assigned tasks found!")

    except Exception as e:
        print(f"DEBUG: Exception occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
