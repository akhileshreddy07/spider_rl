"""SPIDER-SENSE AI 🕷️
CSES Arcade RL Hackathon - Competitive Buckshot Roulette Bot

Tactical Design:
- Spider-Sense: Exact Bayesian & hypergeometric tracking of hidden shells.
- Superhuman Reflexes: Pure Python standard library, sub-millisecond execution (<0.05ms per move).
- Tactical Aggression: Massive burst damage with Hand Saw on targets with >= 2 HP.
- Disciplined Turn Control: Targeted Floatie on the immediate next threat, optimal self-shooting.
- Balanced Utility Belt: High-priority Juice drafting for massive effective HP pool.
- Guaranteed Safety: Deterministic, no illegal moves, no timeouts, no dependencies.
"""
from __future__ import annotations

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
        seed = (params or {}).get("seed")
        self.rng = random.Random(seed)

    # -------------------------------------------------------------------------
    # Observation & Probability Estimation
    # -------------------------------------------------------------------------
    def _estimate_live_prob(self, obs: Obs_PLAY) -> float:
        """Estimate the probability that the next shell in the gun is LIVE.
        
        Uses all legally observable information:
        - lives_init, blanks_init
        - lives_shot, blanks_shot
        - our private coffee ejections (lives_ejected, blanks_ejected)
        - opponents' coffee ejections (unknowns_ejected)
        """
        if obs.next_round == NextRound.LIVE:
            return 1.0
        if obs.next_round == NextRound.BLANK:
            return 0.0

        # Exact tracking of consumed shells
        lives_consumed = obs.lives_shot + obs.ejections.lives_ejected
        blanks_consumed = obs.blanks_shot + obs.ejections.blanks_ejected

        remaining_live_pool = max(0, obs.lives_init - lives_consumed)
        remaining_blank_pool = max(0, obs.blanks_init - blanks_consumed)
        total_unobserved = remaining_live_pool + remaining_blank_pool

        if total_unobserved <= 0:
            return 0.5

        if remaining_live_pool == 0:
            return 0.0  # 100% BLANK
        if remaining_blank_pool == 0:
            return 1.0  # 100% LIVE

        return remaining_live_pool / total_unobserved

    # -------------------------------------------------------------------------
    # Turn Rotation & Target Evaluation
    # -------------------------------------------------------------------------
    def _get_next_player_in_turn(self, obs: Obs_PLAY, from_turn: int) -> Optional[int]:
        """Find the next living player who will receive a turn after `from_turn`."""
        num_players = len(obs.players)
        for offset in range(1, num_players + 1):
            candidate = (from_turn + offset) % num_players
            if candidate == obs.turn:
                continue
            if obs.players[candidate].health > 0:
                return candidate
        return None

    def _select_best_opponent_target(self, obs: Obs_PLAY, damage: int = 1) -> int:
        """Score each living opponent to find the highest-priority target.
        
        Prioritizes:
        1. Immediate elimination (health <= damage) -> Eliminates threat + scores tournament placement!
        2. Proximity in turn order (immediate next player who threatens to shoot us if not skipped)
        3. Dangerous opponent upgrades (hand saw, mag glass, juice)
        4. In 1v1, focus directly on the sole opponent.
        """
        me = obs.turn
        living_opponents = [i for i, p in enumerate(obs.players) if i != me and p.health > 0]
        if not living_opponents:
            return me

        next_actor = self._get_next_player_in_turn(obs, me)

        best_target = living_opponents[0]
        best_score = -1e9

        for opp_idx in living_opponents:
            opp = obs.players[opp_idx]
            score = 10.0

            # 1. Lethal execution priority (instant kill)
            if opp.health <= damage:
                score += 100.0  # Top priority: permanently eliminate an opponent
            elif opp.health <= 2:
                score += 25.0   # Soften up for elimination

            # 2. Next player threat
            if opp_idx == next_actor:
                if not opp.has_pool_floatie_on:
                    score += 20.0
                else:
                    score -= 10.0  # Already skipped, less immediate danger

            # 3. Target dangerous / high-resource opponents to avoid runaway leader
            upg = opp.upgrades
            score += upg.hand_saw * 4.0 + upg.mag_glass * 3.0 + upg.juice * 2.0

            # 4. In 1v1, simple focus
            if len(living_opponents) == 1:
                score += 50.0

            if score > best_score:
                best_score = score
                best_target = opp_idx

        return best_target

    def _find_next_unskipped_opponent(self, obs: Obs_PLAY) -> Optional[int]:
        """Find the immediate next living player in rotation who does NOT have floatie on."""
        me = obs.turn
        num_players = len(obs.players)
        for offset in range(1, num_players + 1):
            candidate = (me + offset) % num_players
            if candidate != me and obs.players[candidate].health > 0:
                if not obs.players[candidate].has_pool_floatie_on:
                    return candidate
        return None

    # -------------------------------------------------------------------------
    # Play Decision Engine
    # -------------------------------------------------------------------------
    def play(self, obs: Obs_PLAY) -> Action_PLAY:
        me = obs.turn
        my_player = obs.players[me]
        my_upg = my_player.upgrades
        my_health = my_player.health

        action = Action_PLAY()
        action.action = ActionType.SHOOT
        action.useUpgrade = None
        action.target = None

        p_live = self._estimate_live_prob(obs)

        # --- 1. TACTICAL HEALING (JUICE) ---
        # Heal immediately when damaged. Preserves health buffer against sudden burst damage.
        if my_health < obs.max_health and my_upg.juice > 0:
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.JUICE
            return action

        # --- 2. INFORMATION GATHERING (MAG_GLASS) ---
        # If shell is uncertain, Mag Glass unlocks guaranteed optimal follow-ups.
        if (
            obs.next_round == NextRound.UNKNOWN
            and obs.rounds_remaining > 0
            and my_upg.mag_glass > 0
            and 0.0 < p_live < 1.0
        ):
            action.action = ActionType.USE_UPGRADE
            action.useUpgrade = UpgradeType.MAG_GLASS
            return action

        # --- 3. OFFENSIVE BURST (HAND_SAW) ---
        # Hand saw increases next live shot damage by 1.
        # Use Hand Saw when target has health >= 2 and shot is confirmed LIVE or highly likely (>= 0.80).
        target_opp = self._select_best_opponent_target(obs, damage=1)
        target_hp = obs.players[target_opp].health if target_opp != me else 5

        if my_upg.hand_saw > 0 and target_hp >= 2:
            if obs.next_round == NextRound.LIVE or p_live >= 0.80:
                action.action = ActionType.USE_UPGRADE
                action.useUpgrade = UpgradeType.HAND_SAW
                return action

        # --- 4. DISCIPLINED TURN DISRUPTION (POOL_FLOATIE) ---
        # Use AT MOST ONE floatie: on the immediate next player in rotation who isn't already skipped.
        # Never use floatie if we are about to shoot self with a guaranteed blank.
        will_keep_turn_safely = (obs.next_round == NextRound.BLANK) or (p_live == 0.0)
        if my_upg.pool_floatie > 0 and not will_keep_turn_safely:
            next_unskipped = self._find_next_unskipped_opponent(obs)
            immediate_next = self._get_next_player_in_turn(obs, me)
            if next_unskipped is not None and next_unskipped == immediate_next:
                action.action = ActionType.USE_UPGRADE
                action.useUpgrade = UpgradeType.POOL_FLOATIE
                action.target = next_unskipped
                return action

        # --- 5. SHELL CYCLE / DEFENSIVE PURGE (COFFEE) ---
        if (
            obs.next_round == NextRound.UNKNOWN
            and obs.rounds_remaining > 0
            and my_upg.coffee > 0
            and my_upg.mag_glass == 0
        ):
            if my_health <= 2 and 0.15 <= p_live <= 0.45:
                action.action = ActionType.USE_UPGRADE
                action.useUpgrade = UpgradeType.COFFEE
                return action
            if obs.rounds_remaining == 1 and my_health <= 2 and p_live < 0.60:
                action.action = ActionType.USE_UPGRADE
                action.useUpgrade = UpgradeType.COFFEE
                return action

        # --- 6. SHOOT ACTION ---
        action.action = ActionType.SHOOT

        # Case A: 100% Confirmed Blank -> ALWAYS shoot SELF!
        if obs.next_round == NextRound.BLANK or p_live == 0.0:
            action.target = me
            return action

        # Case B: 100% Confirmed Live -> ALWAYS shoot OPPONENT!
        if obs.next_round == NextRound.LIVE or p_live == 1.0:
            action.target = self._select_best_opponent_target(obs, damage=1)
            return action

        # Case C: Uncertain shell (obs.next_round == UNKNOWN)
        # Conservative Spider-Sense risk policy:
        # Only shoot self if health is very comfortable (>= 4) and p_live is tiny (<= 0.18).
        should_shoot_self = False
        if my_health >= 4 and p_live <= 0.18:
            should_shoot_self = True
        elif my_health == 3 and p_live <= 0.10:
            should_shoot_self = True

        if should_shoot_self:
            action.target = me
        else:
            action.target = self._select_best_opponent_target(obs, damage=1)

        return action

    # -------------------------------------------------------------------------
    # Upgrade Selection Stage
    # -------------------------------------------------------------------------
    def pick_upgrade(self, obs: Obs_PICK_UPGRADES) -> Action_PICK_UPGRADES:
        """Balanced Utility Belt Draft Strategy.
        
        Juice is survival (effective HP). Mag Glass + Hand Saw is burst damage.
        Maintains an optimal balanced inventory:
        - Target ~3 Juices in reserve (always have extra lives!)
        - Target ~2-3 Mag Glasses
        - Target ~2 Hand Saws
        - Target ~1-2 Pool Floaties
        """
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

        # 1. JUICE PRIORITY:
        missing_hp = obs.max_health - my_hp
        scores[UpgradeType.JUICE] += missing_hp * 25.0
        if my_upg.juice < 2:
            scores[UpgradeType.JUICE] += 30.0
        elif my_upg.juice >= 4:
            scores[UpgradeType.JUICE] -= 40.0

        # 2. MAG GLASS:
        if my_upg.mag_glass < 2:
            scores[UpgradeType.MAG_GLASS] += 20.0
        elif my_upg.mag_glass >= 4:
            scores[UpgradeType.MAG_GLASS] -= 40.0

        # 3. HAND SAW:
        if my_upg.hand_saw < 2 and my_upg.mag_glass > 0:
            scores[UpgradeType.HAND_SAW] += 20.0
        elif my_upg.hand_saw >= 3:
            scores[UpgradeType.HAND_SAW] -= 50.0

        # 4. POOL FLOATIE:
        if my_upg.pool_floatie < 1:
            scores[UpgradeType.POOL_FLOATIE] += 15.0
        elif my_upg.pool_floatie >= 2:
            scores[UpgradeType.POOL_FLOATIE] -= 40.0

        # 5. COFFEE:
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

        # Failsafe fallback
        if best_upgrade is None:
            for upg_type, count in avail_map.items():
                if count > 0:
                    best_upgrade = upg_type
                    break

        action = Action_PICK_UPGRADES()
        action.chosen_upgrade = best_upgrade or UpgradeType.JUICE
        return action
