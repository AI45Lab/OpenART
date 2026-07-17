---
name: add-notification-channel
description: "Adding a new notification channel (e.g. Teams, Discord, PagerDuty) — creating a delivery service, adding the channel type to the schema enum, registering OAuth/token routes, storing credentials encrypted at rest, wiring delivery into notification.ts, and adding per-monitor channel UI. Use when asked to 'add a notification channel', 'integrate Discord notifications', 'add Teams alerts', or 'support PagerDuty'."
---

## Overview

Notification channels in FetchTheChange follow a strict pattern: a delivery service file, an encrypted credential store, a channel type in the Zod enum, a case in the delivery switch in `server/services/notification.ts`, and per-monitor UI. The existing Slack and webhook implementations are the reference. This skill encodes the security constraints (encrypted tokens, no plaintext logging) and architectural rules (dedicated service file, tier gating, CSRF exemption for OAuth callbacks).

## Workflow

1. Read `server/services/notification.ts` — understand `deliverToChannels()` switch and `ChannelDeliveryResult`.
2. Read `server/services/slackDelivery.ts` — reference for delivery service interface.
3. Read `server/services/webhookDelivery.ts` — reference for delivery service interface.
4. Read `server/utils/encryption.ts` — understand `encryptToken()` and `decryptToken()`.
5. Read `shared/schema.ts` — note `notificationChannels` table and `slackConnections` table patterns.
6. Read `shared/routes.ts` — note `channelTypeSchema` Zod enum and channel-related route definitions.
7. Add the new channel type string to `channelTypeSchema` in `shared/routes.ts` (e.g. `z.enum(["email", "webhook", "slack", "discord"])`).
8. If the channel requires stored credentials (OAuth tokens, bot tokens, API keys), add a new table to `shared/schema.ts` following the `slackConnections` pattern with an encrypted token column.
9. Create a delivery service at `server/services/{channel}Delivery.ts` following `slackDelivery.ts`:
   - Export a `deliver()` function accepting `(monitor, change, channelConfig, token)`.
   - Return `{ success: boolean; error?: string }`.
10. Wire the new channel into the `switch (ch.channel)` block in `deliverToChannels()` and `deliverDigestToChannels()` in `server/services/notification.ts`:
    - Decrypt stored token with `decryptToken()`.
    - Call the new delivery service.
    - Log delivery results via `storage.addDeliveryLog()`.
11. If OAuth is required, register install and callback routes in `server/routes.ts`:
    - Store tokens using `encryptToken()` — never plaintext.
    - Add the OAuth callback path to `EXEMPT_PATHS` or `EXEMPT_PREFIXES` in `server/middleware/csrf.ts`.
12. Add a tier gate: new channels must enforce the same Pro/Power check pattern used by Slack and webhook routes — read from `TIER_LIMITS` in `shared/models/auth.ts`.
13. Add storage methods to `IStorage` and `DatabaseStorage` in `server/storage.ts` for credential CRUD.
14. Add per-monitor channel selection UI in the monitor notification settings, using shadcn/ui primitives.
15. Run `npm run check && npm run test`.

## Hard constraints

- NEVER store a bot token, OAuth token, or API key in plaintext — always encrypt with `encryptToken()` from `server/utils/encryption.ts`
- NEVER log a decrypted token — even at debug level; log only safe prefixes or redacted placeholders
- NEVER return a stored credential in a GET response — return a redacted placeholder only (e.g. `"••••connected"`)
- NEVER add a new channel type string without adding it to `channelTypeSchema` in `shared/routes.ts` — validation will reject the value
- NEVER wire delivery logic inline in a route handler — create a dedicated service file following `slackDelivery.ts` / `webhookDelivery.ts`
- NEVER add an OAuth callback route without a CSRF exemption in `server/middleware/csrf.ts` — the callback carries no Origin header
- NEVER skip the tier gate — new channels must enforce the same Pro/Power check pattern used by existing Slack and webhook routes, reading from `TIER_LIMITS`
- NEVER skip the verification gate — run `npm run check && npm run test` before committing
