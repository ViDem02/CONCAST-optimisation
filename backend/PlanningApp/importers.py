"""
Import of a weekly production plan from a CSV timetable and a YAML file,
shared by the admin "Import plan" page and the import_production_plan command.

CSV: a Time column and one 0/1 column per process, one row per interval
(usually 15 minutes) from Monday 00:00 to Sunday.
YAML: for every process, its power and how far its shifts may be moved:

    processes:
      b_past:
        electricity_consumption_kWh: 278
        max_forward_minutes: 120
        max_backwards_minutes: 120
"""

import csv
import io
from datetime import datetime, timedelta

import yaml
from django.db import transaction

from .models import Process, Shift, WeeklyProductionPlan


class PlanFileError(ValueError):
    """The files cannot be imported; the message is meant for the user."""


def _text(source):
    """Text stream from a path, a text stream or an uploaded (binary) file."""
    if isinstance(source, str):
        with open(source, encoding='utf-8-sig') as f:
            return io.StringIO(f.read())
    if isinstance(source, io.TextIOBase):
        return source
    source.seek(0)
    try:
        return io.StringIO(source.read().decode('utf-8-sig'))
    except UnicodeDecodeError:
        raise PlanFileError('The files must be text files (CSV UTF-8 and YAML).')


def read_processes(yaml_source):
    """Process settings from the YAML file: {name: {'power': int, 'forward': int, 'backward': int}}."""
    try:
        config = yaml.safe_load(_text(yaml_source)) or {}
    except yaml.YAMLError as e:
        raise PlanFileError(f'The YAML file cannot be read: {e}')
    processes = config.get('processes') if isinstance(config, dict) else None
    if not processes or not isinstance(processes, dict):
        raise PlanFileError('The YAML file must contain a "processes:" section with one entry per process.')

    result = {}
    for name, settings in processes.items():
        settings = settings or {}
        try:
            power = int(settings['electricity_consumption_kWh'])
            forward = int(settings.get('max_forward_minutes', 0))
            backward = int(settings.get('max_backwards_minutes', 0))
        except KeyError:
            raise PlanFileError(f'Process "{name}": electricity_consumption_kWh is missing in the YAML file.')
        except (TypeError, ValueError):
            raise PlanFileError(f'Process "{name}": the values in the YAML file must be whole numbers.')
        if power < 0 or forward < 0 or backward < 0:
            raise PlanFileError(f'Process "{name}": the values in the YAML file cannot be negative.')
        if forward % 5 or backward % 5:
            raise PlanFileError(f'Process "{name}": the shift tolerances must be multiples of 5 minutes.')
        result[str(name)] = {'power': power, 'forward': forward, 'backward': backward}
    return result


def read_timetable(csv_source, process_names):
    """Shifts of every process: {name: [(start datetime, end datetime), ...]}."""
    reader = csv.DictReader(_text(csv_source))
    columns = set(reader.fieldnames or []) - {'Time'}
    if 'Time' not in (reader.fieldnames or []):
        raise PlanFileError('The CSV timetable must have a "Time" column.')
    if columns != set(process_names):
        problems = []
        if columns - set(process_names):
            problems.append('in the CSV but not in the YAML: ' + ', '.join(sorted(columns - set(process_names))))
        if set(process_names) - columns:
            problems.append('in the YAML but not in the CSV: ' + ', '.join(sorted(set(process_names) - columns)))
        raise PlanFileError('The processes of the two files do not match (' + '; '.join(problems) + ').')

    rows = []
    for line, row in enumerate(reader, start=2):
        try:
            time = datetime.strptime(row['Time'].strip(), '%Y-%m-%d %H:%M:%S')
            active = {name: int(row[name]) for name in process_names}
        except (TypeError, ValueError):
            raise PlanFileError(f'Line {line} of the CSV timetable: expected a time like 2025-09-22 00:15:00 '
                                f'and 0 or 1 for every process.')
        if any(v not in (0, 1) for v in active.values()):
            raise PlanFileError(f'Line {line} of the CSV timetable: process values must be 0 or 1.')
        rows.append((time, active))
    if len(rows) < 2:
        raise PlanFileError('The CSV timetable contains no data.')

    interval = rows[1][0] - rows[0][0]
    if interval <= timedelta(0) or interval.total_seconds() % 300:
        raise PlanFileError('The rows of the CSV timetable must be in time order, every 5, 10, 15... minutes.')

    shifts = {name: [] for name in process_names}
    for name in process_names:
        start = None
        for time, active in rows:
            if active[name] and start is None:
                start = time
            elif not active[name] and start is not None:
                shifts[name].append((start, time))
                start = None
        if start is not None:
            shifts[name].append((start, rows[-1][0] + interval))
    return shifts


@transaction.atomic
def import_plan(csv_source, yaml_source, plan_name, replace=False):
    """Create the production plan `plan_name` from the two files and return it."""
    processes = read_processes(yaml_source)
    shifts = read_timetable(csv_source, list(processes))

    existing = WeeklyProductionPlan.objects.filter(name=plan_name)
    if existing.exists():
        if not replace:
            raise PlanFileError(f'A production plan called "{plan_name}" already exists: '
                                f'choose another name or tick "Replace".')
        existing.delete()

    plan = WeeklyProductionPlan.objects.create(name=plan_name, is_optimized=False)
    for name, settings in processes.items():
        process = Process.objects.create(name=name, electricity_consumption_kWh=settings['power'],
                                         production_plan=plan)
        for number, (start, end) in enumerate(shifts[name], start=1):
            Shift.objects.create(
                name=f'{name}_shift_{number}', process=process,
                start_day=start.weekday(), start_hour=start.hour, start_minutes=start.minute,
                end_day=end.weekday(), end_hour=end.hour, end_minutes=end.minute,
                max_forward_minutes=settings['forward'], max_backwards_minutes=settings['backward'],
            )
    return plan
