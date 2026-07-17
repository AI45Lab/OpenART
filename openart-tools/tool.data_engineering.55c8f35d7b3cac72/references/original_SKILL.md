---
name: data-engineering
description: >
  Data engineering practice patterns for data pipelines, ETL/ELT, orchestration, data quality,
  and infrastructure. Covers Airflow, Dagster, Prefect, Spark, dbt, data lakes, lakehouses,
  Iceberg, Delta Lake, warehouses (Snowflake, BigQuery, Databricks), streaming (Kafka, Kinesis,
  Flink), CDC, data contracts, data governance, data mesh, and batch processing. Use when
  reviewing or building data pipelines, ingestion systems, stream processing, data infrastructure,
  or data platform architecture. Do not use for SQL modeling or dbt projects (use
  analytics-engineering), business dashboards (use analytics), or ML model training (use
  data-science).
---

# Data Engineering Practice

Domain-specific patterns and checklists for data engineering work.

## Scope

- Data pipelines: batch and streaming
- ETL/ELT processes and ingestion patterns
- Orchestration: Airflow, Dagster, Prefect
- Data quality and observability
- Data lakes, lakehouses, and warehouses
- Streaming: Kafka, Kinesis, Flink, Spark Streaming
- CDC (Change Data Capture) patterns
- Data contracts and schema registry
- Data governance, lineage, and cataloging
- Data mesh architecture

## Code Review Checklist

### Pipeline Design
- [ ] Idempotent operations (safe to re-run without duplicates)
- [ ] Atomic writes (all-or-nothing, no partial state)
- [ ] Backfill strategy defined
- [ ] Failure handling and retry logic
- [ ] Appropriate task granularity (not monolithic)
- [ ] Dependencies explicitly declared
- [ ] No hardcoded dates or file paths
- [ ] SLA defined for production pipelines

### Data Quality
- [ ] Schema validation on ingestion (not just at transform time)
- [ ] Null handling explicit (expected vs unexpected nulls)
- [ ] Data type coercion documented
- [ ] Uniqueness constraints where needed
- [ ] Freshness checks (data not stale beyond SLA)
- [ ] Volume anomaly detection (row count within expected range)
- [ ] Data quality tests defined (not just schema tests)

### Orchestration
- [ ] DAG structure is clear and documented
- [ ] Task dependencies are correct and minimal
- [ ] Timeouts configured at task and DAG level
- [ ] Alerts on failure routed to right channel
- [ ] SLAs defined and monitored for critical pipelines
- [ ] Concurrency limits set to prevent resource contention
- [ ] Catchup behavior explicitly configured

### Performance
- [ ] Partitioning strategy appropriate for access pattern
- [ ] Incremental processing where possible (no full refreshes on large tables)
- [ ] No full table scans on large fact tables
- [ ] Appropriate file formats (Parquet/Iceberg/Delta, not CSV)
- [ ] Compression enabled
- [ ] Resource allocation sized appropriately (not default)

## Architecture Patterns

### Pipeline Structure
```
pipelines/
  ingestion/
    source_name/
      extract.py        # Pull from source system
      validate.py       # Schema and quality checks at landing
      load.py           # Write to bronze/raw zone
  transformation/
    domain/
      staging.sql       # Clean, dedupe (silver)
      intermediate.sql  # Business logic joins
      marts.sql         # Aggregated final models (gold)
  orchestration/
    dags/
      source_name_dag.py
  quality/
    checks/
      source_name_checks.py
```

### Idempotency Pattern
```python
# Good: Overwrite partition on re-run — idempotent
def load_partition(date: str):
    df = extract(date)
    (df.write
       .mode("overwrite")
       .partitionBy("date")
       .format("parquet")
       .save(path))

# Bad: Append creates duplicates on re-run
def load_partition(date: str):
    df = extract(date)
    df.write.mode("append").parquet(path)  # ❌
```

### Incremental / Watermark Pattern
```python
def load_incremental(source_table: str):
    watermark = get_watermark(source_table)
    new_records = source.filter(col("updated_at") > watermark)
    if new_records.isEmpty():
        return  # Nothing to do
    write_data(new_records)
    set_watermark(source_table, current_timestamp())
    log_metrics(source_table, new_records.count())
```

## Data Lakehouse and Table Formats

