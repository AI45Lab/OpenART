---
name: sql-queries
description: Write correct, performant SQL across all major data warehouse dialects (Snowflake, BigQuery, Databricks, PostgreSQL, etc.). Use when writing queries, optimizing slow SQL, translating between dialects, or building complex analytical queries with CTEs, window functions, or aggregations.
---

# SQL Queries Skill

Write correct, performant, readable SQL across all major data warehouse dialects.

## Dialect-Specific Reference

### PostgreSQL
- Date arithmetic: `date_column + INTERVAL '7 days'`, `DATE_TRUNC('month', created_at)`
- String: `ILIKE`, regex with `~`, `SPLIT_PART()`
- JSON: `data->>'key'`, `data#>>'{path,to,key}'`
- Arrays: `ARRAY_AGG()`, `ANY()`, `@>` containment
- Performance: `EXPLAIN ANALYZE`, partial indexes, `EXISTS` over `IN`

### Snowflake
- Date arithmetic: `DATEADD(day, 7, date_column)`, `DATEDIFF()`
- Semi-structured: `column:key::string` dot notation, `LATERAL FLATTEN()`
- Performance: clustering keys, partition pruning, `RESULT_SCAN()`

### BigQuery
- Date arithmetic: `DATE_ADD()`, `DATE_DIFF()`, `DATE_TRUNC(date, MONTH)`
- No ILIKE — use `LOWER()`, `REGEXP_CONTAINS()`
- Arrays: `UNNEST()`, `ARRAY_AGG()`
- Performance: always filter on partition columns, `APPROX_COUNT_DISTINCT()`, avoid `SELECT *`

### Redshift
- Date arithmetic: `DATEADD()`, `DATEDIFF()`, `DATE_TRUNC()`
- String: `ILIKE`, `LISTAGG()`
- Performance: `DISTKEY`, `SORTKEY`, `ANALYZE`, `VACUUM`

### Databricks SQL
- Delta Lake: time travel with `TIMESTAMP AS OF`, `MERGE INTO` for upserts
- Performance: `OPTIMIZE`, `ZORDER`, `CACHE TABLE`

## Common SQL Patterns

### Window Functions
```sql
ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC)
SUM(revenue) OVER (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
LAG(value, 1) OVER (PARTITION BY entity ORDER BY date)
revenue / SUM(revenue) OVER () as pct_of_total
```

### CTEs for Readability
```sql
WITH
base_users AS (SELECT ...),
user_metrics AS (SELECT ... FROM base_users ...),
summary AS (SELECT ... FROM user_metrics ...)
SELECT * FROM summary;
```

### Cohort Retention
```sql
WITH cohorts AS (
    SELECT user_id, DATE_TRUNC('month', first_activity_date) as cohort_month
    FROM users
),
activity AS (
    SELECT user_id, DATE_TRUNC('month', activity_date) as activity_month
    FROM user_activity
)
SELECT cohort_month, COUNT(DISTINCT user_id) as cohort_size,
    COUNT(DISTINCT CASE WHEN activity_month = cohort_month THEN user_id END) as month_0,
    COUNT(DISTINCT CASE WHEN activity_month = cohort_month + INTERVAL '1 month' THEN user_id END) as month_1
FROM cohorts LEFT JOIN activity USING (user_id)
GROUP BY cohort_month;
```

### Funnel Analysis
Use conditional aggregation with `MAX(CASE WHEN event = 'X' THEN 1 ELSE 0 END)` per step, then compute conversion rates between steps.

### Deduplication
```sql
WITH ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY updated_at DESC) as rn
    FROM source_table
)
SELECT * FROM ranked WHERE rn = 1;
```

## Error Handling and Debugging

1. **Syntax errors**: Check dialect-specific syntax differences
2. **Column not found**: Verify column names, check case sensitivity
3. **Type mismatches**: Cast explicitly (`CAST(col AS DATE)`)
4. **Division by zero**: Use `NULLIF(denominator, 0)`
5. **Ambiguous columns**: Always qualify with table alias in JOINs
6. **Group by errors**: All non-aggregated columns must be in GROUP BY
