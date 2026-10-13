"""
The end-of-week case: a flexible run on Sunday night allowed to start one hour
later. Before the periodic week was introduced, the run was pushed out of the
week (its demand disappeared, the cost "dropped" to zero) and the write-back
failed with IndexError. Now it keeps its energy and cost (flat price) and the
plan is written. Run it on a throw-away database:

    cd backend
    SQLITE_PATH=/tmp/edge.sqlite3 DJANGO_SECRET_KEY=dev DEBUG=True python manage.py migrate
    SQLITE_PATH=/tmp/edge.sqlite3 DJANGO_SECRET_KEY=dev DEBUG=True python manage.py shell < ../report/analysis/edge_case.py
"""
from datetime import date, datetime, timedelta

import numpy as np
import pytz
from django.conf import settings

from DatasetApp.models import GenerationDataset, GenerationRecord, PricesDataset, PricesRecord
from OptimizerApp import optimizer_packager
from OptimizerApp.models import Optimization
from OptimizerApp.optimizers.milp import MILPOptimizer
from PlanningApp.models import Process, Shift, WeeklyProductionPlan

tz = pytz.timezone(settings.TIME_ZONE)
plan = WeeklyProductionPlan.objects.create(name='edge case')
mixer = Process.objects.create(name='mixer', electricity_consumption_kWh=120, production_plan=plan)
Shift.objects.create(name='sunday night', process=mixer, start_day=6, start_hour=23, end_day=0, end_hour=0,
                     max_forward_minutes=60, max_backwards_minutes=0)
generation = GenerationDataset.objects.create(name='edge case: no generation')
prices = PricesDataset.objects.create(name='edge case: flat price')
hours = [tz.localize(datetime(2024, 7, 8)) + timedelta(hours=h) for h in range(7 * 24 + 1)]
GenerationRecord.objects.bulk_create(GenerationRecord(generation_dataset=generation, timestamp=t,
                                                      ele_generated_by_solar_kWh=0, ele_generated_by_cogen_kWh=0)
                                     for t in hours)
PricesRecord.objects.bulk_create(PricesRecord(prices_dataset=prices, timestamp=t, electricity_price=0.2) for t in hours)
optimization = Optimization.objects.create(
    name='edge case', reference_production_plan=plan, reference_week_start=date(2024, 7, 8),
    reference_week_end=date(2024, 7, 14), generation_dataset=generation, prices_dataset=prices)

captured = {}
original = optimizer_packager.OptimizationProblem
optimizer_packager.OptimizationProblem = lambda *a, **k: captured.setdefault('problem', original(*a, **k))
try:
    optimizer_packager.run_optimization(optimization.pk)
    print('write-back succeeded')
except IndexError as e:
    print('write-back failed:', e)
problem = captured['problem']
shift = MILPOptimizer().optimize(problem).shift_steps
print(f"run steps {problem.run_info[0]['original_start']}-{problem.run_info[0]['original_end']} of {problem.num_timesteps}; "
      f"MILP shift {shift}; cost {problem.cost(np.zeros(1, int)):.2f} -> {problem.cost(shift):.2f}")
