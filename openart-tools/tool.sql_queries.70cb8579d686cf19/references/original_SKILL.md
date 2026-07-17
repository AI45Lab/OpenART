---
name: sql-queries
description: 모든 주요 데이터 웨어하우스 방언(Snowflake, BigQuery, Databricks, PostgreSQL 등)에서 정확하고 성능이 뛰어난 SQL을 작성합니다. 쿼리 작성, 느린 SQL 최적화, 방언 간 변환, CTE·윈도우 함수·집계를 활용한 복잡한 분석 쿼리 작성 시 사용합니다.
---

# SQL 쿼리 스킬

모든 주요 데이터 웨어하우스 방언에서 정확하고 성능이 뛰어나며 가독성 높은 SQL을 작성합니다.

## 방언별 레퍼런스

### PostgreSQL (Aurora, RDS, Supabase, Neon 포함)

**날짜/시간:**
```sql
-- 현재 날짜/시간
CURRENT_DATE, CURRENT_TIMESTAMP, NOW()

-- 날짜 연산
date_column + INTERVAL '7 days'
date_column - INTERVAL '1 month'

-- 기간 단위로 절삭
DATE_TRUNC('month', created_at)

-- 부분 추출
EXTRACT(YEAR FROM created_at)
EXTRACT(DOW FROM created_at)  -- 0=일요일

-- 포맷
TO_CHAR(created_at, 'YYYY-MM-DD')
```

**문자열 함수:**
```sql
-- 연결
first_name || ' ' || last_name
CONCAT(first_name, ' ', last_name)

-- 패턴 매칭
column ILIKE '%pattern%'  -- 대소문자 구분 없음
column ~ '^regex_pattern$'  -- 정규식

-- 문자열 조작
LEFT(str, n), RIGHT(str, n)
SPLIT_PART(str, delimiter, position)
REGEXP_REPLACE(str, pattern, replacement)
```

**배열 및 JSON:**
```sql
-- JSON 접근
data->>'key'  -- 텍스트
data->'nested'->'key'  -- json
data#>>'{path,to,key}'  -- 중첩 텍스트

-- 배열 연산
ARRAY_AGG(column)
ANY(array_column)
array_column @> ARRAY['value']
```

**성능 팁:**
- `EXPLAIN ANALYZE`로 쿼리 프로파일링
- 자주 필터링/조인하는 컬럼에 인덱스 생성
- 상관 서브쿼리는 `IN` 대신 `EXISTS` 사용
- 자주 쓰는 필터 조건에 부분 인덱스 활용
- 동시 접근 시 커넥션 풀링 사용

---

### Snowflake

**날짜/시간:**
```sql
-- 현재 날짜/시간
CURRENT_DATE(), CURRENT_TIMESTAMP(), SYSDATE()

-- 날짜 연산
DATEADD(day, 7, date_column)
DATEDIFF(day, start_date, end_date)

-- 기간 단위로 절삭
DATE_TRUNC('month', created_at)

-- 부분 추출
YEAR(created_at), MONTH(created_at), DAY(created_at)
DAYOFWEEK(created_at)

-- 포맷
TO_CHAR(created_at, 'YYYY-MM-DD')
```

**문자열 함수:**
```sql
-- 기본적으로 대소문자 구분 없음 (콜레이션에 따라 다름)
column ILIKE '%pattern%'
REGEXP_LIKE(column, 'pattern')

-- JSON 파싱
column:key::string  -- VARIANT 닷 표기법
PARSE_JSON('{"key": "value"}')
GET_PATH(variant_col, 'path.to.key')

-- 배열/객체 펼치기
SELECT f.value FROM table, LATERAL FLATTEN(input => array_col) f
```

**반정형 데이터:**
```sql
-- VARIANT 타입 접근
data:customer:name::STRING
data:items[0]:price::NUMBER

-- 중첩 구조 펼치기
SELECT
    t.id,
    item.value:name::STRING as item_name,
    item.value:qty::NUMBER as quantity
FROM my_table t,
LATERAL FLATTEN(input => t.data:items) item
```

