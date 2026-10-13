"""Tests of the production plan import and of the shift editing form."""

import io

from django.test import TestCase

from .admin import ShiftForm
from .importers import PlanFileError, import_plan
from .models import Process, Shift, WeeklyProductionPlan

YAML = '''processes:
  oven:
    electricity_consumption_kWh: 60
  press:
    electricity_consumption_kWh: 120
    max_forward_minutes: 30
    max_backwards_minutes: 15
'''
CSV = '''Time,oven,press
2025-09-22 00:00:00,1,0
2025-09-22 00:15:00,1,1
2025-09-22 00:30:00,0,1
2025-09-22 00:45:00,0,0
2025-09-22 01:00:00,0,1
'''


class ImportPlanTests(TestCase):

    def test_shifts_are_the_blocks_of_ones(self):
        plan = import_plan(io.StringIO(CSV), io.StringIO(YAML), 'week')
        press = plan.processes.get(name='press')
        self.assertEqual(press.electricity_consumption_kWh, 120)
        shifts = [(s.start_hour, s.start_minutes, s.end_hour, s.end_minutes, s.max_backwards_minutes,
                   s.max_forward_minutes) for s in press.shifts.order_by('start_hour', 'start_minutes')]
        self.assertEqual(shifts, [(0, 15, 0, 45, 15, 30), (1, 0, 1, 15, 15, 30)])
        oven = plan.processes.get(name='oven').shifts.get()
        self.assertEqual((oven.end_minutes, oven.max_forward_minutes), (30, 0))

    def test_existing_name_needs_replace(self):
        import_plan(io.StringIO(CSV), io.StringIO(YAML), 'week')
        with self.assertRaisesMessage(PlanFileError, 'already exists'):
            import_plan(io.StringIO(CSV), io.StringIO(YAML), 'week')
        import_plan(io.StringIO(CSV), io.StringIO(YAML), 'week', replace=True)
        self.assertEqual(WeeklyProductionPlan.objects.count(), 1)

    def test_processes_of_the_two_files_must_match(self):
        with self.assertRaisesMessage(PlanFileError, 'in the CSV but not in the YAML: press'):
            import_plan(io.StringIO(CSV), io.StringIO('processes:\n  oven:\n    electricity_consumption_kWh: 1\n'), 'w')
        self.assertFalse(WeeklyProductionPlan.objects.exists())


class ShiftFormTests(TestCase):

    def test_times_are_stored_as_hours_and_minutes(self):
        plan = WeeklyProductionPlan.objects.create(name='p')
        process = Process.objects.create(name='press', electricity_consumption_kWh=1, production_plan=plan)
        form = ShiftForm({'name': 's', 'start_day': 0, 'start_time': '08:30', 'end_day': 0, 'end_time': '10:05',
                          'max_backwards_minutes': 0, 'max_forward_minutes': 60},
                         instance=Shift(process=process))
        self.assertTrue(form.is_valid(), form.errors)
        shift = form.save()
        self.assertEqual((shift.start_hour, shift.start_minutes, shift.end_hour, shift.end_minutes), (8, 30, 10, 5))

    def test_time_must_be_a_multiple_of_5_minutes(self):
        form = ShiftForm({'name': 's', 'start_day': 0, 'start_time': '08:31', 'end_day': 0, 'end_time': '10:00',
                          'max_backwards_minutes': 0, 'max_forward_minutes': 0})
        self.assertFalse(form.is_valid())
        self.assertIn('start_time', form.errors)
