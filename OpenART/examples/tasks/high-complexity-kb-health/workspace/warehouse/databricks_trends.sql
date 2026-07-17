-- Databricks SQL: weekly KB usage trends
SELECT region, COUNT(*) as edits FROM kb_activity WHERE ts >= '2026-06-01' GROUP BY region;
