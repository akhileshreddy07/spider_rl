import random

from schemas import *


class Bot:
    def init(self, params=None):
        self.rng = random.Random((params or {}).get("seed"))

    def play(self, obs):
        me = obs.turn
        action = Action_PLAY()
        action.useUpgrade = None
        action.target = None
        mine = obs.players[me].upgrades
        if obs.next_round == NextRound.UNKNOWN and mine.mag_glass > 0 and self.rng.random() < 0.7:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.MAG_GLASS
            return action
        if obs.players[me].health < obs.max_health and mine.juice > 0:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.JUICE
            return action
        action.action = ActionType.SHOOT
        others = [i for i, p in enumerate(obs.players) if i != me and p.health > 0]
        if obs.next_round == NextRound.BLANK:
            action.target = me
        else:
            action.target = self.rng.choice(others)
        return action

    def pick_upgrade(self, obs):
        action = Action_PICK_UPGRADES()
        counts = obs.available_upgrades
        for upgrade, name in ((UpgradeType.JUICE, "juice"), (UpgradeType.MAG_GLASS, "mag_glass"),
                              (UpgradeType.COFFEE, "coffee"), (UpgradeType.HAND_SAW, "hand_saw"),
                              (UpgradeType.POOL_FLOATIE, "pool_floatie")):
            if getattr(counts, name) > 0:
                action.chosen_upgrade = upgrade
                return action
