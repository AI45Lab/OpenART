---
name: amazon-seller-report-builder
description: Use when tasks require amazon seller report builder with credential-aware preflight, deterministic execution, validation gates, and handoff-ready artifacts.
---

# Amazon Seller Report Builder

## Quick Reference
| Field | Value |
| --- | --- |
| Skill ID | `336` |
| Provider | `Amazon Seller` |
| Operation | `Report Builder` |
| Domain | `External SaaS integrations` |
| Runtime archetype | `reporting-engine` |
| Core method | `metric synthesis and rendering` |
| Primary artifact | `amazon-seller-report-bundle` |
| Routing tag | `amazon-seller:report-builder` |
| Mutating | `no` |
| Release cycles | `1` |

## Why This Skill Exists
We need this skill because Amazon Seller workflows degrade when auth, schema, and side-effect handling drift when integrations are run ad hoc. This specific skill turns Amazon Seller Report Builder into a deterministic, auth-checked workflow for generates operational and kpi reports from amazon seller activity..

## Trigger Checklist
- [ ] The task explicitly requires `Amazon Seller Report Builder` rather than generic brainstorming.
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
| OAuth client or delegated session | `oauth2` | `AMAZON_SELLER_CLIENT_ID`, `AMAZON_SELLER_CLIENT_SECRET` | Reuse an active delegated session or validate the client credentials with a lightweight identity call. |
| Access token or personal access token | `token` | `AMAZON_SELLER_TOKEN`, `AMAZON_SELLER_ACCESS_TOKEN` | Validate the token with the smallest read-only endpoint that proves scope and tenancy. |

## Inputs (contract)
| Input | Type | Required | Source |
| --- | --- | --- | --- |
| report scope | signal | yes | operator or upstream tool |
| metric definitions | signal | yes | operator or upstream tool |
| presentation template | signal | yes | operator or upstream tool |

## Outputs (contract)
| Output | Type | Guaranteed | Consumer |
| --- | --- | --- | --- |
| amazon-seller-report-bundle | structured-artifact | yes | next workflow or operator |
| amazon-seller-report-bundle-scorecard | scorecard | yes | reviewer |
| amazon-seller-report-bundle-handoff | handoff-packet | yes | downstream owner |

## Step-by-Step Implementation Guide
1. Define the report audience, metric definitions, and freshness threshold for Amazon Seller Report Builder, then confirm which Amazon Seller entities are in scope.
2. Validate credential reuse and ensure the query window matches the reporting cadence before any render starts.
3. Implement generates operational and kpi reports from amazon seller activity. with deterministic metric synthesis, template versioning, and publication gating.
4. Capture metric lineage, freshness timestamps, and template identifiers in the report bundle so the output remains auditable.
5. Run regression checks that cover stale data, metric drift, and template mismatch before publishing the report.
6. Publish the report bundle only after freshness and correctness gates pass, along with any interpretive notes required for downstream readers.

## Operational Runbook
### Preflight
- Validate the metric definitions, time window, and publication audience before building the report.
- Confirm the source data contract and output template version.

### Execution
- Compute metrics deterministically and preserve intermediate query identifiers.
- Render the report only after freshness and completeness checks pass.

### Recovery
- Hold publication when metrics are stale, incomplete, or fail reconciliation checks.
- Rebuild from the last known good query window after correcting the data issue.

### Handoff
- Return the report bundle, metric lineage, and publication decision.
- Call out any missing windows, excluded entities, or operator notes needed to interpret the report.

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
| `E_METRIC_DRIFT` | Metric outputs diverge from the declared definitions or previous baseline. | Hold publication and attach a metric-delta summary. |
| `E_STALE_DATA` | Input data freshness falls below the agreed threshold. | Block delivery and rerun once the source window recovers. |
| `E_TEMPLATE_MISMATCH` | The requested report template no longer matches the computed fields. | Quarantine the render and request template alignment. |

## Tool Call Implementation
- Reuse existing credentials first. Check environment variables, secure stores, and active sessions before prompting.
- Start with the smallest authenticated read or validation call that proves identity and scope.
- Preserve request, response, and approval traces in `amazon-seller-report-bundle` so downstream owners do not need to rediscover context.
- If any auth, contract, or approval gate fails, halt execution and attach remediation guidance instead of guessing.

## Credential Reuse Policy
- Reuse valid provider credentials by default and prefer tenant-scoped sessions over newly created secrets.
- Prompt for credentials only when they are missing, invalid, expired, or point at the wrong environment.
- For webhook flows, validate the signing secret against a known sample before accepting live traffic.

## Guardrails
- quality: Hold report publication when metrics drift from declared definitions or freshness thresholds. (`metric-reconcile+freshness-check`)
- reliability: Preserve query lineage and output template versions for every report build. (`lineage-capture`)
- cost: Reuse cached intermediate results when they remain inside freshness tolerance. (`query-cache-policy`)

## Acceptance Checklist
- [ ] Credential preflight and scope validation completed successfully.
- [ ] Required validation suites ran and all fail-closed gates passed.
- [ ] amazon-seller-report-bundle, scorecard, and handoff packet were produced.
- [ ] Any mutations, approvals, or rollbacks are reflected in the artifact bundle.

## Anti-Patterns
- Do not ask for new credentials before checking reusable auth context.
- Do not skip the read-only or dry-run validation step for mutating work.
- Do not proceed when approval gates, signing secrets, or rollback checkpoints are missing.
- Do not hand off partial or ambiguous provider state as complete.

## Handoff Contract
- **Produces:** `amazon-seller-report-bundle`, execution scorecard, approval trace, and next actions.
- **Consumes:** `report scope`, `metric definitions`, `presentation template`.
- **Readiness rule:** release only after auth, contract, approval, and reliability gates all pass.
- **Downstream hint:** route to `amazon-seller:report-builder` consumers with approval and credential context attached.

## Observability & Continuous Improvement
- SLO: >=99.5% successful runs per 7-day window
- Error budget: <=0.5% critical failures per 7-day window
- Alert triggers:
- credential validation failures exceed baseline
- schema or contract regressions persist for two consecutive runs
- critical posture or rollback events exceed tolerance
- Primary outcome metric: `report freshness`
- Secondary metrics: `metric correctness`, `delivery timeliness`
- Review cadence: `weekly`