**성능 팁:**
- 대용량 테이블에 클러스터링 키 사용 (전통적인 인덱스 아님)
- 파티션 프루닝을 위해 클러스터링 키 컬럼으로 필터링
- 쿼리 복잡도에 맞는 웨어하우스 크기 설정
- `RESULT_SCAN(LAST_QUERY_ID())`으로 비용이 큰 쿼리 재실행 방지
- 스테이징/임시 데이터에는 transient 테이블 사용

---

### BigQuery (Google Cloud)

**날짜/시간:**
```sql
-- 현재 날짜/시간
CURRENT_DATE(), CURRENT_TIMESTAMP()

-- 날짜 연산
DATE_ADD(date_column, INTERVAL 7 DAY)
DATE_SUB(date_column, INTERVAL 1 MONTH)
DATE_DIFF(end_date, start_date, DAY)
TIMESTAMP_DIFF(end_ts, start_ts, HOUR)

-- 기간 단위로 절삭
DATE_TRUNC(created_at, MONTH)
TIMESTAMP_TRUNC(created_at, HOUR)

-- 부분 추출
EXTRACT(YEAR FROM created_at)
EXTRACT(DAYOFWEEK FROM created_at)  -- 1=일요일

-- 포맷
FORMAT_DATE('%Y-%m-%d', date_column)
FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', ts_column)
```

**문자열 함수:**
```sql
-- ILIKE 없음, LOWER() 사용
LOWER(column) LIKE '%pattern%'
REGEXP_CONTAINS(column, r'pattern')
REGEXP_EXTRACT(column, r'pattern')

-- 문자열 조작
SPLIT(str, delimiter)  -- ARRAY 반환
ARRAY_TO_STRING(array, delimiter)
```

**배열 및 구조체:**
```sql
-- 배열 연산
ARRAY_AGG(column)
UNNEST(array_column)
ARRAY_LENGTH(array_column)
value IN UNNEST(array_column)

-- 구조체 접근
struct_column.field_name
```

**성능 팁:**
- 스캔 바이트 절감을 위해 항상 파티션 컬럼(보통 날짜)으로 필터링
- 파티션 내 자주 필터링하는 컬럼에 클러스터링 사용
- 대규모 카디널리티 추정에는 `APPROX_COUNT_DISTINCT()` 사용
- `SELECT *` 지양 — 스캔 바이트 기준으로 과금됨
- 파라미터화된 스크립트에는 `DECLARE`와 `SET` 사용
- 대용량 쿼리 실행 전 드라이 런으로 비용 미리 확인

---

### Redshift (Amazon)

**날짜/시간:**
```sql
-- 현재 날짜/시간
CURRENT_DATE, GETDATE(), SYSDATE

-- 날짜 연산
DATEADD(day, 7, date_column)
DATEDIFF(day, start_date, end_date)

-- 기간 단위로 절삭
DATE_TRUNC('month', created_at)

-- 부분 추출
EXTRACT(YEAR FROM created_at)
DATE_PART('dow', created_at)
```

**문자열 함수:**
```sql
-- 대소문자 구분 없음
column ILIKE '%pattern%'
REGEXP_INSTR(column, 'pattern') > 0

-- 문자열 조작
SPLIT_PART(str, delimiter, position)
LISTAGG(column, ', ') WITHIN GROUP (ORDER BY column)
```

**성능 팁:**
- 배치 조인을 위한 배포 키 설계 (DISTKEY)
- 자주 필터링하는 컬럼에 정렬 키 사용 (SORTKEY)
- `EXPLAIN`으로 쿼리 플랜 확인
- 노드 간 데이터 이동 방지 (DS_BCAST, DS_DIST 주의)
- `ANALYZE`와 `VACUUM` 정기 실행
- 스키마 유연성을 위해 late-binding 뷰 사용

