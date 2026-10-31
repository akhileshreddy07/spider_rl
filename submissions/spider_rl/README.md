# Spider-RL: Action-Masked Deep Q-Network

Submission for CSES Arcade RL Hackathon (Buckshot Roulette).

## Overview
Spider-RL combines the exact Bayesian probability tracking of Spider-Sense with a genuine Action-Masked Deep Q-Network (DQN). The model evaluates tactical item usage, risk-reward trade-offs on uncertain shells, and multi-player target prioritization.

## Model Architecture
- **Type:** Deep Q-Network (DQN) with target network and experience replay.
- **Layers:** Multi-Layer Perceptron (MLP)
  - Input Layer: 30 numerical features
  - Hidden Layer 1: 32 units, ReLU activation
  - Hidden Layer 2: 32 units, ReLU activation
  - Output Layer: 11 Q-values (one for each discrete play action)
- **Model Size:** 50 KB (plain JSON format), $\approx 2{,}000$ parameters.

## State Representation (30 Normalized Features)
1. **Shell State (5 features):**
   - `live_prob`: Exact hypergeometric probability of next shell being live $[0.0, 1.0]$.
   - `rounds_remaining / 16.0`: Ammunition left in the barrel.
   - `is_known_live`: $1.0$ if revealed LIVE via Magnifying Glass, else $0.0$.
   - `is_known_blank`: $1.0$ if revealed BLANK via Magnifying Glass, else $0.0$.
   - `session_no / 5.0`: Current game session.
2. **Self State (7 features):**
   - `health / max_health`: Player's current health fraction.
   - Upgrades held: `juice`, `mag_glass`, `hand_saw`, `pool_floatie`, `coffee` (normalized by 5.0).
   - `has_pool_floatie_on`: $1.0$ if skipped next turn, else $0.0$.
3. **Opponents State (18 features):**
   - For relative opponents $+1, +2, +3$ in turn order:
     - `is_alive`, `health_ratio`, `has_pool_floatie_on`, `hand_saw_ratio`, `juice_ratio`, `mag_glass_ratio`.

## Action Space (11 Discrete Play Actions)
- `0`: Shoot Self
- `1`: Shoot Opponent +1 (immediate next player in rotation)
- `2`: Shoot Opponent +2
- `3`: Shoot Opponent +3
- `4`: Use `JUICE`
- `5`: Use `MAG_GLASS`
- `6`: Use `HAND_SAW`
- `7`: Use `COFFEE`
- `8`: Use `POOL_FLOATIE` on Opponent +1
- `9`: Use `POOL_FLOATIE` on Opponent +2
- `10`: Use `POOL_FLOATIE` on Opponent +3

### Action Masking
Actions that violate the official game rules (e.g. using an upgrade not owned, shooting an eliminated player, or using a floatie on an already skipped opponent) are masked with $Q(s, a) = -10^9$. This guarantees zero illegal action faults.

## Reward Function
- **Terminal Placement Points:** $+3.0$ (1st place), $+1.0$ (2nd place), $-1.0$ (3rd place), $-3.0$ (4th place).
- **Damage Dealt:** $+0.3 \times \Delta \text{enemy\_hp}$.
- **Damage Taken:** $-0.4 \times \Delta \text{my\_hp}$.
- **Turn Retention:** $+0.25$ for successfully shooting self with a blank.
- **Healing:** $+0.2$ for successful Juice health recovery.

## Training Process
- Offline training on host machine via `rl_pipeline/train.py`.
- Replay buffer size: 40,000 transitions.
- Optimization: Adam optimizer ($\text{lr}=10^{-3}$, $\beta_1=0.9, \beta_2=0.999$) with Huber/MSE loss.
- Target network updated every 150 gradient steps.

## Inference Process (Submission Runtime)
- **Standard Library Only:** Zero external dependencies (`math`, `json`, `random` only).
- **Execution Speed:** Forward pass computed in $<0.08\text{ ms}$ per decision (well below the $50\text{ ms}$ limit).
- **Memory Footprint:** $\approx 50\text{ KB}$, well within the $128\text{ MB}$ container memory limit.
- **Reliable Fallback:** If weights are missing or corrupted, the bot safely falls back to Spider-Sense rule logic.