### Apache Iceberg
```python
# Preferred for new lakehouses — ACID, schema evolution, time travel
spark.sql("""
    CREATE TABLE catalog.db.orders (
        order_id BIGINT NOT NULL,
        customer_id BIGINT,
        amount DECIMAL(10,2),
        created_at TIMESTAMP
    )
    USING iceberg
    PARTITIONED BY (days(created_at))
    TBLPROPERTIES (
        'write.delete.mode' = 'merge-on-read',
        'write.update.mode' = 'merge-on-read',
        'history.expire.max-snapshot-age-ms' = '604800000'  -- 7 days
    )
""")

# Incremental merge (ACID upsert)
spark.sql("""
    MERGE INTO catalog.db.orders t
    USING staging_orders s ON t.order_id = s.order_id
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
""")
```

### Table Format Decision
| Scenario | Format | Reason |
|---|---|---|
| New Snowflake/BigQuery project | Native tables | Warehouse-managed; no format choice needed |
| Multi-engine lakehouse (Spark + Presto + Flink) | Iceberg | Best interoperability |
| Databricks-only lakehouse | Delta Lake | Native integration, best Databricks perf |
| On-prem HDFS legacy | Parquet + Hive | Pragmatic — migration cost > format benefit |

### Medallion Architecture
```
Bronze (raw)  → Silver (cleaned/conformed) → Gold (business-ready)
```
- **Bronze:** Exact copy, no transformations. All fields including errors. Partition by `ingest_date`. Never delete rows.
- **Silver:** Deduplicated, type-cast, renamed. One row per entity or event. Conforms to data contract.
- **Gold:** Aggregated, dimensional, business-ready. Equivalent to dbt mart layer.

## CDC (Change Data Capture)

### Debezium + Kafka Pattern
```
Source DB (Postgres/MySQL) → Debezium → Kafka → Kafka Sink Connector → Warehouse/Lake
```

```json
// Debezium connector config (Kafka Connect)
{
  "name": "postgres-source-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "${secret:db-password}",
    "database.dbname": "production",
    "table.include.list": "public.orders,public.customers",
    "publication.name": "dbz_publication",
    "slot.name": "dbz_slot",
    "transforms": "unwrap",
    "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
    "transforms.unwrap.add.fields": "op,ts_ms"
  }
}
```

**CDC Checklist:**
- [ ] Replication slot lag monitored (Postgres slots cause disk bloat if consumer falls behind)
- [ ] Schema registry integrated (schema evolution without breaking consumers)
- [ ] Dead letter queue for unprocessable messages
- [ ] Exactly-once or at-least-once semantics explicitly chosen (and compensated if at-least-once)
- [ ] Initial snapshot strategy defined (full table snapshot or skip)

## Data Contracts

A data contract is the schema + SLA agreement between a producer and consumer.

```yaml
# contracts/orders_v2.yaml
contract:
  name: orders
  version: "2.0.0"
  owner: data-platform-team
  consumers: [analytics, ml-team]

  schema:
    - name: order_id
      type: BIGINT
      nullable: false
      description: Unique order identifier
    - name: status
      type: VARCHAR
      nullable: false
      allowed_values: ["pending", "completed", "cancelled", "refunded"]

  sla:
    freshness_minutes: 30
    availability: "99.5%"

  quality:
    - check: row_count_min
      value: 1000
      window: daily
    - check: not_null
      columns: [order_id, status, created_at]
```

### Schema Registry (Confluent / AWS Glue)
- Register schemas before any producer sends data
- Consumers rely on registry for deserialization — not hardcoded schemas
- Use BACKWARD compatibility by default (new schema can read old data)
- Breaking changes require major version bump + consumer migration plan

## Streaming Patterns

### Kafka Topic Design
```
# Naming: {environment}.{domain}.{entity}.{version}
production.commerce.orders.v2
staging.commerce.orders.v2

# Partition strategy:
# - Partition by entity key (customer_id, order_id) for ordered processing
# - More partitions = more parallelism, but more overhead
# - Rule: start with max expected consumers, add headroom
```

