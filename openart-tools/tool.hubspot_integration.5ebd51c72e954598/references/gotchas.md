# HubSpot Integration Gotchas & Pitfalls

Common issues encountered when building HubSpot ↔ Airtable sync workflows.

## Table of Contents
1. [Merge Handling](#merge-handling)
2. [Deletion Handling](#deletion-handling)
3. [Property Names](#property-names)
4. [Data Formats](#data-formats)
5. [Associations](#associations)
6. [Webhooks](#webhooks)
7. [Rate Limits](#rate-limits)
8. [Legacy API Traps](#legacy-api-traps)

---

## Merge Handling

**The Problem:** When Contact A (ID: 100) merges into Contact B (ID: 200):
- ID 100 becomes inactive/archived
- Airtable still references ID 100
- Future syncs for ID 100 will fail with 404
- Associations may move to the primary record

**Detection:** Subscribe to `contact.merge` webhook.

**Payload Fields:**
- `primaryObjectId`: The surviving record (200)
- `mergedObjectIds`: Array of merged records ([100])

**Resolution Pattern:**

```javascript
// On merge event:
async function handleMerge({ primaryId, mergedIds, airtableBase }) {
  for (const mergedId of mergedIds) {
    // 1. Find Airtable record with merged ID
    const records = await airtableBase.select({
      filterByFormula: `{HubSpot ID} = '${mergedId}'`
    }).firstPage();
    
    if (records.length === 0) continue;
    
    // 2. Check if primary already exists
    const primaryRecords = await airtableBase.select({
      filterByFormula: `{HubSpot ID} = '${primaryId}'`
    }).firstPage();
    
    if (primaryRecords.length > 0) {
      // Primary exists - delete the merged record (or merge fields)
      await airtableBase.destroy(records[0].id);
    } else {
      // Primary doesn't exist - update ID reference
      await airtableBase.update(records[0].id, {
        "HubSpot ID": primaryId
      });
    }
    
    // 3. Re-fetch primary record to get updated data
    // (merge may have changed field values)
    await refreshFromHubSpot(primaryId);
  }
}
```

**Maintain Alias Table:** For audit trail, store `merged_hubspot_id → primary_hubspot_id` mapping.

---

## Deletion Handling

**The Problem:** Deleted records don't appear in Search API results. The `lastmodifieddate` filter won't catch them.

**Detection:** Subscribe to:
- `contact.deletion`
- `contact.privacyDeletion` (also triggers `contact.deletion`)
- `*.restore` for reactivation

**Payload Fields:**
- `objectId`: The deleted record ID
- `deletedAt`: Timestamp

**Resolution Pattern:**

```javascript
// On deletion event:
async function handleDeletion({ objectId, airtableBase }) {
  const records = await airtableBase.select({
    filterByFormula: `{HubSpot ID} = '${objectId}'`
  }).firstPage();
  
  if (records.length > 0) {
    // Soft delete (recommended)
    await airtableBase.update(records[0].id, {
      "Status": "Deleted",
      "Deleted At": new Date().toISOString()
    });
    
    // Or hard delete:
    // await airtableBase.destroy(records[0].id);
  }
}
```

**Recommendation:** Soft-delete (mark inactive) rather than hard-delete for audit purposes.

---

## Property Names

**The Problem:** API uses internal names, not UI labels.

| UI Label | Internal Name |
|----------|---------------|
| "Phone Number" | `phone` |
| "Contact owner" | `hubspot_owner_id` |
| "Last Modified Date" | `lastmodifieddate` |
| "Create Date" | `createdate` |

**The Trap:** `hs_lastmodifieddate` vs `lastmodifieddate`
- For contacts Search, use `lastmodifieddate` (not `hs_lastmodifieddate`)
- This varies by object type!

**Solution:** Fetch property schema to validate:

```javascript
async function getPropertyNames({ accessToken, objectType }) {
  const res = await fetch(
    `https://api.hubapi.com/crm/v3/properties/${objectType}`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  );
  
  const data = await res.json();
  return data.results.map(p => ({
    label: p.label,
    name: p.name,
    type: p.type
  }));
}
```

**Webhook Gotcha:** Property-change webhooks cannot subscribe to `hs_lastmodifieddate`.

---

## Data Formats

### Multi-Select Fields
HubSpot uses semicolon-delimited strings:

```javascript
// HubSpot format: "chocolate;strawberry;vanilla"

// Reading from HubSpot:
const airtableArray = hubspotValue.split(";").filter(Boolean);

// Writing to HubSpot:
const hubspotValue = airtableArray.join(";");
```

### Date Fields
May come as epoch milliseconds:

```javascript
// HubSpot: "1674758400000"
const isoDate = new Date(parseInt(hubspotValue)).toISOString();
// → "2023-01-26T16:00:00.000Z"
```

### Checkbox Fields
Come as strings:

```javascript
// HubSpot: "true" or "false" (strings!)
const boolValue = hubspotValue === "true";
```

### Number Fields
Often returned as strings:

```javascript
// HubSpot: "123.45"
const numValue = parseFloat(hubspotValue);
```

### Timezone Issues

**Rule:** Always use UTC with Z designator.

```javascript
// Use Luxon in n8n for safe transformations:
const { DateTime } = require("luxon");
const utc = DateTime.fromISO(localDate).toUTC().toISO();
```

**Trap:** n8n may interpret "2023-01-01" as local server time if not explicit.

---

## Associations

### v3 Only Returns Primary Company

When fetching associations via v3, you only get the **primary** associated company.

**Solution:** Use v4 for all association reads:

```
POST /crm/v4/associations/contacts/companies/batch/read
```

### Association Type IDs Are Directional

The `typeId` for Contact → Company is different from Company → Contact.

**Always specify the correct direction:**

```javascript
// Contact → Company
POST /crm/v4/associations/contacts/companies/batch/read

// Company → Contact  
POST /crm/v4/associations/companies/contacts/batch/read
```

### Custom Label IDs Are Account-Specific

Don't hardcode custom association label IDs across HubSpot portals. They're unique per account.

**Solution:** Fetch types dynamically:

```javascript
GET /crm/v3/associations/contacts/companies/types
// Returns: [{ typeId: 1, label: "Primary", category: "HUBSPOT_DEFINED" }, ...]
```

### Association Changes Fire Twice

Association webhooks fire for **both sides** of the association. Expect two events per change.

**Solution:** Deduplicate by composite key including both object IDs.

---

## Webhooks

### Events Are Batched, Unordered, and Duplicated

- Up to 100 events per webhook call
- No guaranteed order
- `eventId` is **not** guaranteed unique

**Deduplication Key:**

```javascript
const dedupeKey = `${event.portalId}-${event.subscriptionId}-${event.objectId}-${event.occurredAt}`;
```

### 5-Second Timeout

HubSpot considers your endpoint failed if it takes >5 seconds to respond.

**Solution:** ACK immediately, process async via queue.

### HubSpot Retries Failures

- Retries up to 10 times over 24 hours
- Any 4xx/5xx triggers retry
- Timeout (>5s) triggers retry

**Solution:** Always return 200 quickly, even if you can't process immediately.

---

## Rate Limits

### Search API Has Separate Limits

- 5 requests/second per token
- **No rate limit headers returned**

**Trap:** People read `X-HubSpot-RateLimit-*` on other endpoints and assume it applies to Search.

**Solution:** Enforce 5 rps at design time (add delays between Search calls).

### Associations API Has Its Own Limits

Don't assume general tier limits apply:

| Tier | Associations Burst |
|------|-------------------|
| Free/Starter | 100/10s |
| Pro/Enterprise | 150/10s |

### Daily Limits Aren't Infinite

| Tier | Daily Limit |
|------|-------------|
| Free/Starter | 250,000 |
| Professional | 625,000 |
| Enterprise | 1,000,000 |

**Monitor:** `X-HubSpot-RateLimit-Daily-Remaining` header.

---

## Legacy API Traps

### API Keys Are Deprecated

Don't start new work with `?hapikey=`. Use Private App tokens.

### v1 APIs Are Being Sunset

Example: Lists v1 sunset moved to April 30, 2026. After that, v1 list endpoints return 404.

**Action:** If you inherit v1 usage, schedule migration to v3.

### v1/v2 Data Shapes Are Inconsistent

- v1 Contacts: Properties as map (`{ "email": "..." }`)
- v2 Companies: Properties as list (`[{ "name": "email", "value": "..." }]`)

**Solution:** Build on v3 only. It has consistent shapes across all objects.
