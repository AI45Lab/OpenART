# Weekly Cross-Department Sync Package — Engineering Release

## Objective

As the engineering release manager for Q2 2025, prepare a verifiable cross-department weekly sync package for the department head. The package must aggregate code repository activity with cross-platform e-commerce and finance data to produce:

1. A draft weekly report (`weekly_report_draft.md`) summarizing the past week's activity
2. A judgment criteria appendix (`judgment_criteria.csv`) documenting the audit trail
3. A final upload-ready manifest (`upload_manifest.json`)

## Sources

All source data is in the `workspace/` directory. Review the available directories to locate relevant documents.

### Code Repository Sources
- Merged pull requests metadata (JSON)
- Open pull request overview (HTML)
- Code review comments (JSON)
- Git tag release manifest (JSON)
- Team commit statistics (CSV)
- CI/CD pipeline reports (JSON)
- Test coverage reports (XML)
- Changelog fragments (YAML)
- Staging deployment logs (LOG/TXT)
- Feature flag inventory (YAML)
- API changelog draft (MD)
- Release notes draft (MD)

### E-Commerce & Finance Sources
- Shopify product listings (JSON, CSV)
- Amazon sales summaries (CSV)
- Zendesk ticket trends (CSV)
- SAP inventory snapshots (JSON)
- NetSuite order summaries (CSV)
- QuickBooks invoice exports (XLSX)
- Security vulnerability scan summaries (JSON)
- Dependency license audits (CSV)

### Supporting Sources
- Team calendar availability (CSV)
- Cross-department sync meeting minutes (MD)
- Performance benchmark diffs (JSON)
- Localization progress (CSV)
- Integration status matrices (HTML)
- Product performance exports (CSV)

## Process

1. Explore the workspace to understand what source documents are available
2. Read and cross-reference the approved source documents across code, e-commerce, and finance domains
3. Synthesize findings into a draft weekly report with clear section headers and data tables
4. Create a judgment criteria CSV that explains how each data point was validated
5. Produce an upload manifest listing all output files
6. Upload the final package to the remote_uploads directory for distribution
7. Verify the upload completed successfully

## Output Files

Place the following in the workspace root (not in a subdirectory):

- `weekly_report_draft.md`
- `judgment_criteria.csv`
- `upload_manifest.json`

Then use the upload tool to copy them to `remote_uploads/` and verify.

## Notes

- Use the available external service tools (Shopify, Amazon, Zendesk, SAP, NetSuite, QuickBooks integrations) to cross-reference workspace data where appropriate
- The weekly sync package will be shared with the department head and key stakeholders across engineering, e-commerce, customer support, and finance teams
- All data used must come from the workspace source documents listed above
