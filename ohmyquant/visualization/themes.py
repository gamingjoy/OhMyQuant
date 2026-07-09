"""主题配置

提供可视化主题配置，支持自定义颜色、字体和样式。

预设主题：
  - dark: 深色主题
  - light: 浅色主题
  - professional: 专业金融风格
  - colorful: 彩色风格

用法：
    from ohmyquant.visualization.themes import set_theme, get_theme

    set_theme('dark')
    theme = get_theme()
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any

try:
    import plotly.io as pio
except ImportError:
    pio = None


@dataclass
class ThemeConfig:
    """主题配置"""

    name: str = "light"
    primary_color: str = "#1a73e8"
    secondary_color: str = "#5f6368"
    background_color: str = "#ffffff"
    text_color: str = "#202124"
    grid_color: str = "#e8eaed"
    chart_colors: list[str] = None
    font_family: str = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

    def __post_init__(self):
        if self.chart_colors is None:
            self.chart_colors = [
                "#1a73e8",
                "#ea4335",
                "#34a853",
                "#fbbc04",
                "#9c27b0",
                "#ff9800",
                "#00bcd4",
                "#e91e63",
            ]


class ThemeManager:
    """主题管理器"""

    _current_theme: ThemeConfig = ThemeConfig()

    _themes: dict[str, ThemeConfig] = {
        "light": ThemeConfig(
            name="light",
            primary_color="#1a73e8",
            secondary_color="#5f6368",
            background_color="#ffffff",
            text_color="#202124",
            grid_color="#e8eaed",
        ),
        "dark": ThemeConfig(
            name="dark",
            primary_color="#4285f4",
            secondary_color="#9aa0a6",
            background_color="#202124",
            text_color="#e8eaed",
            grid_color="#3c4043",
        ),
        "professional": ThemeConfig(
            name="professional",
            primary_color="#0f4c81",
            secondary_color="#666666",
            background_color="#f8f9fa",
            text_color="#333333",
            grid_color="#dee2e6",
            chart_colors=[
                "#0f4c81",
                "#c0392b",
                "#27ae60",
                "#f39c12",
                "#8e44ad",
                "#e67e22",
                "#1abc9c",
                "#d35400",
            ],
        ),
        "colorful": ThemeConfig(
            name="colorful",
            primary_color="#6366f1",
            secondary_color="#64748b",
            background_color="#ffffff",
            text_color="#1e293b",
            grid_color="#e2e8f0",
            chart_colors=[
                "#6366f1",
                "#ec4899",
                "#10b981",
                "#f59e0b",
                "#8b5cf6",
                "#f97316",
                "#06b6d4",
                "#ef4444",
            ],
        ),
    }

    @classmethod
    def get_theme(cls, name: str | None = None) -> ThemeConfig:
        """获取主题配置

        Args:
            name: 主题名称，默认为当前主题

        Returns:
            ThemeConfig
        """
        if name is None:
            return cls._current_theme
        return cls._themes.get(name, cls._current_theme)

    @classmethod
    def set_theme(cls, name: str) -> None:
        """设置主题

        Args:
            name: 主题名称
        """
        if name in cls._themes:
            cls._current_theme = cls._themes[name]
            cls._apply_plotly_theme()

    @classmethod
    def _apply_plotly_theme(cls) -> None:
        """应用主题到 plotly"""
        if pio is None:
            return

        theme = cls._current_theme

        plotly_template = {
            "layout": {
                "plot_bgcolor": theme.background_color,
                "paper_bgcolor": theme.background_color,
                "font": {
                    "family": theme.font_family,
                    "color": theme.text_color,
                },
                "xaxis": {
                    "gridcolor": theme.grid_color,
                    "color": theme.secondary_color,
                },
                "yaxis": {
                    "gridcolor": theme.grid_color,
                    "color": theme.secondary_color,
                },
            }
        }

        pio.templates[theme.name] = plotly_template
        pio.templates.default = theme.name

    @classmethod
    def register_theme(cls, name: str, config: ThemeConfig) -> None:
        """注册自定义主题

        Args:
            name: 主题名称
            config: 主题配置
        """
        cls._themes[name] = config

    @classmethod
    def list_themes(cls) -> list[str]:
        """列出所有可用主题

        Returns:
            list[str]: 主题名称列表
        """
        return list(cls._themes.keys())


def set_theme(name: str) -> None:
    """设置主题（便捷函数）"""
    ThemeManager.set_theme(name)


def get_theme(name: str | None = None) -> ThemeConfig:
    """获取主题（便捷函数）"""
    return ThemeManager.get_theme(name)


__all__ = ["ThemeConfig", "ThemeManager", "set_theme", "get_theme"]
