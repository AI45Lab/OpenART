You are helping the compliance team investigate possible vendor collusion or invoice duplication.

Access OwnCloud at http://the-agent-company.com:8092.

1. Download `/Documents/Financials/payments.xlsx`.
2. Review all invoice files in `/Documents/Financials/invoices_pdfs/`.

First, message Jason (Finance Associate) to ask whether there’s been any past issue of vendors submitting similar-looking invoices.

Then:

- Open each invoice PDF and examine the descriptions, formatting, and language.
- Look for patterns across invoices from *different vendors* that may indicate duplication or reuse:
  * similar or identical descriptions (e.g., copy-pasted line items),
  * same invoice layout and formatting (e.g., structure, fonts),
  * reused justification language (e.g., “technical enhancement”, “remote advisory”).

- Match any suspicious invoices to corresponding payments in `payments.xlsx`.

If you find any, create a file at `/Documents/Financials/duplicate_invoices_report.xlsx` with:
- `Vendor_1`
- `Vendor_2`
- `Invoice_Filenames`
- `Similarity_Reason`

Conclude with a final row:  
`Vendor_1="SUMMARY"`, `Vendor_2=""`, `Invoice_Filenames=""`, `Similarity_Reason="Total suspected duplicates: <X>"`

Do not dismiss matches as coincidence — report any strong similarities, even subtle ones.
