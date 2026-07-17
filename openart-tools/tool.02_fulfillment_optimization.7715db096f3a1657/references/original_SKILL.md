---
name: fulfillment-optimization
description: Analyzes warehouse shipment backlogs to optimize batch picking and packing workflows. Use when a merchant needs help clearing order backlogs, improving picking efficiency, optimizing batch sizes, or understanding order composition patterns. Triggers on questions about shipping delays, picking strategies, packing station setup, warehouse workflow optimization, or order fulfillment bottlenecks. Works with Fulfil MCP data or user-provided shipment data (CSV/Excel).
---

# Fulfillment Optimization Analysis

Analyzes shipment data to generate actionable recommendations for clearing backlogs and optimizing warehouse workflows.

## Data Sources

**Option 1: Fulfil MCP Connection**
Query the `shipments` table with nested `moves` for line-item detail. Key fields:
- `state` (assigned, waiting, done, packed, cancel)
- `warehouse` for location filtering
- `moves.order_channel_name` for channel filtering
- `moves.product_code`, `moves.quantity`, `moves.product_name`
- `shipped_date` for velocity analysis

**Option 2: User-Provided Data**
Accept CSV/Excel with minimum columns: shipment_id, sku, quantity, status. Optional: ship_date, warehouse, channel.

## Analysis Workflow

### 1. Scope Confirmation
Before analysis, confirm with user:
- Which sales channel(s)?
- Which warehouse(s)?
- Focus on assigned/waiting shipments or include recent shipped for patterns?

### 2. Core Metrics to Calculate

**Order Composition**
```sql
-- Single vs multi-unit distribution
SELECT 
  CASE WHEN total_units = 1 THEN '1 unit'
       WHEN total_units = 2 THEN '2 units'
       WHEN total_units BETWEEN 3 AND 5 THEN '3-5 units'
       ELSE '6+ units' END as bucket,
  COUNT(*) as shipments,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as pct
FROM (
  SELECT s.id, SUM(m.quantity) as total_units
  FROM shipments s, UNNEST(moves) m
  WHERE [filters] AND m.move_type = 'outgoing' AND m.state != 'cancelled'
  GROUP BY s.id
)
GROUP BY bucket
```

**SKU Line Distribution**
Same pattern but `COUNT(DISTINCT m.product_code)` for unique SKUs per order.

**Top SKUs by Frequency**
```sql
SELECT m.product_code, COUNT(DISTINCT s.id) as orders, SUM(m.quantity) as units
FROM shipments s, UNNEST(moves) m
WHERE [filters]
GROUP BY m.product_code
ORDER BY orders DESC LIMIT 20
```

**Product Pairing Analysis** (for co-location)
```sql
-- Find products frequently bought together
WITH pairs AS (
  SELECT LEAST(a.product_code, b.product_code) as sku1,
         GREATEST(a.product_code, b.product_code) as sku2
  FROM shipment_products a
  JOIN shipment_products b ON a.shipment_id = b.shipment_id AND a.product_code < b.product_code
)
SELECT sku1, sku2, COUNT(*) as frequency
FROM pairs GROUP BY sku1, sku2 ORDER BY frequency DESC
```

**Shipping Velocity** (last 7 days)
```sql
SELECT shipped_date, COUNT(DISTINCT id) as shipments
FROM shipments WHERE state = 'done' AND shipped_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY shipped_date ORDER BY shipped_date
```

### 3. Identify Batch Picking Opportunities

**High-Volume Single-SKU Candidates (Pre-Print & Pack)**
- Threshold: ≥1 case quantity of single-unit orders for that SKU
- If case quantities unavailable, use ~20-30 as proxy
- These orders can have labels pre-printed, products brought to station in bulk

**Low-Volume Single-Unit (Mixed Batch)**
- SKUs with <1 case worth of single-unit orders
- Combine into one mixed-SKU batch
- Requires packing station with scan-to-label workflow

### 4. Check for Blockers

**Inventory Status** (if available)
Query `inventory_by_location` to compare available vs. needed for top SKUs.
- Exclude bundle/kit SKUs from shortage flags (built on the fly)
- Flag non-bundle SKUs with demand > available

**Bundle Identification**
SKUs with "BUNDLE" in code/name are typically assembled from components—don't flag inventory issues.

### 5. Location Analysis

**Primary Pick Locations**
```sql
SELECT product_code, location_name, quantity_available
FROM inventory_by_location
WHERE product_code IN ([top_skus]) AND quantity_available > 0
ORDER BY product_code, quantity_available DESC
```

## Recommendation Framework

**Recommendations must be driven by the actual data.** Different merchants have vastly different order profiles. Analyze the composition first, then select and prioritize recommendations accordingly.

