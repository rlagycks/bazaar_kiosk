# Modernization control center

This directory is the handoff surface for modernizing Bazaar Kiosk with GPT-6
Astra. It keeps verified facts, pending decisions, phase boundaries, and session
prompts separate so a fresh session can resume without reconstructing history.

## Recommended order

1. Read [SESSION_SETUP.md](SESSION_SETUP.md) and select GPT-6 Astra.
2. Paste [prompts/01_ANALYZE.md](prompts/01_ANALYZE.md) into a dedicated analysis
   session. That session should produce evidence, not implementation.
3. Resolve product questions in [DECISIONS.md](DECISIONS.md).
4. Paste [prompts/02_REVIEW_BLUEPRINT.md](prompts/02_REVIEW_BLUEPRINT.md) to align
   the construction plan with the completed analysis and decisions.
5. Run one approved phase at a time with
   [prompts/03_IMPLEMENT_PHASE.md](prompts/03_IMPLEMENT_PHASE.md).
6. After the planned phases, use
   [prompts/04_FINAL_AUDIT.md](prompts/04_FINAL_AUDIT.md).

The current starting documents are:

- [BASELINE.md](BASELINE.md) — verified snapshot and initial risk hypotheses;
- [BLUEPRINT.md](BLUEPRINT.md) — dependency-ordered, one-PR-sized phases;
- [GIT_RECOVERY.md](GIT_RECOVERY.md) — non-destructive history cleanup options;
- [DECISIONS.md](DECISIONS.md) — product and technical decision log;
- [WORKLOG.md](WORKLOG.md) — session-to-session handoff record.

## Document states

- `Verified` means a command, code location, or reproducible observation supports
  the statement.
- `Hypothesis` means the risk is plausible but needs a focused reproduction or
  production-context confirmation.
- `Pending decision` means implementation must not silently choose for the user.

Update the `Last verified` field when facts are rechecked. Never overwrite an
important decision without preserving the old entry and rationale.

## Prompt-design source

The session guidance was derived from the official
[GPT-6 Astra model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra),
verified on 2026-09-06. In particular, the prompts explicitly define initiative,
instruction priority, writing style, delegation, and test proportionality because
those are controllable Astra behaviors called out by the guide.

The prompts paraphrase the guide rather than copying it. Recheck the official page
before changing model/API parameters because capabilities and compatibility can
change.
