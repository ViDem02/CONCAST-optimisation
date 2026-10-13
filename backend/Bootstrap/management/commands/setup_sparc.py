"""
First-start setup, run by the Docker container every time it starts (it does
nothing once everything exists):

1. creates the admin account if there is no user yet;
2. if the database has no data at all, loads the CONCAST data found in
   SPARC_DEMO_DATA (the repository's data/ folder) and calculates one example
   optimisation and its check over a month, so the results website is not
   empty on the first visit.
"""

import os
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from DatasetApp.importers import import_csv
from DatasetApp.models import GenerationDataset, PricesDataset, TemperatureDataset
from PlanningApp.importers import import_plan
from PlanningApp.models import Simulation, WeeklyProductionPlan

# (dataset model, kind, file, name)
DATASETS = [
    (GenerationDataset, 'generation', 'generation.csv', 'Generation – current plants'),
    (GenerationDataset, 'generation', 'generation_fv3.csv', 'Generation – with FV3 solar plant'),
    (PricesDataset, 'prices', 'prices.csv', 'Electricity prices 2024–2025'),
    (TemperatureDataset, 'temperature', 'trento_historical_temperature.csv', 'Outside temperature – Trento'),
]
PLAN_NAME = 'CONCAST reference week'
EXAMPLE_WEEK = date(2024, 7, 15)  # A Monday in summer


class Command(BaseCommand):
    help = 'Create the admin account and load the example data on the first start'

    def handle(self, *args, **options):
        self.create_admin()
        data_dir = Path(os.environ.get('SPARC_DEMO_DATA', ''))
        has_data = (WeeklyProductionPlan.objects.exists() or GenerationDataset.objects.exists()
                    or PricesDataset.objects.exists())
        if has_data or not data_dir.is_dir():
            return
        self.load_data(data_dir)
        self.calculate_examples()

    def create_admin(self):
        if User.objects.exists():
            return
        username = os.environ.get('SPARC_ADMIN_USER', 'admin')
        password = os.environ.get('SPARC_ADMIN_PASSWORD', 'sparc')
        User.objects.create_superuser(username=username, email='', password=password)
        self.stdout.write(f'Created the login "{username}" with password "{password}". '
                          f'Change it in the admin (top right: "Change password").')

    def load_data(self, data_dir):
        for model, kind, filename, name in DATASETS:
            path = data_dir / filename
            if path.exists():
                count = import_csv(kind, model.objects.create(name=name), str(path))
                self.stdout.write(f'Loaded "{name}" ({count:,} hours)')
        timetable, config = data_dir / 'production_timetable.csv', data_dir / 'production.yaml'
        if timetable.exists() and config.exists():
            import_plan(str(timetable), str(config), PLAN_NAME)
            self.stdout.write(f'Loaded the production plan "{PLAN_NAME}"')

    def calculate_examples(self):
        from OptimizerApp.models import Optimization
        from OptimizerApp.optimizer_packager import run_optimization
        from SimulationApp.simulation import run_simulation

        plan = WeeklyProductionPlan.objects.filter(name=PLAN_NAME).first()
        generation = GenerationDataset.objects.filter(name=DATASETS[0][3]).first()
        prices = PricesDataset.objects.first()
        if not (plan and generation and prices):
            return
        try:
            optimization = Optimization.objects.create(
                name=f'Example – week of {EXAMPLE_WEEK:%d %b %Y}', reference_production_plan=plan,
                reference_week_start=EXAMPLE_WEEK, reference_week_end=date(2024, 7, 21),
                generation_dataset=generation, prices_dataset=prices,
                notes='Example created on the first start. Copy its settings to optimise other weeks.')
            optimization = run_optimization(optimization.pk)
            simulation = Simulation.objects.create(
                name='Example – July 2024 with the optimised plan',
                notes='Checks the plan optimised on one week over the whole month.',
                original_production_plan=plan, optimized_production_plan=optimization.optimized_production_plan,
                generation_dataset=generation, prices_dataset=prices,
                start_date=date(2024, 7, 1), end_date=date(2024, 7, 31))
            run_simulation(simulation.pk)
            self.stdout.write('Calculated the example optimisation and cost simulation')
        except Exception as e:  # The examples are a convenience: never block the start
            self.stderr.write(f'The examples could not be calculated: {e}')
