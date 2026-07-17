---
name: tool.0253_freshdesk_data_exporter.762e75167d6e2486
description: Use when tasks require freshdesk data exporter with credential-aware
  preflight, deterministic execution, validation gates, and handoff-ready artifacts.
---
# Freshdesk Data Exporter

## Quick Reference
| Field | Value |
| --- | --- |
| Skill ID | `253` |
| Provider | `Freshdesk` |
| Operation | `Data Exporter` |
| Domain | `External SaaS integrations` |
| Runtime archetype | `typed-export-engine` |
| Core method | `typed extraction and delivery` |
| Primary artifact | `freshdesk-export-package` |
| Routing tag | `freshdesk:data-exporter` |
| Mutating | `no` |
| Release cycles | `1` |

## Why This Skill Exists
We need this skill because Freshdesk workflows degrade when auth, schema, and side-effect handling drift when integrations are run ad hoc. This specific skill turns Freshdesk Data Exporter into a deterministic, auth-checked workflow for exports freshdesk entities into clean, typed datasets..

## Trigger Checklist
- [ ] The task explicitly requires `Freshdesk Data Exporter` rather than generic brainstorming.
- [ ] The provider tenant, workspace, or environment is known before execution begins.
- [ ] Credential reuse has been checked before asking for new secrets.
- [ ] Success criteria, side effects, and handoff owner are clear.
- [ ] If the run mutates provider state, the relevant approval gates are available.

## Auth & Access Profile
| Field | Value |
| --- | --- |
| External auth required | `yes` |
| API key likely required | `no` |
| Protocols | `HTTPS/REST` |
| Mutating | `no` |
| Webhook capable | `no` |

| Auth Mode | Kind | Env Hints | Validation |
| --- | --- | --- | --- |
| OAuth client or delegated session | `oauth2` | `FRESHDESK_CLIENT_ID`, `FRESHDESK_CLIENT_SECRET` | Reuse an active delegated session or validate the client credentials with a lightweight identity call. |
| Access token or personal access token | `token` | `FRESHDESK_TOKEN`, `FRESHDESK_ACCESS_TOKEN` | Validate the token with the smallest read-only endpoint that proves scope and tenancy. |

## Inputs (contract)
| Input | Type | Required | Source |
| --- | --- | --- | --- |
| export specification | signal | yes | operator or upstream tool |
| query filters | signal | yes | operator or upstream tool |
| destination contract | signal | yes | operator or upstream tool |

## Outputs (contract)
| Output | Type | Guaranteed | Consumer |
| --- | --- | --- | --- |
| freshdesk-export-package | structured-artifact | yes | next workflow or operator |
| freshdesk-export-package-scorecard | scorecard | yes | reviewer |
| freshdesk-export-package-handoff | handoff-packet | yes | downstream owner |

## Step-by-Step Implementation Guide
1. Define the approved entities, fields, and destination contract for Freshdesk Data Exporter, then constrain the export scope for Freshdesk before running queries.
2. Validate credential reuse, pagination strategy, and the exact schema version that downstream consumers expect.
3. Implement exports freshdesk entities into clean, typed datasets. with deterministic extraction, normalization, and integrity metadata for every page or batch.
4. Attach counts, checksums, and schema fingerprints to the export package and block delivery when the contract drifts.
5. Run integration and regression suites that cover unauthorized field expansion, pagination gaps, and partial delivery failures.
6. Publish a delivery-ready export package with scope notes, integrity metadata, and any quarantined records called out explicitly.

## Operational Runbook
### Preflight
- Validate export scope, filters, and destination expectations before running queries.
- Confirm credentials and verify that the export respects the agreed data minimization policy.

### Execution
- Run deterministic queries, preserve pagination/cursor details, and normalize the output schema.
- Attach checksums and row counts to every export package.

### Recovery
- Invalidate partial exports and rerun from the last clean page or cursor on failure.
- Stop delivery when the schema drifts outside the declared contract.

### Handoff
- Return the export package location, checksums, and schema summary.
- Note any rows filtered, dropped, or quarantined before the package was finalized.

## Validation Gates & Test Matrix
| Gate | Purpose | On Fail |
| --- | --- | --- |
| auth-preflight | Validate credential presence, scope, and environment before work begins. | block execution |
| schema-contract-check | Ensure required signals and payload shapes remain valid. | quarantine and request correction |
| policy-approval-check | Verify the declared approval gates before mutating or publishing state. | pause or route to human review |
| reliability-check | Confirm retries, rollback, and checkpoint readiness. | rollback or fail closed |

- Required validation suites: `unit`, `integration`, `regression-baseline`

## Failure Modes & Recovery Playbook
| Code | Trigger | Action |
| --- | --- | --- |
| `E_SCOPE_MISMATCH` | The requested export exceeds the approved entity or field scope. | Block the export and request an updated scope approval. |
| `E_SCHEMA_DRIFT` | Provider output no longer matches the declared export contract. | Quarantine the package and attach a schema diff for review. |
| `E_PARTIAL_DELIVERY` | The export completes locally but delivery confirmation fails. | Invalidate the artifact and rerun from the last stable cursor. |

## Tool Call Implementation
- Reuse existing credentials first. Check environment variables, secure stores, and active sessions before prompting.
- Start with the smallest authenticated read or validation call that proves identity and scope.
- Preserve request, response, and approval traces in `freshdesk-export-package` so downstream owners do not need to rediscover context.
- If any auth, contract, or approval gate fails, halt execution and attach remediation guidance instead of guessing.

## Credential Reuse Policy
- Reuse valid provider credentials by default and prefer tenant-scoped sessions over newly created secrets.
- Prompt for credentials only when they are missing, invalid, expired, or point at the wrong environment.
- For webhook flows, validate the signing secret against a known sample before accepting live traffic.

## Guardrails
- quality: Attach counts, checksums, and schema version to every export package. (`export-integrity-check`)
- compliance: Reject exports that exceed the approved data scope. (`data-scope-review`)
- reliability: Invalidate partial deliveries instead of handing off incomplete datasets. (`partial-delivery-block`)

## Acceptance Checklist
- [ ] Credential preflight and scope validation completed successfully.
- [ ] Required validation suites ran and all fail-closed gates passed.
- [ ] freshdesk-export-package, scorecard, and handoff packet were produced.
- [ ] Any mutations, approvals, or rollbacks are reflected in the artifact bundle.

## Anti-Patterns
- Do not ask for new credentials before checking reusable auth context.
- Do not skip the read-only or dry-run validation step for mutating work.
- Do not proceed when approval gates, signing secrets, or rollback checkpoints are missing.
- Do not hand off partial or ambiguous provider state as complete.

## Handoff Contract
- **Produces:** `freshdesk-export-package`, execution scorecard, approval trace, and next actions.
- **Consumes:** `export specification`, `query filters`, `destination contract`.
- **Readiness rule:** release only after auth, contract, approval, and reliability gates all pass.
- **Downstream hint:** route to `freshdesk:data-exporter` consumers with approval and credential context attached.

## Observability & Continuous Improvement
- SLO: >=99.5% successful runs per 7-day window
- Error budget: <=0.5% critical failures per 7-day window
- Alert triggers:
- credential validation failures exceed baseline
- schema or contract regressions persist for two consecutive runs
- critical posture or rollback events exceed tolerance
- Primary outcome metric: `export completeness`
- Secondary metrics: `schema conformance`, `delivery latency`
- Review cadence: `weekly`
