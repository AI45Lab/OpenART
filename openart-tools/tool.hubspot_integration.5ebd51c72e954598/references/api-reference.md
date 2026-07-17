# HubSpot API Reference

## Table of Contents
1. [Search API](#search-api)
2. [Batch Operations](#batch-operations)
3. [Associations v4](#associations-v4)
4. [Rate Limit Handling](#rate-limit-handling)
5. [Data Type Mapping](#data-type-mapping)

---

## Search API

### Search Recently Modified Records

```javascript
async function searchModifiedContacts({ accessToken, watermarkMs, cursor }) {
  const body = {
    filterGroups: [{
      filters: [{
        propertyName: "lastmodifieddate",  // NOT hs_lastmodifieddate for contacts
        operator: "GT",
        value: String(watermarkMs)
      }]
    }],
    sorts: [{ propertyName: "lastmodifieddate", direction: "ASCENDING" }],
    limit: 200,  // Max for search
    properties: ["email", "firstname", "lastname", "lastmodifieddate", "hs_object_id"]
  };
  
  if (cursor) body.after = cursor;
  
  const res = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });
  
  return res.json();
}
```

### Paginate Through All Results

```javascript
async function* paginateSearch({ accessToken, watermarkMs }) {
  let cursor = null;
  
  while (true) {
    const result = await searchModifiedContacts({ accessToken, watermarkMs, cursor });
    yield result.results;
    
    cursor = result.paging?.next?.after;
    if (!cursor) break;
  }
}

// Usage:
for await (const batch of paginateSearch({ accessToken, watermarkMs })) {
  await processContacts(batch);  // Process 200 at a time
}
```

### Search Filter Operators

| Operator | Description | Example Value |
|----------|-------------|---------------|
| `EQ` | Equals | `"value"` |
| `NEQ` | Not equals | `"value"` |
| `LT` | Less than | `"1674758400000"` |
| `LTE` | Less than or equal | `"1674758400000"` |
| `GT` | Greater than | `"1674758400000"` |
| `GTE` | Greater than or equal | `"1674758400000"` |
| `CONTAINS_TOKEN` | Contains word | `"term"` |
| `IN` | In list | `["a","b","c"]` |

---

## Batch Operations

### Batch Upsert by Unique Property

```javascript
async function batchUpsertContacts({ accessToken, contacts, idProperty = "email" }) {
  const url = new URL("https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert");
  url.searchParams.set("idProperty", idProperty);
  
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      inputs: contacts.map(c => ({
        id: c[idProperty],  // The unique identifier value
        properties: c.properties
      }))
    })
  });
  
  if (!res.ok) {
    const error = await res.json();
    throw new Error(`Upsert failed: ${JSON.stringify(error)}`);
  }
  
  return res.json();
}
```

**Batch Limits:**
- Batch create: 100 records
- Batch update: 100 records
- Batch upsert: 100 records

### Batch Error Handling (Fallback to Serial)

```javascript
async function robustBatchUpsert({ accessToken, contacts, idProperty }) {
  try {
    return await batchUpsertContacts({ accessToken, contacts, idProperty });
  } catch (error) {
    // Batch failed - fall back to individual updates
    const results = { succeeded: [], failed: [] };
    
    for (const contact of contacts) {
      try {
        const res = await singleUpsert({ accessToken, contact, idProperty });
        results.succeeded.push(res);
      } catch (err) {
        results.failed.push({ contact, error: err.message });
      }
    }
    
    return results;
  }
}
```

---

## Associations v4

### Batch Read Associations

```javascript
async function batchReadContactCompanies({ accessToken, contactIds }) {
  const res = await fetch(
    "https://api.hubapi.com/crm/v4/associations/contacts/companies/batch/read",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        inputs: contactIds.map(id => ({ id: String(id) }))
      })
    }
  );
  
  const data = await res.json();
  
  // Transform to lookup map: { contactId: [companyIds] }
  const assocMap = {};
  for (const result of data.results) {
    assocMap[result.from.id] = result.to.map(t => ({
      id: t.toObjectId,
      labels: t.associationTypes.map(a => a.label).filter(Boolean)
    }));
  }
  
  return assocMap;
}
```

**Batch Limits:**
- Batch read: 1,000 inputs
- Batch create: 2,000 inputs

### Create Labeled Association

```javascript
async function createLabeledAssociation({ 
  accessToken, 
  fromType, 
  fromId, 
  toType, 
  toId, 
  associationTypeId,
  category = "USER_DEFINED"  // or "HUBSPOT_DEFINED"
}) {
  const url = `https://api.hubapi.com/crm/v4/objects/${fromType}/${fromId}/associations/${toType}/${toId}`;
  
  const res = await fetch(url, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify([{
      associationCategory: category,
      associationTypeId: associationTypeId
    }])
  });
  
  return res.json();
}
```

### Get Association Type IDs

```javascript
async function getAssociationTypes({ accessToken, fromType, toType }) {
  const res = await fetch(
    `https://api.hubapi.com/crm/v3/associations/${fromType}/${toType}/types`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  
  return res.json();  // { results: [{ typeId, label, category }] }
}
```

**Note:** Custom association label IDs are account-specific. Don't hardcode across portals.

---

## Rate Limit Handling

### Robust Request Wrapper with Backoff

```javascript
function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function hubspotFetch(url, { accessToken, method = "GET", body, maxRetries = 6 } = {}) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const res = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...(body ? { "Content-Type": "application/json" } : {})
      },
      body: body ? JSON.stringify(body) : undefined
    });
    
    // Success or client error (except 429)
    if (res.status !== 429 && res.status < 500) return res;
    
    // Handle 429 Rate Limit
    if (res.status === 429) {
      const retryAfter = res.headers.get("retry-after");
      if (retryAfter) {
        await sleep(Number(retryAfter) * 1000);
        continue;
      }
      
      const intervalMs = Number(res.headers.get("x-hubspot-ratelimit-interval-milliseconds"));
      if (intervalMs) {
        await sleep(intervalMs);
      } else {
        // TEN_SECONDLY_ROLLING default
        await sleep(10_000);
      }
      continue;
    }
    
    // 5xx: exponential backoff
    await sleep(200 * Math.pow(2, attempt));
  }
  
  throw new Error(`HubSpot request failed after ${maxRetries} retries: ${url}`);
}
```

### Proactive Rate Limit Checking

```javascript
async function rateAwareRequest(url, options) {
  const res = await hubspotFetch(url, options);
  
  // Check remaining quota
  const remaining = res.headers.get("x-hubspot-ratelimit-remaining");
  if (remaining && Number(remaining) < 10) {
    await sleep(3000);  // Proactive pause
  }
  
  return res;
}
```

---

## Data Type Mapping

### HubSpot → Airtable Type Conversion

| HubSpot Type | API Format | Airtable Conversion |
|--------------|------------|---------------------|
| Text | `"string"` | Direct |
| Number | `"123"` (string) | `parseFloat(value)` |
| Date | `"YYYY-MM-DD"` | Direct |
| DateTime | `"1674758400000"` (epoch ms) | `new Date(parseInt(value)).toISOString()` |
| Select | `"internal_value"` | Map to label or use `typecast: true` |
| Multi-select | `"val1;val2;val3"` | `value.split(";")` |
| Checkbox | `"true"` / `"false"` | `value === "true"` |

### Multi-Select Formatting

```javascript
// HubSpot → Airtable
const airtableArray = hubspotValue.split(";").filter(Boolean);

// Airtable → HubSpot  
const hubspotValue = airtableArray.join(";");
```

### Date/Time Handling

```javascript
// Always use UTC ISO-8601 with Z designator
const isoString = new Date(parseInt(hubspotEpochMs)).toISOString();
// "2023-01-26T16:00:00.000Z"

// Airtable → HubSpot (if sending dates)
const epochMs = new Date(airtableIsoDate).getTime();
```

---

## Object Type Reference

### Standard Objects
| Object | Type String | Numeric ID |
|--------|-------------|------------|
| Contacts | `contacts` | `0-1` |
| Companies | `companies` | `0-2` |
| Deals | `deals` | `0-3` |
| Tickets | `tickets` | `0-5` |

### Custom Objects
Use `fullyQualifiedName` (e.g., `p12345_patents`) not numeric `objectTypeId` — numeric IDs differ between sandbox and production.
