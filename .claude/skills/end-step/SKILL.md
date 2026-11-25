---
name: end-step
description: End-of-step routine for this project. Run tests, record design decisions, update PLAN.md, summarize, propose a commit, and after approval commit and push. Use when the user types /end-step or says a step is done.
---

# End-of-step routine

Do these in order. Keep every message short.

1. **Test.** Run `python scripts/test.py` (use `.venv/bin/python` if it exists).
   If anything fails, stop and report only the failures. Do not continue.
2. **Design decisions.** If this step added or changed a design decision,
   record it in `DESIGN.md` with the reason for it. Skip if there is none.
3. **Plan.** If a decision, assumption or step changed, update `PLAN.md`.
   Skip if nothing changed.
4. **Summary.** In a few lines: what was built, how to run/check it, test
   result (pass/fail count only). Propose a commit message: short,
   conventional style, e.g. `feat: fetch weather data`. Then stop and wait.
5. **Commit and push, only after the user approves.**
   - Run `git status`. Never stage `.env` or secrets; leave out files this
     step didn't touch unless the user says otherwise.
   - Commit on `main` with the approved message.
   - Push with `git push`. If there is no remote, say so instead of pushing.
