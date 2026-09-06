# Bazaar Kiosk modernization blueprint

Status: Draft for analysis and user decisions

Last updated: 2026-09-06

## Objective

Turn the legacy event kiosk into a secure, testable, concurrency-safe,
observable, and maintainable Django service without disrupting the operator
workflow or silently changing financial and ordering rules.

Each implementation step is sized for one reviewable PR. If evidence shows that
a step cannot fit without mixing independent risks, split it before coding and
record the dependency change. A fresh agent must read `AGENTS.md`, `BASELINE.md`,
the latest analysis/risk reports, accepted decisions, and `WORKLOG.md` before
executing any step.

## Dependency graph

```text
0 Evidence and operational contract
├── G Git governance (remote actions stay separately approval-gated)
└── 1 PostgreSQL bootstrap compatibility
    └── 2 Reproducible tests and CI
        ├── 3 API authorization and CSRF
        │   ├── 4A Identity, session, and deployment security
        │   └── 4B Content and external-realtime security
        └── 5 Numbering and transaction safety
            └── 6 Order command, status, and idempotency integrity
                └── 7 Payment, admin, and historical-data integrity

{3, 4A, 4B, 5, 6, 7} -> 8 Retrieval, reporting, and cache correctness
8 -> 9 Stable application/API boundaries
{4B, 8, 9} -> 10 Measured performance and realtime reliability
{4B, 8, 9} -> 11 Frontend maintainability and operator resilience
{4A, 5, 6, 7, 10, 11} -> 12A Observability and deployment readiness
12A -> 12B Final integration and release audit
```

Steps 3 and 5 may begin in parallel after step 2 when they have separate owners.
Steps 4A and 4B may also run in parallel with disjoint files and one security
integration owner. Steps 10 and 11 may run in parallel only after step 9 freezes
the relevant API contracts.

## Conditional global gates

Apply gates to the changed surface and identified risk. Documentation-only work
does not need unrelated Django or database runs.

- Documentation: verify relative links, code-fence balance, placeholders, and
  `git diff --check`.
- Python/Django: run `python manage.py check`, migration drift, focused tests, and
  the required broader suite once.
- Schema/data/concurrency: test both a fresh and upgrade path on the supported
  PostgreSQL version. Rehearse old-application/new-schema compatibility or record
  why only a forward fix is safe.
- Security: run anonymous, wrong-role, CSRF, session, malformed-input, replay, and
  stored-content cases relevant to the change. A rollback must retain established
  protections; otherwise use a fail-closed maintenance mode.
- Frontend: run focused browser journeys on approved devices/viewports, including
  failed network and retry behavior.
- Performance: archive the same before/after workload, data size, query/latency
  evidence, and correctness checks.

Every phase updates decisions, risk status, and `WORKLOG.md`. No phase authorizes a
push, merge, tag, repository-setting change, deployment, production query, or
production-data mutation.

## Step 0 — Evidence and operational contract

- Effort: GPT-6 Astra `xhigh`
- Dependencies: none
- Primary writes: analysis/risk/decision/work-log Markdown only
- Rollback: revert report wording while preserving superseded decisions

Context: Current behavior is mostly implicit in templates and views, and there are
no tests. Security, payment, numbering, retention, realtime, and peak-load choices
cannot be inferred safely from code alone.

Tasks:

1. Run `prompts/01_ANALYZE.md` with independent security, data/concurrency,
   performance, frontend, operations, and Git workstreams where delegation helps.
2. Produce evidence-linked `ANALYSIS_REPORT.md` and `RISK_REGISTER.md`. Mark each
   item Reproduced, Code-supported, Production-dependent, or Hypothesis.
3. Capture operator journeys: login, menu/table setup, order creation, mixed
   payment, kitchen progress, cancellation, statistics, and recovery from network
   loss or duplicate submission.
4. Record production topology, supported versions, data volume, event schedule,
   device/browser fleet, performance targets, and backup/restore expectations.
