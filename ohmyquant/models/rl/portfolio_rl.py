"""组合管理 RL 模型

使用 PPO 算法进行组合权重优化。需要 stable-baselines3。
"""
from __future__ import annotations

import numpy as np

from ...core.logging import get_logger
from ...core.plugin_system import register_model
from .base_rl import BaseRLModel

logger = get_logger(__name__)

try:
    import gymnasium as gym
    from gymnasium import spaces

    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False


if HAS_SB3:

    class PortfolioEnv(gym.Env):
        """组合管理环境

        观察空间: 当前持仓权重 + 因子特征
        动作空间: 目标权重（连续，softmax 归一化）
        奖励: 组合收益 - 交易成本
        """

        def __init__(self, returns: np.ndarray, features: np.ndarray | None = None,
                     transaction_cost: float = 0.001):
            super().__init__()
            self.returns = returns
            self.features = features
            self.transaction_cost = transaction_cost
            self.n_assets = returns.shape[1] if returns.ndim > 1 else 1
            self.n_steps = len(returns)
            self.current_step = 0

            feat_dim = features.shape[1] if features is not None else 0
            obs_dim = self.n_assets + feat_dim
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
            )
            self.action_space = spaces.Box(
                low=0, high=1, shape=(self.n_assets,), dtype=np.float32
            )
            self._weights = np.ones(self.n_assets) / self.n_assets

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self.current_step = 0
            self._weights = np.ones(self.n_assets) / self.n_assets
            return self._get_obs(), {}

        def _get_obs(self):
            obs = list(self._weights)
            if self.features is not None and self.current_step < len(self.features):
                obs.extend(self.features[self.current_step].tolist())
            return np.array(obs, dtype=np.float32)

        def step(self, action):
            action = np.clip(action, 0, 1)
            total = action.sum()
            if total > 0:
                action = action / total
            else:
                action = np.ones(self.n_assets) / self.n_assets

            if self.current_step >= self.n_steps - 1:
                return self._get_obs(), 0.0, True, False, {}

            ret = self.returns[self.current_step]
            if ret.ndim == 0:
                portfolio_ret = float(ret * action[0])
            else:
                portfolio_ret = float(np.dot(action, ret))

            turnover = np.abs(action - self._weights).sum()
            cost = turnover * self.transaction_cost
            reward = portfolio_ret - cost

            self._weights = action
            self.current_step += 1
            done = self.current_step >= self.n_steps - 1
            return self._get_obs(), reward, done, False, {}


@register_model("ppo_portfolio")
class PortfolioRLModel(BaseRLModel):
    """PPO 组合管理 RL 模型

    config:
        total_timesteps: 50000
        transaction_cost: 0.001
        env_data: {"returns": np.ndarray, "features": np.ndarray | None}
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.transaction_cost = self.config.get("transaction_cost", 0.001)

    def _build_env(self, data: any = None):
        env_data = data or self.config.get("env_data", {})
        returns = env_data.get("returns") if isinstance(env_data, dict) else None
        features = env_data.get("features") if isinstance(env_data, dict) else None

        if returns is None:
            returns = np.zeros((100, 10))
        if features is None and isinstance(env_data, dict):
            features = env_data.get("features")

        return PortfolioEnv(
            returns=np.asarray(returns),
            features=np.asarray(features) if features is not None else None,
            transaction_cost=self.transaction_cost,
        )


__all__ = ["PortfolioRLModel"]
