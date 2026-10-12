"""
"from-scratch" optimizer: LSQR initialization + coordinate descent refinement,
following the algorithm in simulator.m.

1. LSQR finds a continuous least-squares fit of the shifted demand to the
   generation profile; the highest-weighted shift of each run is taken as
   the initial guess.
2. Coordinate descent refines the shifts by ±1 step at a time while the
   cost keeps decreasing.
"""

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import lsqr

from .base import BaseOptimizer, OptimizerResult


class FromScratchOptimizer(BaseOptimizer):
    name = 'from-scratch'
    label = 'From scratch (LSQR + coordinate descent)'

    def optimize(self, problem):
        elec_demand_matrix = problem.elec_demand_matrix
        phase_info = problem.run_info
        nPhases = problem.num_runs
        N = problem.num_timesteps

        # LSQR Initialization (following simulator.m)
        # Build sparse matrix A for LSQR where each column represents a shift option
        max_shift_steps = max([max(info['max_forward_steps'], info['max_backward_steps'])
                               for info in phase_info] + [24])  # At least ±2 hours

        shift_candidates = list(range(-max_shift_steps, max_shift_steps + 1))
        n_shifts = len(shift_candidates)

        A = lil_matrix((N, nPhases * n_shifts))
        col_idx = 0

        for i in range(nPhases):
            for shift_step in shift_candidates:
                # Check if shift is within allowed bounds for this phase
                if abs(shift_step) <= problem.max_shift_steps[i]:
                    shifted_col = np.zeros(N)
                    original = elec_demand_matrix[i, :]  # Row i of demand matrix

                    if shift_step == 0:
                        shifted_col = original
                    elif shift_step > 0:
                        shifted_col[shift_step:] = original[:-shift_step]
                    else:
                        shifted_col[:shift_step] = original[-shift_step:]

                    A[:, col_idx] = shifted_col.reshape(-1, 1)

                col_idx += 1

        A = A.tocsr()
        b = problem.gen_kWh

        # Run LSQR
        x_lsqr, istop, itn, r1norm = lsqr(A, b, atol=1e-6, btol=1e-6, iter_lim=500)[:4]

        # Extract initial shifts from LSQR solution, respecting per-run bounds
        initial_shifts = np.zeros(nPhases, dtype=int)
        col_ptr = 0
        for i in range(nPhases):
            run_cols = x_lsqr[col_ptr:col_ptr + n_shifts]
            col_ptr += n_shifts

            # Allowed range in steps for this run
            max_steps_allowed = problem.max_shift_steps[i]

            # Build list of indices that are within allowed bounds
            allowed_indices = [idx for idx, s in enumerate(shift_candidates) if abs(s) <= max_steps_allowed]

            if allowed_indices:
                # Pick the best among allowed indices
                best_idx_local = allowed_indices[0]
                best_val = run_cols[best_idx_local]
                for idx in allowed_indices:
                    if run_cols[idx] > best_val:
                        best_idx_local = idx
                        best_val = run_cols[idx]
                chosen_shift = shift_candidates[best_idx_local]
            else:
                # No allowed shifts? default to 0
                chosen_shift = 0

            # Extra safety: clamp to allowed range
            chosen_shift = int(max(-max_steps_allowed, min(max_steps_allowed, chosen_shift)))
            initial_shifts[i] = chosen_shift

        # Calculate initial cost with LSQR shifts
        initial_cost = problem.cost(initial_shifts)

        # Coordinate Descent Refinement (following simulator.m)
        current_shifts = initial_shifts.copy()
        best_cost = initial_cost
        improved = True
        iteration = 0
        max_iterations = 5 * nPhases

        while improved and iteration < max_iterations:
            improved = False

            for i in range(nPhases):
                current_shift = current_shifts[i]

                # Try shifting this phase by ±1 step
                for delta in [-1, +1]:
                    new_shift = current_shift + delta

                    # Check bounds
                    if abs(new_shift) > problem.max_shift_steps[i]:
                        continue

                    # Test this shift
                    test_shifts = current_shifts.copy()
                    test_shifts[i] = new_shift
                    test_cost = problem.cost(test_shifts)

                    if test_cost < best_cost:
                        best_cost = test_cost
                        current_shifts[i] = new_shift
                        improved = True
                        break  # Move to next phase

            iteration += 1

        return OptimizerResult(
            shift_steps=current_shifts,
            data={
                'lsqr_iterations': int(itn),
                'lsqr_residual': float(r1norm),
                'coordinate_descent_iterations': iteration,
                'initial_cost_after_lsqr': float(initial_cost),
            }
        )
