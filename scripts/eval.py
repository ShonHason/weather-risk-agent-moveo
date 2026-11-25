"""Run the eval set against the real agent (calls the Claude API: costs money).

    python scripts/eval.py                  # all cases, 4 at a time
    python scripts/eval.py --case trap_ratio --case hurricane_top3
    python scripts/eval.py --repeat 3      # each case 3 times: pass rates
    AGENT_MODEL=claude-haiku-5-5 python scripts/eval.py   # another model

Claude's answers vary a little from run to run, so --repeat shows how
reliably each case passes, not just whether it passed once.

Prints PASS/FAIL per case with the failed checks, a summary, and saves the
full results to evals/last_run_<model>.json. Exit code 1 if any run failed.
"""

import argparse
import os
import statistics
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))  # so "import app" works

from app.agent import DEFAULT_EFFORT, DEFAULT_MODEL, Agent
from app.env import load_env
from evals.checks import Run, run_checks

CASES_FILE = PROJECT_ROOT / "evals" / "cases.json"
PARALLEL_CASES = 4

# US$ per million tokens (input, output), standard API prices.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def cost(model, usage):
    input_price, output_price = PRICES[model]
    return (usage["input_tokens"] * input_price
            + usage["output_tokens"] * output_price) / 1_000_000


def run_case(case):
    """Ask the case's questions in one conversation, then check the last answer."""
    started = time.time()
    agent = Agent()
    try:
        for question in case["questions"]:
            answer = agent.ask(question)
    except Exception as error:   # any failure to answer fails the case
        return {"id": case["id"], "passed": False, "seconds": round(time.time() - started),
                "usage": agent.usage, "retries": agent.retries,
                "checks": [("answered", False, f"{type(error).__name__}: {error}")]}

    run = Run(questions=case["questions"], answer=answer,
              tool_log=agent.tool_log, last_turn=agent.turn)
    checks = [("answered", True, "valid FinalAnswer")] + run_checks(run, case["checks"])
    return {
        "id": case["id"],
        "passed": all(passed for _, passed, _ in checks),
        "seconds": round(time.time() - started),
        "usage": agent.usage,
        "retries": agent.retries,
        "checks": checks,
        "answer": answer.model_dump(),
        "tools_called": [c["name"] for c in agent.tool_log],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", action="append", help="run only this case id (repeatable)")
    parser.add_argument("--repeat", type=int, default=1, help="run each case N times")
    args = parser.parse_args()

    load_env()
    model = os.environ.get("AGENT_MODEL", DEFAULT_MODEL)
    effort = os.environ.get("AGENT_EFFORT", DEFAULT_EFFORT)
    cases = json.loads(CASES_FILE.read_text())
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
    runs = [case for case in cases for _ in range(args.repeat)]
    print(f"Model {model}, effort {effort}: running {len(cases)} cases x {args.repeat} "
          f"({PARALLEL_CASES} at a time)...\n")
    started = time.time()

    with ThreadPoolExecutor(max_workers=PARALLEL_CASES) as pool:
        results = list(pool.map(run_case, runs))
    wall_seconds = round(time.time() - started)

    for case in cases:
        case_results = [r for r in results if r["id"] == case["id"]]
        passed = sum(r["passed"] for r in case_results)
        status = "PASS" if passed == len(case_results) else "FAIL"
        print(f"{status}  {case['id']}  ({passed}/{len(case_results)} runs passed)")
        for result in case_results:
            for name, ok, detail in result["checks"]:
                if not ok:
                    print(f"        x {name}: {detail}")

    runs_passed = sum(r["passed"] for r in results)
    all_checks = [c for r in results for c in r["checks"]]
    checks_passed = sum(ok for _, ok, _ in all_checks)
    print(f"\nRuns:   {runs_passed}/{len(results)} passed")
    print(f"Checks: {checks_passed}/{len(all_checks)} passed")

    total_cost = sum(cost(model, r["usage"]) for r in results)
    seconds = [r["seconds"] for r in results]
    print(f"Cost:   ${total_cost:.2f} total, ${total_cost / len(results):.3f} per case")
    print(f"Time:   {statistics.median(seconds)}s median per case, "
          f"{max(seconds)}s slowest, {wall_seconds}s total")
    print(f"Retries (incomplete answers asked again): {sum(r['retries'] for r in results)}")

    # A run of selected cases gets its own file, so it never overwrites a full run.
    scope = "partial" if args.case else "full"
    results_file = PROJECT_ROOT / "evals" / f"last_run_{model}_{effort}_{scope}.json"
    results_file.write_text(json.dumps(results, indent=2))
    print(f"Details: {results_file.relative_to(PROJECT_ROOT)}")
    sys.exit(0 if runs_passed == len(results) else 1)


if __name__ == "__main__":
    main()