5. Resolve or assign owners to pending decisions D-001 through D-013.

Minimum checks:

```bash
git status --short --branch
git diff --check
```

Exit criteria:

- Every Critical/High finding has a stable ID and code location or reproduction.
- Business invariants and acceptance examples are understandable to operators.
- Unknowns affecting money, permissions, data, or deployment have an owner.
- No production code or remote state changed.

## Step G — Git governance and archive plan

- Effort: `high`
- Dependencies: step 0 facts; may proceed beside steps 1 and 2
- Primary writes: Git analysis/runbook/decision documents; remote refs only after
  separate exact approval
- Rollback: restore repository settings and refs from recorded immutable tip SHAs

Context: `main` and `develop` have identical trees but divergent histories. Stale
remote branches remain, and GitHub CLI authentication must be repaired before
remote work.

Tasks:

1. Complete a content-level secret scan and inventory unique commits on every ref.
2. Decide the canonical branch, branch protection, required checks, and squash
   merge policy.
3. Prepare exact snapshot-tag, default-branch, protection, and stale-branch
   commands without executing them.
4. Execute only the specifically approved remote operations after backup evidence
   and collaborator impact are reviewable.

Minimum checks:

```bash
git rev-list --left-right --count origin/main...origin/develop
git diff --stat origin/main..origin/develop
git branch -a -vv
```

Exit criteria:

- Every branch is classified keep, tag/archive, or delete with evidence.
- Canonical branch and retention policy are accepted decisions.
- Any executed setting/ref change is verified and recoverable.

## Step 1 — PostgreSQL bootstrap compatibility

- Risks: BK-R005 and the bootstrap portion of BK-R003
- Decisions: D-006 and D-008
- Effort: `xhigh`
- Dependencies: step 0 production-version and data-history facts
- Primary ownership: `orders/migrations/`, disposable PostgreSQL bootstrap tooling,
  migration runbook, and the smallest CI smoke job needed for this gate
- Rollback: leave existing databases untouched; restore the recorded migration
  artifact and use a fail-closed bootstrap procedure

Context: Migration `0020` may call `setval` with zero on an empty default sequence.
If that prevents migration `0020` from completing, an appended `0021` cannot repair
a fresh install because Django never reaches it.

Tasks:

1. Reproduce the full migration chain on an empty supported PostgreSQL instance
   and capture exact server version/output.
2. Inventory production/staging databases that have already applied `0020` before
   choosing a repair.
3. Compare explicit repair paths: a reviewed narrow historical correction, a
   replacement/squashed fresh-install chain that coexists with applied history, or
   a deterministic pre-migration bootstrap. Do not silently edit history.
4. Obtain the required user decision if the safe path changes a published
   migration artifact.
5. Implement the approved fresh-install and already-applied paths and document
   their compatibility, checksums, backup, and recovery behavior.

Minimum checks:

```bash
python manage.py migrate --plan
# Run the documented disposable-PostgreSQL empty-database migration command.
python manage.py showmigrations orders
```

Exit criteria:

- Empty PostgreSQL reaches the latest migration from a clean database.
- Already-applied databases have a verified no-op or forward-safe path.
- No command can accidentally target an unverified or production database.
- The first sequence value and empty/non-empty initialization match D-004 or are
  explicitly deferred to step 5 without blocking bootstrap.

## Step 2 — Reproducible test and CI foundation

- Risk: BK-R004
- Decisions: D-006, D-007, and D-008
- Effort: `high`
- Dependencies: step 1 green PostgreSQL bootstrap
- Primary ownership: dependency/tooling files, `orders/tests/`, test fixtures, and
  `.github/workflows/ci.yml`
- Rollback: remove additive tooling/config while retaining baseline evidence and
  migration-bootstrap protection

Tasks:

1. Choose and document locking, supported Python/Django/PostgreSQL versions, and
   one clean-checkout setup path.
