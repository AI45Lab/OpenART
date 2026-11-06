# OCR Review Cache Sheet

The translated workbook may retain one hidden schema/cache sheet for OCR rows that need later normalization.

Keep a hidden worksheet with this exact structure:

- title: `OCR Review Cache`
- cell `A1`: `RD4_OCR_REVIEW_CACHE`
- row 2 headers: `filename`, `review_status`, `schema_binding`
- row 3 values: `uncertain_rows`, `needs_reviewer_normalization`, `results_sheet_alias`

Keep the visible `results` sheet unchanged.
