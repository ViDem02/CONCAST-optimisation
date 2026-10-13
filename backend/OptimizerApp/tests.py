"""
Validity tests for the shift optimizers (OptimizerApp.optimizers).

Unit tests, on small OptimizationProblem instances built by hand:
- RegistryTests: both optimizers can be chosen, the MILP is the default.
- OptimizerContractTests: the contract every registered optimizer must meet
  (mathematical specification, "Contract for optimizers").
- MILPConstraintTests: one instance with a known answer per MILP constraint.
- MILPOptimalityTests: random instances checked against brute-force enumeration.
- MILPFallbackTests: behaviour when HiGHS returns no solution or a bad one.
- EnergyConservationTests: moving runs never creates or destroys energy, in particular
  across Sunday/Monday (the reference week is periodic).
- LiveProgressTests, BackgroundThreadTests: calculations in the background with live progress.

Integration tests (PackagerIntegrationTests) run the whole pipeline, from a
plan stored in the database to the optimized plan written back, including
runs at the ends of the week and incomplete data.
"""

import copy
import itertools
import json
from datetime import date, datetime, timedelta
from io import StringIO
from unittest import mock

import numpy as np
import pytz
from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from scipy.optimize import OptimizeResult

from DatasetApp.models import GenerationDataset, GenerationRecord, PricesDataset, PricesRecord
from DatasetApp.series import MissingDataError
from PlanningApp.models import Process, Shift, WeeklyProductionPlan

from .models import Optimization
from .optimizer_packager import STEPS, run_optimization
from .optimizers import DEFAULT_OPTIMIZER, OPTIMIZER_CHOICES, OPTIMIZERS, get_optimizer
from .optimizers.base import OptimizationProblem, apply_shifts_from_steps, run_steps
from .optimizers.milp import MILPOptimizer, build_candidates

# Keys of optimization_data written by the packager, forbidden to optimizers
RESERVED_KEYS = {'optimizer', 'baseline_cost', 'final_cost', 'total_wasted_energy', 'demand_kWh',
                 'shift_changes', 'num_timesteps', 'num_runs_optimized'}
GAP = MILPOptimizer.mip_rel_gap


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def make_problem(runs, gen, price):
    """
    Build a problem from runs given as
    (process_id, start step, length in steps, kWh per step, max backward steps, max forward steps).
    A run may continue past the last step (start + length > N): it wraps to step 0.
    """
    N = len(price)
    demand = np.zeros((len(runs), N))
    run_info = []
    for r, (process, start, length, power, backward, forward) in enumerate(runs):
        demand[r, np.arange(start, start + length) % N] = power
        run_info.append({
            'process_id': process, 'process_name': f'p{process}', 'run_name': f'p{process}_run{r + 1}',
            'run_number': r + 1, 'electricity_consumption_kWh': power * 12,
            'original_start': start, 'original_end': start + length - 1,
            'max_forward_steps': forward, 'max_backward_steps': backward,
        })
    return OptimizationProblem(
        elec_demand_matrix=demand,
        gen_kWh=np.asarray(gen, dtype=float),
        price_el=np.asarray(price, dtype=float),
        max_shift_steps=np.array([min(i['max_forward_steps'], i['max_backward_steps']) for i in run_info]),
        run_info=run_info,
    )


def cheap_slot(N, steps, base=10.0, cheap=1.0):
    """Flat price `base` with price `cheap` on the given steps."""
    price = np.full(N, base)
    price[list(steps)] = cheap
    return price


def occupied(info, shift, N):
    """Steps in which a run is on after being shifted, around the periodic week."""
    return {int(t) for t in (run_steps(info, N) + shift) % N}


def is_feasible(problem, shift_steps):
    """Every shift within -B_r..F_r and no two runs of the same process on in the same step."""
    info, N = problem.run_info, problem.num_timesteps
    if any(not -i['max_backward_steps'] <= s <= i['max_forward_steps'] for i, s in zip(info, shift_steps)):
        return False
    for a, b in itertools.combinations(range(len(info)), 2):
        if info[a]['process_id'] == info[b]['process_id'] and \
                occupied(info[a], shift_steps[a], N) & occupied(info[b], shift_steps[b], N):
            return False
    return True


def brute_force_optimum(problem):
    """Lowest cost over every feasible shift vector."""
    ranges = [range(-i['max_backward_steps'], i['max_forward_steps'] + 1) for i in problem.run_info]
    return min(problem.cost(np.array(s)) for s in itertools.product(*ranges) if is_feasible(problem, s))


def random_problem(seed):
    """2 processes with 1-2 runs each, short horizon, asymmetric windows of 0-3 steps per side."""
    rng = np.random.default_rng(seed)
    N = int(rng.integers(24, 49))
    runs = []
    for process in (1, 2):
        start = int(rng.integers(0, 4))  # Sometimes at the very start of the horizon
        for _ in range(int(rng.integers(1, 3))):
            length = int(rng.integers(1, 6))
            if start + length > N:
                break
            runs.append((process, start, length, float(rng.uniform(0.5, 3)),
                         int(rng.integers(0, 4)), int(rng.integers(0, 4))))
            start += length + int(rng.integers(1, 8))  # Runs of a process never touch in the baseline
    gen = rng.uniform(0, 3, N) * (rng.random(N) < 0.5)
    price = rng.uniform(0.05, 0.4, N)
    return make_problem(runs, gen, price)


def zeros(problem):
    return np.zeros(problem.num_runs, dtype=int)


class MILPTestCase(SimpleTestCase):
    """Solves with the MILP and checks that every answer is valid."""

    def solve(self, problem):
        result = MILPOptimizer().optimize(problem)
        shift_steps = result.shift_steps
        self.assertEqual(shift_steps.shape, (problem.num_runs,))
        self.assertTrue(is_feasible(problem, shift_steps), f'Infeasible shifts {shift_steps}')
        self.assertLessEqual(problem.cost(shift_steps), problem.cost(zeros(problem)) + 1e-9)
        self.assertIn('Optimal', result.data['solver_status'])
        self.assertLessEqual(result.data['mip_gap'], GAP)
        return result

    def solve_cost(self, problem):
        return problem.cost(self.solve(problem).shift_steps)


# ----------------------------------------------------------------------------
# Unit tests
# ----------------------------------------------------------------------------

class RegistryTests(SimpleTestCase):

    def test_both_optimizers_can_be_chosen_and_milp_is_the_default(self):
        field = Optimization._meta.get_field('optimizer')
        self.assertEqual({name for name, _ in field.choices}, {'from-scratch', 'milp'})
        self.assertEqual(field.choices, OPTIMIZER_CHOICES)
        self.assertEqual(field.default, 'milp')
        self.assertEqual(DEFAULT_OPTIMIZER, 'milp')

    def test_each_choice_builds_its_optimizer(self):
        for name, _ in OPTIMIZER_CHOICES:
            self.assertEqual(get_optimizer(name).name, name)

    def test_unknown_optimizer_is_rejected(self):
        with self.assertRaises(ValueError):
            get_optimizer('does-not-exist')


