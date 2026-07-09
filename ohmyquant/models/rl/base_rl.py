"""强化学习基类

封装 RL 环境、训练、推理。需要 stable-baselines3（可选依赖）。
"""
from __future__ import annotations

import numpy as np

from ...core.logging import get_logger
from ..base import Model

logger = get_logger(__name__)

try:
    import gymnasium as gym
    from stable_baselines3 import PPO

    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False
    logger.info("stable-baselines3 未安装，RL 模型不可用。请运行: pip install stable-baselines3 gymnasium")


class BaseRLModel(Model):
    """强化学习基类

    子类需实现 _build_env() 返回 gym.Env。
    config:
        total_timesteps: 10000
        learning_rate: 0.0003
        n_steps: 2048
        batch_size: 64
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        if not HAS_SB3:
            raise ImportError(
                "stable-baselines3 未安装，请运行: pip install stable-baselines3 gymnasium"
            )
        self.total_timesteps = self.config.get("total_timesteps", 10000)
        self.learning_rate = self.config.get("learning_rate", 0.0003)
        self.n_steps = self.config.get("n_steps", 2048)
        self.batch_size = self.config.get("batch_size", 64)
        self.model = None
        self._env = None

    def _build_env(self, data: any = None):
        """子类实现：构建 RL 环境"""
        raise NotImplementedError

    def fit(
        self,
        X: np.ndarray | None = None,
        y: np.ndarray | None = None,
        groups: np.ndarray | None = None,
        val_data: tuple | None = None,
    ) -> None:
        """训练 RL 模型

        对于 RL，X/y 不是主要输入，环境才是。
        子类应通过 config 或 _build_env 的 data 参数传入环境数据。
        """
        env = self._build_env(self.config.get("env_data"))
        self._env = env

        self.model = PPO(
            "MlpPolicy",
            env,
            learning_rate=self.learning_rate,
            n_steps=self.n_steps,
            batch_size=self.batch_size,
            verbose=0,
        )
        self.model.learn(total_timesteps=self.total_timesteps)
        self._fitted = True
        logger.info(f"RL 模型训练完成: {self.total_timesteps} timesteps")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测动作（用于推理）"""
        if not self._fitted or self.model is None:
            raise RuntimeError("模型未训练")
        observations = X
        if observations.ndim == 1:
            observations = observations[np.newaxis, :]

        actions = np.array([self.model.predict(obs, deterministic=True)[0] for obs in observations])
        return actions

    def save(self, path: str) -> None:
        if self.model is not None:
            self.model.save(path)

    def load(self, path: str) -> None:
        self.model = PPO.load(path)
        self._fitted = True


__all__ = ["BaseRLModel"]
