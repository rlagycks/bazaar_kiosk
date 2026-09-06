# Legacy baseline

Last verified: 2026-09-06

Snapshot: `origin/develop` at `93a841a` (tree `de8b3f3`)

This is an initial evidence-backed snapshot, not a complete audit. Findings marked
as hypotheses must be reproduced in a dedicated analysis session before a broad
fix is designed.

## Repository profile

| Area | Verified state |
| --- | --- |
| Stack | Django server-rendered app, vanilla JavaScript/CSS, PostgreSQL production path, SQLite fallback, optional Supabase Realtime |
| Size | 55 tracked files, about 4,753 lines including migrations and templates |
| Main app | `orders` with models, services, page views, JSON endpoints, admin, inline frontend code |
| Runtime declaration | `Django>=5.0,<5.3`, `psycopg[binary]>=3.1`, WhiteNoise, Gunicorn; no lock file |
| CI | Python 3.12, dependency install, `manage.py check`, and migration-drift check |
| Tests | No test modules; Django reports `Found 0 test(s)` |
| Documentation | No README or agent/runbook documents before this preparation branch |

The largest maintainability concentrations are `orders/views/api.py` (594 lines),
`orders/templates/orders/order.html` (535 lines), and
`orders/templates/orders/kitchen_supervisor.html` (486 lines). Important behavior
is split between Django views and large inline scripts.

## Reproduced local baseline

The following was run in a fresh Python 3.12 virtual environment:

| Check | Result |
| --- | --- |
| Dependency installation | Passed; resolved Python 3.12.11, Django 5.2.17, psycopg 3.3.5 |
| `python manage.py check` | Passed with zero issues |
| `makemigrations --check --dry-run` | Passed; no model drift |
| Fresh SQLite migration chain | All Django and `orders` migrations through `0020` passed |
| `python manage.py test` | Command passed but ran zero tests |
| `python manage.py check --deploy` | Three warnings: HSTS unset, SSL redirect unset, deliberately weak diagnostic secret |
| PostgreSQL migration/concurrency check | Not run; still required |
| Browser/operator-flow check | Not run; still required |

The system Python is 3.9.6 and had Django 4.2.20, so using an unqualified
`python3` does not reproduce CI or the declared requirements.

## Git condition

- The remote default is `develop`; the local clone initially checked out
  `develop`.
- The repository contains 68 commits, including 16 merge commits, and 10 named
  remote branches plus the symbolic `origin/HEAD` reference.
- `origin/main` and `origin/develop` point to different histories. The symmetric
  difference is 7 commits on the `main` side and 19 on the `develop` side.
- Despite that divergence, both tips have the exact same tree object
  (`de8b3f3712ea25209e2d9e94d044002b3e9e7bff`). The current source content is
  therefore identical while the graph is not.
- No secret-like filename or database/CSV artifact was found among historical
  tracked paths by the initial filename scan. This is not a content-level secret
  audit.
- GitHub CLI authentication for the configured account was invalid. Public clone
  access succeeded.

See [GIT_RECOVERY.md](GIT_RECOVERY.md) before changing any remote refs.

## Initial risk inventory

### Critical candidates

| ID | Finding | Status | Evidence | Why it matters | Next proof |
| --- | --- | --- | --- | --- | --- |
| BK-R001 | Mutating JSON endpoints bypass CSRF and have no role decorator | Code-supported | `orders/views/api.py:7`, `:146`, `:346`, `:379`; only page views use `require_roles` | A page login does not protect direct order creation or status/progress mutation | Test anonymous, wrong-role, and CSRF requests for every endpoint |
| BK-R002 | Role PINs have committed defaults and direct string comparison | Code-supported | `bazaar_kiosk/settings.py:115-130`, `orders/views/auth.py:24-49` | Default credentials, no throttling, and coarse shared roles are unsafe for an exposed service | Confirm deployment exposure and approved auth model |
| BK-R003 | PostgreSQL order numbering does not visibly implement the documented daily reset | Code-supported | `orders/services/numbering.py:12-43` uses a persistent sequence while the SQLite counter keys by date | Numbers and semantics can diverge by backend; conflict retry inside an outer transaction also needs proof | PostgreSQL tests for midnight rollover, retries, and concurrent creation |

