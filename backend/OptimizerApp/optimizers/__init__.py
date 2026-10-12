"""
Registry of the available shift optimizers.

To add a new optimizer:
1. Create a module in this package with a BaseOptimizer subclass that sets
   `name`, `label` and implements optimize(problem) -> OptimizerResult.
2. Add the class to _OPTIMIZER_CLASSES below.
3. Run `python manage.py makemigrations OptimizerApp` (the choices of
   Optimization.optimizer are taken from this registry).
"""

from .base import BaseOptimizer, OptimizationProblem, OptimizerResult
from .from_scratch import FromScratchOptimizer
from .milp import MILPOptimizer


_OPTIMIZER_CLASSES = [
    FromScratchOptimizer,
    MILPOptimizer,
]

OPTIMIZERS = {cls.name: cls for cls in _OPTIMIZER_CLASSES}
OPTIMIZER_CHOICES = [(cls.name, cls.label) for cls in _OPTIMIZER_CLASSES]
DEFAULT_OPTIMIZER = MILPOptimizer.name


def get_optimizer(name):
    """Return an instance of the optimizer registered under `name`."""
    try:
        return OPTIMIZERS[name]()
    except KeyError:
        raise ValueError(
            f"Unknown optimizer '{name}'. Available optimizers: {', '.join(OPTIMIZERS)}"
        )