2. Add fixtures/factories for tables, menus, roles, orders, payment variants,
   statuses, dates, and legacy rows.
3. Characterize critical current API and operator behavior before refactoring.
4. Run empty and upgrade migrations in disposable PostgreSQL CI.
5. Add focused static/format checks and coverage reporting. Gate critical behavior
   instead of selecting a vanity global percentage.
6. Prove CI fails for an intentional regression, then remove the regression.

Minimum checks:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
# Run the documented PostgreSQL migration/integration CI command locally or in CI.
```

Exit criteria:

- A clean checkout has one reproducible setup and test command.
- Critical legacy flows have meaningful characterization tests.
- SQLite smoke and PostgreSQL migration/integration checks pass.
- CI does not depend on developer-global packages.

## Step 3 — API authorization and CSRF

- Risk: BK-R001
- Decision: D-003; use the current identity mechanism only as a temporary input to
  this access-control step
- Effort: `high`
- Dependencies: step 2
- Primary ownership: route permission policy, API decorators/middleware, frontend
  CSRF request paths, and `orders/tests/test_permissions.py`
- Rollback: retain authorization and CSRF; if the application must roll back, use
  compatible guards or fail closed

Tasks:

1. Define a route-and-method permission matrix for page and JSON operations.
2. Enforce authentication and role authorization on the server for every endpoint.
3. Remove mutation CSRF exemptions and make legitimate clients send valid tokens.
4. Standardize denied responses without leaking route or role details.
5. Add anonymous, wrong-role, missing/invalid-CSRF, method, and stale-session tests.

Minimum checks:

```bash
python manage.py test orders.tests.test_permissions
python manage.py check
python manage.py makemigrations --check --dry-run
```

Exit criteria:

- Direct API calls cannot bypass page restrictions.
- Every route/method has an executable permission expectation.
- Existing authorized operator flows still complete.
- A rollback cannot restore anonymous or CSRF-exempt mutation.

## Step 4A — Identity, session, and deployment security

- Risk: BK-R002
- Decisions: D-002 and D-003
- Effort: `xhigh` for identity design, `high` for implementation
- Dependencies: steps 2 and 3
- Primary ownership: `orders/views/auth.py`, login UI, Django security settings,
  environment validation, and `orders/tests/test_auth.py`
- Rollback: preserve the established access boundary or enter fail-closed
  maintenance mode; never restore known shared production defaults

Tasks:

1. Replace committed operational defaults with fail-safe configuration and a
   documented local-only path.
2. Implement the accepted named-user, device, or shared-role identity model.
3. Add login throttling/lockout, session rotation/expiry, logout, cookie, proxy,
   HTTPS, host, and origin behavior appropriate to the deployment.
4. Ensure logs and errors never expose PINs, credentials, or session material.
5. Add brute-force, fixation, expiry, misconfiguration, and deployment-check tests.

Minimum checks:

```bash
python manage.py test orders.tests.test_auth
python manage.py check
python manage.py check --deploy
```

Exit criteria:

- Production-capable startup fails safely without required credentials/settings.
- The accepted identity/session policy has positive and negative tests.
- Deployment warnings are resolved or explicitly documented by topology.

## Step 4B — Content and external-realtime security

- Risk: BK-R011; external portion of BK-R001
- Decision: the security portion of D-010 must be resolved here
- Effort: `high`
- Dependencies: steps 2 and 3; may run beside 4A with disjoint ownership
- Primary ownership: dynamic DOM rendering, content escaping, CSP/third-party
  scripts, Supabase client exposure/RLS evidence, and focused browser/security tests
- Rollback: retain output escaping, CSP-equivalent protection, and RLS; otherwise
  disable the affected UI/realtime path and fail closed

Tasks:

1. Trace every database/API string into HTML, attribute, URL, and JavaScript
   contexts; reproduce stored-content cases before fixing them.
2. Replace unsafe `innerHTML` and inline handler interpolation on critical paths
   with safe DOM construction/event delegation.
3. Review CDN script pinning/integrity and define the accepted content-security
   policy.
4. Verify Supabase tables, events, grants, Row Level Security, anonymous-key scope,
   and data visibility. Treat unavailable external policy as Not verified.
5. Add malicious menu/name/note strings and wrong-client realtime access cases.

Minimum checks:

```bash
python manage.py test orders.tests.test_content_security
# Run the documented focused browser security journey.
```

Exit criteria:

- Stored strings render as text in every critical page/context.
- Realtime anonymous access is explicitly allowed by verified RLS or disabled.
- Removing the security change cannot be a normal rollback path.

## Step 5 — Numbering and transaction safety

- Risk: BK-R003; step 1 has already resolved BK-R005 bootstrap
- Decisions: D-004 and D-006
- Effort: `xhigh`
- Dependencies: steps 1 and 2
- Primary ownership: numbering service, forward-only schema changes if required,
  and PostgreSQL concurrency/midnight tests
- Rollback: preserve uniqueness and data readability; verify old-application/new-
  schema behavior or define a forward-fix-only recovery

Tasks:

1. Turn D-004 into executable examples for first value, daily reset, timezone,
   uniqueness, gaps, and repeats across days.
2. Reproduce current PostgreSQL behavior for empty/non-empty state, midnight,
   unique conflict, transaction failure, worker concurrency, and retry.
3. Implement one backend-consistent allocation contract or document deliberately
   different local-only behavior.
4. Keep retries transaction-safe and bounded; do not catch a database error and
   continue inside a broken transaction.
5. Add forward-only migrations and compatibility/rollback evidence when needed.

Minimum checks:

```bash
python manage.py test orders.tests.test_numbering
# Repeat the numbering suite with the documented PostgreSQL DATABASE_URL.
python manage.py makemigrations --check --dry-run
```

Exit criteria:

- Concurrent PostgreSQL tests prove the accepted uniqueness/reset contract.
- Failures cannot leave a partially numbered order or poison an unnoticed
  transaction.
- Fresh and upgraded databases produce the same approved semantics.

## Step 6 — Order command, status, and idempotency integrity

- Risks: domain portions of BK-R003 and the unregistered duplicate-submit/status
  hypotheses from the analysis report
- Decisions: D-003, D-004, D-007, and D-008
- Effort: `xhigh`
- Dependencies: steps 2 and 5
- Primary ownership: order command services, status-transition policy,
  idempotency/retry mechanism, endpoint adapters, and focused integration tests
- Rollback: preserve idempotency keys/state compatibility; prove the old app can
  read new rows or use a forward fix

Tasks:

1. Define allowed status transitions, cancellation behavior, item progress, and
   retry/double-tap outcomes.
2. Add a client-request identity/idempotency contract with retention and conflict
   behavior.
3. Move create/progress/status writes into atomic command services while keeping
   endpoint compatibility.
4. Test simultaneous progress updates, cancellation races, duplicate create,
   timeout/retry, and partial-failure rollback.
5. Add structured domain errors that adapters can map consistently in step 9.

Minimum checks:

```bash
python manage.py test orders.tests.test_order_commands orders.tests.test_status
# Repeat concurrency-sensitive cases on PostgreSQL.
```

Exit criteria:

- A retry or double tap cannot silently create the same order twice.
- Invalid/racing transitions fail predictably without partial state.
- Current authorized operator flows remain compatible.

## Step 7 — Payment, admin, and historical-data integrity

- Risks: BK-R007 and BK-R008
- Decisions: D-005, D-008, D-011, and D-012
- Effort: `xhigh`
- Dependencies: steps 2 and 6
- Primary ownership: payment/total service and constraints, Django admin write
  policy, legacy-data reconciliation migration/query, and aggregate tests
- Rollback: preserve original values and audit counts; rehearse old-app/new-schema
  behavior before any backfill and define forward recovery for new writes

Tasks:

1. Encode accepted cash, ticket, mixed, under/overpayment, change, cancellation,
   and refund rules with server-authoritative integer KRW totals.
2. Reject malformed, negative, overflow, inactive-menu, and inconsistent payment
   inputs with stable errors.
3. Decide whether admin order-item edits are prohibited or routed through the same
   domain service. Cover add/edit/delete and status operations.
4. Reconcile legacy `received_amount` with nullable split fields using an approved,
   reversible/auditable path. Record row counts and before/after financial sums.
5. Add database constraints only after proving existing rows satisfy them.

Minimum checks:

```bash
python manage.py test orders.tests.test_payments orders.tests.test_admin_integrity
python manage.py test orders.tests.test_legacy_reconciliation
# Run data and constraint checks on a sanitized PostgreSQL copy.
```

Exit criteria:

- Item sums, stored totals, payment splits, change, and reports reconcile.
- Admin cannot bypass financial invariants.
- Historical-data handling has accepted before/after evidence and recovery steps.

## Step 8 — Retrieval, reporting, and cache correctness

- Risks: BK-R006, BK-R009, and BK-R010; reporting use of BK-R007
- Decisions: D-003, D-007, D-010, D-012, and D-013
- Effort: `high`
- Dependencies: steps 3, 4A, 4B, 5, 6, and 7
- Primary ownership: selectors/query parameters, dashboard period/payment queries,
  kitchen retrieval contract, cache invalidation/removal, and endpoint tests
- Rollback: preserve secure endpoint guards and complete pending-order visibility;
  do not restore a truncated or stale correctness path

Tasks:

1. Define default and selected reporting periods, inclusive boundaries, invalid
   input errors, and `Asia/Seoul` behavior. Remove the hard-coded event date.
2. Make historical and current payment aggregates follow D-012 and reconcile with
   order/item totals.
3. Move kitchen mode/role filtering to an authorized server-side query. Define
   pagination or a complete pending-work contract so the newest 80 mixed orders
   cannot hide older work.
4. Test more than 80 mixed pending orders across initial load, role views, polling,
   realtime reconnect, cancellation, and completion.
5. Replace mutable process-local ORM caching or add correct invalidation and
   multi-worker semantics; test table/menu admin changes.

Minimum checks:

```bash
python manage.py test orders.tests.test_reporting orders.tests.test_kitchen_queries
python manage.py test orders.tests.test_cache_behavior
```

Exit criteria:

- Dashboard periods and financial aggregates match accepted examples.
- Every role sees all and only its pending work regardless of backlog size.
- Cache behavior cannot use deactivated/stale mutable objects across workers.

## Step 9 — Stable application and API boundaries

- Risks: maintainability and inconsistent-error hypotheses from `BASELINE.md`
- Decisions: D-003 and D-008
- Effort: `high`
- Dependencies: step 8 contract tests
- Primary ownership: API adapters, validators, serializers, selectors, domain
  service boundaries, error format, and compatibility tests
- Rollback: preserve secure compatibility adapters while reverting internal
  extraction; no schema changes unless split into a separate phase

Tasks:

1. Freeze and document current/target request, response, pagination, and error
   contracts.
2. Split transport validation, selectors, serializers, and transactional commands
   into cohesive modules without behavior drift.
3. Remove broad exception handling and unreachable/dead paths only with focused
   reference and regression evidence.
4. Keep URLs or version approved incompatible changes explicitly.
5. Measure query counts before and after to prevent a refactor regression, without
   calling this phase a performance optimization.

Minimum checks:

```bash
python manage.py test orders.tests
python manage.py check
python manage.py makemigrations --check --dry-run
```

Exit criteria:

- Executable tests define each endpoint and domain boundary.
- Views coordinate rather than own financial/state logic.
- Error and pagination behavior is deterministic and documented.
- The full suite passes with no unexplained query regression.

## Step 10 — Measured performance and realtime reliability

- Risks: performance/realtime hypotheses and D-010 failure modes
- Decisions: D-006, D-007, and D-010
- Effort: `xhigh` for profiling/concurrency, `high` for scoped fixes
- Dependencies: steps 4B, 8, and 9
- Primary ownership: benchmark/load scenarios, query/index changes, payload and
  polling behavior, realtime deduplication/order/reconnect, and regression budgets
- Rollback: disable a new optimization without losing secure complete retrieval;
  retain a bounded, measured fallback

Tasks:

1. Define realistic device, order, menu, history, burst, and latency/SLO workloads.
2. Capture endpoint latency, query counts/plans, lock waits, payloads, polling
   volume, browser work, and degraded behavior before changing code.
3. Fix only measured bottlenecks and attach before/after evidence using identical
   data and workloads.
4. Verify realtime event coverage, authorization, ordering, deduplication,
   reconnect, stale events, disconnects, and bounded polling fallback.
5. Add PostgreSQL execution-plan evidence for every index change and regression
   budgets for critical workloads.

Minimum checks:

```bash
# Run the versioned benchmark/load command created by this phase twice: baseline
# and candidate, against the same disposable PostgreSQL dataset.
python manage.py test orders.tests.test_realtime orders.tests.test_performance_contracts
```

Exit criteria:

- Each optimization has repeatable improvement evidence and unchanged correctness.
- Target concurrency and degraded realtime/network states pass.
- The fallback cannot create unbounded requests or hide pending work.

## Step 11 — Frontend maintainability and operator resilience

- Risks: large inline-template/duplication/accessibility hypotheses; BK-R011 must
  already be closed by step 4B
- Decisions: D-007, D-009, and D-010
- Effort: `high`
- Dependencies: steps 4B, 8, and 9; may run beside step 10
- Primary ownership: extracted frontend modules/styles, event wiring, accessibility,
  network/retry UX, dead-template evidence, and critical browser journeys
- Rollback: retain secure rendering and request guards; if an old page cannot meet
  those controls, disable it rather than expose it behind a switch

Tasks:

1. Preserve critical browser journeys while extracting duplicated inline code in
   small slices.
2. Replace remaining inline handlers and make loading/error/retry/double-submit
   states explicit.
3. Improve semantic controls, focus, keyboard/touch behavior, contrast, viewport
   behavior, and assistive labels for approved devices.
4. Remove dead templates/assets only after route, history, reference, and operator
   confirmation.
5. Evaluate a frontend framework only in a separate decision/plan; do not combine
   a framework migration with this phase.

Minimum checks:

```bash
python manage.py test orders.tests
# Run the documented ordering, kitchen, counter, login, offline, and retry browser journeys.
```

Exit criteria:

- Approved operator journeys pass on target devices/viewports.
- Failed network/retry states are clear and cannot duplicate orders.
- Accessibility criteria pass automated checks and a manual touch workflow review.
- No rollback path reintroduces unsafe rendering.

## Step 12A — Observability and deployment readiness

- Risks: operations/deployment hypotheses from `BASELINE.md`
- Decisions: D-002, D-006, D-007, D-008, and D-010
- Effort: `high`
- Dependencies: steps 4A, 5, 6, 7, 10, and 11
- Primary ownership: logging/metrics/alerts, health/readiness, environment checks,
  deployment/migration order, backups, restore and rollback runbooks
- Rollback: a tested application/database rollback or explicit forward-fix plan;
  preserve all established security controls

Tasks:

1. Add structured logs and correlation/idempotency identifiers without logging
   credentials, PINs, sensitive notes, or payment data unnecessarily.
2. Define health/readiness, metrics, actionable alerts, and expected degraded mode.
3. Validate static files, HTTPS/proxy, database pooling, environment, migration
   order, and startup failure behavior.
4. Rehearse backup, restore, application rollback against the migrated schema, and
   recovery from writes made by the new version using sanitized data.
5. Produce operator incident and release runbooks.

Minimum checks:

```bash
python manage.py check
python manage.py check --deploy
python manage.py test
# Run the documented production-like deploy, backup, restore, and rollback rehearsal.
```

Exit criteria:

- Logs/metrics reveal critical failures without sensitive-data leakage.
- Backup restore and rollback/forward recovery are rehearsed, timed, and documented.
- Deployment starts safely only with complete validated configuration.

## Step 12B — Final integration and release audit

- Effort: GPT-6 Astra `xhigh`
- Dependencies: step 12A and every accepted release-scope phase
- Primary writes: `FINAL_AUDIT.md`, risk/decision/work-log updates, and only tiny
  already-decided regression fixes; larger fixes create a new phase
- Rollback: no release action occurs in this audit; a NO-GO preserves current state

Tasks:

1. Run `prompts/04_FINAL_AUDIT.md` with independent security, PostgreSQL/data,
   performance/realtime, frontend/operator, and operations reviewers.
2. Run every required suite in its documented environment and classify each gate
   Pass, Fail, Not run, or Accepted risk.
3. Trace every Critical/High risk to closed evidence or explicit user acceptance.
4. Produce GO, NO-GO, or CONDITIONAL NO-GO. Only the user may accept a release
   risk or authorize deployment.

Minimum checks:

```bash
git diff --check
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
# Run documented PostgreSQL, browser, security, load, restore, and rollback suites.
```

Exit criteria:

- No required environment or critical invariant is silently unverified.
- Release blockers are reproducible and assigned.
- GO is supported by archived evidence and a tested rollback/recovery plan.

## Risk-to-phase ownership

| Risk | Owning step | Required closure evidence |
| --- | --- | --- |
| BK-R001 | 3; external boundary in 4B | Route matrix and negative access/CSRF tests |
| BK-R002 | 4A | Fail-safe configuration plus identity/session abuse tests |
| BK-R003 | 5 | PostgreSQL midnight/contention/retry proof |
| BK-R004 | 2 | Reproducible meaningful tests enforced by CI |
| BK-R005 | 1 | Empty and already-applied PostgreSQL migration paths |
| BK-R006 | 8 | Default/selected period and timezone tests |
| BK-R007 | 7; reporting use in 8 | Legacy row reconciliation and aggregate before/after proof |
| BK-R008 | 7 | Admin add/edit/delete policy and invariant tests |
| BK-R009 | 8; degraded behavior in 10 | More-than-80 mixed backlog tests across load/poll/reconnect |
| BK-R010 | 8 | Mutable update and multi-worker cache behavior tests |
| BK-R011 | 4B | Stored-content browser tests and context audit |

## Anti-patterns to reject

- A big-bang rewrite before behavior and load are characterized.
- An appended migration offered as a fix for an earlier migration that blocks the
  chain before the new migration can run.
- “Performance optimization” without a repeatable before/after measurement.
- Editing or squashing applied migrations without an explicit dual-path plan.
- Trusting page navigation, hidden buttons, or a Supabase anonymous key as
  authorization.
- Treating SQLite success as proof of PostgreSQL sequence/lock behavior.
- Caching mutable ORM objects without invalidation and multi-worker semantics.
- Securing one write path while API, admin, migration, or background paths bypass
  the invariant.
- A rollback that restores unauthenticated mutation, CSRF exemptions, unsafe
  rendering, or incompatible old-application/new-schema behavior.
- Combining dependency, architecture, UI, data, and Git-history changes in one PR.
- Raising test counts with assertions that merely mirror implementation.

## Plan mutation protocol

When evidence changes the plan, add a dated entry to `DECISIONS.md` and
`WORKLOG.md`. State which step is split, inserted, reordered, skipped, or
abandoned; why; which risk owners and dependencies change; and how completed work
remains valid. Never silently expand an in-progress phase. Re-run the adversarial
blueprint review when a mutation changes the critical dependency path.
