"""
Optimise every full week of the data with the MILP (and the legacy heuristic)
for both generation scenarios, and check every schedule independently.

    python report/analysis/benchmark.py [results.json]       (about 25 minutes)

Prints one line per week and a summary; writes all results to results.json.
"""
import json
import statistics
import sys
import time

import numpy as np

from weeks import build_problem, evaluate, full_weeks, load_generation, load_plan, load_prices, overlaps, season
from OptimizerApp.optimizers.from_scratch import FromScratchOptimizer
from OptimizerApp.optimizers.milp import MILPOptimizer

output = sys.argv[1] if len(sys.argv) > 1 else 'results.json'
prices, plan = load_prices(), load_plan()
results = []
for scenario in ('current', 'fv3'):
    generation = load_generation(scenario)
    for week in full_weeks(generation):
        problem, solar, cogen = build_problem(week, generation, prices, plan)
        row = dict(scenario=scenario, week=f'{week:%Y-%m-%d}', solar_kWh=float(solar.sum()), cogen_kWh=float(cogen.sum()),
                   baseline=evaluate(problem, np.zeros(problem.num_runs, int)))
        for name, optimizer in (('milp', MILPOptimizer()), ('from_scratch', FromScratchOptimizer())):
            start = time.perf_counter()
            result = optimizer.optimize(problem)
            row[name] = evaluate(problem, result.shift_steps) | dict(
                seconds=time.perf_counter() - start, overlaps=len(overlaps(problem, result.shift_steps)),
                status=result.data.get('solver_status'), gap=result.data.get('mip_gap'))
        results.append(row)
        print(scenario, row['week'], f"{row['baseline']['cost']:.1f} -> {row['milp']['cost']:.1f}",
              f"({row['milp']['seconds']:.1f} s)", flush=True)
json.dump(results, open(output, 'w'), indent=1)

for scenario in ('current', 'fv3'):
    rows = [r for r in results if r['scenario'] == scenario]
    base = sum(r['baseline']['cost'] for r in rows)
    best = sum(r['milp']['cost'] for r in rows)
    print(f'\n== {scenario}: {len(rows)} weeks, saving {base - best:.0f} EUR ({(base - best) / base:.2%}), '
          f'{(base - best) / len(rows) * 52:.0f} EUR/year')
    print(f"  MILP: all schedules without overlap: {all(r['milp']['overlaps'] == 0 for r in rows)}; "
          f"never worse than the original plan: {all(r['milp']['cost'] <= r['baseline']['cost'] + 1e-9 for r in rows)}; "
          f"proven within 1e-4: {sum('Optimal' in (r['milp']['status'] or '') for r in rows)}/{len(rows)}; "
          f"median time {statistics.median(r['milp']['seconds'] for r in rows):.2f} s")
    print(f"  legacy: weeks with overlapping runs {sum(r['from_scratch']['overlaps'] > 0 for r in rows)}/{len(rows)}")
    for name in ('Winter', 'Spring', 'Summer', 'Autumn'):
        part = [r for r in rows if season(__import__('datetime').datetime.strptime(r['week'], '%Y-%m-%d')) == name]
        b, m = sum(r['baseline']['cost'] for r in part), sum(r['milp']['cost'] for r in part)
        print(f'  {name:7s} {len(part):3d} weeks, cost/week {b / len(part):7.0f}, saving/week {(b - m) / len(part):5.0f} ({(b - m) / b:.1%})')
