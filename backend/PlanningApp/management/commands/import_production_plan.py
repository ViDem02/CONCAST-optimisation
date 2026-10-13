from django.core.management.base import BaseCommand, CommandError

from PlanningApp.importers import PlanFileError, import_plan


class Command(BaseCommand):
    help = 'Import production plan from CSV timetable and YAML configuration'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV timetable file')
        parser.add_argument('yaml_file', type=str, help='Path to the YAML configuration file')
        parser.add_argument('plan_name', type=str, help='Name of the production plan')
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing plan with the same name before importing',
        )

    def handle(self, *args, **options):
        try:
            plan = import_plan(options['csv_file'], options['yaml_file'], options['plan_name'],
                               replace=options['clear'])
        except FileNotFoundError as e:
            raise CommandError(f'File "{e.filename}" not found')
        except PlanFileError as e:
            raise CommandError(str(e))

        shifts = sum(p.shifts.count() for p in plan.processes.all())
        self.stdout.write(self.style.SUCCESS(
            f'Imported production plan "{plan.name}": {plan.processes.count()} processes, {shifts} shifts'))
