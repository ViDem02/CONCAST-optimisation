"""
Shared helpers of the analysis scripts: rebuild, without Django, the
OptimizationProblem that SPARC builds for a reference week, from the CSV files
in data/ (same 5-minute grid, periodic run detection, interpolation, data checks and
tolerances as OptimizerApp.optimizer_packager), and evaluate shift vectors with the same cost.
"""

import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / 'data'
sys.path.insert(0, str(REPO / 'backend'))

from OptimizerApp.optimizers.base import OptimizationProblem, apply_shifts_from_steps, compute_cost, run_steps  # noqa: E402

STEP = 5                 # minutes
DT = STEP / 60           # hours per step
STEPS_PER_WEEK = 7 * 24 * 60 // STEP
GENERATION_FILES = {'current': 'generation.csv', 'fv3': 'generation_fv3.csv'}


def load_hourly(name, columns):
    """{naive local datetime: [values]} from a CSV of data/."""
    with open(DATA / name) as f:
        return {datetime.strptime(r['Time'], '%Y-%m-%d %H:%M:%S'): [float(r[c]) for c in columns]
                for r in csv.DictReader(f)}


def load_generation(scenario):
    return load_hourly(GENERATION_FILES[scenario], ['cogen_kWh', 'solar_kWh'])


def load_prices():
    return load_hourly('prices.csv', ['electricity_price'])


def load_plan(window_minutes=None):
    """
    Processes of production.yaml and the weekly timetable as
    {(process, weekday, minute of day): 0/1}. With window_minutes, the
    flexible processes (b_*) get that window in both directions.
    """
    config = yaml.safe_load(open(DATA / 'production.yaml'))['processes']
    if window_minutes is not None:
        for name, settings in config.items():
            if name.startswith('b_'):
                settings['max_forward_minutes'] = settings['max_backwards_minutes'] = window_minutes
    template = {}
    for row in csv.DictReader(open(DATA / 'production_timetable.csv')):
        ts = datetime.strptime(row['Time'], '%Y-%m-%d %H:%M:%S')
        for name in config:
            template[(name, ts.weekday(), ts.hour * 60 + ts.minute)] = int(row[name])
    return config, template


def _retime(hourly, timesteps, linear):
    """Like DatasetApp.series: every hour must exist; the last hour holds if there is no next one."""
    values = []
    for ts in timesteps:
        hour = ts.replace(minute=0)
        if hour not in hourly:
            raise ValueError(f'missing hour {hour}')
        before = hourly[hour]
        if linear:
            after = hourly.get(hour + timedelta(hours=1), before)
            values.append(before + (after - before) * ts.minute / 60)
        else:
            values.append(before)
    return np.array(values)


def _runs(activity):
    """Blocks of activity; a block crossing Sunday 24:00 is one run with end >= N (periodic week)."""
    runs, start = [], None
    for i, value in enumerate(list(activity) + [0]):
        if value and start is None:
            start = i
        elif not value and start is not None:
            runs.append((start, i - 1))
            start = None
    N = len(activity)
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == N - 1:
        first, last = runs.pop(0), runs.pop()
        runs.append((last[0], first[1] + N))
    return runs


def build_problem(week_start, generation, prices, plan):
    """OptimizationProblem of the week starting at week_start (a Monday), like run_optimization."""
    config, template = plan
    timesteps = [week_start + timedelta(minutes=STEP * k) for k in range(STEPS_PER_WEEK)]
    end = timesteps[-1] + timedelta(minutes=STEP - 1)
    rows, info = [], []
    for process_id, name in enumerate(config):
        activity = [template[(name, ts.weekday(), ts.hour * 60 + ts.minute // 15 * 15)] for ts in timesteps]
        for number, (start, last) in enumerate(_runs(activity), start=1):
            demand = np.zeros(len(timesteps))
            demand[np.arange(start, last + 1) % len(timesteps)] = config[name]['electricity_consumption_kWh'] * DT
            rows.append(demand)
            info.append(dict(process_id=process_id, process_name=name, run_name=f'{name}_run{number}',
                             run_number=number, electricity_consumption_kWh=config[name]['electricity_consumption_kWh'],
                             original_start=start, original_end=last,
                             max_forward_steps=config[name]['max_forward_minutes'] // STEP,
                             max_backward_steps=config[name]['max_backwards_minutes'] // STEP))
    # Records of the week plus the next Monday 00:00 (used to interpolate the last hour)
    in_week = lambda hourly: {k: v for k, v in hourly.items() if week_start <= k <= end + timedelta(hours=1)}
    week_generation = in_week(generation)
    solar = _retime({k: v[1] for k, v in week_generation.items()}, timesteps, linear=True) * DT
    cogen = _retime({k: v[0] for k, v in week_generation.items()}, timesteps, linear=True) * DT
    price = _retime({k: v[0] for k, v in in_week(prices).items()}, timesteps, linear=False)
    problem = OptimizationProblem(
        elec_demand_matrix=np.vstack(rows), gen_kWh=solar + cogen, price_el=price,
        max_shift_steps=np.array([min(i['max_forward_steps'], i['max_backward_steps']) for i in info]),
        run_info=info)
    return problem, solar, cogen


def full_weeks(generation):
    """Mondays of every full week covered by the generation data."""
    week, last = datetime(2024, 1, 1), max(generation)
    while week + timedelta(days=7) <= last:
        yield week
        week += timedelta(days=7)


def evaluate(problem, shift_steps):
    """Cost and energy figures of a shift vector, with SPARC's cost function."""
    shifts = np.asarray(shift_steps, dtype=int)
    demand = apply_shifts_from_steps(problem.elec_demand_matrix, shifts).sum(axis=0)
    cost, details = compute_cost(demand, problem.gen_kWh, problem.price_el)
    return dict(cost=float(cost), grid_kWh=float(details['grid_purchase'].sum()),
                waste_kWh=float(details['total_wasted']), demand_kWh=float(demand.sum()),
                moved_runs=int((shifts != 0).sum()), shift_minutes=[int(k) * STEP for k in shifts])


def overlaps(problem, shift_steps):
    """Pairs of runs of the same process that overlap after shifting (independent of the MILP)."""
    N = problem.num_timesteps
    occupied = defaultdict(list)
    for info, k in zip(problem.run_info, shift_steps):
        occupied[info['process_name']].append((set(((run_steps(info, N) + int(k)) % N).tolist()), info['run_name']))
    pairs = []
    for runs in occupied.values():
        pairs += [(name_a, name_b) for i, (a, name_a) in enumerate(runs)
                  for b, name_b in runs[i + 1:] if a & b]
    return pairs


def season(monday):
    return {12: 'Winter', 1: 'Winter', 2: 'Winter', 3: 'Spring', 4: 'Spring', 5: 'Spring',
            6: 'Summer', 7: 'Summer', 8: 'Summer'}.get(monday.month, 'Autumn')
