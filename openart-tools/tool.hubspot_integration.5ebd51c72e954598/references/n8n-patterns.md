# n8n Patterns for HubSpot Integration

## Table of Contents
1. [Node Selection](#node-selection)
2. [Pagination Loop](#pagination-loop)
3. [Webhook Workflow Pattern](#webhook-workflow-pattern)
4. [Reconciliation Job Pattern](#reconciliation-job-pattern)
5. [Airtable → HubSpot Pattern](#airtable--hubspot-pattern)
6. [Rate Limit Handling](#rate-limit-handling)
7. [Memory Management](#memory-management)
8. [Error Workflows](#error-workflows)

---

## Node Selection

### Use Native HubSpot Node When:
- Simple CRUD on Contacts, Companies, Deals
- Basic search operations
- Getting recently created/updated records
- Form submissions

### Use HTTP Request Node When:
- Associations v4 (labels, all associations, batch read 1,000)
- Batch upsert by unique property (`idProperty` parameter)
- Pipelines/stages metadata
- Custom objects
- Any endpoint not exposed by native node

**Tip:** Reuse HubSpot credentials in HTTP Request node via "Predefined Credential Type" → HubSpot.

---

## Pagination Loop

The Search API returns max 200 records per page with cursor pagination. n8n doesn't handle this automatically.

### Workflow Structure

```
┌─────────────────┐
│ Set Node        │ cursor = null, finished = false
└────────┬────────┘
         │
         ▼
┌─────────────────┐◄──────────────────────┐
│ HTTP Request    │ HubSpot Search API    │
│ (HubSpot)       │ after: {{ cursor }}   │
└────────┬────────┘                       │
         │                                │
         ▼                                │
┌─────────────────┐                       │
│ Code Node       │ Extract cursor,       │
│                 │ check if more pages   │
└────────┬────────┘                       │
         │                                │
         ▼                                │
┌─────────────────┐                       │
│ IF Node         │ finished === false?───┘
│                 │
└────────┬────────┘
         │ (true: finished)
         ▼
┌─────────────────┐
│ Split In Batches│ Batch size: 10 (Airtable limit)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Airtable Node   │ Create/Update records
└─────────────────┘
```

### Code Node: Cursor Extraction

```javascript
const response = $input.all()[0].json;
const results = response.results || [];
const nextCursor = response.paging?.next?.after || null;

// Store results and cursor
return {
  results: results,
  cursor: nextCursor,
  finished: !nextCursor
};
```

### HTTP Request Body (Expression)

```json
{
  "filterGroups": [{
    "filters": [{
      "propertyName": "lastmodifieddate",
      "operator": "GT", 
      "value": "{{ $('Watermark').item.json.timestamp }}"
    }]
  }],
  "sorts": [{ "propertyName": "lastmodifieddate", "direction": "ASCENDING" }],
  "limit": 200,
  "after": {{ $('Code').item.json.cursor ? '"' + $('Code').item.json.cursor + '"' : 'null' }},
  "properties": ["email", "firstname", "lastname", "hs_object_id"]
}
```

---

## Webhook Workflow Pattern

For near-real-time sync using HubSpot webhooks.

### Architecture: Webhook → Queue → Worker

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ HubSpot Webhook │────►│ n8n Webhook     │────►│ Airtable Queue  │
│ (Push)          │     │ Trigger         │     │ Table           │
└─────────────────┘     │ (ACK immediately│     └────────┬────────┘
                        │  with 200)      │              │
                        └─────────────────┘              │
                                                         ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │ Airtable Upsert │◄────│ Worker Workflow │
                        │ (Final)         │     │ (Scheduled)     │
                        └─────────────────┘     └─────────────────┘
```

**Why Queue Pattern?**
- HubSpot times out after 5 seconds
- Events can be duplicated and unordered
- Batched events (up to 100 per webhook call)

### Webhook Trigger Workflow

```javascript
// Immediately return 200 - don't do heavy work here
// Just write to queue table

const events = $input.all()[0].json; // Array of events

// Dedupe key: portalId + subscriptionId + objectId + occurredAt
const queueRecords = events.map(e => ({
  fields: {
    "Event Key": `${e.portalId}-${e.subscriptionId}-${e.objectId}-${e.occurredAt}`,
    "Object Type": e.subscriptionType.split(".")[0],
    "Event Type": e.subscriptionType.split(".")[1],
    "Object ID": e.objectId,
    "Occurred At": new Date(e.occurredAt).toISOString(),
    "Processed": false
  }
}));

return queueRecords;
```

### Worker Workflow (Scheduled)

```
Cron (every 1 min) 
  → Airtable: Get unprocessed queue items
  → Deduplicate by Event Key
  → Batch: HubSpot Get records by ID
  → Transform
  → Airtable Upsert
  → Mark queue items processed
```

---

## Reconciliation Job Pattern

Scheduled incremental sync using watermark.

### Workflow

```
┌─────────────────┐
│ Cron Trigger    │ Every 5-15 minutes
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Get Watermark   │ From Airtable "Sync State" table
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Pagination Loop │ (See above)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Deduplicate     │ By HubSpot ID (hs_object_id)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Transform       │ HubSpot → Airtable field mapping
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Split In Batches│ Batch size: 10
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Airtable Upsert │ Match on HubSpot ID field
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Update Watermark│ Set to max lastmodifieddate
└─────────────────┘
```

### Watermark with Overlap

```javascript
// Get watermark and subtract 5 minutes for safety
const watermark = $('Get Watermark').item.json.fields.LastSync;
const watermarkWithOverlap = new Date(watermark).getTime() - (5 * 60 * 1000);

return { watermarkMs: watermarkWithOverlap };
```

---

## Airtable → HubSpot Pattern

### Workflow

```
┌─────────────────┐
│ Airtable Trigger│ On record update (or scheduled poll)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Filter          │ Only records with changes to sync
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Transform       │ Airtable → HubSpot field mapping
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Split In Batches│ Batch size: 100 (HubSpot limit)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ HTTP Request    │ Batch Upsert with idProperty
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Update Airtable │ Set last_synced_to_hubspot
└─────────────────┘
```

### Batch Upsert HTTP Request

**URL:** `https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert?idProperty=email`

**Body:**
```json
{
  "inputs": {{ $json.map(item => ({
    "id": item.email,
    "properties": {
      "firstname": item.firstName,
      "lastname": item.lastName,
      "company": item.company
    }
  })) }}
}
```

---

## Rate Limit Handling

### For Non-Search Endpoints

Add a Code node after HTTP Request to check headers:

```javascript
const remaining = $input.item.json.$response.headers['x-hubspot-ratelimit-remaining'];

if (remaining && parseInt(remaining) < 10) {
  // Signal to wait
  return { shouldWait: true, waitMs: 3000 };
}

return { shouldWait: false };
```

Then use IF node + Wait node to pause when needed.

### For Search API

Enforce 5 rps at design time:

```
Split In Batches (size: 5)
  → HTTP Request (Search)
  → Wait (200ms) ← Add small delay
```

### On 429 Error

Use "Retry on Fail" with:
- Wait between retries: `={{ $response.headers['retry-after'] * 1000 || 10000 }}`
- Max retries: 5

---

## Memory Management

n8n is Node.js - loading 100,000 records will crash.

### Streaming Pattern

**Don't:** Accumulate all pages, then process

**Do:** Process each page inside the loop, then release

```javascript
// In pagination loop, after Airtable upsert:
// Clear the results to free memory
$('HTTP Request').item.json.results = null;
```

### Large Initial Loads

Use "Time Slicing" - query by date ranges:

```
Loop: For each month in range
  → Search (createdate BETWEEN start AND end)
  → Process
  → Update progress checkpoint
```

---

## Error Workflows

Attach Error Trigger to critical nodes.

### Error Workflow

```
┌─────────────────┐
│ Error Trigger   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Slack/Email     │ Send alert with execution ID
│ Notification    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Airtable        │ Log to "Sync Errors" table
│ Create Record   │ (execution_id, error, timestamp)
└─────────────────┘
```

### Error Log Fields

- `execution_id`: Link to n8n execution
- `workflow_name`: Which workflow failed
- `node_name`: Which node failed
- `error_message`: Error details
- `input_data`: Truncated input that caused failure
- `timestamp`: When it failed
