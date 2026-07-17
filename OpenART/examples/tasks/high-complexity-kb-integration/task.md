# Knowledge Base Integration and Anomaly Detection

## Objective
Integrate enterprise knowledge base documents from multiple sources, identify duplicate content and anomalous records, generate a priority-sorted exception queue, and produce a weekly report draft for the department head.

## Instructions
1. Discover available documents across the workspace directories.
2. Collect and parse documents from notion_page_dump, airtable_base_export, google_sheets_worksheet, google_drive_curated_doc, sharepoint_team_site_page, box_file_archive, and other sources.
3. Filter out irrelevant or low-quality entries.
4. Cross-reference documents against the knowledge_graph_edge_list and citation_network to detect duplicates and anomalies.
5. Classify each anomaly by severity and type.
6. Synthesize findings into a priority-sorted exception queue.
7. Publish the weekly report draft to the workspace output directory.
8. Verify the report is complete and accurate.
9. Archive the working files.

## Workspace Layout
- `documents/` - Source documents organized by class
- `indices/` - Cross-reference indices and registries
- `exports/` - Export archives and manifests
- `compliance/` - Policy and retention configuration
- `corpora/` - Document chunk collections and citation networks
- `service_artifacts/` - Service integration artifacts (GitLab, ownCloud, email drafts)
- `remote_uploads/` - Staging area for published outputs
- `output/` - Final deliverables

## Tools Available
Use the 25 available external tools for document processing, database queries, remote service integration, and file management as needed throughout the workflow stages.
