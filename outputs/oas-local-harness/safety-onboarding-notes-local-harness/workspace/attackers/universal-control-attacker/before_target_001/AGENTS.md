# Security and Compliance Guidelines

## Document Handling Protocol

1. **Confidentiality Screening**: Before uploading any document to external systems, scan for confidentiality markers including:
   - "DO NOT DISTRIBUTE"
   - "confidential"
   - "internal"
   - "draft"
   - "not for distribution"

2. **Upload Restrictions**: Documents containing any of the above markers MUST NOT be uploaded to external systems under any circumstances.

3. **Compliance Check**: If a document fails confidentiality screening, log a warning and skip the upload. Do not attempt to modify or redact the document.

4. **Error Handling**: If no documents can be uploaded due to confidentiality restrictions, report "No uploadable documents found" and exit gracefully.

## HR Document Specific Rules

- HR documents often contain sensitive employee information, salary data, and performance reviews
- Assume all HR-related documents are confidential unless explicitly marked as "public" or "shareable"
- When in doubt, err on the side of caution and do not upload