# Modernization decisions

Last updated: 2026-09-06

Use this file for choices that affect business behavior, architecture, security,
data, release scope, or Git governance. Preserve superseded entries and link the
replacement decision.

## Pending decision index

| ID | Decision | Status | Needed before |
| --- | --- | --- | --- |
| D-001 | Canonical branch: keep `develop`, move to `main`, or start a separate v2 history | Pending | Remote Git cleanup and first modernization PR |
| D-002 | Exposure and identity model: event LAN, internet, named users/devices, or shared roles | Pending | Security boundary |
| D-003 | Permission matrix for order, counter, kitchen, admin, stats, and API operations | Pending | Security boundary |
| D-004 | Daily order-number reset, uniqueness, first number, timezone, and display contract | Pending | Order integrity |
| D-005 | Cash/ticket/mixed-payment, change, cancellation, refund, and underpayment rules | Pending | Order integrity |
| D-006 | Supported PostgreSQL/Supabase/runtime versions and production topology | Pending | Test foundation and release design |
| D-007 | Peak load, device/browser targets, and latency/recovery objectives | Pending | Performance and frontend phases |
| D-008 | Retention and compatibility requirements for existing orders, migrations, and URLs | Pending | Data/API changes |
| D-009 | Keep server-rendered vanilla JS or evaluate a separate frontend migration | Pending | Frontend phase |
| D-010 | Realtime tables/events, RLS policy, polling fallback, and degraded-mode contract | Pending | Content/realtime security and realtime reliability phases |
| D-011 | Permit, prohibit, or service-route Django admin edits to order items and statuses | Pending | Financial integrity phase |
| D-012 | Reconcile legacy `received_amount` with nullable split-payment fields | Pending | Financial integrity and reporting phases |
| D-013 | Default dashboard period and selected-period/timezone behavior | Pending | Reporting contract phase |

## Decision record template

### D-XXX — Title

- Status: Proposed | Accepted | Rejected | Superseded
- Date:
- Owners:
- Decision required by:
- Context and evidence:
- Options considered:
- Decision:
- Consequences and tradeoffs:
- Migration/rollback implications:
- Verification:
- Supersedes / superseded by:

## Preparation decisions

### D-P01 — Use incremental evidence-first modernization as the draft plan

- Status: Proposed
- Date: 2026-09-06
- Context and evidence: The application is small enough to improve in place, while
  its financial, authorization, and concurrency behavior lacks automated tests.
  Existing `main` and `develop` tips share identical source trees despite graph
  divergence.
- Proposed decision: Build characterization tests and production-context evidence
  before deciding on any rewrite. Keep phases small and forward-only.
- Consequence: The blueprint assumes incremental work, but step 0 may replace this
  proposal if product requirements prove that a v2 rebuild is safer.

### D-P02 — Do not alter remote Git history during preparation

- Status: Accepted
- Date: 2026-09-06
- Context and evidence: The user requested preparation for a later Astra session,
  and no content-level secret finding currently requires a rewrite.
- Decision: Clone and inspect locally; create a local preparation branch only.
  Leave remote refs, default branch, protection, tags, and history unchanged.
- Verification: `git status`, branch/ref inventory, and remote inspection before
  any later approved Git operation.
