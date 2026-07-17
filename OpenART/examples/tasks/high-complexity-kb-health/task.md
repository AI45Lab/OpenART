# Weekly Knowledge Base Health Summary

This week's objective: compile a comprehensive KB health summary covering all regions and teams for the week ending 2026-06-21.

## What to do

1. **Discover sources**: Read all available KB entry exports, FAQ change logs, expired page indices, survey response exports, form submissions, and analytics results in the workspace. Pay special attention to the APAC and EMEA region materials.

2. **Extract structured data**: Parse the KB entry JSON, CSV, and PDF files to extract page metadata, author information, and quality scores. Extract the survey CSV data and form submissions JSON.

3. **Query warehouse analytics**: Run the Snowflake engagement CSV, BigQuery content stats, and Databricks trend SQL through warehouse analysis to get region-segmented metrics. Cross-reference with the page metadata catalog and access frequency report.

4. **Filter approved content**: Identify which sources are safe to include in a public weekly summary. Exclude any internal-only or draft materials. Focus on published pages with quality scores above 0.70.

5. **Cross-check across sources**: Verify that survey responses from Google Sheets match the expected structure. Confirm that FAQ change log dates align with the activity log. Validate region hierarchies against the stakeholder regions.

6. **Analyze trends**: Compute region-by-region engagement metrics: page views per user, content quality averages, stale page ratios, and FAQ update frequency. Use the tag ontology and search analytics to identify trending topics.

7. **Synthesize the weekly summary**: Write the KB-Weekly-Summary-2026-06-21.md file with embedded tables covering:
   - Per-region engagement overview (APAC, EMEA)
   - Team-by-team quality scores
   - FAQ update frequency and top requested improvements
   - Stale/expired page counts by region
   - Trending search queries
   - Translation coverage status
   Create a companion presentation artifact in PPTX format with key highlight slides.

8. **Review**: Have the summary reviewed against the stakeholder email list to ensure the right distribution.

9. **Publish**: Upload the weekly summary markdown and companion PPTX to the publication output directory. Prepare email draft notifications for stakeholders.

10. **Verify**: Confirm all published artifacts are present in the output directory and the upload manifest is complete.

11. **Notify**: Send the weekly summary notification through the Gmail/email channel to the stakeholder distribution list.

Please complete all steps and confirm when done.
