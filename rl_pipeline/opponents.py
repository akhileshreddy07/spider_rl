"""Diverse Opponent Pool for Training and Evaluation.

Provides:
- RandomBot: Uniform baseline
- SpiderSenseBot: Existing expert heuristic bot
- ConservativeBot: Defensive bot focusing on survival, healing, and self-preservation
- AggressiveBot: Aggressive bot focusing on maximum damage and elimination
"""
from __future__ import annotations
import random
from schemas import (
    Action_PLAY,
    Action_PICK_UPGRADES,
    ActionType,
    UpgradeType,
    NextRound,
    Obs_PLAY,
    Obs_PICK_UPGRADES,
)
from submissions.spider_sense.bot import Bot as SpiderSenseBot


class ConservativeBot:
    """Defensive bot: Prioritizes healing, safe self-shots, and survival."""
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def play(self, obs: Obs_PLAY) -> Action_PLAY:
        me = obs.turn
        my_p = obs.players[me]
        action = Action_PLAY()
        action.useUpgrade = None
        action.target = None

        # Always heal first if injured
        if my_p.health < obs.max_health and my_p.upgrades.juice > 0:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.JUICE
            return action

        # Always inspect with mag glass if available
        if obs.next_round == NextRound.UNKNOWN and my_p.upgrades.mag_glass > 0 and obs.rounds_remaining > 0:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.MAG_GLASS
            return action

        # Floatie the next living opponent
        if my_p.upgrades.pool_floatie > 0:
            for offset in (1, 2, 3):
                cand = (me + offset) % len(obs.players)
                if cand != me and obs.players[cand].health > 0 and not obs.players[cand].has_pool_floatie_on:
                    action.action = ActionType.USE_UPGRADE
                    action.useUpgrade = UpgradeType.POOL_FLOATIE
                    action.target = cand
                    return action

        action.action = ActionType.SHOOT
        if obs.next_round == NextRound.BLANK:
            action.target = me
            return action

        # If live or unknown, shoot the leader (opponent with highest health)
        living = [i for i, p in enumerate(obs.players) if i != me and p.health > 0]
        if living:
            leader = max(living, key=lambda i: obs.players[i].health)
            action.target = leader
        else:
            action.target = me
        return action

    def pick_upgrade(self, obs: Obs_PICK_UPGRADES) -> Action_PICK_UPGRADES:
        action = Action_PICK_UPGRADES()
        avail = obs.available_upgrades
        for upg, name in ((UpgradeType.JUICE, "juice"), (UpgradeType.MAG_GLASS, "mag_glass"),
                          (UpgradeType.POOL_FLOATIE, "pool_floatie"), (UpgradeType.COFFEE, "coffee"),
                          (UpgradeType.HAND_SAW, "hand_saw")):
            if getattr(avail, name, 0) > 0:
                action.chosen_upgrade = upg
                return action
        action.chosen_upgrade = UpgradeType.JUICE
        return action


class AggressiveBot:
    """Aggressive bot: Prioritizes burst damage and quick eliminations."""
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def play(self, obs: Obs_PLAY) -> Action_PLAY:
        me = obs.turn
        my_p = obs.players[me]
        action = Action_PLAY()
        action.useUpgrade = None
        action.target = None

        living = [i for i, p in enumerate(obs.players) if i != me and p.health > 0]
        if not living:
            action.action = ActionType.SHOOT
            action.target = me
            return action

        # Find lowest health target (lethal execution)
        weakest = min(living, key=lambda i: obs.players[i].health)

        # Use hand saw whenever available
        if my_p.upgrades.hand_saw > 0:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.HAND_SAW
            return action

        action.action = ActionType.SHOOT
        if obs.next_round == NextRound.BLANK:
            action.target = me
        else:
            action.target = weakest
        return action

    def pick_upgrade(self, obs: Obs_PICK_UPGRADES) -> Action_PICK_UPGRADES:
        action = Action_PICK_UPGRADES()
        avail = obs.available_upgrades
        for upg, name in ((UpgradeType.HAND_SAW, "hand_saw"), (UpgradeType.MAG_GLASS, "mag_glass"),
                          (UpgradeType.POOL_FLOATIE, "pool_floatie"), (UpgradeType.JUICE, "juice"),
                          (UpgradeType.COFFEE, "coffee")):
            if getattr(avail, name, 0) > 0:
                action.chosen_upgrade = upg
                return action
        action.chosen_upgrade = UpgradeType.HAND_SAW
        return action