### Flink Windowing
```java
// Tumbling windows — non-overlapping, fixed size
DataStream<OrderMetrics> windowed = orders
    .keyBy(order -> order.getRegion())
    .window(TumblingEventTimeWindows.of(Time.minutes(5)))
    .aggregate(new OrderAggregator());

// Always: set watermarks for event time processing
DataStream<Order> withWatermarks = orders
    .assignTimestampsAndWatermarks(
        WatermarkStrategy.<Order>forBoundedOutOfOrderness(Duration.ofSeconds(30))
            .withTimestampAssigner((event, ts) -> event.getTimestamp())
    );
```

### Late Data Handling
```python
# Define what "late" means upfront — don't discover it in production
WATERMARK_DELAY_SECONDS = 30  # Accept data up to 30s late
ALLOWED_LATENESS_SECONDS = 300  # Process up to 5min late (side output)

# Late data should go to: side output → correction pipeline → restatement
```

## Data Quality Framework

### Validation Layers
1. **Schema validation** — column names, types, nullability (fail fast at landing)
2. **Semantic validation** — value ranges, formats, referential integrity
3. **Statistical validation** — volume, distribution, anomalies vs baseline

### Great Expectations Pattern
```python
# Define expectations as code — version-controlled quality contract
context = gx.get_context()
suite = context.add_expectation_suite("orders.bronze")

suite.add_expectation(
    gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id")
)
suite.add_expectation(
    gx.expectations.ExpectColumnValuesToBeBetween(column="amount", min_value=0, max_value=1_000_000)
)
suite.add_expectation(
    gx.expectations.ExpectTableRowCountToBeBetween(min_value=1_000, max_value=10_000_000)
)

# Run as a checkpoint in your pipeline — block if quality fails
checkpoint.run(batch_request=batch, run_name=f"orders_{date}")
```

## Orchestration Best Practices

### Dagster (Preferred for new projects)
```python
@asset(
    partitions_def=DailyPartitionsDefinition(start_date="2024-01-01"),
    metadata={"owner": "data-platform"},
)
def orders_bronze(context: AssetExecutionContext) -> None:
    partition_date = context.partition_key
    df = extract_orders(partition_date)
    validate_schema(df)
    df.write_parquet(f"s3://data-lake/bronze/orders/date={partition_date}/")
    context.add_output_metadata({"row_count": len(df)})

@asset(deps=[orders_bronze])
def orders_silver(context: AssetExecutionContext) -> None:
    # Automatic lineage from asset dependency graph
    ...
```

### Airflow (Existing deployments)
- Use TaskFlow API (Airflow 2.x) — cleaner than classic operators
- `catchup=False` unless backfill is needed
- `max_active_runs=1` for sequential pipelines
- Use pools for shared resource limits (DB connections, API rate limits)
- XCom for metadata only (IDs, counts) — not DataFrames

## Common Anti-Patterns

| Anti-pattern | Fix |
|---|---|
| Non-idempotent pipelines | Use `overwrite` + partition strategy |
| Hardcoded credentials | Secrets manager (AWS Secrets Manager, HashiCorp Vault) |
| No backfill capability | Parameterize all date logic; never hardcode |
| Monolithic DAGs | Split by domain and source |
| Silent failures | Alert on every failure; define severity levels |
| Full refreshes when incremental is possible | Implement watermark / incremental load |
| No data quality checks | Quality gates in pipeline, not as afterthought |
| Tight coupling between extract and transform | Stage to intermediate storage first |
| CSV files for large data | Parquet or Iceberg always |
| Schema changes without consumer notification | Data contracts + schema registry |

## Technology-Specific Notes

### Spark
- Avoid `collect()` on large datasets (driver memory)
- Use broadcast joins for tables < 100MB
- Partition by high-cardinality filter columns, not low-cardinality
- Cache (`persist()`) only if reused more than twice in the same job
- Tune shuffle partitions: `spark.sql.shuffle.partitions` defaults to 200 — too high for small data, too low for large

### Kafka
- Monitor consumer lag as primary health metric
- Consumer group naming: `{service}-{purpose}` (e.g., `analytics-etl`)
- Dead letter queue for every consumer — unprocessable messages must not block progress
- Retention: event sourcing topics = infinite; operational topics = 7 days

### Snowflake (Data Engineering)
- Use COPY INTO for bulk loads — not INSERT SELECT for large volumes
- Snowpipe for continuous micro-batch ingestion
- Dynamic tables for incremental transformations without Airflow/dbt
- Monitor credits by warehouse; alert on unexpected spend
