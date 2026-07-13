"""OhMyQuant 包安装配置"""
from setuptools import find_packages, setup

setup(
    name="ohmyquant",
    version="0.1.0",
    description="一站式量化策略开发框架 — 从数据到策略，从回测到实盘",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="OhMyQuant",
    license="MIT",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "polars>=0.20.0",
        "duckdb>=0.9.0",
        "pydantic>=2.0.0",
        "loguru>=0.7.0",
        "pyyaml>=6.0",
        "numpy>=1.24.0",
    ],
    extras_require={
        "ml": ["lightgbm>=4.0.0", "xgboost>=2.0.0"],
        "dl": ["torch>=2.0.0"],
        "rl": ["stable-baselines3>=2.0.0", "gymnasium>=0.28.0"],
        "viz": ["plotly>=5.0.0"],
        "stats": ["scipy>=1.10.0"],
        "dev": ["pytest>=7.0.0", "pytest-cov>=4.0.0"],
        "all": [
            "lightgbm>=4.0.0",
            "xgboost>=2.0.0",
            "torch>=2.0.0",
            "stable-baselines3>=2.0.0",
            "gymnasium>=0.28.0",
            "plotly>=5.0.0",
            "scipy>=1.10.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "omq=ohmyquant.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
)
