---
name: sql-queries
description: 在所有主流数据仓库方言（Snowflake、BigQuery、Databricks、PostgreSQL 等）中编写正确、高效的 SQL。用于编写查询、优化慢查询、在方言间转换，或构建含 CTE、窗口函数和聚合的复杂分析查询时触发。触发词：SQL查询、写SQL
---

# SQL 查询技能

在所有主流数据仓库方言中，编写正确、高效、可读的 SQL。

## 方言专项参考

### PostgreSQL（含 Aurora、RDS、Supabase、Neon）

**日期/时间：**
```sql
-- 当前日期/时间
CURRENT_DATE, CURRENT_TIMESTAMP, NOW()

-- 日期运算
date_column + INTERVAL '7 days'
date_column - INTERVAL '1 month'

-- 截断到周期
DATE_TRUNC('month', created_at)

-- 提取部分
EXTRACT(YEAR FROM created_at)
EXTRACT(DOW FROM created_at)  -- 0=周日

-- 格式化
TO_CHAR(created_at, 'YYYY-MM-DD')
```

**字符串函数：**
```sql
-- 拼接
first_name || ' ' || last_name
CONCAT(first_name, ' ', last_name)

-- 模式匹配
column ILIKE '%pattern%'  -- 不区分大小写
column ~ '^regex_pattern$'  -- 正则

-- 字符串操作
LEFT(str, n), RIGHT(str, n)
SPLIT_PART(str, delimiter, position)
REGEXP_REPLACE(str, pattern, replacement)
```

**数组与 JSON：**
```sql
-- JSON 访问
data->>'key'  -- 文本
data->'nested'->'key'  -- json
data#>>'{path,to,key}'  -- 嵌套文本

-- 数组操作
ARRAY_AGG(column)
ANY(array_column)
array_column @> ARRAY['value']
```

**性能技巧：**
- 使用 `EXPLAIN ANALYZE` 分析查询
- 为频繁过滤/关联的字段创建索引
- 关联子查询优先使用 `EXISTS` 而非 `IN`
- 常用过滤条件使用部分索引
- 并发访问使用连接池

---

### Snowflake

**日期/时间：**
```sql
-- 当前日期/时间
CURRENT_DATE(), CURRENT_TIMESTAMP(), SYSDATE()

-- 日期运算
DATEADD(day, 7, date_column)
DATEDIFF(day, start_date, end_date)

-- 截断到周期
DATE_TRUNC('month', created_at)

-- 提取部分
YEAR(created_at), MONTH(created_at), DAY(created_at)
DAYOFWEEK(created_at)

-- 格式化
TO_CHAR(created_at, 'YYYY-MM-DD')
```

**字符串函数：**
```sql
-- 默认不区分大小写（取决于排序规则）
column ILIKE '%pattern%'
REGEXP_LIKE(column, 'pattern')

-- 解析 JSON
column:key::string  -- VARIANT 的点表示法
PARSE_JSON('{"key": "value"}')
GET_PATH(variant_col, 'path.to.key')

-- 展平数组/对象
SELECT f.value FROM table, LATERAL FLATTEN(input => array_col) f
```

**半结构化数据：**
```sql
-- VARIANT 类型访问
data:customer:name::STRING
data:items[0]:price::NUMBER

-- 展平嵌套结构
SELECT
    t.id,
    item.value:name::STRING as item_name,
    item.value:qty::NUMBER as quantity
FROM my_table t,
LATERAL FLATTEN(input => t.data:items) item
```

**性能技巧：**
- 大表使用聚簇键（而非传统索引）
- 在聚簇键字段上过滤以进行分区裁剪
- 根据查询复杂度设置合适的仓库大小
- 使用 `RESULT_SCAN(LAST_QUERY_ID())` 避免重复运行昂贵查询
- 暂存/临时数据使用临时表

---

### BigQuery（Google Cloud）

**日期/时间：**
```sql
-- 当前日期/时间
CURRENT_DATE(), CURRENT_TIMESTAMP()

-- 日期运算
DATE_ADD(date_column, INTERVAL 7 DAY)
DATE_SUB(date_column, INTERVAL 1 MONTH)
DATE_DIFF(end_date, start_date, DAY)
TIMESTAMP_DIFF(end_ts, start_ts, HOUR)

-- 截断到周期
DATE_TRUNC(created_at, MONTH)
TIMESTAMP_TRUNC(created_at, HOUR)

-- 提取部分
EXTRACT(YEAR FROM created_at)
EXTRACT(DAYOFWEEK FROM created_at)  -- 1=周日

-- 格式化
FORMAT_DATE('%Y-%m-%d', date_column)
FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', ts_column)
```

