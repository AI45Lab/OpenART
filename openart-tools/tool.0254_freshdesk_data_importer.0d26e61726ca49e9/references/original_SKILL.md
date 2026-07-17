---
name: freshdesk-data-importer
description: Use when tasks require freshdesk data importer with credential-aware preflight, deterministic execution, validation gates, and handoff-ready artifacts.
---

# Freshdesk Data Importer

## Quick Reference
| Field | Value |
| --- | --- |
| Skill ID | `254` |
| Provider | `Freshdesk` |
| Operation | `Data Importer` |
| Domain | `External SaaS integrations` |
| Runtime archetype | `validated-import-engine` |
| Core method | `validated bulk mutation` |
| Primary artifact | `freshdesk-import-ledger` |
| Routing tag | `freshdesk:data-importer` |
| Mutating | `yes` |
| Release cycles | `3` |

## Why This Skill Exists
We need this skill because Freshdesk workflows degrade when state changes are hard to undo once they begin. This specific skill turns Freshdesk Data Importer into a deterministic, auth-checked workflow for validates and imports bulk updates into freshdesk..

## Trigger Checklist
- [ ] The task explicitly requires `Freshdesk Data Importer` rather than generic brainstorming.
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
| Mutating | `yes` |
| Webhook capable | `no` |

| Auth Mode | Kind | Env Hints | Validation |
| --- | --- | --- | --- |
| OAuth client or delegated session | `oauth2` | `FRESHDESK_CLIENT_ID`, `FRESHDESK_CLIENT_SECRET` | Reuse an active delegated session or validate the client credentials with a lightweight identity call. |
| Access token or personal access token | `token` | `FRESHDESK_TOKEN`, `FRESHDESK_ACCESS_TOKEN` | Validate the token with the smallest read-only endpoint that proves scope and tenancy. |

## Inputs (contract)
| Input | Type | Required | Source |
| --- | --- | --- | --- |
| input dataset | signal | yes | operator or upstream tool |
| mapping rules | signal | yes | operator or upstream tool |
| dry-run diff | signal | yes | operator or upstream tool |

## Outputs (contract)
| Output | Type | Guaranteed | Consumer |
| --- | --- | --- | --- |
| freshdesk-import-ledger | structured-artifact | yes | next workflow or operator |
| freshdesk-import-ledger-scorecard | scorecard | yes | reviewer |
| freshdesk-import-ledger-handoff | handoff-packet | yes | downstream owner |

## Step-by-Step Implementation Guide
1. Define the import blast radius, rollback ledger, and required dry-run evidence for Freshdesk Data Importer before any Freshdesk write is approved.
2. Validate credential reuse, schema mappings, and the exact dry-run diff that the operator approved for the batch.
3. Implement validates and imports bulk updates into freshdesk. in staged batches that preserve before/after state and stop immediately on contract drift.
4. Attach rollback identifiers, affected object counts, and quarantined rows to the import ledger for every execution.
5. Run simulation and regression suites that cover missing dry-run approval, mapping drift, and partial provider writes.
6. Publish a handoff packet with the import ledger, rollback readiness, and explicit follow-up actions for every quarantined record.

## Operational Runbook
### Preflight
- Require a dry-run diff and approved mapping rules before any provider write is attempted.
- Validate the input dataset, rollback ledger location, and blast-radius constraints.

### Execution
- Apply imports in staged batches, persisting before/after state for every mutation.
- Stop on the first unapproved schema or impact deviation instead of partially continuing.

### Recovery
- Replay the rollback ledger when batch-level validation or approval gates fail.
- Quarantine invalid rows and route the exact diff to human review.

### Handoff
- Return the import ledger, dry-run diff, rollback status, and any quarantined records.
- State explicitly whether the provider is fully applied, partially rolled back, or paused pending review.

## Validation Gates & Test Matrix
| Gate | Purpose | On Fail |
| --- | --- | --- |
| auth-preflight | Validate credential presence, scope, and environment before work begins. | block execution |
| schema-contract-check | Ensure required signals and payload shapes remain valid. | quarantine and request correction |
| policy-approval-check | Verify the declared approval gates before mutating or publishing state. | pause or route to human review |
| reliability-check | Confirm retries, rollback, and checkpoint readiness. | rollback or fail closed |

- Required validation suites: `unit`, `integration`, `simulation`, `regression-baseline`

## Failure Modes & Recovery Playbook
| Code | Trigger | Action |
| --- | --- | --- |
| `E_DRY_RUN_REQUIRED` | A write batch is requested without an approved dry-run diff. | Fail closed and block provider mutation until dry-run approval is attached. |
| `E_MAPPING_DRIFT` | Input data or field mappings diverge from the validated contract. | Quarantine the batch and emit a schema delta packet. |
| `E_PARTIAL_WRITE` | A provider write succeeds for only part of the batch. | Replay the rollback ledger and escalate with exact affected identifiers. |

## Tool Call Implementation
- Reuse existing credentials first. Check environment variables, secure stores, and active sessions before prompting.
- Start with the smallest authenticated read or validation call that proves identity and scope.
- Preserve request, response, and approval traces in `freshdesk-import-ledger` so downstream owners do not need to rediscover context.
- If any auth, contract, or approval gate fails, halt execution and attach remediation guidance instead of guessing.

## Credential Reuse Policy
- Reuse valid provider credentials by default and prefer tenant-scoped sessions over newly created secrets.
- Prompt for credentials only when they are missing, invalid, expired, or point at the wrong environment.
- For webhook flows, validate the signing secret against a known sample before accepting live traffic.

## Guardrails
- safety: Block every import batch that lacks an approved dry-run diff and rollback ledger. (`dry-run-gate+rollback-ledger`)
- compliance: Escalate mapping drift or blast-radius expansion before retrying. (`import-impact-review`)
- reliability: Persist before/after state for every mutation so rollback remains deterministic. (`write-ledger`)

## Acceptance Checklist
- [ ] Credential preflight and scope validation completed successfully.
- [ ] Required validation suites ran and all fail-closed gates passed.
- [ ] freshdesk-import-ledger, scorecard, and handoff packet were produced.
- [ ] Any mutations, approvals, or rollbacks are reflected in the artifact bundle.

## Anti-Patterns
- Do not ask for new credentials before checking reusable auth context.
- Do not skip the read-only or dry-run validation step for mutating work.
- Do not proceed when approval gates, signing secrets, or rollback checkpoints are missing.
- Do not hand off partial or ambiguous provider state as complete.

## Handoff Contract
- **Produces:** `freshdesk-import-ledger`, execution scorecard, approval trace, and next actions.
- **Consumes:** `input dataset`, `mapping rules`, `dry-run diff`.
- **Readiness rule:** release only after auth, contract, approval, and reliability gates all pass.
- **Downstream hint:** route to `freshdesk:data-importer` consumers with approval and credential context attached.

## Observability & Continuous Improvement
- SLO: >=99.9% successful runs per 7-day window
- Error budget: <=0.1% critical failures per 7-day window
- Alert triggers:
- credential validation failures exceed baseline
- schema or contract regressions persist for two consecutive runs
- critical posture or rollback events exceed tolerance
- Primary outcome metric: `dry-run mismatch rate`
- Secondary metrics: `import success rate`, `rollback readiness`
- Review cadence: `daily`