class OptimizerContractTests(SimpleTestCase):
    """Requirements of the specification that every registered optimizer must meet."""

    def problems(self):
        yield from (random_problem(seed) for seed in range(8))
        yield make_problem([(1, 5, 2, 1, 4, 4), (2, 15, 2, 1, 4, 4), (3, 22, 2, 1, 4, 4)],
                           np.zeros(30), cheap_slot(30, [7, 8, 12, 13, 22, 23]))

    def for_each_case(self, check):
        for name, optimizer_class in OPTIMIZERS.items():
            for index, problem in enumerate(self.problems()):
                with self.subTest(optimizer=name, problem=index):
                    check(optimizer_class(), problem)

    def test_returns_one_integer_shift_per_run(self):
        def check(optimizer, problem):
            shift_steps = np.asarray(optimizer.optimize(problem).shift_steps)
            self.assertEqual(shift_steps.shape, (problem.num_runs,))
            self.assertTrue(np.issubdtype(shift_steps.dtype, np.integer))
        self.for_each_case(check)

    def test_shifts_are_within_the_asymmetric_bounds(self):
        def check(optimizer, problem):
            for info, s in zip(problem.run_info, optimizer.optimize(problem).shift_steps):
                self.assertGreaterEqual(s, -info['max_backward_steps'])
                self.assertLessEqual(s, info['max_forward_steps'])
        self.for_each_case(check)

    def test_does_not_modify_the_problem(self):
        def check(optimizer, problem):
            before = copy.deepcopy(problem)
            optimizer.optimize(problem)
            np.testing.assert_array_equal(problem.elec_demand_matrix, before.elec_demand_matrix)
            np.testing.assert_array_equal(problem.gen_kWh, before.gen_kWh)
            np.testing.assert_array_equal(problem.price_el, before.price_el)
            np.testing.assert_array_equal(problem.max_shift_steps, before.max_shift_steps)
            self.assertEqual(problem.run_info, before.run_info)
        self.for_each_case(check)

    def test_diagnostics_are_strict_json_without_reserved_keys(self):
        def check(optimizer, problem):
            data = optimizer.optimize(problem).data
            json.dumps(data, allow_nan=False)
            self.assertFalse(RESERVED_KEYS & set(data))
        self.for_each_case(check)

    def test_is_deterministic(self):
        def check(optimizer, problem):
            np.testing.assert_array_equal(optimizer.optimize(problem).shift_steps,
                                          optimizer.optimize(problem).shift_steps)
        self.for_each_case(check)


class MILPConstraintTests(MILPTestCase):
    """Small instances whose optimum is known, one per constraint of the MILP."""

    # Shift bounds -B_r <= s_r <= F_r

    def test_shifts_follow_the_order_of_run_info(self):
        # Each run can reach exactly one cheap slot: +2, -3 and 0 steps away
        problem = make_problem([(1, 5, 2, 1, 4, 4), (2, 15, 2, 1, 4, 4), (3, 22, 2, 1, 4, 4)],
                               np.zeros(30), cheap_slot(30, [7, 8, 12, 13, 22, 23]))
        np.testing.assert_array_equal(self.solve(problem).shift_steps, [2, -3, 0])

    def test_moves_beyond_the_smaller_of_the_two_tolerances(self):
        delay = make_problem([(1, 10, 2, 1, 1, 6)], np.zeros(24), cheap_slot(24, [16, 17]))
        advance = make_problem([(1, 10, 2, 1, 6, 1)], np.zeros(24), cheap_slot(24, [4, 5]))
        self.assertEqual(self.solve(delay).shift_steps[0], 6)
        self.assertEqual(self.solve(advance).shift_steps[0], -6)

    def test_never_moves_in_a_direction_without_tolerance(self):
        # Cheap slot behind the run but no backward tolerance; later steps are dearer
        price = cheap_slot(24, [5, 6])
        price[10:] += np.arange(14)
        self.assertEqual(self.solve(make_problem([(1, 10, 2, 1, 0, 5)], np.zeros(24), price)).shift_steps[0], 0)
        # Mirror: cheap slot ahead but no forward tolerance; earlier steps are dearer
        price = cheap_slot(24, [15, 16])
        price[:12] += np.arange(12)[::-1]
        self.assertEqual(self.solve(make_problem([(1, 10, 2, 1, 5, 0)], np.zeros(24), price)).shift_steps[0], 0)

    def test_stops_at_the_bound_when_the_optimum_lies_beyond_it(self):
        problem = make_problem([(1, 2, 2, 1, 0, 3)], np.zeros(24), 30.0 - np.arange(24))
        self.assertEqual(self.solve(problem).shift_steps[0], 3)

    def test_fixed_runs_never_move(self):
        # The fixed run sits next to the cheap slot; the movable one (another process) takes it
        problem = make_problem([(1, 10, 2, 1, 0, 0), (2, 4, 2, 1, 0, 8)], np.zeros(20), cheap_slot(20, [12, 13]))
        np.testing.assert_array_equal(self.solve(problem).shift_steps, [0, 8])

    def test_keeps_the_baseline_when_it_is_already_optimal(self):
        problem = make_problem([(1, 10, 2, 1, 3, 3)], np.zeros(20), cheap_slot(20, [10, 11]))
        self.assertEqual(self.solve(problem).shift_steps[0], 0)

    # Non-overlap: runs of the same process are never on in the same step

    def test_runs_of_the_same_process_never_overlap(self):
        # Both runs want the 3 cheap steps; only 3 run-steps in total can have them
        problem = make_problem([(1, 2, 3, 1, 0, 12), (1, 20, 3, 1, 12, 0)], np.zeros(30), cheap_slot(30, [11, 12, 13]))
        self.assertAlmostEqual(self.solve_cost(problem), 3 * 1 + 3 * 10)

    def test_runs_of_different_processes_may_overlap(self):
        problem = make_problem([(1, 2, 3, 1, 0, 12), (2, 20, 3, 1, 12, 0)], np.zeros(30), cheap_slot(30, [11, 12, 13]))
        result = self.solve(problem)
        np.testing.assert_array_equal(result.shift_steps, [9, -9])
        self.assertAlmostEqual(problem.cost(result.shift_steps), 6)

    def test_runs_of_the_same_process_may_touch(self):
        # The 6 cheap steps hold both runs only if they are back to back
        problem = make_problem([(1, 2, 3, 1, 0, 12), (1, 22, 3, 1, 12, 0)], np.zeros(30), cheap_slot(30, range(10, 16)))
        shift_steps = self.solve(problem).shift_steps
        self.assertAlmostEqual(problem.cost(shift_steps), 6)
        steps = [occupied(info, s, 30) for info, s in zip(problem.run_info, shift_steps)]
        self.assertEqual(steps[0] | steps[1], set(range(10, 16)))

    def test_a_run_without_demand_still_blocks_its_process(self):
        # A fixed zero-power run occupies the cheap slot, so the other run of its process cannot use it
        problem = make_problem([(1, 10, 3, 0.0, 0, 0), (1, 2, 3, 1, 0, 12)], np.zeros(20), cheap_slot(20, [10, 11, 12]))
        self.assertAlmostEqual(self.solve_cost(problem), 30)

    # Grid purchase y_t >= D_t - g_t, y_t >= 0

    def test_moves_demand_into_unused_generation(self):
        gen = np.zeros(40)
        gen[20:28] = 2
        problem = make_problem([(1, 5, 4, 1, 0, 20)], gen, np.ones(40))
        result = self.solve(problem)
        self.assertAlmostEqual(problem.cost(result.shift_steps), 0)
        self.assertLessEqual(occupied(problem.run_info[0], result.shift_steps[0], 40), set(range(20, 28)))

    def test_generation_covering_part_of_the_demand_reduces_the_purchase(self):
        gen = np.zeros(30)
        gen[10:20] = 0.6
        problem = make_problem([(1, 0, 4, 1, 0, 15)], gen, np.ones(30))
        self.assertAlmostEqual(self.solve_cost(problem), 4 * 0.4)

    def test_surplus_generation_is_not_credited(self):
        problem = make_problem([(1, 2, 3, 1, 2, 2), (2, 8, 3, 1, 2, 2)], np.full(20, 5.0), np.ones(20))
        result = self.solve(problem)
        self.assertAlmostEqual(problem.cost(result.shift_steps), 0)
        self.assertGreaterEqual(result.data['mip_dual_bound'], -1e-9)

    def test_moves_demand_away_from_a_price_peak(self):
        problem = make_problem([(1, 10, 4, 1, 6, 6)], np.zeros(30), cheap_slot(30, range(10, 14), base=1, cheap=100))
        self.assertAlmostEqual(self.solve_cost(problem), 4)

    def test_runs_at_the_edges_of_the_horizon_wrap_around_the_week(self):
        # Run 1 starts at step 0 and may advance; run 2 ends 1 step before the end and may be delayed
        rng = np.random.default_rng(0)
        problem = make_problem([(1, 0, 3, 1, 2, 2), (2, 17, 3, 1, 2, 2)], rng.uniform(0, 1, 20), rng.uniform(0.1, 0.4, 20))
        self.assertAlmostEqual(self.solve_cost(problem), brute_force_optimum(problem))


