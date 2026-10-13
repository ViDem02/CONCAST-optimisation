"""
Savings when the plan is prepared without knowing the week: reuse last week's
optimised moves, or one set of moves per season (from the 2024 week of median cost).

    python report/analysis/strategies.py [results.json]       (uses the output of benchmark.py)
"""
import json
import sys
from datetime import datetime

import numpy as np

from weeks import build_problem, evaluate, load_generation, load_plan, load_prices, season

results = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'results.json'))
prices, plan = load_prices(), load_plan()
for scenario in ('current', 'fv3'):
    generation = load_generation(scenario)
    rows = [r for r in results if r['scenario'] == scenario]
    references = {}
    for name in ('Winter', 'Spring', 'Summer', 'Autumn'):
        candidates = sorted((r for r in rows if season(datetime.strptime(r['week'], '%Y-%m-%d')) == name
                             and r['week'] < '2025'), key=lambda r: r['baseline']['cost'])
        references[name] = candidates[len(candidates) // 2]
    totals = dict(base=0, perfect=0, seasonal=0, seasonal_worse=0, rolling=0, rolling_base=0, rolling_perfect=0,
                  rolling_worse=0)
    for i, row in enumerate(rows):
        week = datetime.strptime(row['week'], '%Y-%m-%d')
        problem, _, _ = build_problem(week, generation, prices, plan)
        moves = lambda r: np.array(r['milp']['shift_minutes']) // 5
        seasonal = evaluate(problem, moves(references[season(week)]))['cost']
        totals['base'] += row['baseline']['cost']
        totals['perfect'] += row['milp']['cost']
        totals['seasonal'] += seasonal
        totals['seasonal_worse'] += seasonal > row['baseline']['cost'] + 1e-6
        if i:
            rolling = evaluate(problem, moves(rows[i - 1]))['cost']
            totals['rolling'] += rolling
            totals['rolling_base'] += row['baseline']['cost']
            totals['rolling_perfect'] += row['milp']['cost']
            totals['rolling_worse'] += rolling > row['baseline']['cost'] + 1e-6
    n = len(rows)
    print(f"== {scenario}: perfect {totals['base'] - totals['perfect']:.0f} EUR over {n} weeks; "
          f"seasonal {totals['base'] - totals['seasonal']:.0f} (worse than original in {totals['seasonal_worse']} weeks); "
          f"reuse last week {totals['rolling_base'] - totals['rolling']:.0f} vs perfect "
          f"{totals['rolling_base'] - totals['rolling_perfect']:.0f} on the same {n - 1} weeks "
          f"(worse than original in {totals['rolling_worse']} weeks)")
