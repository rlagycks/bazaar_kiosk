# GPT-6 Astra session setup

Last verified: 2026-09-06

## Model and reasoning

Use `gpt-6-astra` as explicitly selected for this modernization.

- Analysis, architecture, migration, and adversarial review: start at `xhigh`.
- A well-scoped implementation phase: start at `high`.
- Raise to `max` only for a concrete hard problem such as a concurrency proof,
  data-migration design, or conflicting architecture constraints.
- Lower effort for routine documentation or mechanical follow-ups only after the
  difficult decisions are stable.

GPT-6 Astra does not support `none` reasoning effort. In an API integration, use
the Responses API for tool-calling work and verify all current request parameters
against the official model guide. This repository setup does not add OpenAI API
code or credentials.

## Repository state prepared for later sessions

- Clone: local repository is available with full history.
- Preparation branch: `chore/astra-modernization-setup`.
- Upstream default branch at inspection time: `origin/develop`.
- Local environment: `.venv`, Python 3.12.11, Django 5.2.17.
- Local smoke database: ignored `db.sqlite3` with all migrations applied.
- GitHub CLI: installed, but the stored `rlagycks` token was invalid at inspection
  time. Re-authentication is required before PR or remote-management work.

Do not assume that the preparation branch exists remotely until the user chooses
to push it. Do not switch to `main` or rewrite history as an automatic setup step.

Before creating a new worktree, the preparation documents must exist in a local
checkpoint commit on its base. Verify both commands against the intended ref:

```bash
git cat-file -e <intended-ref>:AGENTS.md
git cat-file -e <intended-ref>:docs/modernization/BLUEPRINT.md
```

If either command fails, do not start a worktree from that ref. First use the local
preparation branch tip or integrate its checkpoint through a reviewed Git action.
Publishing or merging the checkpoint remains separately approval-gated.

## Start every new task

1. Open the repository and read `AGENTS.md` plus this directory's control files.
2. Inspect the current branch, status, and existing diff.
3. Verify that the selected base contains the preparation control files, then use
   a dedicated branch or worktree for one approved blueprint phase.
4. Run the phase's baseline checks before editing.
5. Proceed through the approved work autonomously. Ask only when a missing answer
   changes business behavior, persisted data, security, or an irreversible action.
6. Update `WORKLOG.md` before handing off.

Suggested branch names:

```text
modernize/01-postgres-bootstrap
modernize/02-test-ci-foundation
modernize/03-api-access-control
modernize/04a-identity-security
modernize/04b-content-realtime-security
modernize/05-numbering
modernize/06-order-commands
modernize/07-financial-integrity
modernize/08-reporting-retrieval
modernize/09-api-boundaries
modernize/10-performance-realtime
modernize/11-frontend-resilience
modernize/12a-operations
```

Prefer squash merges after review so the existing merge-heavy graph does not keep
growing. Remote branch deletion, default-branch changes, and protection rules are
separate user-approved operations.

## Local commands

```bash
env -u DATABASE_URL .venv/bin/python manage.py check
env -u DATABASE_URL .venv/bin/python manage.py makemigrations --check --dry-run
env -u DATABASE_URL .venv/bin/python manage.py test
```

For security-sensitive or deployment work, also run a production-style Django
deployment check with realistic non-secret configuration. For persistence,
numbering, or concurrency work, add a disposable PostgreSQL environment and run
the focused integration suite there.

## Output style for Astra

Lead with the result. Use concise paragraphs and lists only when they improve
comparison or sequence. Every finding should separate evidence, inference, and
unknowns. Every implementation handoff should list changed files, checks run,
remaining risks, and the next blueprint gate.
