# Working Rules

- This is a take-home assignment. Requirements are in ASSIGNMENT.pdf.
- The agreed plan, decisions and assumptions are in PLAN.md. Follow it, and update it when we change a decision.
- Work ONE step at a time. Never start the next step without my explicit approval.
- Before writing code, briefly explain what you plan to do and why.
- After each step: run the `/end-step` skill (tests, docs, summary, commit and push). It defines the end-of-step routine.
- Keep the code simple and readable. I'll walk the client's team through it
  and explain every part in a follow-up interview, so optimize for clarity
  over cleverness.
- Don't add features or dependencies I didn't approve.
- If anything in the assignment is unclear, ask me before deciding.
- Keep secrets (API keys) in `.env`, list it in `.gitignore`, and provide a `.env.example`.
- Every step includes a quick way to check it works (a small test or a command to run).
- When there's a real design choice, give a short recommendation and the trade-off.
- Documentation, as three separate files:
  - `README.md`: setup and how to run it. Keep it updated as we go.
  - `DESIGN.md`: architecture, storage choice, assumptions and limitations.
    Keep it updated as we go.
  - `DESCRIPTION.md`: a one-page overall description in English.
    Write it only at the end of the task.

## Git
- First step: `git init` with a `.gitignore` (`.env`, virtualenv/`node_modules`, caches).
- Work directly on `main`. No feature branches.
- One commit per approved step, made by `/end-step`. Never commit `.env` or secrets.

## Testing
- One test framework: the language's standard one (e.g. `pytest`). No other test dependencies.
- Unit-test the core logic with small fake inputs.
- Mock external APIs and LLM calls in tests, so they are fast, free and deterministic.
- Keep one manual smoke-check command that calls the real API. It is not part of the test suite.
- Each step adds tests for its own code.
- Report only pass/fail and any failures, not full test logs.
- One cross-platform test script in Python, written in step 1:
  - `python scripts/test.py`: unit tests (mocked, fast, free).
  - `python scripts/test.py smoke`: one real API call, run by hand.
  - Quiet output: pass/fail and failures only.

## Token use
- Read only the files a step needs. Read the assignment PDF once.
- Keep step summaries to a few lines.
- No subagents.
