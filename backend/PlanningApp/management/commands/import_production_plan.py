import csv
import yaml
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PlanningApp.models import WeeklyProductionPlan, Process, Shift


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

    @transaction.atomic
    def handle(self, *args, **options):
        csv_file = options['csv_file']
        yaml_file = options['yaml_file']
        plan_name = options['plan_name']
        clear_existing = options['clear']

        # Clear existing plan if requested
        if clear_existing:
            try:
                existing_plan = WeeklyProductionPlan.objects.get(name=plan_name)
                existing_plan.delete()
                self.stdout.write(self.style.WARNING(f'Deleted existing plan: {plan_name}'))
            except WeeklyProductionPlan.DoesNotExist:
                pass

        # Load YAML configuration
        try:
            with open(yaml_file, 'r') as f:
                config = yaml.safe_load(f)
                processes_config = config.get('processes', {})
        except FileNotFoundError:
            raise CommandError(f'YAML file "{yaml_file}" not found')
        except yaml.YAMLError as e:
            raise CommandError(f'Error parsing YAML file: {str(e)}')
        except Exception as e:
            raise CommandError(f'Error reading YAML file: {str(e)}')

        if not processes_config:
            raise CommandError('No processes found in YAML configuration')

        # Load CSV timetable
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            raise CommandError(f'CSV file "{csv_file}" not found')
        except Exception as e:
            raise CommandError(f'Error reading CSV file: {str(e)}')

        if not rows:
            raise CommandError('CSV file is empty')

        # Validate CSV headers
        csv_columns = set(rows[0].keys()) - {'Time'}
        yaml_processes = set(processes_config.keys())
        
        if csv_columns != yaml_processes:
            missing_in_yaml = csv_columns - yaml_processes
            missing_in_csv = yaml_processes - csv_columns
            error_msg = []
            if missing_in_yaml:
                error_msg.append(f"Processes in CSV but not in YAML: {missing_in_yaml}")
            if missing_in_csv:
                error_msg.append(f"Processes in YAML but not in CSV: {missing_in_csv}")
            raise CommandError('\n'.join(error_msg))

        # Create production plan
        production_plan = WeeklyProductionPlan.objects.create(
            name=plan_name,
            is_optimized=False
        )
        self.stdout.write(self.style.SUCCESS(f'Created production plan: {plan_name}'))

        # Parse timetable to detect shifts
        processes_data = {}
        for process_name in csv_columns:
            processes_data[process_name] = []
            for row in rows:
                timestamp = datetime.strptime(row['Time'], '%Y-%m-%d %H:%M:%S')
                is_active = int(row[process_name]) == 1
                processes_data[process_name].append({
                    'timestamp': timestamp,
                    'active': is_active
                })

        # Create processes and detect shifts
        total_processes = 0
        total_shifts = 0

        for process_name, process_config in processes_config.items():
            # Create process
            process = Process.objects.create(
                name=process_name,
                electricity_consumption_kWh=process_config['electricity_consumption_kWh'],
                production_plan=production_plan
            )
            total_processes += 1
            self.stdout.write(f'  Created process: {process_name}')

            # Detect shifts from timetable data
            shifts = self._detect_shifts(processes_data[process_name])
            
            # Create shifts
            for shift_idx, shift_data in enumerate(shifts, start=1):
                shift_name = f"{process_name}_shift_{shift_idx}"
                
                start_timestamp = shift_data['start']
                end_timestamp = shift_data['end']
                
                shift = Shift.objects.create(
                    name=shift_name,
                    process=process,
                    start_day=start_timestamp.weekday(),
                    end_day=end_timestamp.weekday(),
                    start_hour=start_timestamp.hour,
                    start_minutes=start_timestamp.minute,
                    end_hour=end_timestamp.hour,
                    end_minutes=end_timestamp.minute,
                    max_forward_minutes=process_config.get('max_forward_minutes', 0),
                    max_backwards_minutes=process_config.get('max_backwards_minutes', 0)
                )
                total_shifts += 1
                self.stdout.write(f'    Created shift: {shift_name} ({start_timestamp} to {end_timestamp})')

        # Summary
        self.stdout.write(self.style.SUCCESS(f'\nImport complete:'))
        self.stdout.write(f'  Production plan: {plan_name}')
        self.stdout.write(f'  Processes created: {total_processes}')
        self.stdout.write(f'  Shifts created: {total_shifts}')

    def _detect_shifts(self, timetable_data):
        """
        Detect shifts from timetable data.
        A shift is a continuous block of 1's (active periods).
        Breaks in the sequence (0's) separate different shifts.
        """
        shifts = []
        current_shift = None
        
        for i, entry in enumerate(timetable_data):
            if entry['active']:
                if current_shift is None:
                    # Start of a new shift
                    current_shift = {
                        'start': entry['timestamp'],
                        'end': entry['timestamp']
                    }
                else:
                    # Continue current shift
                    current_shift['end'] = entry['timestamp']
            else:
                if current_shift is not None:
                    # End of current shift
                    # Add 15 minutes to the end timestamp to include the full interval
                    current_shift['end'] = current_shift['end'] + timedelta(minutes=15)
                    shifts.append(current_shift)
                    current_shift = None
        
        # Handle case where shift continues until the end
        if current_shift is not None:
            current_shift['end'] = current_shift['end'] + timedelta(minutes=15)
            shifts.append(current_shift)
        
        return shifts
