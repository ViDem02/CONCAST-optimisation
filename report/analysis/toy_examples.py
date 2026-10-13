"""
The small examples of the technical note, solved with SPARC's MILP and checked by enumeration.

    python report/analysis/toy_examples.py
"""
import itertools

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from weeks import apply_shifts_from_steps
from OptimizerApp.optimizers.base import OptimizationProblem
from OptimizerApp.optimizers.milp import MILPOptimizer


def make(runs, generation, price):
    """runs: (process, first step, length, kWh per step, max advance, max delay)."""
    demand, info = np.zeros((len(runs), len(price))), []
    for r, (process, start, length, power, back, forward) in enumerate(runs):
        demand[r, start:start + length] = power
        info.append(dict(process_id=process, process_name=f'p{process}', run_name=f'p{process}_run{r + 1}',
                         run_number=r + 1, electricity_consumption_kWh=power * 12, original_start=start,
                         original_end=start + length - 1, max_forward_steps=forward, max_backward_steps=back))
    return OptimizationProblem(demand, np.asarray(generation, float), np.asarray(price, float),
                               np.array([min(i['max_forward_steps'], i['max_backward_steps']) for i in info]), info)


def costs(problem):
    ranges = [range(-i['max_backward_steps'], i['max_forward_steps'] + 1) for i in problem.run_info]
    return {s: round(problem.cost(np.array(s)), 4) for s in itertools.product(*ranges)}


print('B: one run, prices only')
problem = make([(1, 4, 3, 1, 2, 3)], np.zeros(12), [3, 3, 3, 3, 4, 4, 2, 1, 1, 2.5, 3, 3])
print('  ', costs(problem), 'MILP:', MILPOptimizer().optimize(problem).shift_steps)

print('C: two runs competing for the same generation')
generation, price = np.zeros(12), np.ones(12)
generation[5:8], price[9:12] = 1, 2
problem = make([(1, 1, 3, 1, 0, 4), (2, 9, 3, 1, 4, 0)], generation, price)
table = costs(problem)
print('  ', {k: table[k] for k in [(0, 0), (4, 0), (0, -4), (4, -4)]}, 'MILP:', MILPOptimizer().optimize(problem).shift_steps)

print('D: no-overlap rule')
price = np.full(30, 10.0)
price[[11, 12, 13]] = 1
for same in (True, False):
    problem = make([(1, 2, 3, 1, 0, 12), (1 if same else 2, 20, 3, 1, 12, 0)], np.zeros(30), price)
    s = MILPOptimizer().optimize(problem).shift_steps
    print('  ', 'same process' if same else 'different processes', s, problem.cost(s))

print('E: LP relaxation smears a run')
generation = np.zeros(6)
generation[[1, 3]] = 0.5
problem = make([(1, 2, 1, 1, 1, 1)], generation, np.ones(6))
shifted = np.array([apply_shifts_from_steps(problem.elec_demand_matrix, np.array([k]))[0] for k in (-1, 0, 1)]).T
lp = milp(c=np.r_[np.zeros(3), problem.price_el],
          constraints=[LinearConstraint(np.r_[np.ones(3), np.zeros(6)][None, :], 1, 1),
                       LinearConstraint(np.hstack([shifted, -np.eye(6)]), -np.inf, problem.gen_kWh)],
          integrality=np.zeros(9), bounds=Bounds(0, np.r_[np.ones(3), np.full(6, np.inf)]))
print('   integer:', costs(problem), 'LP:', round(lp.fun, 4), 'x =', np.round(lp.x[:3], 3))
