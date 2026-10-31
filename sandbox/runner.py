"""Runs inside the sandbox: loads a submission's Bot and serves JSON-line requests on stdin/stdout.

Protocol (one JSON object per line):
  {"id": 0, "type": "init", "params": {...}}          -> {"id": 0, "ok": true}
  {"id": n, "type": "PLAY", "obs": {...}}             -> {"id": n, "action": {...}}
  {"id": n, "type": "PICK_UPGRADE", "obs": {...}}     -> {"id": n, "action": {...}}
Any failure is reported as {"id": n, "error": "..."}.
"""
import importlib.util
import inspect
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wire  # noqa: E402


def _load_bot(submission_dir: str, params: dict):
    sys.path.insert(1, submission_dir)
    spec = importlib.util.spec_from_file_location("bot", os.path.join(submission_dir, "bot.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["bot"] = module
    spec.loader.exec_module(module)
    try:
        bot = module.Bot()
    except TypeError:
        bot = module.Bot(params)
    init = getattr(bot, "init", None)
    if callable(init):
        takes_params = len(inspect.signature(init).parameters) > 0
        init(params) if takes_params else init()
    return bot


def main() -> None:
    # Keep the protocol channel private: anything the bot prints goes to stderr.
    out = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr

    submission_dir = os.environ.get("SUBMISSION_DIR", "/submission")
    bot = None
    for line in sys.stdin:
        request = json.loads(line)
        reply = {"id": request["id"]}
        try:
            if request["type"] == "init":
                bot = _load_bot(submission_dir, request.get("params") or {})
                reply["ok"] = True
            elif request["type"] == "PLAY":
                action = bot.play(wire.obs_play_from_wire(request["obs"]))
                reply["action"] = wire.action_play_to_wire(action)
            elif request["type"] == "PICK_UPGRADE":
                action = bot.pick_upgrade(wire.obs_pick_from_wire(request["obs"]))
                reply["action"] = wire.action_pick_to_wire(action)
            else:
                reply["error"] = "unknown request type"
        except BaseException:
            reply["error"] = traceback.format_exc()[-2000:]
        out.write(json.dumps(reply) + "\n")


if __name__ == "__main__":
    main()
