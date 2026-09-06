# Prompt 02 — Adversarial blueprint review

Recommended model: GPT-6 Astra

Recommended reasoning: `xhigh`

Run this only after `ANALYSIS_REPORT.md`, `RISK_REGISTER.md`, and the important
business decisions exist.

```text
Review and revise the Bazaar Kiosk modernization blueprint as an adversarial
architect. Read AGENTS.md and every current file under docs/modernization/,
including ANALYSIS_REPORT.md, RISK_REGISTER.md, accepted decisions, and WORKLOG.md.

The goal is a construction plan that a fresh GPT-6 Astra task can execute one
phase at a time without hidden context. This is a planning/documentation task.
Do not implement application code, alter dependencies or migrations, change
remote Git/GitHub state, deploy, or touch production data.

You are authorized to update:

- docs/modernization/BLUEPRINT.md
- docs/modernization/DECISIONS.md when recording reviewed proposals or accepted
  choices already supplied by the user
- docs/modernization/WORKLOG.md
- docs/modernization/prompts/03_IMPLEMENT_PHASE.md only if its generic execution
  contract must change to match the reviewed blueprint

First test the current plan against the evidence. Look for missing dependencies,
phases that are too large for one PR, overlapping write scopes, circular ordering,
unverifiable exit criteria, unsafe migration or rollback assumptions, accidental
business-rule choices, and work that should be deferred or removed. Explicitly
challenge whether incremental modernization is still safer than a partial or full
rewrite.

For every phase, require a self-contained context brief, approved scope, expected
files or ownership boundary, prerequisites, task list, acceptance criteria,
verification commands/environments, migration and rollback strategy, observability
impact, security impact, and handoff artifacts. Map every Critical/High risk to one
owner phase and ensure no risk disappears between documents.

Detect safe parallelism, but do not split tightly coupled schema, transaction, and
API-contract changes across competing owners. Identify the integration owner for
parallel work. Keep remote Git cleanup as a separate approval-gated operation.

Reject big-bang rewrites, unmeasured optimization, SQLite-only database proof,
test-count vanity, silent API changes, and vague exits such as “works correctly.”
Forward-only migrations are the default. A step-1 correction to a published
migration artifact is eligible only when the user explicitly approves the exact
repair and the plan proves both fresh-install and already-applied paths; reject any
other edit to applied migration history. Prefer the smallest phase sequence that
reaches the documented target safely.

If a user decision is still missing, complete all plan sections that do not depend
on it and mark the exact gate. Ask only for decisions that would materially change
the plan; do not ask the user to approve routine planning details.

Before completing, cross-check risk-to-phase coverage, validate all Markdown
links, and run git diff --check. Update WORKLOG. In the final response, lead with
whether the blueprint is executable, list material changes, show the critical
dependency path and parallel phases, and ask for only the next decision or phase
approval that is truly required.
```
