OhMyQuant API 文档
===================

.. toctree::
   :maxdepth: 2
   :caption: 模块索引:

   ohmyquant

快速开始
--------

.. code-block:: bash

   pip install -e ".[dev]"
   cd docs/api && sphinx-build -b html . _build/html

模块概览
--------

.. autosummary::
   :toctree: _autosummary
   :recursive:

   ohmyquant.strategy.base
   ohmyquant.strategy.runner
   ohmyquant.engine.base
   ohmyquant.engine.selector
   ohmyquant.execution.rebalancer
   ohmyquant.execution.scheduler
   ohmyquant.factors.base
   ohmyquant.optimization.walk_forward
   ohmyquant.analysis.metrics
