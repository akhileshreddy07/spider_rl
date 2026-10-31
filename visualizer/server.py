#!/usr/bin/env python3
"""Buckshot Roulette Visualizer Server.

Provides a local HTTP server and REST API for:
- Serving the visualizer web client (HTML, CSS, JS)
- Listing historical tournament / match logs from out*/logs/ and visualizer/logs/
- Fetching match event stream records (.jsonl)
- Running on-demand simulator matches between spider_sense and opponent bots
"""

import argparse
import glob
import http.server
import json
import os
import sys
import time
import urllib.parse
from typing import Any, Dict, List

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VISUALIZER_DIR = os.path.join(ROOT_DIR, "visualizer")
LOGS_DIR = os.path.join(VISUALIZER_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def scan_matches() -> List[Dict[str, Any]]:
    """Scan all out*/logs/*.jsonl and visualizer/logs/*.jsonl for match summaries."""
    matches = []
    search_patterns = [
        os.path.join(ROOT_DIR, "out*", "logs", "*.jsonl"),
        os.path.join(LOGS_DIR, "*.jsonl"),
    ]

    seen_paths = set()
    for pattern in search_patterns:
        for file_path in glob.glob(pattern):
            abs_path = os.path.abspath(file_path)
            if abs_path in seen_paths:
                continue
            seen_paths.add(abs_path)

            rel_path = os.path.relpath(abs_path, ROOT_DIR)
            file_stat = os.stat(abs_path)
            if file_stat.st_size == 0:
                continue

            # Read the last line for summary
            summary = None
            action_count = 0
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [ln.strip() for ln in f if ln.strip()]
                    if lines:
                        action_count = len(lines) - 1
                        last_line = lines[-1]
                        try:
                            last_obj = json.loads(last_line)
                            summary = last_obj.get("summary")
                        except Exception:
                            pass
            except Exception:
                continue

            match_id = os.path.splitext(os.path.basename(abs_path))[0]
            if summary and summary.get("match_id"):
                match_id = summary["match_id"]

            matches.append({
                "path": rel_path,
                "filename": os.path.basename(abs_path),
                "match_id": match_id,
                "mtime": file_stat.st_mtime,
                "size_bytes": file_stat.st_size,
                "actions": action_count,
                "summary": summary,
            })

    # Sort descending by modification time
    matches.sort(key=lambda m: m["mtime"], reverse=True)
    return matches


def read_match_log(rel_path: str) -> List[Dict[str, Any]]:
    """Safely read and parse a JSONL match file."""
    # Prevent directory traversal
    clean_path = os.path.normpath(rel_path)
    abs_path = os.path.abspath(os.path.join(ROOT_DIR, clean_path))
    if not abs_path.startswith(ROOT_DIR):
        raise ValueError("Invalid path access")
    if not abs_path.endswith(".jsonl") or not os.path.isfile(abs_path):
        raise FileNotFoundError(f"File not found: {rel_path}")

    records = []
    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def run_new_match(seed: int, num_players: int = 2) -> Dict[str, Any]:
    """Execute a match via engine.run_match locally and record the log."""
    from engine.run_match import Submission, run_match

    num_players = max(2, min(4, int(num_players)))
    match_id = f"sim_{int(time.time())}_s{seed}_{num_players}p"
    log_filename = f"{match_id}.jsonl"
    log_path = os.path.join(LOGS_DIR, log_filename)

    spider_sense_path = os.path.join(ROOT_DIR, "submissions", "spider_sense")
    baseline_path = os.path.join(ROOT_DIR, "bots", "random_bot")

    seats = [Submission("spider_sense", spider_sense_path)]
    for i in range(1, num_players):
        seats.append(Submission(f"random_bot_{i}", baseline_path, {"seed": seed + i * 17}))

    summary = run_match(
        seats=seats,
        seed=seed,
        log_path=log_path,
        backend="local",
        match_id=match_id,
        keep_stderr=False,
    )

    records = read_match_log(os.path.relpath(log_path, ROOT_DIR))
    return {
        "ok": True,
        "match_id": match_id,
        "rel_path": os.path.relpath(log_path, ROOT_DIR),
        "summary": summary,
        "records": records,
    }


class VisualizerRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=VISUALIZER_DIR, **kwargs)

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/matches":
            self.send_json(200, scan_matches())
            return

        if path == "/api/match":
            qs = urllib.parse.parse_qs(parsed_url.query)
            file_rel = qs.get("path", [""])[0]
            if not file_rel:
                self.send_json(400, {"error": "Missing 'path' query parameter"})
                return
            try:
                records = read_match_log(file_rel)
                self.send_json(200, {"path": file_rel, "records": records})
            except Exception as exc:
                self.send_json(404, {"error": str(exc)})
            return

        # Fallback to static file serving from VISUALIZER_DIR
        return super().do_GET()

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/run":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                data = json.loads(body) if body else {}
                seed = int(data.get("seed", int(time.time()) % 100000))
                num_players = int(data.get("num_players", 2))
                result = run_new_match(seed=seed, num_players=num_players)
                self.send_json(200, result)
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        self.send_json(404, {"error": "Endpoint not found"})

    def send_json(self, status: int, data: Any) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep terminal output clean
        pass


def start_server(port: int = 8080) -> None:
    # Try specified port, or search for next free port
    server = None
    chosen_port = port
    for p in range(port, port + 20):
        try:
            server = http.server.ThreadingHTTPServer(("0.0.0.0", p), VisualizerRequestHandler)
            chosen_port = p
            break
        except OSError:
            continue

    if server is None:
        print(f"Error: Could not bind to any port between {port} and {port + 20}")
        sys.exit(1)

    print(f"==================================================")
    print(f"  BUCKSHOT ROULETTE VISUALIZER SERVER RUNNING     ")
    print(f"  URL: http://localhost:{chosen_port}/           ")
    print(f"==================================================")
    print(f"Serving UI from: {VISUALIZER_DIR}")
    print(f"Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down visualizer server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Buckshot Roulette Visualizer Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    args = parser.parse_args()
    start_server(args.port)