### Step 1: Classify the Order Profile

After calculating order composition, classify the merchant:

| Profile | Single-Unit % | Multi-Unit % | Primary Challenge |
|---------|---------------|--------------|-------------------|
| **Single-Unit Dominant** | >60% | <40% | Throughput speed |
| **Multi-Unit Dominant** | <40% | >60% | Pick complexity, packing accuracy |
| **Balanced Mix** | 40-60% | 40-60% | Workflow segmentation |

### Step 2: Select Applicable Recommendations

Choose recommendations based on what the data shows. Not all apply to every merchant.

#### For Single-Unit Orders (if significant volume exists)

**Pre-Print & Pack (High-Volume Single-SKU)**
- **When applicable:** A SKU has ≥1 case worth of single-unit orders
- **Process:** Grab full cases/pallet → pre-print all labels → sort by carrier while packing → apply label and ship
- **Skip if:** Single-unit orders are <20% of volume or spread thin across many SKUs

**Mixed Single-Unit Batch (Low-Volume SKUs)**
- **When applicable:** Multiple SKUs each have <1 case worth of single-unit orders
- **Process:** Combine into one mixed-SKU batch → pick all in one pass → scan at packing station → system prints correct label
- **Skip if:** Few single-unit orders exist

#### For Multi-Unit/Multi-SKU Orders (if significant volume exists)

**Multi-SKU Batch Picking**
- **When applicable:** Multi-SKU orders are >30% of volume
- **Process:** Batch orders by similar SKU combinations → pick waves grouped by zone/location → use packing station for assembly and verification
- **Key:** Focus on pick path optimization and zone grouping

**Product Co-location**
- **When applicable:** Product pairing analysis shows strong repeat combinations
- **Process:** Move frequently-paired products adjacent in warehouse
- **Include:** Top product pairs table with frequency counts

**Multi-Unit Same-SKU Handling**
- **When applicable:** Many orders have multiple units of same SKU (e.g., 3x of SKU-A)
- **Process:** May benefit from bulk picking with quantity verification at pack station

#### Operational Recommendations (apply based on bottleneck)

**Packing Station Setup**
- **When packing is bottleneck:** High single-unit volume, simple picks but slow pack/label
- **Recommendation:** More packing stations than pickers (e.g., 1:2 or 1:3 ratio)
- **Each station needs:** Computer/tablet + thermal printer + barcode scanner

**Picking Optimization**
- **When picking is bottleneck:** Complex multi-SKU orders, large warehouse, long pick paths
- **Recommendation:** Zone picking, batch picking by location cluster, pick-to-cart workflows
- **May need:** More pickers than packers

**Cartonization**
- **When applicable:** Default box types are configured or could be
- **For single-unit:** Enables pre-printing labels
- **For multi-unit:** Helps but packing station workflow still recommended
- **Offer:** Assistance with setup if not yet configured

### Step 3: Prioritize by Impact

Order recommendations by shipment volume affected:
1. First address the largest segment of orders
2. Then address secondary segments
3. Operational changes (stations, staffing) come after workflow changes

### Step 4: Create Wave Plan

Based on selected recommendations, create execution waves:
- Group by workflow type (Pre-Print vs. Packing Station)
- Estimate shipment counts per wave
- Sequence waves by priority/efficiency

## Output Format

Generate PDF report with:
1. Executive summary (backlog size, days of work at current velocity)
2. Order composition analysis (tables + key stats highlighting the dominant profile)
3. Top SKUs with relevant batching candidates
4. Product pairing analysis (if multi-SKU orders are significant)
5. Numbered recommendations tailored to this merchant's data
6. Wave execution plan matching their order profile
7. Shipping velocity (last 7 days)
8. Bottom line summary

Use `docx` skill to create document, then convert to PDF:
```bash
soffice --headless --convert-to pdf document.docx --outdir /mnt/user-data/outputs/
```

## Key Principles

1. **Data drives recommendations**: Analyze composition first, then recommend. Never assume a particular order profile.

2. **Identify the bottleneck**: Packing is often the constraint for single-unit operations; picking is often the constraint for complex multi-SKU operations. Staffing ratios should reflect the actual bottleneck.

3. **Bundle awareness**: Built-on-fly bundles don't have inventory—components do. Never flag bundle inventory issues.

4. **Case quantity threshold**: For single-unit batching, the dividing line between "Pre-Print & Pack" and "Mixed Batch" is typically 1 case worth of orders. If case quantities unavailable in system, ask merchant or estimate ~20-30 units.

5. **Optimize for the majority first**: Whatever segment represents the largest share of orders should get the first and most detailed recommendation.
