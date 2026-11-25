"""A small command-line chat with the agent, for manual testing.

    python scripts/chat.py           # type 'quit' to exit
    python scripts/chat.py --json    # also print the raw structured answer
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # so "import app" works

from app.agent import Agent, AgentError
from app.env import load_env


def print_answer(answer):
    print(f"\n{answer.answer}\n")
    for i, hub in enumerate(answer.ranking, start=1):
        print(f"  {i}. {hub.hub_name:<20} {hub.score:>5}  {hub.note}")
    if answer.ranking:
        print()
    print("Reasoning:")
    for step in answer.reasoning:
        print(f"  - {step}")
    print("Assumptions:")
    for item in answer.assumptions:
        print(f"  - {item}")
    print(f"Confidence: {answer.confidence}\n")


def main():
    load_env()
    show_json = "--json" in sys.argv
    agent = Agent()
    print("Weather risk agent. Ask about the hubs; type 'quit' to exit.")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("quit", "exit"):
            break
        if not question:
            continue
        try:
            answer = agent.ask(question)
        except AgentError as error:
            print(f"Sorry, I couldn't answer that: {error}\n")
            continue
        print_answer(answer)
        if show_json:
            print(answer.model_dump_json(indent=2), "\n")


if __name__ == "__main__":
    main()
