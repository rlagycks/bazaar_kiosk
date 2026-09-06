# Bazaar Kiosk

A Django-based ordering, payment, kitchen-progress, and sales-dashboard system
for a one-floor bazaar operation. The repository is being prepared for an
incremental modernization; current behavior should be treated as legacy behavior
until it is confirmed by tests and an operator decision.

## Local setup

Use Python 3.12, matching the existing CI workflow.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The application reads configuration from environment variables. It does not load
`.env` automatically. Establish and inspect local configuration before running any
database command. The following preserves an existing `.env`:

```bash
test -e .env || cp .env.example .env
# Review .env before sourcing it. Keep DATABASE_URL empty for local SQLite.
set -a
source .env
set +a
```

For an explicitly local SQLite database, clear any inherited database URL for each
database-affecting command:

```bash
env -u DATABASE_URL python manage.py migrate
env -u DATABASE_URL python manage.py runserver
```

Do not run migrations while `DATABASE_URL` points at an unverified database. Local
SQLite is selected when `DATABASE_URL` is empty or unset. PostgreSQL is the
intended production backend and must be used in a disposable environment for
sequence, locking, migration, and concurrency verification.

The example sets `DEBUG=1`. In the current legacy settings that makes
`ALLOWED_HOSTS` equal to `['*']`; the allowlist in `.env.example` becomes effective
only when debug is disabled. Treat this as local development behavior, not a safe
deployment configuration.

Useful local URLs:

- `http://127.0.0.1:8000/orders/` — role login
- `http://127.0.0.1:8000/admin/` — Django admin

## Baseline checks

```bash
env -u DATABASE_URL .venv/bin/python manage.py check
env -u DATABASE_URL .venv/bin/python manage.py makemigrations --check --dry-run
env -u DATABASE_URL .venv/bin/python manage.py test
```

At the preparation baseline, Django's checks and SQLite migrations pass, but the
project contains no automated tests. Passing the commands above is therefore not
evidence that ordering, payment, authorization, PostgreSQL numbering, or realtime
behavior is correct.

## Modernization workflow

Start with [the modernization guide](docs/modernization/README.md). It contains:

- a repository-specific baseline and risk inventory;
- recommended GPT-6 Astra session settings;
- a safe Git recovery strategy;
- a multi-session construction blueprint;
- ready-to-paste prompts for analysis, plan review, implementation, and final
  audit;
- decision and work-log templates for clean handoffs.

Agents must read [AGENTS.md](AGENTS.md) before changing code.
