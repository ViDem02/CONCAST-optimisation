"""
Saving against the width of the window of the flexible processes, on one week in four.

    python report/analysis/sensitivity.py       (about 15 minutes)
"""
import time

import numpy as np

from weeks import build_problem, evaluate, full_weeks, load_generation, load_plan, load_prices
from OptimizerApp.optimizers.milp import MILPOptimizer

generation, prices = load_generation('current'), load_prices()
weeks = list(full_weeks(generation))[::4]
for window in (60, 120, 180, 240):
    plan = load_plan(window_minutes=window)
    base = best = longest = 0
    limited = 0
    for week in weeks:
        problem, _, _ = build_problem(week, generation, prices, plan)
        start = time.perf_counter()
        result = MILPOptimizer().optimize(problem)
        longest = max(longest, time.perf_counter() - start)
        limited += 'Time limit' in result.data['solver_status']
        base += evaluate(problem, np.zeros(problem.num_runs, int))['cost']
        best += evaluate(problem, result.shift_steps)['cost']
    print(f'+-{window} min: saving {base - best:.0f} EUR ({(base - best) / base:.2%}) over {len(weeks)} weeks, '
          f'{(base - best) / len(weeks) * 52:.0f} EUR/year, longest solve {longest:.1f} s, '
          f'time limit reached in {limited} weeks', flush=True)