---

### Databricks SQL

**날짜/시간:**
```sql
-- 현재 날짜/시간
CURRENT_DATE(), CURRENT_TIMESTAMP()

-- 날짜 연산
DATE_ADD(date_column, 7)
DATEDIFF(end_date, start_date)
ADD_MONTHS(date_column, 1)

-- 기간 단위로 절삭
DATE_TRUNC('MONTH', created_at)
TRUNC(date_column, 'MM')

-- 부분 추출
YEAR(created_at), MONTH(created_at)
DAYOFWEEK(created_at)
```

**Delta Lake 기능:**
```sql
-- 타임 트래블
SELECT * FROM my_table TIMESTAMP AS OF '2024-01-15'
SELECT * FROM my_table VERSION AS OF 42

-- 히스토리 조회
DESCRIBE HISTORY my_table

-- 머지 (upsert)
MERGE INTO target USING source
ON target.id = source.id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
```

**성능 팁:**
- 쿼리 성능을 위해 Delta Lake의 `OPTIMIZE`와 `ZORDER` 사용
- 컴퓨팅 집약적 쿼리에 Photon 엔진 활용
- 자주 접근하는 데이터셋에 `CACHE TABLE` 사용
- 낮은 카디널리티의 날짜 컬럼으로 파티셔닝

---

## 공통 SQL 패턴

### 윈도우 함수

```sql
-- 순위
ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC)
RANK() OVER (PARTITION BY category ORDER BY revenue DESC)
DENSE_RANK() OVER (ORDER BY score DESC)

-- 누적 합계 / 이동 평균
SUM(revenue) OVER (ORDER BY date_col ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as running_total
AVG(revenue) OVER (ORDER BY date_col ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as moving_avg_7d

-- 이전값 / 다음값
LAG(value, 1) OVER (PARTITION BY entity ORDER BY date_col) as prev_value
LEAD(value, 1) OVER (PARTITION BY entity ORDER BY date_col) as next_value

-- 첫 번째 / 마지막 값
FIRST_VALUE(status) OVER (PARTITION BY user_id ORDER BY created_at ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
LAST_VALUE(status) OVER (PARTITION BY user_id ORDER BY created_at ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)

-- 전체 대비 비율
revenue / SUM(revenue) OVER () as pct_of_total
revenue / SUM(revenue) OVER (PARTITION BY category) as pct_of_category
```

### 가독성을 위한 CTE

```sql
WITH
-- 1단계: 기준 모집단 정의
base_users AS (
    SELECT user_id, created_at, plan_type
    FROM users
    WHERE created_at >= DATE '2024-01-01'
      AND status = 'active'
),

-- 2단계: 사용자 수준 지표 계산
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

-- 3단계: 요약 수준으로 집계
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

### 코호트 리텐션

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

### 퍼널 분석

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

### 중복 제거

```sql
-- 키 기준으로 가장 최근 레코드 유지
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

## 오류 처리 및 디버깅

쿼리 실패 시:

1. **문법 오류**: 방언별 문법 확인 (예: BigQuery에서 `ILIKE` 미지원, `SAFE_DIVIDE`는 BigQuery 전용)
2. **컬럼 없음**: 스키마에서 컬럼명 검증 — 오탈자, 대소문자 구분 확인 (PostgreSQL은 따옴표 식별자에서 대소문자 구분)
3. **타입 불일치**: 다른 타입 비교 시 명시적 캐스트 (`CAST(col AS DATE)`, `col::DATE`)
4. **0으로 나누기**: `NULLIF(denominator, 0)` 또는 방언별 안전 나누기 함수 사용
5. **모호한 컬럼**: JOIN에서 항상 테이블 별칭으로 컬럼명 한정
6. **GROUP BY 오류**: 집계되지 않은 모든 컬럼은 GROUP BY에 포함 (BigQuery는 별칭으로 그룹화 허용)
