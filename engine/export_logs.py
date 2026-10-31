"""Split match logs into one training file per model.

    python -m engine.export_logs out/        # writes out/training/<model>.jsonl

Each line is one decision made by that model: the observation it saw, the action it chose, and how
the match ended for it (placement and points), so the file can be used directly for training.
"""
import argparse
import glob
import json
import os

from .scoring import placement_points


def export(out_dir: str) -> dict:
    target = os.path.join(out_dir, "training")
    os.makedirs(target, exist_ok=True)
    files, counts = {}, {}
    try:
        for log_path in sorted(glob.glob(os.path.join(out_dir, "logs", "*.jsonl"))):
            with open(log_path) as f:
                records = [json.loads(line) for line in f]
            summary = records[-1].get("summary")
            if summary is None:  # match was interrupted
                continue
            k = len(summary["seats"])
            for record in records[:-1]:
                if record.get("stage") == "INIT":
                    continue
                name = summary["seats"][record["seat"]]
                if name not in files:
                    files[name] = open(os.path.join(target, f"{name}.jsonl"), "w")
                place = summary["placements"][record["seat"]]
                row = {"match_id": summary["match_id"], "seed": summary["seed"], "placement": place,
                       "points": placement_points(place, k), **record}
                files[name].write(json.dumps(row) + "\n")
                counts[name] = counts.get(name, 0) + 1
    finally:
        for f in files.values():
            f.close()
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    for name, n in export(ap.parse_args().out_dir).items():
        print(f"{name}: {n} decisions")
