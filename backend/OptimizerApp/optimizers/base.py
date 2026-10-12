"""
Common interface shared by all shift optimizers.

An optimizer receives an OptimizationProblem (demand of each phase-run,
generation, prices and shift bounds, all on the same 5-minute grid) and
returns an OptimizerResult with one integer shift (in timesteps) per run.
Loading data from the database and persisting the optimized plan are handled
by OptimizerApp.optimizer_packager, so optimizers only deal with numpy arrays.
"""

from dataclasses import dataclass, field
import numpy as np


def apply_shifts_from_steps(base_matrix, shift_steps):
    """
    Apply time shifts to each row of the phase activity matrix.
    This follows simulator.m's apply_shifts_from_steps function.

    Args:
        base_matrix: nPhases x N numpy array
        shift_steps: array of nPhases integers (positive = delay, negative = advance)

    Returns:
        Shifted nPhases x N numpy array
    """
    nPhases, N = base_matrix.shape
    shifted = np.zeros_like(base_matrix)

    for i in range(nPhases):
        shift = int(shift_steps[i])
        original = base_matrix[i, :]

        if shift == 0:
            shifted[i, :] = original
        elif shift > 0:
            # Delay: shift forward
            shifted[i, shift:] = original[:-shift]
        else:
            # Advance: shift backward
            shifted[i, :shift] = original[-shift:]

    return shifted


def compute_cost(elec_demand, gen_kWh, price_el):
    """
    Compute total cost based on demand, generation, and prices.

    Cost = sum(grid_purchase * price_el)
    where grid_purchase = max(0, demand - generation)

    Also tracks wasted energy = max(0, generation - demand)
    """
    grid_purchase = np.maximum(0, elec_demand - gen_kWh)
    wasted_energy = np.maximum(0, gen_kWh - elec_demand)

    cost_el = np.sum(grid_purchase * price_el)
    total_wasted = np.sum(wasted_energy)

    return cost_el, {
        'grid_purchase': grid_purchase,
        'wasted_energy': wasted_energy,
        'total_wasted': total_wasted
    }


@dataclass
class OptimizationProblem:
    """
    Input of an optimizer.

    Attributes:
        elec_demand_matrix: nRuns x N array, electricity demand (kWh per step) of each phase-run
        gen_kWh: N-length array, on-site generation (kWh per step)
        price_el: N-length array, grid electricity price per timestep
        max_shift_steps: nRuns-length int array, allowed shift is -max..+max steps
        run_info: list of nRuns dicts describing each phase-run (see expand_phases_to_runs)
    """
    elec_demand_matrix: np.ndarray
    gen_kWh: np.ndarray
    price_el: np.ndarray
    max_shift_steps: np.ndarray
    run_info: list

    @property
    def num_runs(self):
        return self.elec_demand_matrix.shape[0]

    @property
    def num_timesteps(self):
        return self.elec_demand_matrix.shape[1]

    def cost(self, shift_steps):
        """Electricity cost of the schedule obtained by applying shift_steps."""
        shifted_demand = apply_shifts_from_steps(self.elec_demand_matrix, shift_steps)
        total_demand = shifted_demand.sum(axis=0)  # Sum across phases to get total per timestep
        cost, _ = compute_cost(total_demand, self.gen_kWh, self.price_el)
        return cost


@dataclass
class OptimizerResult:
    """
    Output of an optimizer.

    Attributes:
        shift_steps: nRuns-length int array (positive = delay, negative = advance)
        data: optimizer-specific diagnostics, stored in Optimization.optimization_data
    """
    shift_steps: np.ndarray
    data: dict = field(default_factory=dict)


class BaseOptimizer:
    """
    Base class for shift optimizers.

    Subclasses set `name` (identifier stored in Optimization.optimizer),
    `label` (human-readable name) and implement optimize().
    """
    name = None
    label = None

    def optimize(self, problem: OptimizationProblem) -> OptimizerResult:
        raise NotImplementedError