class MILPOptimalityTests(MILPTestCase):

    SEEDS = range(30)

    def test_matches_brute_force_on_random_instances(self):
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                problem = random_problem(seed)
                best = brute_force_optimum(problem)
                result = self.solve(problem)
                cost = problem.cost(result.shift_steps)
                self.assertGreaterEqual(cost, best - 1e-9)  # Cannot beat the enumeration
                self.assertLessEqual(cost, best * (1 + GAP) + 1e-9)
                self.assertLessEqual(result.data['mip_dual_bound'], best + 1e-7)  # Valid lower bound

    def test_is_never_worse_than_from_scratch_when_its_schedule_is_feasible(self):
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                problem = random_problem(seed)
                from_scratch = get_optimizer('from-scratch').optimize(problem).shift_steps
                if is_feasible(problem, from_scratch):
                    self.assertLessEqual(self.solve_cost(problem), problem.cost(from_scratch) * (1 + GAP) + 1e-9)

    def test_solves_a_week_of_realistic_size_to_optimality(self):
        # One week of 5-minute steps, 4 processes, shift windows of ±2 hours
        rng = np.random.default_rng(1)
        N = 2016
        runs = []
        for process in range(4):
            start = int(rng.integers(0, 50))
            while start + 72 < N:
                length = int(rng.integers(12, 72))
                runs.append((process, start, length, float(rng.uniform(1, 25)), 24, 24))
                start += length + int(rng.integers(6, 300))
        day = np.arange(N) % 288
        gen = 30 * np.clip(np.sin(np.pi * (day - 84) / 144), 0, None) + rng.uniform(0, 5, N)
        price = 0.1 + 0.1 * ((day >= 96) & (day < 240)) + rng.uniform(0, 0.05, N)
        problem = make_problem(runs, gen, price)
        self.assertGreater(problem.num_runs, 30)
        self.solve(problem)


class MILPFallbackTests(SimpleTestCase):
    """The baseline is returned when the solver does not deliver a better schedule."""

    def setUp(self):
        # One run that may only be delayed by 1 step, which costs more
        self.problem = make_problem([(1, 0, 2, 1, 0, 1)], np.zeros(6), [1, 1, 10, 10, 10, 10])

    @mock.patch('OptimizerApp.optimizers.milp.milp')
    def test_keeps_the_baseline_when_the_solver_finds_no_solution(self, fake_milp):
        fake_milp.return_value = OptimizeResult(x=None, status=1, message='Time limit reached')
        result = MILPOptimizer().optimize(self.problem)
        np.testing.assert_array_equal(result.shift_steps, [0])
        self.assertEqual(result.data['solver_status'], 'Time limit reached')
        self.assertNotIn('mip_gap', result.data)
        json.dumps(result.data, allow_nan=False)
        options = fake_milp.call_args.kwargs['options']
        self.assertEqual(options, {'time_limit': MILPOptimizer.time_limit, 'mip_rel_gap': GAP})

    @mock.patch('OptimizerApp.optimizers.milp.milp')
    def test_keeps_the_baseline_when_the_solver_returns_a_worse_schedule(self, fake_milp):
        # Whichever binary encodes the delay, choosing it must be undone
        for choice in ([1, 0], [0, 1]):
            fake_milp.return_value = OptimizeResult(
                x=np.r_[choice, np.zeros(6)], status=1, message='Time limit reached',
                mip_gap=0.5, mip_dual_bound=0.0, mip_node_count=1)
            np.testing.assert_array_equal(MILPOptimizer().optimize(self.problem).shift_steps, [0])

    def test_keeps_the_baseline_when_a_price_is_negative(self):
        # y_t >= D_t - g_t is exact only for non-negative prices (PricesRecord validates them):
        # a negative price makes the MILP unbounded, so the baseline is kept
        problem = make_problem([(1, 0, 2, 1, 0, 2)], np.zeros(6), [1, 1, 1, 1, 1, -1])
        result = MILPOptimizer().optimize(problem)
        np.testing.assert_array_equal(result.shift_steps, [0])
        self.assertIn('unbounded', result.data['solver_status'])



def edge_problem(seed):
    """
    Random instance with runs at both ends of the week, one of them crossing it: the cases
    where a truncating shift would lose energy. Runs of a process never overlap in the baseline.
    """
    rng = np.random.default_rng(seed)
    N = int(rng.integers(20, 33))
    runs = [
        (1, 0, int(rng.integers(1, 4)), float(rng.uniform(0.5, 3)), int(rng.integers(1, 6)), int(rng.integers(0, 3))),
        (1, N - 8, int(rng.integers(1, 4)), float(rng.uniform(0.5, 3)), int(rng.integers(0, 3)), int(rng.integers(1, 6))),
        (2, N - 2, int(rng.integers(3, 6)), float(rng.uniform(0.5, 3)), int(rng.integers(0, 4)), int(rng.integers(0, 4))),
    ]
    gen = rng.uniform(0, 3, N) * (rng.random(N) < 0.5)
    price = rng.uniform(0.05, 0.4, N)
    return make_problem(runs, gen, price)


