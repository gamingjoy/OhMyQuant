"""Sphinx API 文档配置

构建命令:
    cd docs/api && sphinx-build -b html . _build/html

依赖:
    pip install sphinx sphinx-autodoc-typehints furo
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

# ── Project info ─────────────────────────────────────────────────────────────

project = "OhMyQuant"
author = "OhMyQuant"
release = "0.1.0"

# ── General config ───────────────────────────────────────────────────────────

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# ── HTML output ──────────────────────────────────────────────────────────────

html_theme = "furo"
html_static_path = ["_static"]

# ── Autodoc config ───────────────────────────────────────────────────────────

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_type_hints = "signature"

# ── Intersphinx ──────────────────────────────────────────────────────────────

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "polars": ("https://pola-rs.github.io/polars/py-polars/html/", None),
}
