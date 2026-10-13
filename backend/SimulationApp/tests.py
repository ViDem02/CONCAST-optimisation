"""Tests of the cost simulation (SimulationApp.simulation)."""

import itertools
from datetime import date, datetime, timedelta

import numpy as np
import pytz
from django.conf import settings
from django.test import SimpleTestCase, TestCase

from DatasetApp.models import GenerationDataset, GenerationRecord, PricesDataset, PricesRecord
from PlanningApp.models import Process, Shift, Simulation, WeeklyProductionPlan

from .simulation import is_timestep_in_shift, minutes_of_week, run_simulation, shift_activity


class ShiftActivityTests(SimpleTestCase):
    """The vectorized shift_activity must match the reference is_timestep_in_shift."""

    def test_matches_is_timestep_in_shift(self):
        start = datetime(2024, 7, 8)  # A Monday
        timesteps = [start + timedelta(minutes=5 * k) for k in range(7 * 288)]
        week_minutes = minutes_of_week(timesteps)
        times = [(0, 0), (0, 5), (6, 30), (12, 0), (23, 55)]
        for (start_day, end_day), (sh, sm), (eh, em) in itertools.product(
                itertools.product(range(7), repeat=2), times, times):
            shift = Shift(start_day=start_day, start_hour=sh, start_minutes=sm,
                          end_day=end_day, end_hour=eh, end_minutes=em)
            expected = [is_timestep_in_shift(ts, shift) for ts in timesteps]
            with self.subTest(shift=(start_day, sh, sm, end_day, eh, em)):
                np.testing.assert_array_equal(shift_activity(week_minutes, shift), expected)


class RunSimulationTests(TestCase):
    """One process of 120 kW, Monday 10:00-12:00; 60 kWh/h of solar from 10:00 to 11:00; flat price."""

    @classmethod
    def setUpTestData(cls):
        tz = pytz.timezone(settings.TIME_ZONE)
        cls.plan = WeeklyProductionPlan.objects.create(name='current')
        press = Process.objects.create(name='press', electricity_consumption_kWh=120, production_plan=cls.plan)
        Shift.objects.create(name='s', process=press, start_day=0, start_hour=10, end_day=0, end_hour=12,
                             max_forward_minutes=0, max_backwards_minutes=0)
        cls.later = WeeklyProductionPlan.objects.create(name='later')
        press = Process.objects.create(name='press', electricity_consumption_kWh=120, production_plan=cls.later)
        Shift.objects.create(name='s', process=press, start_day=0, start_hour=14, end_day=0, end_hour=16,
                             max_forward_minutes=0, max_backwards_minutes=0)

        cls.generation = GenerationDataset.objects.create(name='gen')
        cls.prices = PricesDataset.objects.create(name='prices')
        hours = [tz.localize(datetime(2024, 7, 8)) + timedelta(hours=h) for h in range(25)]
        GenerationRecord.objects.bulk_create(
            GenerationRecord(generation_dataset=cls.generation, timestamp=ts, ele_generated_by_cogen_kWh=0,
                             ele_generated_by_solar_kWh=60 if 10 <= ts.hour <= 11 else 0) for ts in hours)
        PricesRecord.objects.bulk_create(
            PricesRecord(prices_dataset=cls.prices, timestamp=ts, electricity_price=0.5) for ts in hours)

    def simulate(self, compared=None):
        simulation = Simulation.objects.create(
            name=f'sim {compared}', original_production_plan=self.plan, optimized_production_plan=compared,
            generation_dataset=self.generation, prices_dataset=self.prices,
            start_date=date(2024, 7, 8), end_date=date(2024, 7, 8))
        return run_simulation(simulation.pk)

    def test_single_plan_has_no_compared_cost(self):
        results = self.simulate()
        self.assertAlmostEqual(results.total_electricity_used_kWh, 240)
        self.assertIsNone(results.optimized_cost_euros)
        self.assertIsNone(results.savings_euros)
        # Solar is 60 kWh/h from 10:00 to 11:00, then interpolated from 60 to 0 by 12:00: the second
        # hour gets 60 * (1 - mean(minute) / 60) = 60 * (1 - 27.5 / 60) = 32.5 kWh
        self.assertAlmostEqual(results.grid_electricity_purchased_kWh, 240 - 60 - 32.5)

    def test_compared_plan_cost_and_saving(self):
        results = self.simulate(compared=self.later)
        self.assertAlmostEqual(results.optimized_cost_euros, 240 * 0.5)  # No solar in the afternoon
        self.assertAlmostEqual(results.savings_euros, results.original_cost_euros - results.optimized_cost_euros)
        self.assertLess(results.savings_euros, 0)

    def test_missing_hours_are_refused(self):
        from DatasetApp.series import MissingDataError
        GenerationRecord.objects.filter(generation_dataset=self.generation, timestamp__hour__in=[13, 14]).delete()
        with self.assertRaisesMessage(MissingDataError, 'have no value for 2 hour(s)'):
            self.simulate()
        self.assertFalse(Simulation.objects.filter(results__isnull=False).exists())

