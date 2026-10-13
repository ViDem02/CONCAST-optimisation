"""
Validity tests for the shift optimizers (OptimizerApp.optimizers).

Unit tests, on small OptimizationProblem instances built by hand:
- RegistryTests: both optimizers can be chosen, the MILP is the default.
- OptimizerContractTests: the contract every registered optimizer must meet
  (mathematical specification, "Contract for optimizers").
- MILPConstraintTests: one instance with a known answer per MILP constraint.
- MILPOptimalityTests: random instances checked against brute-force enumeration.
- MILPFallbackTests: behaviour when HiGHS returns no solution or a bad one.

Integration tests (PackagerIntegrationTests) run the whole pipeline, from a
plan stored in the database to the optimized plan written back.
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
from django.test import SimpleTestCase, TestCase
from scipy.optimize import OptimizeResult

from DatasetApp.models import GenerationDataset, GenerationRecord, PricesDataset, PricesRecord
from PlanningApp.models import Process, Shift, WeeklyProductionPlan

from .models import Optimization
from .optimizer_packager import run_optimization
from .optimizers import DEFAULT_OPTIMIZER, OPTIMIZER_CHOICES, OPTIMIZERS, get_optimizer
from .optimizers.base import OptimizationProblem
from .optimizers.milp import MILPOptimizer

# Keys of optimization_data written by the packager, forbidden to optimizers
RESERVED_KEYS = {'optimizer', 'baseline_cost', 'final_cost', 'total_wasted_energy',
                 'shift_changes', 'num_timesteps', 'num_runs_optimized'}
GAP = MILPOptimizer.mip_rel_gap


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def make_problem(runs, gen, price):
    """
    Build a problem from runs given as
    (process_id, start step, length in steps, kWh per step, max backward steps, max forward steps).
    """
    N = len(price)
    demand = np.zeros((len(runs), N))
    run_info = []
    for r, (process, start, length, power, backward, forward) in enumerate(runs):
        demand[r, start:start + length] = power
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
    """Steps in which a run is on after being shifted (cut at the edges of the horizon)."""
    return set(range(max(0, info['original_start'] + shift), min(N, info['original_end'] + shift + 1)))


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

    def test_runs_at_the_edges_of_the_horizon_follow_problem_cost(self):
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
