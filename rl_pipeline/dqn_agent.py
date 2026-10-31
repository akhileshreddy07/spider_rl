"""Vectorized NumPy Deep Q-Network with Action Masking and Adam Optimizer.

Runs 100% locally on standard macOS CPU without heavy third-party dependencies,
and exports compact JSON weights compatible with the Python standard library.
"""
from __future__ import annotations
import json
import random
from collections import deque
from typing import List, Tuple, Optional
import numpy as np


class ReplayBuffer:
    def __init__(self, capacity: int = 50000):
        self.buffer = deque(maxlen=capacity)

    def push(self, state: List[float], action: int, reward: float,
             next_state: List[float], done: bool, next_mask: List[bool]):
        self.buffer.append((
            np.array(state, dtype=np.float32),
            action,
            float(reward),
            np.array(next_state, dtype=np.float32),
            done,
            np.array(next_mask, dtype=bool)
        ))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones, next_masks = zip(*batch)
        return (
            np.stack(states),
            np.array(actions, dtype=np.int64),
            np.array(rewards, dtype=np.float32),
            np.stack(next_states),
            np.array(dones, dtype=bool),
            np.stack(next_masks)
        )

    def __len__(self):
        return len(self.buffer)


class DQNAgent:
    def __init__(
        self,
        state_dim: int = 30,
        action_dim: int = 11,
        hidden_dim: int = 32,
        lr: float = 0.001,
        gamma: float = 0.95,
        epsilon_start: float = 1.0,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.9995,
        target_update_freq: int = 200,
        seed: int = 42,
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.hidden_dim = hidden_dim
        self.gamma = gamma
        self.lr = lr
        self.epsilon = epsilon_start
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.target_update_freq = target_update_freq
        self.train_step = 0

        self.rng = np.random.RandomState(seed)

        # Initialize network parameters using He / Kaiming normal initialization
        self.W1 = self.rng.randn(state_dim, hidden_dim).astype(np.float32) * np.sqrt(2.0 / state_dim)
        self.b1 = np.zeros(hidden_dim, dtype=np.float32)

        self.W2 = self.rng.randn(hidden_dim, hidden_dim).astype(np.float32) * np.sqrt(2.0 / hidden_dim)
        self.b2 = np.zeros(hidden_dim, dtype=np.float32)

        self.W3 = self.rng.randn(hidden_dim, action_dim).astype(np.float32) * np.sqrt(2.0 / hidden_dim)
        self.b3 = np.zeros(action_dim, dtype=np.float32)

        # Target network weights
        self.t_W1 = self.W1.copy()
        self.t_b1 = self.b1.copy()
        self.t_W2 = self.W2.copy()
        self.t_b2 = self.b2.copy()
        self.t_W3 = self.W3.copy()
        self.t_b3 = self.b3.copy()

        # Adam optimizer state
        self.m = {k: np.zeros_like(v) for k, v in self._params().items()}
        self.v = {k: np.zeros_like(v) for k, v in self._params().items()}
        self.beta1 = 0.9
        self.beta2 = 0.999
        self.eps = 1e-8
        self.opt_t = 0

    def _params(self):
        return {
            "W1": self.W1, "b1": self.b1,
            "W2": self.W2, "b2": self.b2,
            "W3": self.W3, "b3": self.b3,
        }

    def _forward(self, X: np.ndarray, W1, b1, W2, b2, W3, b3):
        z1 = X @ W1 + b1
        a1 = np.maximum(0.0, z1)
        z2 = a1 @ W2 + b2
        a2 = np.maximum(0.0, z2)
        q = a2 @ W3 + b3
        return z1, a1, z2, a2, q

    def predict_q(self, state: np.ndarray) -> np.ndarray:
        if state.ndim == 1:
            state = state[np.newaxis, :]
        _, _, _, _, q = self._forward(state, self.W1, self.b1, self.W2, self.b2, self.W3, self.b3)
        return q[0]

    def select_action(self, state: List[float], legal_mask: List[bool], evaluate: bool = False) -> int:
        legal_indices = [i for i, ok in enumerate(legal_mask) if ok]
        if not legal_indices:
            return 0  # Fallback to shoot self

        if not evaluate and self.rng.rand() < self.epsilon:
            return int(self.rng.choice(legal_indices))

        q_values = self.predict_q(np.array(state, dtype=np.float32))
        # Mask out illegal actions with a large negative value
        masked_q = np.full_like(q_values, -1e9)
        masked_q[legal_indices] = q_values[legal_indices]
        return int(np.argmax(masked_q))

    def update(self, replay_buffer: ReplayBuffer, batch_size: int = 64) -> Optional[float]:
        if len(replay_buffer) < batch_size:
            return None

        states, actions, rewards, next_states, dones, next_masks = replay_buffer.sample(batch_size)

        # 1. Target Q values: y = r + gamma * max_a' Q_target(s', a') [masked]
        _, _, _, _, target_q_next = self._forward(
            next_states, self.t_W1, self.t_b1, self.t_W2, self.t_b2, self.t_W3, self.t_b3
        )
        # Apply legal mask to target Q
        target_q_next[~next_masks] = -1e9
        max_target_q = np.max(target_q_next, axis=1)
        # If no legal next action, default to 0
        max_target_q = np.where(max_target_q < -1e8, 0.0, max_target_q)
        targets = rewards + (1.0 - dones) * self.gamma * max_target_q

        # 2. Current Q values forward pass
        z1, a1, z2, a2, q = self._forward(
            states, self.W1, self.b1, self.W2, self.b2, self.W3, self.b3
        )

        # 3. Compute loss and gradients
        # Gradient of MSE loss: dLoss/dQ = 2/N * (Q - target) for chosen action, 0 elsewhere
        batch_idx = np.arange(batch_size)
        chosen_q = q[batch_idx, actions]
        td_error = chosen_q - targets
        loss = float(np.mean(td_error ** 2))

        dq = np.zeros_like(q)
        dq[batch_idx, actions] = (2.0 / batch_size) * td_error
        dq = np.clip(dq, -1.0, 1.0)  # Gradient clipping for stability

        # Backpropagation
        dW3 = a2.T @ dq
        db3 = np.sum(dq, axis=0)

        da2 = dq @ self.W3.T
        dz2 = da2 * (z2 > 0)
        dW2 = a1.T @ dz2
        db2 = np.sum(dz2, axis=0)

        da1 = dz2 @ self.W2.T
        dz1 = da1 * (z1 > 0)
        dW1 = states.T @ dz1
        db1 = np.sum(dz1, axis=0)

        grads = {
            "W1": dW1, "b1": db1,
            "W2": dW2, "b2": db2,
            "W3": dW3, "b3": db3,
        }

        # 4. Adam Optimizer Step
        self.opt_t += 1
        params = self._params()
        for k in params:
            g = grads[k]
            self.m[k] = self.beta1 * self.m[k] + (1.0 - self.beta1) * g
            self.v[k] = self.beta2 * self.v[k] + (1.0 - self.beta2) * (g ** 2)
            m_hat = self.m[k] / (1.0 - self.beta1 ** self.opt_t)
            v_hat = self.v[k] / (1.0 - self.beta2 ** self.opt_t)
            params[k] -= self.lr * m_hat / (np.sqrt(v_hat) + self.eps)

        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        self.train_step += 1

        # Periodically update target network
        if self.train_step % self.target_update_freq == 0:
            self.t_W1 = self.W1.copy()
            self.t_b1 = self.b1.copy()
            self.t_W2 = self.W2.copy()
            self.t_b2 = self.b2.copy()
            self.t_W3 = self.W3.copy()
            self.t_b3 = self.b3.copy()

        return loss

    def export_weights(self, path: str):
        """Exports weights into standard JSON for pure Python standard library inference."""
        data = {
            "W1": self.W1.tolist(),
            "b1": self.b1.tolist(),
            "W2": self.W2.tolist(),
            "b2": self.b2.tolist(),
            "W3": self.W3.tolist(),
            "b3": self.b3.tolist(),
            "metadata": {
                "state_dim": self.state_dim,
                "hidden_dim": self.hidden_dim,
                "action_dim": self.action_dim,
                "train_steps": self.train_step,
            }
        }
        with open(path, "w") as f:
            json.dump(data, f)
