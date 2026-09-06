# Prompt 03 — Implement one approved phase

Recommended model: GPT-6 Astra

Recommended reasoning: `high` by default; use `xhigh` for schema, security, or
concurrency-heavy phases

Replace every angle-bracket placeholder before use.

```text
Implement exactly one approved Bazaar Kiosk modernization phase.

PHASE: <step number and title>
APPROVED SCOPE: <copy the approved tasks and explicit exclusions>
ACCEPTANCE CRITERIA: <copy the phase exit criteria plus user amendments>
BASE COMMIT OR BRANCH: <verified ref; do not invent it>
USER DECISIONS USED: <accepted D-IDs>

Read AGENTS.md, docs/modernization/README.md, BASELINE.md, ANALYSIS_REPORT.md,
RISK_REGISTER.md, BLUEPRINT.md, DECISIONS.md, and WORKLOG.md before editing. Inspect
the current branch, status, and diff, and preserve all user or concurrent-agent
changes. Work on a dedicated phase branch/worktree; do not edit main/develop
directly.

Treat this prompt as authorization to carry the approved phase through analysis,
implementation, focused refactoring, tests, verification, and documentation.
Infer routine implementation details and persist until every acceptance criterion
is satisfied or a concrete blocker remains. Do not stop after restating a plan and
do not request permission for reversible local work already inside scope.

Ask me only if a missing answer would change money, permissions, persisted data,
operator behavior, an external system, or an irreversible action. Before asking,
finish all independent authorized work and present the concrete alternatives and
evidence. Do not deploy, mutate production data, push/merge, rewrite history,
delete remote refs, or change GitHub settings without explicit authorization.

Establish a failing regression or characterization test before changing behavior
when a meaningful test can observe it. Keep server-side prices, totals,
authorization, state transitions, and numbering authoritative. Preserve existing
contracts unless an accepted decision explicitly changes them. Use forward-only,
data-safe migrations by default and never edit history merely to clean it up. The
only exception is blueprint step 1 after the user explicitly approves the exact
published-artifact repair and both fresh-install and already-applied paths are
designed and verified.

Use PostgreSQL for sequence, lock, constraint, migration, and concurrency claims.
Use safe DOM rendering for dynamic data. Measure performance before and after with
the same workload; do not claim optimization from code structure. Calibrate tests
to the phase: run focused checks first, then required broader checks once. Do not
add redundant tests that only duplicate implementation details.

If collaboration tools can save time or improve quality, delegate independent,
non-overlapping slices with explicit file ownership. Keep one owner for coupled
domain/schema/API changes. Do not redo delegated work, and review every returned
change before integration.

Keep the diff reviewable. Do not mix unrelated dependency upgrades, formatting,
dead-code removal, UI redesign, or architecture changes into this phase. If you
discover important out-of-scope work, add it to RISK_REGISTER.md or the work log
with evidence instead of silently expanding scope.

Before completion:

1. Run the phase-specific checks and every global gate from AGENTS.md and
   BLUEPRINT.md that applies to the changed surface and identified risk.
2. Review the diff for security, data loss, concurrency, compatibility, error
   handling, and unnecessary complexity.
3. Update relevant docs, accepted decisions, risk statuses, and WORKLOG.md.
4. Run git diff --check and report any check that could not run with the exact
   reason and risk.

In the final response, lead with the completed outcome. Then list changed files,
behavior/contract changes, migrations, tests and measured results, remaining
risks, rollback notes, and the next blueprint gate. Do not claim completion while
an acceptance criterion is unverified.
```
