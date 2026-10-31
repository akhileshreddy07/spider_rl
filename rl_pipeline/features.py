"""Feature representation and legal-action masking for Buckshot Roulette.

Reuses the exact shell-probability formula from Spider-Sense and builds
normalized feature vectors (30-dim or enhanced 34-dim) from Obs_PLAY.
"""
from __future__ import annotations
from typing import List, Tuple, Optional
from schemas import (
    Obs_PLAY,
    NextRound,
    Action_PLAY,
    ActionType,
    UpgradeType,
)

# Dimensions
STATE_DIM_V1 = 30
STATE_DIM_V2 = 34
ACTION_DIM = 11


def estimate_live_prob(obs: Obs_PLAY) -> float:
    """Exact hypergeometric live-shell probability from Spider-Sense."""
    if obs.next_round == NextRound.LIVE:
        return 1.0
    if obs.next_round == NextRound.BLANK:
        return 0.0

    lives_consumed = obs.lives_shot + obs.ejections.lives_ejected
    blanks_consumed = obs.blanks_shot + obs.ejections.blanks_ejected

    remaining_live_pool = max(0, obs.lives_init - lives_consumed)
    remaining_blank_pool = max(0, obs.blanks_init - blanks_consumed)
    total_unobserved = remaining_live_pool + remaining_blank_pool

    if total_unobserved <= 0:
        return 0.5
    if remaining_live_pool == 0:
        return 0.0
    if remaining_blank_pool == 0:
        return 1.0

    return remaining_live_pool / total_unobserved


def get_relative_opponents(obs: Obs_PLAY) -> List[Optional[int]]:
    """Returns absolute seat indices for relative offsets +1, +2, +3."""
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


def extract_features(obs: Obs_PLAY, live_prob: Optional[float] = None, version: int = 2) -> List[float]:
    """Extracts a normalized feature vector from Obs_PLAY.
    
    version=1: 30 features
    version=2: 34 features (adds lethal kill opportunity and immediate next threat)
    """
    if live_prob is None:
        live_prob = estimate_live_prob(obs)

    me = obs.turn
    my_p = obs.players[me]
    my_upg = my_p.upgrades

    features: List[float] = [
        # Shell and environment features (5)
        float(live_prob),
        min(1.0, obs.rounds_remaining / 16.0),
        1.0 if obs.next_round == NextRound.LIVE else 0.0,
        1.0 if obs.next_round == NextRound.BLANK else 0.0,
        min(1.0, obs.session_no / 5.0),

        # Self features (7)
        my_p.health / float(obs.max_health),
        min(1.0, my_upg.juice / 5.0),
        min(1.0, my_upg.mag_glass / 5.0),
        min(1.0, my_upg.hand_saw / 5.0),
        min(1.0, my_upg.pool_floatie / 5.0),
        min(1.0, my_upg.coffee / 5.0),
        1.0 if my_p.has_pool_floatie_on else 0.0,
    ]

    # Opponent features for 3 relative seats (+1, +2, +3) -> 3 * 6 = 18 features
    rel_opponents = get_relative_opponents(obs)
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

    if version == 2:
        # 4 tactical strategic features:
        # 1-3. Lethal kill flags: Can opponent i be eliminated with current shot?
        # (Assuming baseline 1 damage, or 2 if hand saw owned)
        current_saw_damage = 2 if my_upg.hand_saw > 0 else 1
        for opp_seat in rel_opponents:
            if opp_seat is not None and opp_seat < len(obs.players):
                opp = obs.players[opp_seat]
                can_kill = 1.0 if (opp.health > 0 and opp.health <= current_saw_damage) else 0.0
                features.append(can_kill)
            else:
                features.append(0.0)

        # 4. Immediate threat: Is next actor in rotation an unskipped living opponent?
        next_threat = 0.0
        for opp_seat in rel_opponents:
            if opp_seat is not None and opp_seat < len(obs.players):
                if obs.players[opp_seat].health > 0 and not obs.players[opp_seat].has_pool_floatie_on:
                    next_threat = 1.0
                    break
        features.append(next_threat)

    expected_len = STATE_DIM_V2 if version == 2 else STATE_DIM_V1
    assert len(features) == expected_len, f"Expected {expected_len} features, got {len(features)}"
    return features


def get_legal_action_mask(obs: Obs_PLAY) -> List[bool]:
    """Generates a boolean mask of length ACTION_DIM representing valid actions."""
    mask = [False] * ACTION_DIM
    me = obs.turn
    my_p = obs.players[me]
    my_upg = my_p.upgrades
    rel_opponents = get_relative_opponents(obs)

    has_rounds = obs.rounds_remaining > 0

    # Action 0: Shoot Self (valid as long as gun has rounds)
    if has_rounds:
        mask[0] = True

    # Actions 1..3: Shoot Opponents
    for idx, opp_seat in enumerate(rel_opponents):
        if opp_seat is not None and opp_seat < len(obs.players) and has_rounds:
            if obs.players[opp_seat].health > 0:
                mask[1 + idx] = True

    # Action 4: Use JUICE (valid if owned)
    if my_upg.juice > 0:
        mask[4] = True

    # Action 5: Use MAG_GLASS (valid if owned, gun has rounds, and next round unknown)
    if my_upg.mag_glass > 0 and has_rounds and obs.next_round == NextRound.UNKNOWN:
        mask[5] = True

    # Action 6: Use HAND_SAW (valid if owned)
    if my_upg.hand_saw > 0:
        mask[6] = True

    # Action 7: Use COFFEE (valid if owned and gun has rounds)
    if my_upg.coffee > 0 and has_rounds:
        mask[7] = True

    # Actions 8..10: Use POOL_FLOATIE on Opponents
    if my_upg.pool_floatie > 0:
        for idx, opp_seat in enumerate(rel_opponents):
            if opp_seat is not None and opp_seat < len(obs.players):
                opp = obs.players[opp_seat]
                if opp.health > 0 and not opp.has_pool_floatie_on:
                    mask[8 + idx] = True

    return mask


def action_id_to_action(action_id: int, obs: Obs_PLAY) -> Action_PLAY:
    """Converts a discrete action index (0..10) into an Action_PLAY object."""
    me = obs.turn
    rel_opponents = get_relative_opponents(obs)
    action = Action_PLAY()
    action.useUpgrade = None
    action.target = None

    if action_id == 0:
        action.action = ActionType.SHOOT
        action.target = me
    elif 1 <= action_id <= 3:
        opp_seat = rel_opponents[action_id - 1]
        action.action = ActionType.SHOOT
        action.target = opp_seat
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
        opp_seat = rel_opponents[action_id - 8]
        action.action = ActionType.USE_UPGRADE
        action.useUpgrade = UpgradeType.POOL_FLOATIE
        action.target = opp_seat
    else:
        raise ValueError(f"Unknown action_id: {action_id}")

    return action