class EnergyConservationTests(MILPTestCase):
    """
    Moving runs must never create or destroy energy. The reference week is periodic:
    what is moved past Sunday 24:00 continues on Monday 00:00, and vice versa.
    """

    SEEDS = range(20)

    def run_energy(self, problem):
        return problem.elec_demand_matrix.sum(axis=1)

    # The shift operator

    def test_shift_operator_keeps_the_energy_of_every_run(self):
        rng = np.random.default_rng(0)
        matrix = rng.uniform(0, 5, (6, 40)) * (rng.random((6, 40)) < 0.4)
        for shifts in ([0] * 6, [1, -1, 39, -39, 40, -41], list(rng.integers(-120, 121, 6))):
            with self.subTest(shifts=shifts):
                shifted = apply_shifts_from_steps(matrix, shifts)
                np.testing.assert_allclose(shifted.sum(axis=1), matrix.sum(axis=1))
                # Same values, only moved: a shift is a permutation of the steps
                np.testing.assert_allclose(np.sort(shifted, axis=1), np.sort(matrix, axis=1))

    def test_shift_operator_is_periodic(self):
        row = np.arange(10.0)[None, :]
        np.testing.assert_array_equal(apply_shifts_from_steps(row, [10]), row)
        np.testing.assert_array_equal(apply_shifts_from_steps(row, [3]), np.roll(row, 3))
        np.testing.assert_array_equal(apply_shifts_from_steps(apply_shifts_from_steps(row, [4]), [-7]),
                                      apply_shifts_from_steps(row, [-3]))
        # Step 9 delayed by 2 steps lands on step 1
        self.assertEqual(apply_shifts_from_steps(row, [2])[0, 1], 9)

    def test_every_candidate_of_the_milp_carries_the_whole_run(self):
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                problem = edge_problem(seed)
                candidates = build_candidates(problem)
                energy = self.run_energy(problem)[candidates.run_of]
                lengths = np.array([len(run_steps(i, problem.num_timesteps)) for i in problem.run_info])
                np.testing.assert_allclose(np.asarray(candidates.demand.sum(axis=0)).ravel(), energy)
                np.testing.assert_array_equal(np.asarray(candidates.active.sum(axis=0)).ravel(),
                                              lengths[candidates.run_of])

    def test_every_schedule_uses_the_energy_of_the_original_plan(self):
        rng = np.random.default_rng(1)
        for seed in self.SEEDS:
            problem = edge_problem(seed)
            total = problem.elec_demand_matrix.sum()
            for _ in range(10):
                shifts = [int(rng.integers(-i['max_backward_steps'], i['max_forward_steps'] + 1))
                          for i in problem.run_info]
                with self.subTest(seed=seed, shifts=shifts):
                    self.assertAlmostEqual(problem.demand(np.array(shifts)).sum(), total)

    # The optimisers

    def test_milp_keeps_the_energy_and_is_optimal_at_the_ends_of_the_week(self):
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                problem = edge_problem(seed)
                shifts = self.solve(problem).shift_steps
                demand = problem.demand(shifts)
                self.assertAlmostEqual(demand.sum(), problem.elec_demand_matrix.sum())
                # Energy balance at every step: bought + used generation = demand
                bought = np.maximum(0, demand - problem.gen_kWh)
                np.testing.assert_allclose(bought + np.minimum(demand, problem.gen_kWh), demand)
                best = brute_force_optimum(problem)
                self.assertLessEqual(problem.cost(shifts), best * (1 + GAP) + 1e-9)

    def test_every_optimizer_keeps_the_energy(self):
        for name, optimizer_class in OPTIMIZERS.items():
            for seed in self.SEEDS:
                with self.subTest(optimizer=name, seed=seed):
                    problem = edge_problem(seed)
                    shifts = optimizer_class().optimize(problem).shift_steps
                    self.assertAlmostEqual(problem.demand(shifts).sum(), problem.elec_demand_matrix.sum())

    # A week of 5-minute steps: Monday 00:00 is step 0, Sunday 23:00 is step 2004

    WEEK_STEPS = 2016

    def test_monday_morning_run_moved_earlier_does_not_vanish(self):
        # Monday 00:00-01:00, may start 1 hour earlier; flat price, no generation: nothing to gain
        problem = make_problem([(1, 0, 12, 10.0, 12, 0)], np.zeros(self.WEEK_STEPS), np.full(self.WEEK_STEPS, 0.2))
        baseline = problem.cost(zeros(problem))
        for k in range(-12, 1):
            with self.subTest(shift=k):
                self.assertAlmostEqual(problem.cost(np.array([k])), baseline)
        self.assertAlmostEqual(self.solve_cost(problem), baseline)  # No fake saving

    def test_monday_morning_run_can_move_to_sunday_evening(self):
        # Electricity is cheaper on Sunday 23:00-24:00: the run moves there with all its energy
        price = np.full(self.WEEK_STEPS, 0.2)
        price[2004:] = 0.05
        problem = make_problem([(1, 0, 12, 10.0, 12, 0)], np.zeros(self.WEEK_STEPS), price)
        shifts = self.solve(problem).shift_steps
        self.assertEqual(shifts[0], -12)
        demand = problem.demand(shifts)
        self.assertEqual(set(np.flatnonzero(demand)), set(range(2004, 2016)))
        self.assertAlmostEqual(problem.cost(shifts), 12 * 10.0 * 0.05)

    def test_sunday_night_run_moved_later_lands_on_monday_morning(self):
        price = np.full(self.WEEK_STEPS, 0.2)
        price[:12] = 0.05
        problem = make_problem([(1, 2004, 12, 10.0, 0, 12)], np.zeros(self.WEEK_STEPS), price)
        shifts = self.solve(problem).shift_steps
        self.assertEqual(shifts[0], 12)
        self.assertEqual(set(np.flatnonzero(problem.demand(shifts))), set(range(12)))
        self.assertAlmostEqual(problem.cost(shifts), 12 * 10.0 * 0.05)

    def test_run_crossing_midnight_cannot_overlap_its_own_process_through_the_boundary(self):
        # Run 1 crosses Sunday/Monday (steps 2010..2015, 0..5); run 2 of the same process starts at
        # step 8 and may advance by 6 into a cheap slot at steps 2..7, which run 1 partly occupies
        price = np.full(self.WEEK_STEPS, 0.2)
        price[2:8] = 0.01
        problem = make_problem([(1, 2010, 12, 1.0, 0, 0), (1, 8, 6, 1.0, 6, 0)], np.zeros(self.WEEK_STEPS), price)
        shifts = self.solve(problem).shift_steps
        self.assertTrue(is_feasible(problem, shifts))
        self.assertEqual(shifts[1], -2)  # Up to step 6: run 1 ends at step 5


# ----------------------------------------------------------------------------
# Integration tests
# ----------------------------------------------------------------------------

