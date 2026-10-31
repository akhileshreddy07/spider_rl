"""Evaluate submissions: each chosen group of up to 4 plays every seating on every seed.

    python -m engine.tournament SUBMISSION_DIR... [--root DIR] [--seeds 5] [--out out/]
                                [--finalists 8] [--deadline SECONDS] [--backend docker|local]

A submission is a directory holding bot.py (+ optional params.json); `--root DIR` adds every such
subdirectory of DIR. With <= 4 submissions this is a single eval (k! * seeds matches).

Phase 1 plays balanced groups (every bot plays about equally often; all groups if there are few enough).
Phase 2 (`--finalists M`) re-ranks the top M with a round-robin of groups drawn from them.
Results are appended to out/results.jsonl, so an interrupted run resumes where it stopped.
Matches are ordered by seed first, so a run cut off by --deadline still has even coverage.
"""
import argparse
import csv
import hashlib
import itertools
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from math import comb

from .limits import Limits, submission_problems
from .run_match import Submission, run_match
from .scoring import leaderboard


def pick_groups(n: int, k: int, max_groups: int, rng: random.Random) -> list:
    """Groups of k indices out of range(n). Greedy: always seat the least-used bots together."""
    if comb(n, k) <= max_groups:
        return list(itertools.combinations(range(n), k))
    usage, chosen = [0] * n, set()
    while len(chosen) < max_groups:
        by_usage = sorted(range(n), key=lambda i: (usage[i], rng.random()))
        group = tuple(sorted(by_usage[:k]))
        if group in chosen:
            group = tuple(sorted(rng.sample(range(n), k)))
        if group not in chosen:
            chosen.add(group)
            for i in group:
                usage[i] += 1
    return sorted(chosen)


def build_schedule(groups: list, seeds: int, tournament_seed: int, tag: str) -> list:
    """(match_id, seed, seating) tuples. The seed depends on group and seed index, not on the seating."""
    schedule = []
    for seed_idx in range(seeds):
        for group in groups:
            digest = hashlib.sha256(f"{tournament_seed}|{tag}|{group}|{seed_idx}".encode()).digest()
            seed = int.from_bytes(digest[:4], "big")
            for seating in itertools.permutations(group):
                match_id = f"{tag}_g{'-'.join(map(str, group))}_s{seed_idx}_p{''.join(map(str, seating))}"
                schedule.append((match_id, seed, seating))
    return schedule


def load_submissions(paths, root, limits):
    paths = list(paths)
    if root:
        paths += sorted(
            os.path.join(root, d)
            for d in os.listdir(root)
            if os.path.isdir(os.path.join(root, d))
        )

    subs = []
    name_counts = {}
    used_names = set()

    for path in paths:
        problems = submission_problems(path, limits)
        if problems:
            print(f"rejected {path}: {'; '.join(problems)}")
            continue

        base_name = os.path.basename(os.path.normpath(path))
        count = name_counts.get(base_name, 0) + 1
        name = base_name if count == 1 else f"{base_name}#{count}"

        while name in used_names:
            count += 1
            name = f"{base_name}#{count}"

        name_counts[base_name] = count
        used_names.add(name)
        subs.append(Submission(name, path))

    return subs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("submissions", nargs="*")
    ap.add_argument("--root")
    ap.add_argument("--seeds", type=int, default=5, help="seeds per group (each played in all seatings)")
    ap.add_argument("--group-size", type=int, default=4)
    ap.add_argument("--max-groups", type=int, default=50, help="phase 1: groups to sample if there are more")
    ap.add_argument("--finalists", type=int, default=0, help="phase 2: round-robin among the top M")
    ap.add_argument("--tournament-seed", type=int, default=0)
    ap.add_argument("--deadline", type=float, help="stop starting new matches after this many seconds")
    ap.add_argument("--out", default="out")
    ap.add_argument("--backend", default="docker", choices=["docker", "local"])
    ap.add_argument("--image", default="cses-arcade-sandbox")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2), help="parallel matches (4 bot processes each)")
    ap.add_argument("--move-timeout", type=float, default=Limits.move_timeout)
    ap.add_argument("--bot-time-budget", type=float, default=Limits.bot_time_budget)
    args = ap.parse_args()

    limits = Limits(move_timeout=args.move_timeout, bot_time_budget=args.bot_time_budget)
    subs = load_submissions(args.submissions, args.root, limits)
    if len(subs) < 2:
        ap.error("need at least 2 valid submissions")
    k = min(args.group_size, len(subs))

    os.makedirs(os.path.join(args.out, "logs"), exist_ok=True)
    results_path = os.path.join(args.out, "results.jsonl")
    done = {}
    if os.path.exists(results_path):
        with open(results_path) as f:
            done = {row["match_id"]: row for row in map(json.loads, f)}

    end_time = time.monotonic() + args.deadline if args.deadline else None
    rng = random.Random(args.tournament_seed)

    def play(item):
        match_id, seed, seating = item
        if end_time and time.monotonic() > end_time:
            return None
        log_path = os.path.join(args.out, "logs", f"{match_id}.jsonl")
        return run_match([subs[i] for i in seating], seed, log_path, args.backend, args.image, limits, match_id)

    def run_phase(tag, indices, max_groups):
        groups = [tuple(indices[i] for i in g) for g in pick_groups(len(indices), k, max_groups, rng)]
        todo = [m for m in build_schedule(groups, args.seeds, args.tournament_seed, tag) if m[0] not in done]
        print(f"{tag}: {len(groups)} groups, {len(todo)} matches to run ({len(done)} already done)")
        skipped = 0
        with ThreadPoolExecutor(args.workers) as pool, open(results_path, "a") as results:
            for count, summary in enumerate(pool.map(play, todo), start=1):
                if summary is None:
                    skipped += 1
                    continue
                done[summary["match_id"]] = summary
                results.write(json.dumps(summary) + "\n")
                results.flush()
                if count % 25 == 0:
                    print(f"  {count}/{len(todo)}")
        if skipped:
            print(f"  deadline reached: {skipped} matches not run")

    run_phase("p1", list(range(len(subs))), args.max_groups)
    if args.finalists >= k:
        names = [row["name"] for row in leaderboard(done.values())][:args.finalists]
        finalists = [i for i, s in enumerate(subs) if s.name in names]
        run_phase("p2", finalists, args.max_groups)

    rows = leaderboard(done.values())
    with open(os.path.join(args.out, "leaderboard.json"), "w") as f:
        json.dump(rows, f, indent=2)
    with open(os.path.join(args.out, "leaderboard.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
