"""Smoke-test one submission in the sandbox before it enters a tournament.

    python -m engine.validate SUBMISSION_DIR [--backend docker|local] [--games 3]

Plays a few matches with the submission in seat 0 against three baseline random bots and
reports any fault (crash, timeout, bad output, illegal move) or limit violation. Exit code 1 on problems.
"""
import argparse
import os
import sys
import tempfile

from .limits import Limits, submission_problems
from .run_match import Submission, run_match

BASELINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bots", "random_bot")


def validate(path: str, backend: str, image: str, games: int, limits: Limits = Limits()) -> list:
    problems = submission_problems(path, limits)
    if problems:
        return problems
    candidate = Submission("candidate", path)
    opponents = [Submission(f"baseline{i}", BASELINE, {"seed": i}) for i in range(3)]
    with tempfile.TemporaryDirectory() as tmp:
        for seed in range(games):
            log_path = os.path.join(tmp, f"{seed}.jsonl")
            summary = run_match([candidate] + opponents, seed, log_path, backend, image, limits, keep_stderr=True)
            print(f"game {seed}: place {summary['placements'][0]}, {summary['actions']} actions, "
                  f"{summary['time_used'][0]}s of {limits.bot_time_budget}s budget")
            if summary["faults"][0]:
                problems.append(f"game {seed}: faults {summary['faults'][0]}")
                stderr_file = f"{log_path}.seat0.stderr"
                if os.path.exists(stderr_file):
                    print(open(stderr_file, errors="replace").read()[-1500:])
                print(f"  first fault: {_first_fault(log_path)}")
    return problems


def _first_fault(log_path: str) -> str:
    import json
    with open(log_path) as f:
        for record in map(json.loads, f):
            if record.get("seat") == 0 and "fault" in record:
                return f"{record['fault']}: {record.get('detail', '')[:300]}"
    return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("submission")
    ap.add_argument("--backend", default="docker", choices=["docker", "local"])
    ap.add_argument("--image", default="cses-arcade-sandbox")
    ap.add_argument("--games", type=int, default=3)
    args = ap.parse_args()
    problems = validate(args.submission, args.backend, args.image, args.games)
    print("OK" if not problems else "FAILED:\n  " + "\n  ".join(problems))
    sys.exit(bool(problems))


if __name__ == "__main__":
    main()
