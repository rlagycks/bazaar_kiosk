# Prompt 04 — Final integration and release-readiness audit

Recommended model: GPT-6 Astra

Recommended reasoning: `xhigh`

```text
Perform the final adversarial integration and release-readiness audit for the
Bazaar Kiosk modernization. Read AGENTS.md and all current modernization reports,
decisions, risks, blueprint phases, work-log entries, and release/runbook files.
Compare the final branch with the approved canonical base and inspect every
material change, not just the latest commit.

This is an audit-first task. Do not deploy, merge, push, change GitHub settings,
rewrite history, rotate credentials, or access production data. Do not launch a
broad cleanup. You may fix a small, clearly in-scope defect only when its intended
behavior is already covered by an accepted decision and regression test; otherwise
record it as a release blocker or follow-up with evidence.

Audit these gates:

- every accepted business invariant and operator-critical journey;
- route-level authentication, authorization, CSRF, session, input, XSS, secret,
  dependency, third-party script, and Supabase RLS assumptions;
- payment/total/status/idempotency correctness and failure responses;
- fresh and upgraded PostgreSQL migrations, constraints, daily numbering,
  contention, retries, rollback/mitigation, backup, and restore;
- API compatibility, error contract, frontend rendering, accessibility, target
  devices, offline/reconnect, duplicate-submit, and realtime/polling behavior;
- reproducible dependencies, CI, static checks, focused/unit/integration/browser
  tests, coverage of critical paths, and absence of meaningless tests;
- measured query/latency/load budgets using the documented production-like
  workload;
- structured logs, sensitive-data redaction, health/readiness, metrics, alerts,
  deployment order, rollback, and operator runbook;
- risk-to-phase closure, decision traceability, Git diff quality, and absence of
  accidental unrelated changes.

Use independent reviewers in parallel when collaboration tools are available:
security, PostgreSQL/data integrity, performance/realtime, frontend/operator UX,
and release/operations. Give each a disjoint audit question, not a duplicate code
review. Integrate their evidence and resolve contradictory findings.

Run the documented checks in the required environments. For every failure, report
the exact command/workload, output summary, affected invariant, severity,
reproducibility, and smallest safe correction. Clearly distinguish a failed check
from one that was not run. Do not treat SQLite as proof of PostgreSQL behavior or
an unavailable production dependency as passing.

Create or update docs/modernization/FINAL_AUDIT.md and RISK_REGISTER.md, then add a
WORKLOG entry. FINAL_AUDIT.md must contain a traceable go/no-go table with four
possible states per gate: Pass, Fail, Not run, or Accepted risk. Only the user may
accept a release risk.

Before completing, run git diff --check and verify documentation links. In the
final response, lead with GO, NO-GO, or CONDITIONAL NO-GO; list release blockers
in severity order, summarize passed evidence, identify checks not run, and state
the smallest next action. Do not declare GO while a critical invariant or required
environment remains unverified.
```
