from dev.dev_common.jira_utils import JiraTicket
from available_tools.content_tools.t_gen_md_by_jira_ticket import gen_content_markdown


def _make_ticket(issue_links):
    return JiraTicket(
        "https://example.atlassian.net",
        {
            "key": "ESA1W-7367",
            "fields": {
                "summary": "Test KIM 300",
                "issuetype": {"name": "Task"},
                "issuelinks": issue_links,
            },
        },
    )


def test_parse_linked_issues_and_render_markdown():
    ticket = _make_ticket([
        {
            "type": {"name": "Parent/Child", "outward": "is parent of", "inward": "is child of"},
            "outwardIssue": {"key": "ESA1W-1001"},
        },
        {
            "type": {"name": "Parent/Child", "outward": "is parent of", "inward": "is child of"},
            "inwardIssue": {"key": "ESA1W-1002"},
        },
        {
            "type": {"name": "Parent/Child", "outward": "is parent of", "inward": "is child of"},
            "outwardIssue": {"key": "ESA1W-1003"},
        },
    ])

    assert [item["key"] for item in ticket.linked_issues] == ["ESA1W-1001", "ESA1W-1002", "ESA1W-1003"]
    assert [item["relation"] for item in ticket.linked_issues] == ["is parent of", "is child of", "is parent of"]
    assert ticket.linked_issues[0]["url"] == "https://example.atlassian.net/browse/ESA1W-1001"

    markdown = gen_content_markdown(ticket, coding_task_info=None, has_ticket_context=False)
    assert "- Linked Work Item(s):" in markdown
    assert "Is Child Of: [ESA1W-1002](https://example.atlassian.net/browse/ESA1W-1002)" in markdown
    assert "Is Parent Of: [ESA1W-1001](https://example.atlassian.net/browse/ESA1W-1001), [ESA1W-1003](https://example.atlassian.net/browse/ESA1W-1003)" in markdown


def test_render_markdown_when_no_linked_issues():
    ticket = _make_ticket([])
    markdown = gen_content_markdown(ticket, coding_task_info=None, has_ticket_context=False)
    assert "- Linked Work Item(s):" in markdown
    assert "No Linked Work Item(s)." in markdown
