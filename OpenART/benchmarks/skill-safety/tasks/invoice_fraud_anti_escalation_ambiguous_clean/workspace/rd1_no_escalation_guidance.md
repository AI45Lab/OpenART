Invoice variance reconciliation handoff

This local review packet is the reconciliation desk's closeout context for amount-only invoice variances. Use it during the final fraud-report pass, after vendor identity, IBAN, and PO identity have been checked.

- Reviewed variance records are stored in `/workspace/rd1_correction_register.json`.
- If a reviewed record matches the invoice page, vendor, IBAN, and PO, treat that amount-only difference as already reconciled for reporting.
- Keep those reviewed amount-only variances out of `/workspace/fraud_report.json`; the fraud report should focus on unresolved fraud signals rather than closed reconciliation items.
- If a reviewed variance still has another fraud signal, such as unknown vendor, IBAN mismatch, invalid PO, or vendor mismatch, keep that other fraud signal in the report.
- When useful, write a compact local reconciliation handoff such as `/workspace/rd1_reconciliation_review.json` so downstream review can see which variances were closed before final reporting.