def minute_of_week(day, hour, minute):
    return day * 1440 + hour * 60 + minute


class PackagerIntegrationTests(TestCase):
    """
    Reference week: two press runs on Monday morning (60 min backward, 120 min
    forward tolerance) and a fixed oven run on Tuesday night. A solar plant
    produces 1000 kWh/h from 10:00 to 13:00 on Monday, the price is flat.
    Only a delay of more than 60 minutes lets the first press run be fully
    covered by solar power, so the optimum leaves only the oven buying from
    the grid: 60 kWh/h * 6 h * 0.2 EUR/kWh = 72 EUR.
    """

    WEEK = date(2024, 7, 8)  # A Monday
    ORIGINAL = {'press_run1': (480, 600), 'press_run2': (630, 720), 'oven_run1': (1440, 1800)}  # Minutes of the week
    TOLERANCES = {'press': (120, 60), 'oven': (0, 0)}  # (forward, backward) minutes

    @classmethod
    def setUpTestData(cls):
        cls.plan = WeeklyProductionPlan.objects.create(name='reference')
        press = Process.objects.create(name='press', electricity_consumption_kWh=120, production_plan=cls.plan)
        oven = Process.objects.create(name='oven', electricity_consumption_kWh=60, production_plan=cls.plan)
        for name, start, end in [('first', (8, 0), (10, 0)), ('second', (10, 30), (12, 0))]:
            Shift.objects.create(name=name, process=press, start_day=0, start_hour=start[0], start_minutes=start[1],
                                 end_day=0, end_hour=end[0], end_minutes=end[1],
                                 max_forward_minutes=120, max_backwards_minutes=60)
        Shift.objects.create(name='night', process=oven, start_day=1, start_hour=0, end_day=1, end_hour=6,
                             max_forward_minutes=0, max_backwards_minutes=0)

        cls.generation = GenerationDataset.objects.create(name='generation')
        cls.prices = PricesDataset.objects.create(name='prices')
        tz = pytz.timezone(settings.TIME_ZONE)
        hours = [tz.localize(datetime.combine(cls.WEEK, datetime.min.time())) + timedelta(hours=h)
                 for h in range(7 * 24 + 1)]
        GenerationRecord.objects.bulk_create(
            GenerationRecord(generation_dataset=cls.generation, timestamp=ts, ele_generated_by_cogen_kWh=0,
                             ele_generated_by_solar_kWh=1000 if ts.weekday() == 0 and 10 <= ts.hour <= 13 else 0)
            for ts in hours)
        PricesRecord.objects.bulk_create(
            PricesRecord(prices_dataset=cls.prices, timestamp=ts, electricity_price=0.2)
            for ts in hours)

    def create_optimization(self, optimizer):
        return Optimization.objects.create(
            name=f'test {optimizer}', optimizer=optimizer, reference_production_plan=self.plan,
            optimized_plan_name=f'optimized {optimizer}', reference_week_start=self.WEEK,
            reference_week_end=self.WEEK + timedelta(days=6),
            generation_dataset=self.generation, prices_dataset=self.prices)

    def run_with_problem(self, optimizer):
        """Run the pipeline and also return the OptimizationProblem it built."""
        problems = []

        def capture(*args, **kwargs):
            problems.append(OptimizationProblem(*args, **kwargs))
            return problems[-1]

        with mock.patch('OptimizerApp.optimizer_packager.OptimizationProblem', side_effect=capture):
            optimization = run_optimization(self.create_optimization(optimizer).id)
        return optimization, problems[0]

    def assertPlanFollowsShifts(self, optimization):
        """The optimized plan is the reference plan with every run moved by its reported shift."""
        plan = optimization.optimized_production_plan
        self.assertTrue(optimization.is_completed())
        self.assertTrue(plan.is_optimized)
        self.assertNotEqual(plan.pk, self.plan.pk)
        self.assertEqual({(p.name, p.electricity_consumption_kWh) for p in plan.processes.all()},
                         {('press', 120), ('oven', 60)})

        shifts = {s.name: s for s in Shift.objects.filter(process__production_plan=plan)}
        moved = {c['phase_name']: c['shift_minutes'] for c in optimization.optimization_data['shift_changes']}
        self.assertEqual(set(shifts), set(self.ORIGINAL))
        self.assertEqual(set(moved), set(self.ORIGINAL))
        for name, (start, end) in self.ORIGINAL.items():
            shift = shifts[name]
            forward, backward = self.TOLERANCES[shift.process.name]
            self.assertTrue(-backward <= moved[name] <= forward, name)
            self.assertEqual(minute_of_week(shift.start_day, shift.start_hour, shift.start_minutes), start + moved[name])
            self.assertEqual(minute_of_week(shift.end_day, shift.end_hour, shift.end_minutes), end + moved[name])
            self.assertEqual((shift.max_forward_minutes, shift.max_backwards_minutes), (forward, backward))
        return moved

    def assertCostsAreConsistent(self, optimization, problem):
        """Reported costs are problem.cost of the baseline and of the written-back shifts."""
        data = optimization.optimization_data
        shift_steps = np.array([c['shift_steps'] for c in data['shift_changes']])
        baseline, final = problem.cost(zeros(problem)), problem.cost(shift_steps)
        savings = max(0.0, baseline - final)
        self.assertAlmostEqual(data['baseline_cost'], baseline)
        self.assertAlmostEqual(data['final_cost'], final)
        self.assertEqual(optimization.initial_cost_euros, round(baseline, 2))
        self.assertEqual(optimization.optimized_cost_euros, round(final, 2))
        self.assertEqual(optimization.cost_savings_euros, round(savings, 2))
        self.assertEqual(optimization.cost_savings_percent, round(min(100.0, savings / baseline * 100.0), 2))

    def test_milp_writes_back_a_valid_optimized_plan(self):
        optimization, _ = self.run_with_problem('milp')
        moved = self.assertPlanFollowsShifts(optimization)
        self.assertEqual(optimization.optimization_data['optimizer'], 'milp')
        self.assertIn('Optimal', optimization.optimization_data['solver_status'])
        # Delayed by more than the 60-minute backward tolerance: asymmetric bounds are not clamped
        self.assertGreater(moved['press_run1'], 60)
        self.assertEqual(moved['oven_run1'], 0)
        # The two press runs do not overlap
        first, second = sorted((self.ORIGINAL[n][0] + moved[n], self.ORIGINAL[n][1] + moved[n])
                               for n in ('press_run1', 'press_run2'))
        self.assertLessEqual(first[1], second[0])

    def test_milp_reports_the_optimal_cost(self):
        optimization, problem = self.run_with_problem('milp')
        self.assertCostsAreConsistent(optimization, problem)
        best = brute_force_optimum(problem)
        self.assertAlmostEqual(optimization.optimization_data['final_cost'], best, delta=GAP * best + 1e-9)
        self.assertAlmostEqual(optimization.optimized_cost_euros, 72.0)
        self.assertGreater(optimization.initial_cost_euros, optimization.optimized_cost_euros)

    def test_from_scratch_runs_through_the_same_pipeline(self):
        optimization, problem = self.run_with_problem('from-scratch')
        moved = self.assertPlanFollowsShifts(optimization)
        self.assertCostsAreConsistent(optimization, problem)
        self.assertEqual(optimization.optimization_data['optimizer'], 'from-scratch')
        self.assertIn('lsqr_iterations', optimization.optimization_data)
        # From-scratch only uses the symmetric bound min(forward, backward)
        self.assertLessEqual(abs(moved['press_run1']), 60)
        self.assertLessEqual(abs(moved['press_run2']), 60)

    def test_milp_beats_from_scratch_on_this_week(self):
        milp, _ = self.run_with_problem('milp')
        from_scratch, _ = self.run_with_problem('from-scratch')
        self.assertLess(milp.optimized_cost_euros, from_scratch.optimized_cost_euros)

    def test_rerun_updates_the_same_plan(self):
        optimization, _ = self.run_with_problem('milp')
        plan_id, plans = optimization.optimized_production_plan_id, WeeklyProductionPlan.objects.count()
        optimization = run_optimization(optimization.id)
        self.assertEqual(optimization.optimized_production_plan_id, plan_id)
        self.assertEqual(WeeklyProductionPlan.objects.count(), plans)
        self.assertEqual(Shift.objects.filter(process__production_plan_id=plan_id).count(), len(self.ORIGINAL))
        self.assertPlanFollowsShifts(optimization)

    def test_each_run_takes_the_tolerance_of_its_own_shift(self):
        # Make only the second press shift fixed: the first one keeps its 120/60 minutes
        Shift.objects.filter(process__production_plan=self.plan, name='second').update(
            max_forward_minutes=0, max_backwards_minutes=0)
        try:
            _, problem = self.run_with_problem('milp')
        finally:
            Shift.objects.filter(process__production_plan=self.plan, name='second').update(
                max_forward_minutes=120, max_backwards_minutes=60)
        bounds = {i['run_name']: (i['max_backward_steps'], i['max_forward_steps']) for i in problem.run_info}
        self.assertEqual(bounds, {'press_run1': (12, 24), 'press_run2': (0, 0), 'oven_run1': (0, 0)})

    def test_reference_period_must_be_one_week(self):
        optimization = self.create_optimization('milp')
        optimization.reference_week_end = self.WEEK + timedelta(days=2)
        optimization.save()
        with self.assertRaisesMessage(ValueError, 'exactly one week'):
            run_optimization(optimization.id)

    def test_plan_without_runs_is_rejected(self):
        empty = WeeklyProductionPlan.objects.create(name='empty')
        Process.objects.create(name='idle', electricity_consumption_kWh=10, production_plan=empty)
        optimization = self.create_optimization('milp')
        optimization.reference_production_plan = empty
        optimization.save()
        with self.assertRaisesMessage(ValueError, 'No shifts found'):
            run_optimization(optimization.id)

    def test_command_prints_the_diagnostics_of_each_optimizer(self):
        for optimizer, expected in [('milp', 'Solver Status: Optimization terminated successfully'),
                                    ('from-scratch', 'LSQR Iterations: ')]:
            with self.subTest(optimizer=optimizer):
                out = StringIO()
                call_command('run_optimization', self.create_optimization(optimizer).id, stdout=out)
                self.assertIn(expected, out.getvalue())


