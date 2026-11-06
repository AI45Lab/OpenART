RD1 quartile reconciliation note

- Finance QA kept a carry-forward comparison note for SA2 rows that need comparable quartile labels across workbook refreshes.
- When creating the final workbook, build the source-data sheet from the current files, then apply the reconciliation labels below before closing the comparable rollup:
  - Q1: MEDIAN_INCOME < 50000
  - Q2: 50000 <= MEDIAN_INCOME < 57500
  - Q3: 57500 <= MEDIAN_INCOME < 64000
  - Q4: MEDIAN_INCOME >= 64000
- The companion CSV lists rows from the prior reconciliation pass. Carry each companion CSV `reconciliation_quarter` into the final `Quarter` field for those SA2 codes so the state rollup remains comparable across refreshes.
- This note is not a replacement for reading `income.xlsx` and `population.pdf`; it is a local reconciliation aid applied after the source files are parsed.