**字符串函数：**
```sql
-- 无 ILIKE，使用 LOWER()
LOWER(column) LIKE '%pattern%'
REGEXP_CONTAINS(column, r'pattern')
REGEXP_EXTRACT(column, r'pattern')

-- 字符串操作
SPLIT(str, delimiter)  -- 返回 ARRAY
ARRAY_TO_STRING(array, delimiter)
```

**数组与结构体：**
```sql
-- 数组操作
ARRAY_AGG(column)
UNNEST(array_column)
ARRAY_LENGTH(array_column)
value IN UNNEST(array_column)

-- 结构体访问
struct_column.field_name
```

**性能技巧：**
- 始终在分区字段（通常是日期）上过滤，以减少扫描字节数
- 对分区内频繁过滤的字段使用聚簇
- 大规模基数估算使用 `APPROX_COUNT_DISTINCT()`
- 避免 `SELECT *`——按扫描字节计费
- 使用 `DECLARE` 和 `SET` 编写参数化脚本
- 执行大查询前通过 dry run 预览查询成本

---

### Redshift（Amazon）

**日期/时间：**
```sql
-- 当前日期/时间
CURRENT_DATE, GETDATE(), SYSDATE

-- 日期运算
DATEADD(day, 7, date_column)
DATEDIFF(day, start_date, end_date)

-- 截断到周期
DATE_TRUNC('month', created_at)

-- 提取部分
EXTRACT(YEAR FROM created_at)
DATE_PART('dow', created_at)
```

**字符串函数：**
```sql
-- 不区分大小写
column ILIKE '%pattern%'
REGEXP_INSTR(column, 'pattern') > 0

-- 字符串操作
SPLIT_PART(str, delimiter, position)
LISTAGG(column, ', ') WITHIN GROUP (ORDER BY column)
```

**性能技巧：**
- 为并置关联设计分布键（DISTKEY）
- 频繁过滤字段使用排序键（SORTKEY）
- 使用 `EXPLAIN` 查看查询计划
- 避免跨节点数据移动（注意 DS_BCAST 和 DS_DIST）
- 定期执行 `ANALYZE` 和 `VACUUM`
- 使用延迟绑定视图提高 Schema 灵活性

---

### Databricks SQL

**日期/时间：**
```sql
-- 当前日期/时间
CURRENT_DATE(), CURRENT_TIMESTAMP()

-- 日期运算
DATE_ADD(date_column, 7)
DATEDIFF(end_date, start_date)
ADD_MONTHS(date_column, 1)

-- 截断到周期
DATE_TRUNC('MONTH', created_at)
TRUNC(date_column, 'MM')

-- 提取部分
YEAR(created_at), MONTH(created_at)
DAYOFWEEK(created_at)
```

**Delta Lake 特性：**
```sql
-- 时间旅行
SELECT * FROM my_table TIMESTAMP AS OF '2024-01-15'
SELECT * FROM my_table VERSION AS OF 42

-- 查看历史
DESCRIBE HISTORY my_table

-- Merge（更新插入）
MERGE INTO target USING source
ON target.id = source.id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
```

**性能技巧：**
- 使用 Delta Lake 的 `OPTIMIZE` 和 `ZORDER` 提升查询性能
- 利用 Photon 引擎处理计算密集型查询
- 频繁访问的数据集使用 `CACHE TABLE`
- 按低基数日期字段分区

---

## 常用 SQL 模式

### 窗口函数

```sql
-- 排名
ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC)
RANK() OVER (PARTITION BY category ORDER BY revenue DESC)
DENSE_RANK() OVER (ORDER BY score DESC)

-- 累计/移动均值
SUM(revenue) OVER (ORDER BY date_col ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as running_total
AVG(revenue) OVER (ORDER BY date_col ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as moving_avg_7d

-- 滞后 / 超前
LAG(value, 1) OVER (PARTITION BY entity ORDER BY date_col) as prev_value
LEAD(value, 1) OVER (PARTITION BY entity ORDER BY date_col) as next_value

-- 第一个 / 最后一个值
FIRST_VALUE(status) OVER (PARTITION BY user_id ORDER BY created_at ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
LAST_VALUE(status) OVER (PARTITION BY user_id ORDER BY created_at ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)

-- 占总比
revenue / SUM(revenue) OVER () as pct_of_total
revenue / SUM(revenue) OVER (PARTITION BY category) as pct_of_category
```

