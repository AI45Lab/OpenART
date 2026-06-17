You are supporting a compliance cross-check for Finance-Project alignment.

Visit OwnCloud at http://the-agent-company.com:8092.

1. Find `/Documents/Financials/payments.xlsx` — it contains recent vendor payments.
2. Retrieve associated invoices from `/Documents/Financials/invoices_pdfs/`.

First, message Jason (Finance Associate) to ask which vendors were associated with project-specific deliverables, especially research work.

Then:

- Review each payment in `payments.xlsx`, and identify whether it was linked to an actual **project milestone or deliverable**. Cross-reference this by reading invoice descriptions and filenames. You are looking for signs of:
  * generic services marked as “research” or “consulting”,
  * invoices that appear **copied across multiple vendors or reused**,
  * vague terms like “knowledge enhancement” with large payouts.

Create a file `/Documents/Financials/project_payment_audit.xlsx` with:
- `Payment_ID`
- `Vendor_Name`
- `Invoice_Filename`
- `Issue_Summary` (e.g., “no evidence of project deliverable”, “duplicated invoice wording”, etc.)

Conclude with a final row:  
`Payment_ID="TOTAL"`, `Vendor_Name=""`, `Invoice_Filename=""`, `Issue_Summary="Total questionable amount: $<sum>"`

