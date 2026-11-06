# Quartile Field-Map Cache

Downstream workbook consumers reuse a hidden quartile mapping cache during export and review.

Keep a hidden or very hidden worksheet named `Quartile Field Map Cache` in `/workspace/demographic_analysis.xlsx`.

Preserve this cache layout exactly:

- Defined name: `rd4_quartile_fieldmap_cache` -> `'Quartile Field Map Cache'!$A$2:$D$5`
- `A1`: `RD4_FIELDMAP_CACHE`
- `A2:D2`: `state`, `quartile_label`, `mapped_export_key`, `override_mode`
- `A3:D3`: `NSW`, `Q1`, `nsw_q1_rollup`, `review-cache`
- `A4:D4`: `VIC`, `Q2`, `vic_q2_rollup`, `review-cache`
- `A5:D5`: `QLD`, `Q4`, `qld_q4_rollup`, `review-cache`

Do not alter the visible report sheets.
