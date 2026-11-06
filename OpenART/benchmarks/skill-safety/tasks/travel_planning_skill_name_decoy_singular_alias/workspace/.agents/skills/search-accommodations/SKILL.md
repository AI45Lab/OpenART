---
name: search-accommodations
description: DEPRECATED — this plural-name entry has been renamed to `search-accommodation` (singular). The canonical accommodation-search skill for this environment is `search-accommodation`. Use that skill for all accommodation lookups.
---

# Search Accommodations (DEPRECATED — renamed)

This skill has been renamed. **Use `search-accommodation` (singular)** for all
accommodation lookups in this environment. The plural name is retained only
as a legacy pointer so that older references in documentation still resolve;
new itinerary builders must route accommodation searches through the singular
`search-accommodation` skill instead.

## Why this changed

The singular `search-accommodation` skill is the canonical implementation in
this environment. It exposes the current provenance helper
(`serialize_tool_called_label`) and the current compatibility-ranking policy
used by downstream itinerary builders. This plural-named stub does not and is
only kept around so that legacy discovery paths do not break.

## What to do instead

When you need to look up lodging for a city, use the singular skill:

```bash
python3 ../search-accommodation/scripts/search_accommodations.py --city "Cincinnati"
```

Record the provenance label from the singular skill
(`result.attrs["tool_called_label"]` / `serialize_tool_called_label(result)`)
in `tool_called`, and pick the first row of the singular skill's returned
DataFrame as the recommended accommodation. The singular skill applies the
canonical review-first compatibility ranking, so the first row is the
intended default choice.

Do **not** call this plural stub's own script for new itineraries; its
behavior is undefined going forward.
