"""JSON (de)serialisation of observations and actions, shared by the engine and the sandbox runner."""
from enum import Enum
from typing import Any

from schemas import *

_UPGRADE_FIELDS = ("juice", "coffee", "mag_glass", "pool_floatie", "hand_saw")
_EJECTION_FIELDS = ("blanks_ejected", "lives_ejected", "unknowns_ejected")


def to_wire(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [to_wire(item) for item in obj]
    if hasattr(obj, "__dict__"):
        return {name: to_wire(value) for name, value in vars(obj).items()}
    return obj


def _upgrade_counts(data: dict) -> UpgradeCounts:
    counts = UpgradeCounts()
    for name in _UPGRADE_FIELDS:
        setattr(counts, name, int(data[name]))
    return counts


def _player(data: dict) -> Player:
    player = Player()
    player.health = int(data["health"])
    player.upgrades = _upgrade_counts(data["upgrades"])
    player.has_pool_floatie_on = bool(data["has_pool_floatie_on"])
    return player


def _ejections(data: dict) -> EjectionStatus:
    status = EjectionStatus()
    for name in _EJECTION_FIELDS:
        setattr(status, name, int(data[name]))
    return status


def obs_play_from_wire(data: dict) -> Obs_PLAY:
    obs = Obs_PLAY()
    obs.max_health = data["max_health"]
    obs.players = [_player(p) for p in data["players"]]
    obs.turn = data["turn"]
    obs.session_no = data["session_no"]
    for name in ("lives_init", "blanks_init", "rounds_remaining", "lives_shot", "blanks_shot"):
        setattr(obs, name, data[name])
    obs.ejections = _ejections(data["ejections"])
    obs.next_round = NextRound(data["next_round"])
    return obs


def obs_pick_from_wire(data: dict) -> Obs_PICK_UPGRADES:
    obs = Obs_PICK_UPGRADES()
    obs.max_health = data["max_health"]
    obs.players = [_player(p) for p in data["players"]]
    obs.turn = data["turn"]
    obs.session_no = data["session_no"]
    obs.available_upgrades = _upgrade_counts(data["available_upgrades"])
    return obs


def action_play_to_wire(action: Any) -> dict:
    use = getattr(action, "useUpgrade", None)
    return {
        "action": ActionType(action.action).value,
        "useUpgrade": UpgradeType(use).value if use is not None else None,
        "target": getattr(action, "target", None),
    }


def action_pick_to_wire(action: Any) -> dict:
    return {"chosen_upgrade": UpgradeType(action.chosen_upgrade).value}


def action_play_from_wire(data: dict) -> Action_PLAY:
    """Raises ValueError/KeyError/TypeError on malformed input."""
    action = Action_PLAY()
    action.action = ActionType(data["action"])
    use = data.get("useUpgrade")
    action.useUpgrade = UpgradeType(use) if use is not None else None
    target = data.get("target")
    if target is not None and (isinstance(target, bool) or not isinstance(target, int)):
        raise TypeError("target must be an int or null")
    action.target = target
    return action


def action_pick_from_wire(data: dict) -> Action_PICK_UPGRADES:
    action = Action_PICK_UPGRADES()
    action.chosen_upgrade = UpgradeType(data["chosen_upgrade"])
    return action
