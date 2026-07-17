---
name: hubspot-integration
description: Build reliable HubSpot ↔ Airtable sync workflows. Covers API selection, rate limits, sync architecture, and n8n implementation patterns.
---

# HubSpot Integration Patterns

Build reliable HubSpot ↔ Airtable sync workflows. This skill covers API selection, rate limits, sync architecture, and n8n implementation.

## Quick Reference

| Task | API | Endpoint Pattern |
|------|-----|------------------|
| CRUD objects | v3 | `POST /crm/v3/objects/{type}` |
| Search/filter | v3 | `POST /crm/v3/objects/{type}/search` |
| Batch upsert | v3 | `POST /crm/v3/objects/{type}/batch/upsert` |
| Associations (all) | v4 | `POST /crm/v4/associations/{from}/{to}/batch/read` |
| Labeled associations | v4 | `PUT /crm/v4/objects/{type}/{id}/associations/{toType}/{toId}` |

## API Selection

### Use v3 for Objects + Search
```
/crm/v3/objects/contacts          # CRUD
/crm/v3/objects/contacts/search   # Filter + paginate
/crm/v3/objects/contacts/batch/upsert  # Bulk writes
```

### Use v4 for Associations
v3 associations only return the **primary** associated company. v4 returns **all** associations with labels.

```
/crm/v4/associations/contacts/companies/batch/read  # Batch read (1000 inputs)
/crm/v4/objects/contact/{id}/associations/company/{companyId}  # Labeled association
```

## Authentication

Use **Private App tokens** (Bearer auth). API keys are deprecated.

```
Authorization: Bearer {ACCESS_TOKEN}
```

**Required scopes for sync:**
- `crm.objects.contacts.read` / `.write`
- `crm.objects.companies.read` / `.write`
- `crm.objects.deals.read` / `.write`
- `crm.schemas.custom.read`

## Rate Limits

### Tiered Limits (Private Apps)

| Tier | Burst (per 10s) | Daily |
|------|-----------------|-------|
| Free/Starter | 100 | 250,000 |
| Professional | 190 | 625,000 |
| Enterprise | 190 | 1,000,000 |

### Search API: Separate Limit
**5 requests/second per token** — no rate limit headers returned.

### Associations API (v4)
- Burst: 100-150/10s depending on tier
- Batch read: 1,000 inputs max
- Batch create: 2,000 inputs max

### Rate Limit Headers
```
X-HubSpot-RateLimit-Remaining      # Requests left in 10s window
X-HubSpot-RateLimit-Daily-Remaining # Requests left today
Retry-After                        # Seconds to wait after 429
```

**Backoff Strategy:**
1. If `Retry-After` header exists, wait that duration
2. Otherwise, if `X-HubSpot-RateLimit-Remaining < 10`, wait 3 seconds
3. On 429 without headers, wait 10 seconds (TEN_SECONDLY_ROLLING policy)

## Sync Architecture

### Recommended: Hybrid Pattern
- **Webhooks** for immediacy (deletions, merges, critical updates)
- **Polling with watermark** for completeness (incremental sync)

### Watermark Incremental Sync (Read Path)

```javascript
// Store watermark: last_sync_timestamp (epoch ms)
{
  "filterGroups": [{
    "filters": [{
      "propertyName": "lastmodifieddate",  // Note: NOT hs_lastmodifieddate for contacts
      "operator": "GT",
      "value": "1674758400000"
    }]
  }],
  "sorts": [{ "propertyName": "lastmodifieddate", "direction": "ASCENDING" }],
  "limit": 200,
  "after": "cursor_from_previous_page",
  "properties": ["email", "firstname", "lastname", "hs_object_id"]
}
```

**Critical:** Use overlap window (watermark minus 2-5 minutes) to avoid missing records with identical timestamps.

### Write Path (Airtable → HubSpot)
Use batch upsert with `idProperty` for idempotent writes:

```javascript
POST /crm/v3/objects/contacts/batch/upsert?idProperty=email
{
  "inputs": [
    { "id": "user@example.com", "properties": { "firstname": "James" } }
  ]
}
```

## Avoiding N+1 Queries

**Bad:** Fetch 100 contacts, then 100 individual association calls = 101 requests

**Good:** Batch read associations:
```javascript
POST /crm/v4/associations/contacts/companies/batch/read
{ "inputs": [{ "id": "101" }, { "id": "102" }, ...] }  // up to 1000
```

## Bi-Directional Loop Prevention

Prevent infinite sync loops with:

1. **Field-level diffing:** Only write if incoming value differs from existing
2. **"Last Updated By" filter:** Exclude changes made by integration user
   ```
   hs_updated_by_user_id NOT_EQ {integration_user_id}
   ```

## Reference Files

- **[references/gotchas.md](references/gotchas.md)** — Merge handling, deletions, property names, data formats
- **[references/n8n-patterns.md](references/n8n-patterns.md)** — Pagination loops, webhook patterns, rate limiting
- **[references/api-reference.md](references/api-reference.md)** — Code examples for search, batch ops, associations
