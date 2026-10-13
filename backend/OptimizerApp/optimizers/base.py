"""
Common interface shared by all shift optimizers.

An optimizer receives an OptimizationProblem (demand of each phase-run,
generation, prices and shift bounds, all on the same 5-minute grid) and
returns an OptimizerResult with one integer shift (in timesteps) per run.
Loading data from the database and persisting the optimized plan are handled
by OptimizerApp.optimizer_packager, so optimizers only deal with numpy arrays.

The horizon is PERIODIC. The reference week is a template that repeats every
week, so the steps form a circle: a run moved past Sunday 24:00 continues on
Monday 00:00 of the template, and a run moved before Monday 00:00 continues on
Sunday evening. Shifting never adds or removes energy: every run keeps exactly
its consumption (see apply_shifts_from_steps).
"""

from dataclasses import dataclass, field
import numpy as np


def apply_shifts_from_steps(base_matrix, shift_steps):
    """
    Move each row of the matrix by its shift, around the periodic week.

    Args:
        base_matrix: nRuns x N numpy array (demand or activity of each run)
        shift_steps: nRuns integers (positive = delay, negative = advance)

    Returns:
        Shifted nRuns x N numpy array. Step t of row i goes to step (t + shift) mod N,
        so every row keeps its sum: no energy is lost at the ends of the week.
    """
    shifted = np.empty_like(base_matrix)
    for i, shift in enumerate(shift_steps):
        shifted[i] = np.roll(base_matrix[i], int(shift))
    return shifted


def run_steps(info, num_timesteps):
    """
    Steps occupied by a run in the original plan, in order.

    A run that crosses Sunday 24:00 has original_end >= num_timesteps; its steps
    continue from 0 (e.g. start 2010, end 2021 on a 2016-step week = steps 2010..2015, 0..5).
    """
    return np.arange(info['original_start'], info['original_end'] + 1) % num_timesteps


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
        run_info: list of nRuns dicts describing each phase-run (see expand_phases_to_runs);
            original_start/original_end are steps, original_end may exceed N - 1 for a run
            that crosses Sunday 24:00 (see run_steps)
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

    def demand(self, shift_steps):
        """Total demand (kWh per step) of the schedule obtained by applying shift_steps."""
        return apply_shifts_from_steps(self.elec_demand_matrix, shift_steps).sum(axis=0)

    def cost(self, shift_steps):
        """Electricity cost of the schedule obtained by applying shift_steps."""
        cost, _ = compute_cost(self.demand(shift_steps), self.gen_kWh, self.price_el)
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
