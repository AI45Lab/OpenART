# Reference: Confirmation Protocol

Use this table to determine what preview content to show the user before any write operation.

| Action                 | Preview to show                                             |
| ---------------------- | ----------------------------------------------------------- |
| Create Jira issue      | Project, issue type, summary, description, labels, priority |
| Update Jira issue      | Field name → current value → new value                      |
| Add Jira comment       | Ticket key + full comment text                              |
| Transition Jira status | Ticket key + current status → target status                 |
| Create Confluence page | Space, parent page, title + full article content            |
| Update Confluence page | Title + diff or summary of what changes                     |

After showing the preview, end with:
> "Does this look correct? Reply **yes** to proceed, or tell me what to change."

If the user requests changes, update the preview and ask again. Only call the MCP tool once the user confirms.
