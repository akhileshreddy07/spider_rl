"""Run one k-player match between sandboxed bots and write its log.

Each log line is a JSON object describing one decision; the last line is {"summary": ...}.
"""
import json
import os
import random
import time
from dataclasses import dataclass
from typing import List, Optional

import game_API as api
import wire
from schemas import *

from .bot_process import BotFault, BotProcess
from .limits import Limits

FATAL_FAULTS = ("crash", "budget")


@dataclass
class Submission:
    name: str
    path: str  # directory containing bot.py
    params: Optional[dict] = None  # overrides params.json

    def load_params(self) -> dict:
        if self.params is not None:
            return self.params
        params_file = os.path.join(self.path, "params.json")
        if os.path.exists(params_file):
            with open(params_file) as f:
                return json.load(f)
        return {}


def _fallback_play(state: api.GameState, rng: random.Random) -> Action_PLAY:
    action = Action_PLAY()
    action.action = ActionType.SHOOT
    action.useUpgrade = None
    action.target = rng.choice([i for i, p in enumerate(state.players) if i != state.turn and p.health > 0])
    return action


def _fallback_pick(state: api.GameState) -> Action_PICK_UPGRADES:
    action = Action_PICK_UPGRADES()
    for upgrade, name in ((UpgradeType.JUICE, "juice"), (UpgradeType.COFFEE, "coffee"),
                          (UpgradeType.MAG_GLASS, "mag_glass"), (UpgradeType.POOL_FLOATIE, "pool_floatie"),
                          (UpgradeType.HAND_SAW, "hand_saw")):
        if getattr(state.available_upgrades, name) > 0:
            action.chosen_upgrade = upgrade
            return action
    raise RuntimeError("no upgrades available")


def _placements(state: api.GameState) -> List[int]:
    """Survivors ranked by health (then seat), followed by the dead in reverse order of death."""
    alive = sorted((i for i, p in enumerate(state.players) if p.health > 0),
                   key=lambda i: (-state.players[i].health, i))
    placements = [0] * len(state.players)
    for place, seat in enumerate(alive + list(reversed(state.elimination_order)), start=1):
        placements[seat] = place
    return placements


def run_match(seats: List[Submission], seed: int, log_path: Optional[str] = None, backend: str = "docker",
              image: str = "cses-arcade-sandbox", limits: Limits = Limits(), match_id: str = "",
              keep_stderr: bool = False) -> dict:
    """seats[i] plays as player i. Returns a summary dict; `placements[seat]` is 1 for the winner."""
    k = len(seats)
    state = api.initGame(seed, k)
    fallback_rng = random.Random(seed ^ 0x5EED)
    strikes = [0] * k
    faults = [{} for _ in range(k)]
    disqualified = [False] * k
    time_used = [0.0] * k
    bots: List[Optional[BotProcess]] = [None] * k
    log = open(log_path, "w") if log_path else None

    def write(record: dict) -> None:
        if log:
            log.write(json.dumps(record) + "\n")

    def record_fault(seat: int, fault: BotFault) -> None:
        faults[seat][fault.kind] = faults[seat].get(fault.kind, 0) + 1
        strikes[seat] += 1
        if fault.kind in FATAL_FAULTS or strikes[seat] >= limits.max_strikes:
            disqualified[seat] = True
            bots[seat].close()
            api.eliminate_player(state, seat)

    steps = 0
    try:
        for seat, sub in enumerate(seats):
            stderr_path = f"{log_path}.seat{seat}.stderr" if (log_path and keep_stderr) else None
            bots[seat] = BotProcess(sub.path, backend, image, limits.memory, stderr_path=stderr_path)
            try:
                bots[seat].request({"type": "init", "params": sub.load_params()}, limits.init_timeout)
            except BotFault as fault:
                write({"seat": seat, "stage": "INIT", "fault": fault.kind, "detail": fault.detail[:500]})
                record_fault(seat, BotFault("crash", fault.detail))  # a bot that cannot start is out

        while not state.game_over and steps < limits.max_actions:
            steps += 1
            seat, stage = state.turn, state.stage
            obs = api.play_observation(state) if stage == Stage.PLAY else api.upgrade_observation(state)
            record = {"step": steps, "seat": seat, "stage": stage.value, "obs": wire.to_wire(obs)}

            try:
                remaining = limits.bot_time_budget - time_used[seat]
                if remaining <= 0:
                    raise BotFault("budget", f"used {time_used[seat]:.1f}s of {limits.bot_time_budget}s")
                started = time.monotonic()
                try:
                    reply = bots[seat].request({"type": stage.value, "obs": record["obs"]},
                                               min(limits.move_timeout, remaining))
                finally:
                    time_used[seat] += time.monotonic() - started
                try:
                    parse = wire.action_play_from_wire if stage == Stage.PLAY else wire.action_pick_from_wire
                    action = parse(reply["action"])
                except (KeyError, ValueError, TypeError) as exc:
                    raise BotFault("invalid", repr(exc))
                record["action"] = reply["action"]
                try:
                    (api.step_PLAY if stage == Stage.PLAY else api.step_PICK_UPGRADE)(state, action)
                except ValueError as exc:
                    raise BotFault("illegal", str(exc))
            except BotFault as fault:
                record["fault"], record["detail"] = fault.kind, fault.detail[:500]
                record_fault(seat, fault)
                if not disqualified[seat] and not state.game_over:  # keep the game moving
                    if stage == Stage.PLAY:
                        api.step_PLAY(state, _fallback_play(state, fallback_rng))
                    else:
                        api.step_PICK_UPGRADE(state, _fallback_pick(state))
            write(record)
    finally:
        for bot in bots:
            if bot:
                bot.close()

    placements = _placements(state)
    summary = {
        "match_id": match_id,
        "seed": seed,
        "seats": [s.name for s in seats],
        "placements": placements,
        "winner": placements.index(1),
        "reason": "last_alive" if state.game_over else "max_actions",
        "actions": steps,
        "faults": faults,
        "disqualified": disqualified,
        "time_used": [round(t, 2) for t in time_used],
        "final_health": [p.health for p in state.players],
    }
    write({"summary": summary})
    if log:
        log.close()
    return summary