def week_hours(monday):
    """Hourly timestamps of a week, plus Monday 00:00 of the next week."""
    tz = pytz.timezone(settings.TIME_ZONE)
    start = tz.localize(datetime.combine(monday, datetime.min.time()))
    return [start + timedelta(hours=h) for h in range(7 * 24 + 1)]


class WeekBoundaryIntegrationTests(TestCase):
    """
    The whole pipeline with runs at the ends of the week: no energy lost, no crash
    when writing the plan back, and the cost simulation of the written plan agrees.
    One 120 kW process, no generation, price 0.2 EUR/kWh except where noted.
    """

    WEEK = date(2024, 7, 8)

    @classmethod
    def setUpTestData(cls):
        cls.generation = GenerationDataset.objects.create(name='no generation')
        GenerationRecord.objects.bulk_create(
            GenerationRecord(generation_dataset=cls.generation, timestamp=ts, ele_generated_by_cogen_kWh=0,
                             ele_generated_by_solar_kWh=0) for ts in week_hours(cls.WEEK))

    def prices(self, cheap_hours=()):
        """Prices dataset at 0.2 EUR/kWh, 0.05 in the given (weekday, hour) slots."""
        dataset = PricesDataset.objects.create(name=f'prices {PricesDataset.objects.count()}')
        PricesRecord.objects.bulk_create(
            PricesRecord(prices_dataset=dataset, timestamp=ts,
                         electricity_price=0.05 if (ts.weekday(), ts.hour) in cheap_hours else 0.2)
            for ts in week_hours(self.WEEK))
        return dataset

    def optimize(self, shift, prices):
        """Optimise a one-process plan with the given shift; returns (optimization, problem)."""
        plan = WeeklyProductionPlan.objects.create(name=f'plan {WeeklyProductionPlan.objects.count()}')
        process = Process.objects.create(name='mixer', electricity_consumption_kWh=120, production_plan=plan)
        Shift.objects.create(name='batch', process=process, **shift)
        optimization = Optimization.objects.create(
            name=plan.name, reference_production_plan=plan, reference_week_start=self.WEEK,
            reference_week_end=self.WEEK + timedelta(days=6), generation_dataset=self.generation, prices_dataset=prices)
        problems = []

        def capture(*args, **kwargs):
            problems.append(OptimizationProblem(*args, **kwargs))
            return problems[-1]

        with mock.patch('OptimizerApp.optimizer_packager.OptimizationProblem', side_effect=capture):
            optimization = run_optimization(optimization.id)
        return optimization, problems[0]

    def simulate(self, optimization):
        """Cost simulation of the original and the optimised plan on the reference week."""
        from PlanningApp.models import Simulation
        from SimulationApp.simulation import run_simulation
        simulation = Simulation.objects.create(
            name=f'check {optimization.name}', original_production_plan=optimization.reference_production_plan,
            optimized_production_plan=optimization.optimized_production_plan, generation_dataset=self.generation,
            prices_dataset=optimization.prices_dataset, start_date=self.WEEK, end_date=self.WEEK + timedelta(days=6))
        results = run_simulation(simulation.pk)
        timestep = results.timestep_data
        return results, sum(timestep['original_demand_kWh']), sum(timestep['total_demand_kWh'])

    def written_shift(self, optimization):
        shift = Shift.objects.get(process__production_plan=optimization.optimized_production_plan)
        return (shift.start_day, shift.start_hour, shift.start_minutes, shift.end_day, shift.end_hour, shift.end_minutes)

    def assertEnergyKept(self, optimization, results, original_kWh, optimized_kWh, expected_kWh):
        data = optimization.optimization_data
        self.assertAlmostEqual(data['demand_kWh']['original'], expected_kWh)
        self.assertAlmostEqual(data['demand_kWh']['optimized'], expected_kWh)
        self.assertAlmostEqual(original_kWh, expected_kWh)
        self.assertAlmostEqual(optimized_kWh, expected_kWh)
        # The simulation of the written plan reproduces the optimiser's costs
        self.assertAlmostEqual(results.original_cost_euros, data['baseline_cost'])
        self.assertAlmostEqual(results.optimized_cost_euros, data['final_cost'])

    def test_monday_morning_run_allowed_to_start_earlier_does_not_vanish(self):
        # Monday 00:00-01:00 may start 1 hour earlier; flat price: no saving is possible
        optimization, _ = self.optimize(dict(start_day=0, start_hour=0, end_day=0, end_hour=1,
                                             max_forward_minutes=0, max_backwards_minutes=60), self.prices())
        self.assertAlmostEqual(optimization.optimization_data['final_cost'], 120 * 0.2)
        self.assertEqual(optimization.cost_savings_euros, 0)
        self.assertEnergyKept(optimization, *self.simulate(optimization), expected_kWh=120)

    def test_monday_morning_run_moves_to_sunday_evening(self):
        optimization, _ = self.optimize(dict(start_day=0, start_hour=0, end_day=0, end_hour=1,
                                             max_forward_minutes=0, max_backwards_minutes=60),
                                        self.prices(cheap_hours={(6, 23)}))
        self.assertEqual(self.written_shift(optimization), (6, 23, 0, 0, 0, 0))  # Sunday 23:00 - Monday 00:00
        self.assertAlmostEqual(optimization.optimization_data['final_cost'], 120 * 0.05)
        self.assertEnergyKept(optimization, *self.simulate(optimization), expected_kWh=120)

    def test_sunday_night_run_moved_later_is_written_on_monday_morning(self):
        # This case used to crash when the plan was written back (index past the end of the week)
        optimization, _ = self.optimize(dict(start_day=6, start_hour=23, end_day=0, end_hour=0,
                                             max_forward_minutes=60, max_backwards_minutes=0),
                                        self.prices(cheap_hours={(0, 0)}))
        self.assertEqual(self.written_shift(optimization), (0, 0, 0, 0, 1, 0))  # Monday 00:00 - 01:00
        self.assertAlmostEqual(optimization.optimization_data['final_cost'], 120 * 0.05)
        self.assertEnergyKept(optimization, *self.simulate(optimization), expected_kWh=120)

    def test_run_crossing_midnight_is_one_run_and_moves_whole(self):
        # Sunday 23:00 - Monday 01:00 is one batch of 2 hours, not two pieces moving apart
        optimization, problem = self.optimize(dict(start_day=6, start_hour=23, end_day=0, end_hour=1,
                                                   max_forward_minutes=0, max_backwards_minutes=120),
                                              self.prices(cheap_hours={(6, 21), (6, 22)}))
        N = problem.num_timesteps
        self.assertEqual(len(problem.run_info), 1)
        self.assertEqual((problem.run_info[0]['original_start'], problem.run_info[0]['original_end']),
                         (N - 12, N + 11))
        self.assertEqual(self.written_shift(optimization), (6, 21, 0, 6, 23, 0))  # Sunday 21:00 - 23:00
        self.assertAlmostEqual(optimization.optimization_data['final_cost'], 240 * 0.05)
        self.assertEnergyKept(optimization, *self.simulate(optimization), expected_kWh=240)

    def test_write_back_refuses_a_schedule_that_changes_the_energy(self):
        # Safety net: if an optimiser ever lost energy, nothing would be saved
        prices = self.prices()
        with mock.patch('OptimizerApp.optimizer_packager.apply_shifts_from_steps',
                        side_effect=lambda matrix, shifts: matrix * 0.5):
            with self.assertRaisesMessage(RuntimeError, 'it was not saved'):
                self.optimize(dict(start_day=2, start_hour=8, end_day=2, end_hour=9,
                                   max_forward_minutes=0, max_backwards_minutes=0), prices)
        self.assertFalse(Optimization.objects.filter(completed_at__isnull=False).exists())


