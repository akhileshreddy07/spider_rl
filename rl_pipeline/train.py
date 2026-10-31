"""Rigorous Multi-Agent RL Training Pipeline for Buckshot Roulette.

Supports:
- Reward Configurations: 'terminal_only', 'terminal_shaped', 'baseline_v1'
- Opponent Mixtures: 'mixed', 'spider_sense', 'random', 'self_play'
- Episodic Return-to-Go Credit Assignment (resolves multi-step credit problem)
- Regular held-out evaluation intervals and checkpointing
"""
from __future__ import annotations
import os
import sys
import random
from typing import List, Optional, Dict, Tuple
import numpy as np

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import game_API as api
from schemas import Stage, ActionType, UpgradeType, Action_PICK_UPGRADES, Action_PLAY
from engine.scoring import placement_points
from rl_pipeline.features import (
    extract_features,
    get_legal_action_mask,
    action_id_to_action,
    STATE_DIM_V1,
    STATE_DIM_V2,
    ACTION_DIM,
)
from rl_pipeline.dqn_agent import DQNAgent, ReplayBuffer
from rl_pipeline.opponents import ConservativeBot, AggressiveBot, SpiderSenseBot


def run_random_play(obs, rng: random.Random) -> Action_PLAY:
    me = obs.turn
    action = Action_PLAY()
    action.useUpgrade = None
    action.target = None
    mine = obs.players[me].upgrades

    if mine.juice > 0 and obs.players[me].health < obs.max_health and rng.random() < 0.5:
        action.action = ActionType.USE_UPGRADE
        action.useUpgrade = UpgradeType.JUICE
        return action

    action.action = ActionType.SHOOT
    others = [i for i, p in enumerate(obs.players) if i != me and p.health > 0]
    if rng.random() < 0.2:
        action.target = me
    elif others:
        action.target = rng.choice(others)
    else:
        action.target = me
    return action


def run_default_pick(obs) -> Action_PICK_UPGRADES:
    action = Action_PICK_UPGRADES()
    avail = obs.available_upgrades
    for upg, name in (
        (UpgradeType.JUICE, "juice"),
        (UpgradeType.MAG_GLASS, "mag_glass"),
        (UpgradeType.HAND_SAW, "hand_saw"),
        (UpgradeType.POOL_FLOATIE, "pool_floatie"),
        (UpgradeType.COFFEE, "coffee"),
    ):
        if getattr(avail, name, 0) > 0:
            action.chosen_upgrade = upg
            return action
    action.chosen_upgrade = UpgradeType.JUICE
    return action


def get_match_placements(state: api.GameState) -> List[int]:
    alive = sorted(
        (i for i, p in enumerate(state.players) if p.health > 0),
        key=lambda i: (-state.players[i].health, i)
    )
    placements = [0] * len(state.players)
    for place, seat in enumerate(alive + list(reversed(state.elimination_order)), start=1):
        placements[seat] = place
    return placements


def evaluate_agent(agent: DQNAgent, num_matches: int = 50, seed: int = 9999, feature_version: int = 2) -> Dict[str, float]:
    """Runs held-out evaluation against SpiderSense + 2 RandomBots."""
    rng = random.Random(seed)
    spider_bot = SpiderSenseBot({"seed": seed})
    total_pts = 0.0
    wins = 0
    places = [0, 0, 0, 0]

    for m in range(num_matches):
        m_seed = rng.randint(0, 10000000)
        state = api.initGame(seed=m_seed, num_players=4)

        while not state.game_over:
            if state.stage == Stage.PICK_UPGRADE:
                obs_pick = api.upgrade_observation(state)
                api.step_PICK_UPGRADE(state, run_default_pick(obs_pick))
                continue

            obs = api.play_observation(state)
            curr = state.turn

            if curr == 0:
                s = extract_features(obs, version=feature_version)
                mask = get_legal_action_mask(obs)
                a_id = agent.select_action(s, mask, evaluate=True)
                act = action_id_to_action(a_id, obs)
                api.step_PLAY(state, act)
            elif curr == 1:
                act = spider_bot.play(obs)
                api.step_PLAY(state, act)
            else:
                act = run_random_play(obs, rng)
                api.step_PLAY(state, act)

        placements = get_match_placements(state)
        p = placements[0]
        places[p - 1] += 1
        pts = placement_points(p, 4)
        total_pts += pts
        if p == 1:
            wins += 1

    return {
        "avg_points": total_pts / num_matches,
        "win_rate": wins / num_matches,
        "avg_place": sum((i + 1) * count for i, count in enumerate(places)) / num_matches,
        "first_rate": places[0] / num_matches,
        "fourth_rate": places[3] / num_matches,
    }