### High candidates

| ID | Finding | Status | Evidence | Why it matters | Next proof |
| --- | --- | --- | --- | --- | --- |
| BK-R004 | There are no automated tests | Reproduced | CI and local `manage.py test` | Refactoring payment, status, and numbering has no safety net | Build a behavior-characterization suite before refactoring |
| BK-R005 | Fresh PostgreSQL sequence migration may be unsafe when no prior order exists | Code-supported | `orders/migrations/0020_create_floor_sequences.py:9-16` calls `setval` with a possible zero and marks it called | A new PostgreSQL environment may fail before a later corrective migration can run | Apply the full chain to an empty supported PostgreSQL version before choosing a repair path |
| BK-R006 | Dashboard period is hard-coded to 2025-10-18 | Code-supported | `orders/views/api.py:98-105` | Query parameters are ignored and the dashboard becomes stale | Endpoint regression tests for approved default and selected periods |
| BK-R007 | Historical payment totals may omit orders created before split fields existed | Code-supported | Migration `0017` adds nullable split columns without a backfill; `orders/views/api.py:508-517` aggregates only those columns | Revenue can remain correct while cash/ticket reconciliation is understated | Compare legacy `received_amount` rows with approved backfill/query semantics and aggregate totals |
| BK-R008 | Django admin can edit item quantity/unit price while the stored order total is read-only | Code-supported | `orders/admin.py:45-50`, `:70-76`; no inline save/delete total recalculation is present | Admin edits can leave item sums and financial totals inconsistent | Test edit/add/delete paths and decide whether to prohibit or service-route operational edits |
| BK-R009 | Kitchen role boards fetch the newest 80 mixed orders before filtering by role in the browser | Code-supported | `kitchen_supervisor.html:94`, `:139-147`; `orders/views/api.py:160-170` | A large newer backlog for one mode can hide an older pending order from another role | Reproduce with more than 80 mixed pending orders across load, poll, and reconnect |
| BK-R010 | Cached ORM table objects have no invalidation path | Code-supported | `orders/views/api.py:108-110` uses process-local `lru_cache` | Deactivated or renamed tables can remain usable until process restart and differ between workers | Reproduce an admin update followed by order creation |
| BK-R011 | Stored values are interpolated into dynamic HTML and inline handlers in some pages | Code-supported | `order.html:260-269`, `:318-332`; `b1_counter.html:120-154` | A menu or reporting string may cross into executable markup or JavaScript context | Add malicious-string rendering tests and audit every rendering context; note that the kitchen template has a manual escape helper |

### Medium candidates

- API parsing catches broad exceptions and returns plain-text errors with an
  inconsistent JSON contract.
- Order/payment rules are duplicated between JavaScript and Python, with no
  explicit underpayment or idempotency contract.
- `orders/views/api.py` combines serialization, validation, writes, state
  transitions, statistics, and query construction.
- Several artifacts look obsolete or incomplete: `serve.html`,
  `role_select.html`, `forms_admin.py`, `recalc_totals`, legacy admin field-name
  probes, and the retained SQLite counter path. Confirm usage before removal.
- Dependencies use open ranges and CI does not run tests, security checks,
  PostgreSQL migrations, JavaScript checks, or browser flows.
- Operational logging, health/readiness checks, backups, restore drills,
  observability, and load targets are not represented in the repository.

## Unknowns that block design choices

Record answers in `DECISIONS.md`:

1. Is this system public on the internet, private on an event network, or both?
2. Which roles may read, create, update progress, cancel, and view revenue?
3. What exactly resets daily, in which timezone, and may order numbers repeat?
4. What are valid cash/ticket/combined-payment and refund/cancellation rules?
5. What are peak devices, orders per minute, menu size, and acceptable latency?
6. Which PostgreSQL/Supabase versions, hosting platform, and deployment process are
   production truth?
7. Is Supabase Realtime protected by Row Level Security, and which tables/events
   are intentionally exposed to anonymous clients?
8. Must historical production data and current URLs remain compatible?
9. Should the frontend remain server-rendered vanilla JavaScript or may it be
   replaced after the API contract is stabilized?

Do not turn an unknown into a silent implementation assumption when it changes
money, permissions, persisted data, or operator workflow.
