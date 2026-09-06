# Prompt 01 — Evidence-first legacy analysis

Recommended model: GPT-6 Astra

Recommended reasoning: `xhigh`

Copy the prompt below into a new task opened on the prepared repository. This is
an analysis task: it may create or update modernization reports, but it must not
implement application fixes.

```text
Analyze this Bazaar Kiosk repository deeply enough to make its modernization plan
safe and executable. Use the repository's AGENTS.md as the operating contract and
read docs/modernization/README.md, BASELINE.md, BLUEPRINT.md, GIT_RECOVERY.md,
DECISIONS.md, and WORKLOG.md before forming conclusions.

This phase is evidence-first and analysis-only. Do not modify production code,
historical migrations, dependencies, CI, remote Git refs, GitHub settings,
infrastructure, or production data. You may run read-only commands and create
ignored local environments/test databases. You may write only these analysis
artifacts unless I explicitly expand scope:

- docs/modernization/ANALYSIS_REPORT.md
- docs/modernization/RISK_REGISTER.md
- evidence corrections to docs/modernization/BASELINE.md
- pending or proposed entries in docs/modernization/DECISIONS.md; never mark a
  decision accepted unless the user explicitly supplied that decision
- a new entry in docs/modernization/WORKLOG.md

Infer routine details from the repository and continue autonomously. Do not stop
to ask questions that are not required to gather evidence. Put unresolved product
questions into the report and proposed/pending DECISIONS.md entries rather than
guessing. Ask me directly
only if access or an ambiguity blocks all useful analysis, or if the next action
would be destructive, irreversible, external, or outside this authorized scope.

Inspect the full tracked source and relevant Git history. Establish the real
runtime and deployment assumptions from code, workflows, and configuration. Run
the existing checks in Python 3.12, then add no dependencies but use available
tools for focused static inspection. Distinguish SQLite observations from claims
that require PostgreSQL or Supabase. Do not claim production behavior that cannot
be verified locally.

Cover these independent workstreams:

1. Product and domain behavior: operator journeys, order lifecycle, table/takeout
   semantics, pricing, cash/ticket payment, cancellation, statistics, and daily
   boundaries.
2. Security: authentication, authorization by route and method, CSRF, session
   policy, default credentials, input validation, XSS/unsafe DOM rendering,
   secrets, third-party scripts, Django deployment settings, and Supabase RLS
   assumptions.
3. Data and concurrency: transaction boundaries, duplicate submission,
   idempotency, status races, total integrity, constraints, migration safety,
   PostgreSQL sequence behavior, midnight rollover, retries, and backend parity.
4. Performance and realtime: query shapes/count risks, indexes, payload sizes,
   caches and invalidation, polling, reconnect/deduplication, multi-worker behavior,
   and the concrete workload needed for measurement. Do not call code faster
   without a benchmark or plan evidence.
5. Maintainability and frontend: module responsibilities, dead/duplicate code,
   inline JavaScript/CSS, error contracts, accessibility, touch workflows,
   browser support, and test seams.
6. Delivery and operations: dependency reproducibility, CI coverage, supported
   versions, environment validation, logging/metrics, health checks, backup and
   restore, release/rollback, and incident runbooks.
7. Git: classify the graph problem, unique branch work, content-level secret risk,
   and non-destructive cleanup options. Do not change refs or repository settings.

If collaboration tools are available, delegate genuinely independent workstreams
in parallel. Give each agent a concrete question, avoid duplicated analysis, and
keep one integration owner. Messages and reports must be legible to a human.

For every finding, provide:

- stable ID and severity (Critical/High/Medium/Low);
- status (Reproduced, Code-supported, Production-dependent, or Hypothesis);
- exact file and line evidence or command/reproduction;
- affected operator/business invariant;
- realistic failure or abuse scenario;
- smallest safe remediation direction, dependencies, and regression tests;
- confidence and remaining unknowns.

Rank findings by risk and dependency, not by cosmetic code quality. Call out false
positives or corrections to the existing BASELINE.md explicitly. Include a route
and permission matrix, data-flow description, migration/numbering analysis, test
gap map, performance measurement plan, and Git recommendation.

ANALYSIS_REPORT.md must end with a decision-ready recommendation: incremental
modernization, partial replacement, or clean v2 rebuild, with evidence and
tradeoffs. RISK_REGISTER.md must be sortable by severity, dependency, owner, and
target blueprint step. Do not implement fixes in this phase.

Before completing, verify Markdown links and run git diff --check. Update WORKLOG
with commands run, unavailable checks, files written, corrected assumptions, and
the exact next prompt. In the final response, lead with the recommendation, then
summarize critical evidence, files created, checks run, and decisions needed from
me.
```