def train_dqn(
    total_matches: int = 1500,
    batch_size: int = 64,
    learning_rate: float = 0.001,
    reward_mode: str = "terminal_shaped",  # 'terminal_only', 'terminal_shaped', 'baseline_v1'
    opponent_mode: str = "mixed",          # 'mixed', 'spider_sense', 'random'
    feature_version: int = 2,              # 1 (30 dims), 2 (34 dims)
    hidden_dim: int = 32,
    export_path: Optional[str] = None,
    checkpoint_dir: Optional[str] = None,
    seed: int = 42,
    log_interval: int = 250,
    eval_interval: int = 500,
) -> Tuple[DQNAgent, List[Dict]]:
    """Runs a controlled training experiment with logging and checkpoints."""
    rng = random.Random(seed)
    np.random.seed(seed)

    state_dim = STATE_DIM_V2 if feature_version == 2 else STATE_DIM_V1
    agent = DQNAgent(
        state_dim=state_dim,
        action_dim=ACTION_DIM,
        hidden_dim=hidden_dim,
        lr=learning_rate,
        gamma=0.95,
        epsilon_start=1.0,
        epsilon_min=0.05,
        epsilon_decay=0.9994,
        target_update_freq=150,
        seed=seed,
    )
    buffer = ReplayBuffer(capacity=50000)

    # Opponent pool
    spider_bot = SpiderSenseBot({"seed": seed})
    cons_bot = ConservativeBot(seed)
    agg_bot = AggressiveBot(seed)

    eval_history = []
    total_points = 0.0
    wins = 0

    print(f"=== DQN Training Run ===")
    print(f"Matches: {total_matches} | Reward: {reward_mode} | Opponents: {opponent_mode} | Features: {state_dim}D | Hidden: {hidden_dim}")

    for match_idx in range(1, total_matches + 1):
        num_players = 4
        m_seed = rng.randint(0, 10000000)
        state = api.initGame(seed=m_seed, num_players=num_players)

        # Record agent transitions during this episode: [(s, a, step_r, s_next, mask_next)]
        episode_transitions = []
        last_s = None
        last_a = None
        last_r = 0.0

        step_count = 0
        max_steps = 300

        while not state.game_over and step_count < max_steps:
            step_count += 1
            curr_turn = state.turn
            stage = state.stage

            if stage == Stage.PICK_UPGRADE:
                obs_pick = api.upgrade_observation(state)
                pick_action = run_default_pick(obs_pick)
                try:
                    api.step_PICK_UPGRADE(state, pick_action)
                except ValueError:
                    pass
                continue

            obs = api.play_observation(state)

            if curr_turn == 0:
                s = extract_features(obs, version=feature_version)
                mask = get_legal_action_mask(obs)

                if last_s is not None:
                    episode_transitions.append((last_s, last_a, last_r, s, mask))
                    last_s = None
                    last_a = None
                    last_r = 0.0

                action_id = agent.select_action(s, mask, evaluate=False)
                action_obj = action_id_to_action(action_id, obs)

                prev_my_hp = obs.players[0].health
                prev_opp_hp = sum(p.health for i, p in enumerate(obs.players) if i != 0)

                try:
                    api.step_PLAY(state, action_obj)
                    step_r = 0.0

                    if reward_mode == "terminal_shaped":
                        curr_my_hp = state.players[0].health
                        curr_opp_hp = sum(p.health for i, p in enumerate(state.players) if i != 0)
                        # Modest non-distorting shaping
                        if curr_opp_hp < prev_opp_hp:
                            step_r += 0.10 * (prev_opp_hp - curr_opp_hp)
                        if curr_my_hp < prev_my_hp:
                            step_r -= 0.15 * (prev_my_hp - curr_my_hp)
                        if action_id == 4 and curr_my_hp > prev_my_hp:
                            step_r += 0.05
                    elif reward_mode == "baseline_v1":
                        curr_my_hp = state.players[0].health
                        curr_opp_hp = sum(p.health for i, p in enumerate(state.players) if i != 0)
                        if curr_opp_hp < prev_opp_hp:
                            step_r += 0.3 * (prev_opp_hp - curr_opp_hp)
                        if curr_my_hp < prev_my_hp:
                            step_r -= 0.4 * (prev_my_hp - curr_my_hp)
                        if action_id == 4 and curr_my_hp > prev_my_hp:
                            step_r += 0.2
                        if action_id == 0 and curr_my_hp == prev_my_hp and state.turn == 0 and not state.game_over:
                            step_r += 0.25

                    last_s = s
                    last_a = action_id
                    last_r = step_r

                except ValueError:
                    episode_transitions.append((s, action_id, -1.0, s, mask))

            else:
                # Opponent turn
                if opponent_mode == "mixed":
                    if curr_turn == 1:
                        opp_act = spider_bot.play(obs)
                    elif curr_turn == 2:
                        opp_act = cons_bot.play(obs) if (match_idx % 2 == 0) else agg_bot.play(obs)
                    else:
                        opp_act = run_random_play(obs, rng)
                elif opponent_mode == "spider_sense":
                    opp_act = spider_bot.play(obs)
                else:
                    opp_act = run_random_play(obs, rng)

                try:
                    api.step_PLAY(state, opp_act)
                except ValueError:
                    alive_others = [i for i, p in enumerate(state.players) if i != curr_turn and p.health > 0]
                    target = rng.choice(alive_others) if alive_others else curr_turn
                    fb = Action_PLAY()
                    fb.action = ActionType.SHOOT
                    fb.useUpgrade = None
                    fb.target = target
                    api.step_PLAY(state, fb)

            if len(buffer) >= batch_size and step_count % 2 == 0:
                agent.update(buffer, batch_size=batch_size)

        # Episode Complete: Evaluate Terminal Points
        placements = get_match_placements(state)
        p = placements[0]
        pts = float(placement_points(p, num_players))
        total_points += pts
        if p == 1:
            wins += 1

        if last_s is not None:
            dummy_next_s = [0.0] * state_dim
            dummy_mask = [False] * ACTION_DIM
            episode_transitions.append((last_s, last_a, last_r, dummy_next_s, dummy_mask))

        # Push episode transitions to replay buffer with proper episodic credit
        if episode_transitions:
            T = len(episode_transitions)
            for t, (s_t, a_t, r_t, s_next, mask_next) in enumerate(episode_transitions):
                is_terminal = (t == T - 1)
                if reward_mode == "baseline_v1":
                    # Old v1 behavior: only last step gets half terminal reward
                    rew = (r_t + (pts * 0.5)) if is_terminal else r_t
                else:
                    # Return-to-go credit assignment:
                    # Every action shares in the terminal match success discounted by how far back it occurred
                    discount = 0.95 ** (T - 1 - t)
                    rew = r_t + (discount * pts)

                buffer.push(s_t, a_t, rew, s_next, is_terminal, mask_next)

        # Logging & periodic evaluation
        if match_idx % log_interval == 0:
            avg_pts = total_points / match_idx
            win_rate = wins / match_idx
            print(f"Match {match_idx:5d}/{total_matches} | WinRate: {win_rate:6.2%} | AvgPts: {avg_pts:+5.2f} | Eps: {agent.epsilon:.3f} | Buf: {len(buffer)}")

        if match_idx % eval_interval == 0:
            eval_res = evaluate_agent(agent, num_matches=60, seed=12345 + match_idx, feature_version=feature_version)
            eval_history.append({"match": match_idx, **eval_res})
            print(f"--> EVAL at {match_idx}: AvgPts: {eval_res['avg_points']:+.3f} | WinRate: {eval_res['win_rate']:.1%} | 4thRate: {eval_res['fourth_rate']:.1%}")

            if checkpoint_dir:
                os.makedirs(checkpoint_dir, exist_ok=True)
                ckpt_path = os.path.join(checkpoint_dir, f"ckpt_match_{match_idx}.json")
                agent.export_weights(ckpt_path)

    if export_path:
        os.makedirs(os.path.dirname(os.path.abspath(export_path)), exist_ok=True)
        agent.export_weights(export_path)
        print(f"Exported final model weights to {export_path}")

    return agent, eval_history