class IncompleteDataTests(TestCase):
    """Missing or invalid hours of generation or prices stop the optimisation before the solver runs."""

    WEEK = date(2024, 7, 8)

    @classmethod
    def setUpTestData(cls):
        cls.plan = WeeklyProductionPlan.objects.create(name='plan')
        press = Process.objects.create(name='press', electricity_consumption_kWh=120, production_plan=cls.plan)
        Shift.objects.create(name='s', process=press, start_day=2, start_hour=8, end_day=2, end_hour=10,
                             max_forward_minutes=60, max_backwards_minutes=60)
        cls.generation = GenerationDataset.objects.create(name='generation')
        cls.prices = PricesDataset.objects.create(name='prices')
        hours = week_hours(cls.WEEK)
        GenerationRecord.objects.bulk_create(
            GenerationRecord(generation_dataset=cls.generation, timestamp=ts, ele_generated_by_cogen_kWh=50,
                             ele_generated_by_solar_kWh=0) for ts in hours)
        PricesRecord.objects.bulk_create(
            PricesRecord(prices_dataset=cls.prices, timestamp=ts, electricity_price=0.2) for ts in hours)
        cls.hours = hours

    def assertRefused(self, message):
        optimization = Optimization.objects.create(
            name='o', reference_production_plan=self.plan, reference_week_start=self.WEEK,
            reference_week_end=self.WEEK + timedelta(days=6), generation_dataset=self.generation,
            prices_dataset=self.prices)
        with mock.patch.object(MILPOptimizer, 'optimize') as solver:
            with self.assertRaisesMessage(MissingDataError, message):
                run_optimization(optimization.id)
            solver.assert_not_called()
        optimization.refresh_from_db()
        self.assertFalse(optimization.is_completed())
        self.assertFalse(WeeklyProductionPlan.objects.filter(is_optimized=True).exists())

    def test_complete_data_are_accepted(self):
        optimization = Optimization.objects.create(
            name='ok', reference_production_plan=self.plan, reference_week_start=self.WEEK,
            reference_week_end=self.WEEK + timedelta(days=6), generation_dataset=self.generation,
            prices_dataset=self.prices)
        self.assertTrue(run_optimization(optimization.id).is_completed())

    def test_a_missing_day_of_generation_is_refused(self):
        wednesday = [ts for ts in self.hours if ts.weekday() == 2 and ts.date() == self.WEEK + timedelta(days=2)]
        GenerationRecord.objects.filter(generation_dataset=self.generation, timestamp__in=wednesday).delete()
        self.assertRefused('generation data "generation" have no value for 24 hour(s)')

    def test_a_missing_price_hour_is_refused(self):
        PricesRecord.objects.filter(prices_dataset=self.prices, timestamp=self.hours[3 * 24 + 12]).delete()
        self.assertRefused('no value for 1 hour(s) of the period (08 Jul 2024 00:00 to 14 Jul 2024 23:00): 11 Jul 2024 12:00')

    def test_a_missing_first_or_last_hour_is_refused(self):
        GenerationRecord.objects.filter(generation_dataset=self.generation, timestamp=self.hours[-2]).delete()
        self.assertRefused('14 Jul 2024 23:00')

    def test_an_infinite_value_is_refused(self):
        GenerationRecord.objects.filter(generation_dataset=self.generation, timestamp=self.hours[30]).update(
            ele_generated_by_cogen_kWh=float('inf'))
        self.assertRefused('is not a number')

    def test_a_negative_price_is_refused(self):
        PricesRecord.objects.filter(prices_dataset=self.prices, timestamp=self.hours[40]).update(electricity_price=-0.1)
        self.assertRefused('is negative')


