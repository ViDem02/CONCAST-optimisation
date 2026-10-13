"""
"milp" optimizer: exact mixed-integer linear program solved by HiGHS through
scipy.optimize.milp.

Every allowed shift k in {-B_r, ..., F_r} of run r gets a binary x_{r,k};
y_t >= 0 is the energy bought from the grid at step t:

    min   sum_t pi_t y_t
    s.t.  sum_k x_{r,k} = 1                                for every run r
          sum_{r,k} x_{r,k} (T_k d_r)_t - y_t <= g_t       for every step t
          sum_{r of p, k} x_{r,k} (T_k a_r)_t <= 1         for every process p and step t

The last constraint keeps the runs of the same process from overlapping.
The shifted demand T_k d_r and activity T_k a_r are precomputed with the
periodic shift operator used by problem.cost (see optimizers.base), so the
MILP objective is exactly J(s) and every candidate column carries the whole
energy of its run: moving a run across Sunday/Monday never makes it vanish.
The linearization of y = max(0, D - g) assumes non-negative prices.
"""

import numpy as np
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

from dataclasses import dataclass

from .base import BaseOptimizer, OptimizerResult, apply_shifts_from_steps, run_steps


@dataclass
class Candidates:
    """
    Every allowed position of every run: candidate j is run run_of[j] moved by shift_of[j] steps.

    demand: N x n sparse matrix, column j = shifted demand of the run (kWh per step)
    active: N x n sparse matrix, column j = shifted activity (0/1) of the run
    process_of: n process indices (0..P-1) of the candidates
    """
    run_of: np.ndarray
    shift_of: np.ndarray
    process_of: np.ndarray
    demand: sparse.csr_matrix
    active: sparse.coo_matrix


def build_candidates(problem):
    info, N = problem.run_info, problem.num_timesteps
    run_of = np.concatenate([np.full(i['max_backward_steps'] + i['max_forward_steps'] + 1, r)
                             for r, i in enumerate(info)])
    shift_of = np.concatenate([np.arange(-i['max_backward_steps'], i['max_forward_steps'] + 1)
                               for i in info])
    _, process_of = np.unique([info[r]['process_id'] for r in run_of], return_inverse=True)

    activity = np.zeros_like(problem.elec_demand_matrix)
    for r, i in enumerate(info):
        activity[r, run_steps(i, N)] = 1
    return Candidates(
        run_of=run_of, shift_of=shift_of, process_of=process_of,
        demand=sparse.csr_matrix(apply_shifts_from_steps(problem.elec_demand_matrix[run_of], shift_of).T),
        active=sparse.coo_matrix(apply_shifts_from_steps(activity[run_of], shift_of).T),
    )


class MILPOptimizer(BaseOptimizer):
    name = 'milp'
    label = 'MILP (HiGHS)'

    # Calculations run in the background with live progress (OptimizerApp.background),
    # so the limit only bounds how long users wait: a normal week is solved in 1-2 s.
    # When it is reached, the best solution found so far is returned with its gap.
    time_limit = 20  # seconds
    mip_rel_gap = 1e-4

    def optimize(self, problem):
        R, N = problem.num_runs, problem.num_timesteps
        info = problem.run_info

        # Candidate j = (run_of[j], shift_of[j]) for every run and allowed shift, with its
        # precomputed shifted demand d_{r,k} and activity a_{r,k}
        candidates = build_candidates(problem)
        run_of, shift_of, process_of = candidates.run_of, candidates.shift_of, candidates.process_of
        demand, active = candidates.demand, candidates.active
        n, P = len(run_of), process_of.max() + 1

        # Variables z = [x (n binaries), y (N continuous)]
        one_shift_per_run = sparse.coo_matrix((np.ones(n), (run_of, np.arange(n))), shape=(R, n))
        no_overlap = sparse.coo_matrix(
            (active.data, (process_of[active.col] * N + active.row, active.col)), shape=(P * N, n))
        constraints = [
            LinearConstraint(sparse.hstack([one_shift_per_run, sparse.csr_matrix((R, N))]), 1, 1),
            LinearConstraint(sparse.hstack([demand, -sparse.identity(N)]), -np.inf, problem.gen_kWh),
            LinearConstraint(sparse.hstack([no_overlap, sparse.csr_matrix((P * N, N))]), -np.inf, 1),
        ]

        res = milp(
            c=np.r_[np.zeros(n), problem.price_el],
            constraints=constraints,
            integrality=np.r_[np.ones(n), np.zeros(N)],
            bounds=Bounds(0, np.r_[np.ones(n), np.full(N, np.inf)]),
            options={'time_limit': self.time_limit, 'mip_rel_gap': self.mip_rel_gap},
        )

        # s_r = k where x_{r,k} = 1; keep the baseline if no better solution was found
        shift_steps = np.zeros(R, dtype=int)
        if res.x is not None:
            chosen = res.x[:n] > 0.5
            shift_steps[run_of[chosen]] = shift_of[chosen]
        if problem.cost(shift_steps) > problem.cost(np.zeros(R, dtype=int)):
            shift_steps[:] = 0

        data = {
            'solver': 'HiGHS (scipy.optimize.milp)',
            'solver_status': res.message,
            'num_binary_variables': int(n),
            'time_limit_seconds': self.time_limit,
        }
        if res.x is not None:
            data.update(mip_gap=float(res.mip_gap), mip_dual_bound=float(res.mip_dual_bound),
                        mip_node_count=int(res.mip_node_count))
        return OptimizerResult(shift_steps=shift_steps, data=data)
