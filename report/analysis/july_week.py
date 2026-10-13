"""
Dissect the week of 15 July 2024 (current plants): MILP vs LP relaxation, size of
the model, cost of moving one run, hourly profile of Wednesday, legacy heuristic.

    python report/analysis/july_week.py
"""
from datetime import datetime

import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

from weeks import build_problem, evaluate, load_generation, load_plan, load_prices, overlaps
from OptimizerApp.optimizers.base import apply_shifts_from_steps
from OptimizerApp.optimizers.from_scratch import FromScratchOptimizer
from OptimizerApp.optimizers.milp import MILPOptimizer

problem, _, _ = build_problem(datetime(2024, 7, 15), load_generation('current'), load_prices(), load_plan())
info, R, N = problem.run_info, problem.num_runs, problem.num_timesteps
result = MILPOptimizer().optimize(problem)
s = result.shift_steps
print(f'original {problem.cost(np.zeros(R, int)):.4f}  MILP {problem.cost(s):.4f}  {result.data}')

# The MILP of optimizers/milp.py, rebuilt to solve its LP relaxation and count its size
run_of = np.concatenate([np.full(i['max_backward_steps'] + i['max_forward_steps'] + 1, r) for r, i in enumerate(info)])
shift_of = np.concatenate([np.arange(-i['max_backward_steps'], i['max_forward_steps'] + 1) for i in info])
_, process_of = np.unique([info[r]['process_id'] for r in run_of], return_inverse=True)
n, P = len(run_of), process_of.max() + 1
activity = np.zeros_like(problem.elec_demand_matrix)
for r, i in enumerate(info):
    activity[r, i['original_start']:i['original_end'] + 1] = 1
demand = sparse.csr_matrix(apply_shifts_from_steps(problem.elec_demand_matrix[run_of], shift_of).T)
active = sparse.coo_matrix(apply_shifts_from_steps(activity[run_of], shift_of).T)
blocks = [sparse.hstack([sparse.coo_matrix((np.ones(n), (run_of, np.arange(n))), shape=(R, n)), sparse.csr_matrix((R, N))]),
          sparse.hstack([demand, -sparse.identity(N)]),
          sparse.hstack([sparse.coo_matrix((active.data, (process_of[active.col] * N + active.row, active.col)),
                                           shape=(P * N, n)), sparse.csr_matrix((P * N, N))])]
print(f'binaries {n}, continuous {N}, rows {R} + {N} + {P * N}, non-zeros {sum(b.nnz for b in blocks)}')
lp = milp(c=np.r_[np.zeros(n), problem.price_el],
          constraints=[LinearConstraint(blocks[0], 1, 1), LinearConstraint(blocks[1], -np.inf, problem.gen_kWh),
                       LinearConstraint(blocks[2], -np.inf, 1)],
          integrality=np.zeros(n + N), bounds=Bounds(0, np.r_[np.ones(n), np.full(N, np.inf)]))
fractional = sorted({info[run_of[j]]['run_name'] for j in range(n) if 1e-6 < lp.x[j] < 1 - 1e-6})
print(f'LP relaxation {lp.fun:.4f}; fractional runs: {fractional}')

for name in ('b_past_run1', 'b_past_run4'):
    r = [i['run_name'] for i in info].index(name)
    curve = []
    for k in range(-info[r]['max_backward_steps'], info[r]['max_forward_steps'] + 1):
        moved = s.copy()
        moved[r] = k
        feasible = not overlaps(problem, moved)
        curve.append(f'{k * 5:+d}:{problem.cost(moved) - problem.cost(s):.2f}{"" if feasible else "x"}')
    print(name, 'cost change when moved alone (x = overlaps):', ' '.join(curve))

wednesday = slice(2 * 288, 3 * 288)
hourly = lambda v: [round(float(v[wednesday][h * 12:(h + 1) * 12].sum()), 1) for h in range(24)]
print('Wednesday generation', hourly(problem.gen_kWh))
print('Wednesday demand, original ', hourly(problem.elec_demand_matrix.sum(0)))
print('Wednesday demand, optimised', hourly(apply_shifts_from_steps(problem.elec_demand_matrix, s).sum(0)))

legacy = FromScratchOptimizer().optimize(problem)
print(f'legacy {problem.cost(legacy.shift_steps):.2f} {legacy.data}; overlapping pairs: {overlaps(problem, legacy.shift_steps)}')