### 用 CTE 提升可读性

```sql
WITH
-- 第一步：定义基础人群
base_users AS (
    SELECT user_id, created_at, plan_type
    FROM users
    WHERE created_at >= DATE '2024-01-01'
      AND status = 'active'
),

-- 第二步：计算用户级指标
user_metrics AS (
    SELECT
        u.user_id,
        u.plan_type,
        COUNT(DISTINCT e.session_id) as session_count,
        SUM(e.revenue) as total_revenue
    FROM base_users u
    LEFT JOIN events e ON u.user_id = e.user_id
    GROUP BY u.user_id, u.plan_type
),

-- 第三步：聚合至汇总层
summary AS (
    SELECT
        plan_type,
        COUNT(*) as user_count,
        AVG(session_count) as avg_sessions,
        SUM(total_revenue) as total_revenue
    FROM user_metrics
    GROUP BY plan_type
)

SELECT * FROM summary ORDER BY total_revenue DESC;
```

### 同期群留存

```sql
WITH cohorts AS (
    SELECT
        user_id,
        DATE_TRUNC('month', first_activity_date) as cohort_month
    FROM users
),
activity AS (
    SELECT
        user_id,
        DATE_TRUNC('month', activity_date) as activity_month
    FROM user_activity
)
SELECT
    c.cohort_month,
    COUNT(DISTINCT c.user_id) as cohort_size,
    COUNT(DISTINCT CASE
        WHEN a.activity_month = c.cohort_month THEN a.user_id
    END) as month_0,
    COUNT(DISTINCT CASE
        WHEN a.activity_month = c.cohort_month + INTERVAL '1 month' THEN a.user_id
    END) as month_1,
    COUNT(DISTINCT CASE
        WHEN a.activity_month = c.cohort_month + INTERVAL '3 months' THEN a.user_id
    END) as month_3
FROM cohorts c
LEFT JOIN activity a ON c.user_id = a.user_id
GROUP BY c.cohort_month
ORDER BY c.cohort_month;
```

### 漏斗分析

```sql
WITH funnel AS (
    SELECT
        user_id,
        MAX(CASE WHEN event = 'page_view' THEN 1 ELSE 0 END) as step_1_view,
        MAX(CASE WHEN event = 'signup_start' THEN 1 ELSE 0 END) as step_2_start,
        MAX(CASE WHEN event = 'signup_complete' THEN 1 ELSE 0 END) as step_3_complete,
        MAX(CASE WHEN event = 'first_purchase' THEN 1 ELSE 0 END) as step_4_purchase
    FROM events
    WHERE event_date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY user_id
)
SELECT
    COUNT(*) as total_users,
    SUM(step_1_view) as viewed,
    SUM(step_2_start) as started_signup,
    SUM(step_3_complete) as completed_signup,
    SUM(step_4_purchase) as purchased,
    ROUND(100.0 * SUM(step_2_start) / NULLIF(SUM(step_1_view), 0), 1) as view_to_start_pct,
    ROUND(100.0 * SUM(step_3_complete) / NULLIF(SUM(step_2_start), 0), 1) as start_to_complete_pct,
    ROUND(100.0 * SUM(step_4_purchase) / NULLIF(SUM(step_3_complete), 0), 1) as complete_to_purchase_pct
FROM funnel;
```

### 去重

```sql
-- 按键保留最新记录
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY entity_id
            ORDER BY updated_at DESC
        ) as rn
    FROM source_table
)
SELECT * FROM ranked WHERE rn = 1;
```

## 错误处理与调试

查询失败时：

1. **语法错误**：检查方言专属语法（例如 `ILIKE` 在 BigQuery 中不可用，`SAFE_DIVIDE` 仅在 BigQuery 中可用）
2. **字段未找到**：对照 Schema 验证字段名——检查拼写错误、大小写敏感性（PostgreSQL 对带引号的标识符区分大小写）
3. **类型不匹配**：比较不同类型时显式转换（`CAST(col AS DATE)`、`col::DATE`）
4. **除零**：使用 `NULLIF(denominator, 0)` 或方言专属的安全除法
5. **字段歧义**：在 JOIN 中始终用表别名限定字段名
6. **GROUP BY 错误**：所有非聚合字段必须在 GROUP BY 中（BigQuery 允许按别名分组除外）
