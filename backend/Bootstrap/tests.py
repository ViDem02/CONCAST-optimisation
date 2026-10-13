"""
End-to-end check of what a user sees: the first-start setup with the real
CONCAST data, then every admin page and every API list.
"""

import os
from datetime import date
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from ChillersApp.models import Chiller, ChillerSimulation
from DatasetApp.models import GenerationDataset, TemperatureDataset
from OptimizerApp.models import Optimization
from PlanningApp.models import Process, Simulation, WeeklyProductionPlan

DATA_DIR = Path(settings.BASE_DIR).parent / 'data'


ENVIRONMENT = {'SPARC_DEMO_DATA': str(DATA_DIR), 'SPARC_ADMIN_PASSWORD': 'secret'}


@override_settings(OPTIMIZATION_BACKGROUND=False)
@mock.patch.dict(os.environ, ENVIRONMENT)
class FirstStartTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        with mock.patch.dict(os.environ, ENVIRONMENT):
            call_command('setup_sparc', stdout=open(os.devnull, 'w'))
        cls.chiller = Chiller.objects.create(name='Room', insulation_u_value=0.3, surface_area=200)
        cls.chiller_simulation = ChillerSimulation.objects.create(
            name='Cold room July', chiller=cls.chiller, min_temperature=2, max_temperature=6,
            start_date='2024-07-15', end_date='2024-07-16',
            generation_dataset=GenerationDataset.objects.first(), temperature_dataset=TemperatureDataset.objects.get())

    def setUp(self):
        self.assertTrue(self.client.login(username='admin', password='secret'))

    def test_data_and_examples_are_ready(self):
        self.assertEqual(GenerationDataset.objects.count(), 2)
        self.assertEqual(WeeklyProductionPlan.objects.filter(is_optimized=False).count(), 1)
        optimization = Optimization.objects.get()
        self.assertTrue(optimization.is_completed())
        self.assertGreater(optimization.cost_savings_euros, 0)
        results = Simulation.objects.get().results
        self.assertLess(results.optimized_cost_euros, results.original_cost_euros)

    def test_setup_runs_only_once(self):
        call_command('setup_sparc', stdout=open(os.devnull, 'w'))
        self.assertEqual(Optimization.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_every_admin_page_opens(self):
        objects = [GenerationDataset.objects.first(), WeeklyProductionPlan.objects.first(), Process.objects.first(),
                   Simulation.objects.get(), Optimization.objects.get(), self.chiller, self.chiller_simulation,
                   User.objects.get()]
        urls = ['/admin/', '/admin/PlanningApp/weeklyproductionplan/import/']
        for model_admin in self.client.get('/admin/').context['available_apps']:
            for model in model_admin['models']:
                urls += [model['admin_url'], model['add_url']]
        for obj in objects:
            opts = obj._meta
            urls.append(f'/admin/{opts.app_label}/{opts.model_name}/{obj.pk}/change/')
            urls.append(f'/admin/{opts.app_label}/{opts.model_name}/{obj.pk}/delete/')
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_hidden_pages_are_not_on_the_home_page(self):
        names = {m['object_name'] for app in self.client.get('/admin/').context['available_apps'] for m in app['models']}
        self.assertNotIn('Process', names)
        self.assertNotIn('Group', names)
        self.assertNotIn('SimulationResults', names)

    def test_save_and_calculate_runs_the_cold_room_simulation(self):
        url = f'/admin/ChillersApp/chillersimulation/{self.chiller_simulation.pk}/change/'
        form = self.client.get(url).context['adminform'].form
        data = {k: v for k, v in form.initial.items() if v is not None}
        data.update(chiller=self.chiller.pk, generation_dataset=form.initial['generation_dataset'],
                    temperature_dataset=form.initial['temperature_dataset'], _run='1')
        data.pop('production_plan_result', None)
        data['allow_grid_power'] = 'on'
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, 'calculated')
        self.chiller_simulation.refresh_from_db()
        self.assertTrue(self.chiller_simulation.calculated_temperature)

    def test_changing_settings_removes_the_old_result(self):
        optimization = Optimization.objects.get()
        url = f'/admin/OptimizerApp/optimization/{optimization.pk}/change/'
        form = self.client.get(url).context['adminform'].form
        data = {k: v for k, v in form.initial.items() if v is not None}
        data.update(reference_week_start='2024-07-22', reference_week_end='')
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, 'previous result was removed')
        optimization.refresh_from_db()
        self.assertFalse(optimization.is_completed())
        self.assertEqual(optimization.reference_week_end, date(2024, 7, 28))  # Filled in automatically

        data['_run'] = '1'
        self.assertContains(self.client.post(url, data, follow=True), 'optimised: grid electricity cost')
        optimization.refresh_from_db()
        self.assertTrue(optimization.is_completed())

    def test_api_lists_answer(self):
        for url in ['/api/datasets/generation-datasets/', '/api/planning/production-plans/',
                    '/api/planning/simulations/', '/api/simulation/simulation-results/',
                    '/api/optimizer/optimizations/', '/api/chillers/chiller-simulations/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        simulation = self.client.get('/api/planning/simulations/').json()['results'][0]
        self.assertIsNotNone(simulation['results']['savings_euros'])
