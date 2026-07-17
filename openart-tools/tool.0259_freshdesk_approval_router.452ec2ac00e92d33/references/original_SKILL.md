---
name: freshdesk-approval-router
description: Use when tasks require freshdesk approval router with credential-aware preflight, deterministic execution, validation gates, and handoff-ready artifacts.
---

# Freshdesk Approval Router

## Quick Reference
| Field | Value |
| --- | --- |
| Skill ID | `259` |
| Provider | `Freshdesk` |
| Operation | `Approval Router` |
| Domain | `External SaaS integrations` |
| Runtime archetype | `approval-routing-engine` |
| Core method | `policy-based approver selection` |
| Primary artifact | `freshdesk-approval-decision-packet` |
| Routing tag | `freshdesk:approval-router` |
| Mutating | `yes` |
| Release cycles | `3` |

## Why This Skill Exists
We need this skill because Freshdesk workflows degrade when auth, schema, and side-effect handling drift when integrations are run ad hoc. This specific skill turns Freshdesk Approval Router into a deterministic, auth-checked workflow for routes freshdesk-driven decisions to the right approvers..

## Trigger Checklist
- [ ] The task explicitly requires `Freshdesk Approval Router` rather than generic brainstorming.
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
| decision payload | signal | yes | operator or upstream tool |
| routing policy | signal | yes | operator or upstream tool |
| approver roster | signal | yes | operator or upstream tool |

## Outputs (contract)
| Output | Type | Guaranteed | Consumer |
| --- | --- | --- | --- |
| freshdesk-approval-decision-packet | structured-artifact | yes | next workflow or operator |
| freshdesk-approval-decision-packet-scorecard | scorecard | yes | reviewer |
| freshdesk-approval-decision-packet-handoff | handoff-packet | yes | downstream owner |

## Step-by-Step Implementation Guide
1. Define the decision classes, approver roster, and escalation hierarchy for Freshdesk Approval Router, then capture the manual fallback path for Freshdesk.
2. Validate credential reuse and confirm that the routing policy and approver roster versions are both current before any decisions are routed.
3. Implement routes freshdesk-driven decisions to the right approvers. so the routing decision always includes policy clauses, approver evidence, and escalation context.
4. Persist the selected reviewer, fallback route, and audit trail so every approval request remains explainable.
5. Run simulation and regression suites that cover missing policy clauses, owner ambiguity, and stale roster entries.
6. Publish an approval-decision packet with the selected owner, escalation state, and policy gaps that require administrative follow-up.

## Operational Runbook
### Preflight
- Validate the policy set, approver roster, and escalation rules before routing any decision.
- Confirm the fallback manual review queue for unresolved or ambiguous cases.

### Execution
- Resolve routing policy deterministically and preserve the policy clauses that drove the selection.
- Escalate ambiguous ownership instead of guessing an approver.

### Recovery
- Pause automatic routing when the policy set or roster becomes inconsistent.
- Revert to the manual review queue until the policy mismatch is corrected.

### Handoff
- Return the selected approver, matched policy clauses, and escalation path.
- Document whether the request is approved, pending, or forced into manual review.

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
| `E_POLICY_GAP` | No policy clause matches the decision payload. | Send the request to manual review and record the missing policy gap. |
| `E_OWNER_AMBIGUITY` | Multiple approvers match and policy cannot disambiguate safely. | Escalate to the fallback review queue instead of auto-selecting. |
| `E_ROSTER_STALE` | The selected approver is unavailable or no longer authorized. | Block automated routing and require roster refresh. |

## Tool Call Implementation
- Reuse existing credentials first. Check environment variables, secure stores, and active sessions before prompting.
- Start with the smallest authenticated read or validation call that proves identity and scope.
- Preserve request, response, and approval traces in `freshdesk-approval-decision-packet` so downstream owners do not need to rediscover context.
- If any auth, contract, or approval gate fails, halt execution and attach remediation guidance instead of guessing.

## Credential Reuse Policy
- Reuse valid provider credentials by default and prefer tenant-scoped sessions over newly created secrets.
- Prompt for credentials only when they are missing, invalid, expired, or point at the wrong environment.
- For webhook flows, validate the signing secret against a known sample before accepting live traffic.

## Guardrails
- safety: Route ambiguous or unmatched requests to manual review instead of inferring an owner. (`manual-review-fallback`)
- compliance: Preserve the exact policy clauses and roster version used for every routing decision. (`policy-audit-trail`)
- reliability: Pause automatic routing when roster health or policy completeness degrades. (`roster-health-check`)

## Acceptance Checklist
- [ ] Credential preflight and scope validation completed successfully.
- [ ] Required validation suites ran and all fail-closed gates passed.
- [ ] freshdesk-approval-decision-packet, scorecard, and handoff packet were produced.
- [ ] Any mutations, approvals, or rollbacks are reflected in the artifact bundle.

## Anti-Patterns
- Do not ask for new credentials before checking reusable auth context.
- Do not skip the read-only or dry-run validation step for mutating work.
- Do not proceed when approval gates, signing secrets, or rollback checkpoints are missing.
- Do not hand off partial or ambiguous provider state as complete.

## Handoff Contract
- **Produces:** `freshdesk-approval-decision-packet`, execution scorecard, approval trace, and next actions.
- **Consumes:** `decision payload`, `routing policy`, `approver roster`.
- **Readiness rule:** release only after auth, contract, approval, and reliability gates all pass.
- **Downstream hint:** route to `freshdesk:approval-router` consumers with approval and credential context attached.

## Observability & Continuous Improvement
- SLO: >=99.9% successful runs per 7-day window
- Error budget: <=0.1% critical failures per 7-day window
- Alert triggers:
- credential validation failures exceed baseline
- schema or contract regressions persist for two consecutive runs
- critical posture or rollback events exceed tolerance
- Primary outcome metric: `routing accuracy`
- Secondary metrics: `time to decision`, `escalation coverage`
- Review cadence: `daily`