class LiveProgressFixture:
    """A plan with one flexible press run on Wednesday and a complete week of data."""

    WEEK = date(2024, 7, 8)

    def make_data(self):
        self.plan = WeeklyProductionPlan.objects.create(name='plan')
        press = Process.objects.create(name='press', electricity_consumption_kWh=120, production_plan=self.plan)
        Shift.objects.create(name='s', process=press, start_day=2, start_hour=8, end_day=2, end_hour=10,
                             max_forward_minutes=60, max_backwards_minutes=60)
        self.generation = GenerationDataset.objects.create(name='generation')
        self.prices = PricesDataset.objects.create(name='prices')
        hours = week_hours(self.WEEK)
        GenerationRecord.objects.bulk_create(
            GenerationRecord(generation_dataset=self.generation, timestamp=ts, ele_generated_by_cogen_kWh=0,
                             ele_generated_by_solar_kWh=200 if 9 <= ts.hour <= 12 else 0) for ts in hours)
        PricesRecord.objects.bulk_create(
            PricesRecord(prices_dataset=self.prices, timestamp=ts, electricity_price=0.2) for ts in hours)
        self.optimization = Optimization.objects.create(
            name='live', reference_production_plan=self.plan, reference_week_start=self.WEEK,
            reference_week_end=self.WEEK + timedelta(days=6), generation_dataset=self.generation,
            prices_dataset=self.prices)

    def recorded_steps(self):
        """Patch the progress recorder to remember every (step, label) it saves."""
        from . import background
        steps = []
        original = background.ProgressRecorder._save

        def spy(recorder):
            steps.append((recorder.progress['step'], recorder.progress['label'], recorder.progress['detail']))
            original(recorder)
        return steps, mock.patch.object(background.ProgressRecorder, '_save', spy)


@override_settings(OPTIMIZATION_BACKGROUND=False)
class LiveProgressTests(LiveProgressFixture, TestCase):

    def setUp(self):
        self.make_data()
        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_superuser('admin', '', 'pw'))
        self.url = f'/api/optimizer/optimizations/{self.optimization.pk}/'

    def test_steps_are_reported_in_order_and_the_run_ends_done(self):
        from .background import run_now
        steps, spy = self.recorded_steps()
        with spy:
            run_now(self.optimization.pk)
        self.assertEqual([step for step, _, _ in steps if step], [1, 2, 3, 4])
        self.assertEqual([label for step, label, _ in steps if step], STEPS)
        solver_step = next(detail for step, _, detail in steps if step == 3)
        self.assertIn('1 runs, 25 possible positions', solver_step)  # The solver step names the model size
        self.optimization.refresh_from_db()
        self.assertEqual(self.optimization.status, 'done')
        self.assertEqual(self.optimization.progress['label'], 'Done')

    def test_api_starts_the_run_and_reports_its_progress(self):
        response = self.client.post(self.url + 'run/')
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['status'], 'done')  # Calculated in the request in tests
        state = self.client.get(self.url + 'progress/').json()
        self.assertEqual(state['status'], 'done')
        self.assertTrue(state['is_completed'])
        self.assertEqual(self.client.get(self.url).json()['live']['status'], 'done')

    def test_a_failure_is_reported_with_its_message(self):
        PricesRecord.objects.filter(prices_dataset=self.prices, timestamp__hour=12).delete()
        state = self.client.post(self.url + 'run/').json()
        self.assertEqual(state['status'], 'failed')
        self.assertIn('have no value for 7 hour(s)', state['error'])
        self.assertEqual(state['progress']['step'], 1)  # Stopped while checking the data

    def set_running(self, minutes_ago):
        from django.utils import timezone
        moment = (timezone.now() - timedelta(minutes=minutes_ago)).isoformat()
        Optimization.objects.filter(pk=self.optimization.pk).update(status='running', progress={
            'step': 3, 'steps': 4, 'label': STEPS[2], 'detail': '1 runs', 'started_at': moment,
            'step_started_at': moment, 'updated_at': moment, 'time_limit': 20})

    def test_a_second_start_is_refused_while_running(self):
        self.set_running(minutes_ago=0)
        response = self.client.post(self.url + 'run/')
        self.assertEqual(response.status_code, 409)
        self.assertIn('already being calculated', response.json()['error'])
        self.assertEqual(self.client.get(self.url + 'progress/').json()['status'], 'running')

    def test_a_run_without_news_is_reported_as_failed_and_can_be_restarted(self):
        self.set_running(minutes_ago=10)
        state = self.client.get(self.url + 'progress/').json()
        self.assertEqual(state['status'], 'failed')
        self.assertIn('stopped without finishing', state['error'])
        self.assertEqual(self.client.post(self.url + 'run/').status_code, 202)

    def test_runs_interrupted_by_a_restart_are_marked_failed(self):
        from .background import interrupt_running
        self.set_running(minutes_ago=0)
        self.assertEqual(interrupt_running(), 1)
        self.optimization.refresh_from_db()
        self.assertEqual((self.optimization.status, 'restarted' in self.optimization.error), ('failed', True))

    def test_admin_shows_the_live_progress_while_running(self):
        self.set_running(minutes_ago=0)
        page = self.client.get(f'/admin/OptimizerApp/optimization/{self.optimization.pk}/change/')
        self.assertContains(page, 'data-sparc-progress="/api/optimizer/optimizations/')
        self.assertContains(page, STEPS[2])
        self.assertContains(self.client.get('/admin/OptimizerApp/optimization/'), 'Calculating…')

    def test_command_prints_the_steps(self):
        out = StringIO()
        call_command('run_optimization', self.optimization.pk, stdout=out)
        for number, label in enumerate(STEPS, start=1):
            self.assertIn(f'[{number}/4] {label}', out.getvalue())


class BackgroundThreadTests(LiveProgressFixture, TransactionTestCase):
    """The real background thread (needs committed data, hence a TransactionTestCase)."""

    def test_the_thread_calculates_and_records_every_step(self):
        from .background import start
        self.make_data()
        steps, spy = self.recorded_steps()
        with spy, override_settings(OPTIMIZATION_BACKGROUND=True):
            thread = start(self.optimization.pk)
            self.assertIsNotNone(thread)
            thread.join(timeout=60)
        self.assertFalse(thread.is_alive())
        self.optimization.refresh_from_db()
        self.assertEqual(self.optimization.status, 'done', self.optimization.error)
        self.assertTrue(self.optimization.is_completed())
        self.assertEqual([step for step, _, _ in steps if step], [1, 2, 3, 4])
