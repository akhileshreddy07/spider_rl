"""SPIDER-RL AI 🕷️⚡ (v2)
CSES Arcade RL Hackathon - Action-Masked Deep Q-Network Submission

Key Features:
- Adaptive Pure-Python Forward Pass: Automatically configures input dimensions (30 or 34) and hidden units from weights.json metadata.
- Zero External Dependencies: Standard library only (no torch, no numpy). Sub-millisecond execution.
- Action-Masked DQN: Masking guarantees zero illegal moves or faults.
- Configurable Safety Overrides: Can be evaluated independently via params.json.
- Resilient Fallback: Defaults safely to Spider-Sense rule logic if weights are missing.
"""
from __future__ import annotations

import json
import os
import random
from typing import List, Optional

from schemas import (
    Action_PICK_UPGRADES,
    Action_PLAY,
    ActionType,
    NextRound,
    Obs_PICK_UPGRADES,
    Obs_PLAY,
    Player,
    UpgradeType,
)


class Bot:
    def __init__(self, params: Optional[dict] = None) -> None:
        self.init(params)

    def init(self, params: Optional[dict] = None) -> None:
        params = params or {}
        seed = params.get("seed", 42)
        self.rng = random.Random(seed)

        # Configurable overrides
        self.enable_safety_overrides = params.get("enable_safety_overrides", True)
        self.enable_defensive_heal = params.get("enable_defensive_heal", True)

        self.model_loaded = False
        self.weights = None
        weights_path = params.get("weights_path") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "weights.json"
        )

        if os.path.exists(weights_path):
            try:
                with open(weights_path, "r") as f:
                    data = json.load(f)
                self.W1 = data["W1"]
                self.b1 = data["b1"]
                self.W2 = data["W2"]
                self.b2 = data["b2"]
                self.W3 = data["W3"]
                self.b3 = data["b3"]
                self.state_dim = len(self.W1)
                self.model_loaded = True
            except Exception:
                self.model_loaded = False
        else:
            self.model_loaded = False

    # -------------------------------------------------------------------------
    # Observation & Probability Tracking
    # -------------------------------------------------------------------------
    def _estimate_live_prob(self, obs: Obs_PLAY) -> float:
        if obs.next_round == NextRound.LIVE:
            return 1.0
        if obs.next_round == NextRound.BLANK:
            return 0.0

        lives_consumed = obs.lives_shot + obs.ejections.lives_ejected
        blanks_consumed = obs.blanks_shot + obs.ejections.blanks_ejected

        remaining_live = max(0, obs.lives_init - lives_consumed)
        remaining_blank = max(0, obs.blanks_init - blanks_consumed)
        total_unobserved = remaining_live + remaining_blank

        if total_unobserved <= 0:
            return 0.5
        if remaining_live == 0:
            return 0.0
        if remaining_blank == 0:
            return 1.0

        return remaining_live / total_unobserved

    def _get_relative_opponents(self, obs: Obs_PLAY) -> List[Optional[int]]:
        me = obs.turn
        num_players = len(obs.players)
        opponents = []
        for offset in (1, 2, 3):
            if offset < num_players:
                target_seat = (me + offset) % num_players
                opponents.append(target_seat)
            else:
                opponents.append(None)
        return opponents

    def _extract_features(self, obs: Obs_PLAY, live_prob: float) -> List[float]:
        me = obs.turn
        my_p = obs.players[me]
        my_upg = my_p.upgrades

        features: List[float] = [
            live_prob,
            min(1.0, obs.rounds_remaining / 16.0),
            1.0 if obs.next_round == NextRound.LIVE else 0.0,
            1.0 if obs.next_round == NextRound.BLANK else 0.0,
            min(1.0, obs.session_no / 5.0),
            my_p.health / float(obs.max_health),
            min(1.0, my_upg.juice / 5.0),
            min(1.0, my_upg.mag_glass / 5.0),
            min(1.0, my_upg.hand_saw / 5.0),
            min(1.0, my_upg.pool_floatie / 5.0),
            min(1.0, my_upg.coffee / 5.0),
            1.0 if my_p.has_pool_floatie_on else 0.0,
        ]

        rel_opponents = self._get_relative_opponents(obs)
        for opp_seat in rel_opponents:
            if opp_seat is not None and opp_seat < len(obs.players):
                opp = obs.players[opp_seat]
                is_alive = 1.0 if opp.health > 0 else 0.0
                features.extend([
                    is_alive,
                    opp.health / float(obs.max_health) if is_alive else 0.0,
                    1.0 if opp.has_pool_floatie_on else 0.0,
                    min(1.0, opp.upgrades.hand_saw / 5.0),
                    min(1.0, opp.upgrades.juice / 5.0),
                    min(1.0, opp.upgrades.mag_glass / 5.0),
                ])
            else:
                features.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

        if getattr(self, "state_dim", 30) == 34:
            current_saw_damage = 2 if my_upg.hand_saw > 0 else 1
            for opp_seat in rel_opponents:
                if opp_seat is not None and opp_seat < len(obs.players):
                    opp = obs.players[opp_seat]
                    can_kill = 1.0 if (opp.health > 0 and opp.health <= current_saw_damage) else 0.0
                    features.append(can_kill)
                else:
                    features.append(0.0)

            next_threat = 0.0
            for opp_seat in rel_opponents:
                if opp_seat is not None and opp_seat < len(obs.players):
                    if obs.players[opp_seat].health > 0 and not obs.players[opp_seat].has_pool_floatie_on:
                        next_threat = 1.0
                        break
            features.append(next_threat)

        return features

    # -------------------------------------------------------------------------
    # Legal Action Masking
    # -------------------------------------------------------------------------
    def _get_legal_mask(self, obs: Obs_PLAY) -> List[bool]:
        mask = [False] * 11
        me = obs.turn
        my_p = obs.players[me]
        my_upg = my_p.upgrades
        rel_opponents = self._get_relative_opponents(obs)
        has_rounds = obs.rounds_remaining > 0

        # Action 0: Shoot Self
        if has_rounds:
            mask[0] = True

        # Actions 1..3: Shoot Opponents
        for idx, opp_seat in enumerate(rel_opponents):
            if opp_seat is not None and opp_seat < len(obs.players) and has_rounds:
                if obs.players[opp_seat].health > 0:
                    mask[1 + idx] = True

        # Action 4: JUICE
        if my_upg.juice > 0:
            mask[4] = True

        # Action 5: MAG_GLASS
        if my_upg.mag_glass > 0 and has_rounds and obs.next_round == NextRound.UNKNOWN:
            mask[5] = True

        # Action 6: HAND_SAW
        if my_upg.hand_saw > 0:
            mask[6] = True

        # Action 7: COFFEE
        if my_upg.coffee > 0 and has_rounds:
            mask[7] = True

        # Actions 8..10: POOL_FLOATIE
        if my_upg.pool_floatie > 0:
            for idx, opp_seat in enumerate(rel_opponents):
                if opp_seat is not None and opp_seat < len(obs.players):
                    opp = obs.players[opp_seat]
                    if opp.health > 0 and not opp.has_pool_floatie_on:
                        mask[8 + idx] = True

        return mask

    # -------------------------------------------------------------------------
    # Pure Python Forward Pass
    # -------------------------------------------------------------------------
    def _forward(self, x: List[float]) -> List[float]:
        # Layer 1
        h1 = []
        for j in range(len(self.b1)):
            val = self.b1[j]
            for i in range(len(x)):
                val += x[i] * self.W1[i][j]
            h1.append(val if val > 0.0 else 0.0)

        # Layer 2
        h2 = []
        for j in range(len(self.b2)):
            val = self.b2[j]
            for i in range(len(h1)):
                val += h1[i] * self.W2[i][j]
            h2.append(val if val > 0.0 else 0.0)

        # Output Layer
        q = []
        for j in range(len(self.b3)):
            val = self.b3[j]
            for i in range(len(h2)):
                val += h2[i] * self.W3[i][j]
            q.append(val)

        return q

    def _action_id_to_action(self, action_id: int, obs: Obs_PLAY) -> Action_PLAY:
        me = obs.turn
        rel_opponents = self._get_relative_opponents(obs)
        action = Action_PLAY()
        action.useUpgrade = None
        action.target = None

        if action_id == 0:
            action.action = ActionType.SHOOT
            action.target = me
        elif 1 <= action_id <= 3:
            action.action = ActionType.SHOOT
            action.target = rel_opponents[action_id - 1]
        elif action_id == 4:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.JUICE
        elif action_id == 5:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.MAG_GLASS
        elif action_id == 6:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.HAND_SAW
        elif action_id == 7:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.COFFEE
        elif 8 <= action_id <= 10:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.POOL_FLOATIE
            action.target = rel_opponents[action_id - 8]
        else:
            action.action = ActionType.SHOOT
            action.target = me

        return action

    # -------------------------------------------------------------------------
    # Play Decision
    # -------------------------------------------------------------------------
    def play(self, obs: Obs_PLAY) -> Action_PLAY:
        p_live = self._estimate_live_prob(obs)
        me = obs.turn
        my_p = obs.players[me]

        # Strategic Safety Overrides (Configurable)
        if self.enable_safety_overrides:
            # 1. Defensive heal: Always heal if injured to protect against 1-shot burst execution
            if self.enable_defensive_heal and my_p.health < obs.max_health and my_p.upgrades.juice > 0:
                action = Action_PLAY()
                action.action = ActionType.USE_UPGRADE
                action.useUpgrade = UpgradeType.JUICE
                return action

            # 2. 100% confirmed blank: Always shoot self for free turn
            if obs.next_round == NextRound.BLANK or p_live == 0.0:
                action = Action_PLAY()
                action.action = ActionType.SHOOT
                action.target = me
                return action

        # RL Policy Forward Pass
        if self.model_loaded:
            features = self._extract_features(obs, p_live)
            q_values = self._forward(features)
            legal_mask = self._get_legal_mask(obs)

            best_action_id = 0
            best_q = -1e9
            for i, (q_val, is_legal) in enumerate(zip(q_values, legal_mask)):
                if is_legal and q_val > best_q:
                    best_q = q_val
                    best_action_id = i

            return self._action_id_to_action(best_action_id, obs)

        # Baseline Fallback
        return self._rule_fallback_play(obs, p_live)

    def pick_upgrade(self, obs: Obs_PICK_UPGRADES) -> Action_PICK_UPGRADES:
        me = obs.turn
        my_player = obs.players[me]
        my_upg = my_player.upgrades
        my_hp = my_player.health
        avail = obs.available_upgrades

        scores = {
            UpgradeType.JUICE: 100.0,
            UpgradeType.MAG_GLASS: 95.0,
            UpgradeType.HAND_SAW: 85.0,
            UpgradeType.POOL_FLOATIE: 80.0,
            UpgradeType.COFFEE: 40.0,
        }

        missing_hp = obs.max_health - my_hp
        scores[UpgradeType.JUICE] += missing_hp * 25.0
        if my_upg.juice < 2:
            scores[UpgradeType.JUICE] += 30.0
        elif my_upg.juice >= 4:
            scores[UpgradeType.JUICE] -= 40.0

        if my_upg.mag_glass < 2:
            scores[UpgradeType.MAG_GLASS] += 20.0
        elif my_upg.mag_glass >= 4:
            scores[UpgradeType.MAG_GLASS] -= 40.0

        if my_upg.hand_saw < 2 and my_upg.mag_glass > 0:
            scores[UpgradeType.HAND_SAW] += 20.0
        elif my_upg.hand_saw >= 3:
            scores[UpgradeType.HAND_SAW] -= 50.0

        if my_upg.pool_floatie < 1:
            scores[UpgradeType.POOL_FLOATIE] += 15.0
        elif my_upg.pool_floatie >= 2:
            scores[UpgradeType.POOL_FLOATIE] -= 40.0

        if my_upg.coffee >= 2:
            scores[UpgradeType.COFFEE] -= 30.0

        avail_map = {
            UpgradeType.JUICE: avail.juice,
            UpgradeType.MAG_GLASS: avail.mag_glass,
            UpgradeType.HAND_SAW: avail.hand_saw,
            UpgradeType.POOL_FLOATIE: avail.pool_floatie,
            UpgradeType.COFFEE: avail.coffee,
        }

        best_upgrade = None
        best_score = -1e9
        for upg_type, count in avail_map.items():
            if count > 0:
                score = scores.get(upg_type, 0.0)
                if score > best_score:
                    best_score = score
                    best_upgrade = upg_type

        action = Action_PICK_UPGRADES()
        action.chosen_upgrade = best_upgrade or UpgradeType.JUICE
        return action

    def _rule_fallback_play(self, obs: Obs_PLAY, p_live: float) -> Action_PLAY:
        me = obs.turn
        my_player = obs.players[me]
        my_upg = my_player.upgrades
        my_health = my_player.health

        action = Action_PLAY()
        action.action = ActionType.SHOOT
        action.useUpgrade = None
        action.target = None

        if my_health < obs.max_health and my_upg.juice > 0:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.JUICE
            return action

        living = [i for i, p in enumerate(obs.players) if i != me and p.health > 0]
        target = living[0] if living else me

        if obs.next_round == NextRound.BLANK or p_live == 0.0:
            action.target = me
        else:
            action.target = target

        return action
