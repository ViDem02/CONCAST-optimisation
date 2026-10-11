import csv
from datetime import datetime, timedelta
from collections import defaultdict
from django.core.management.base import BaseCommand, CommandError
from PlanningApp.models import WeeklyProductionPlan, Process, Shift
from django.conf import settings


class Command(BaseCommand):
    help = 'Export production plan to CSV timetable format'

    def add_arguments(self, parser):
        parser.add_argument('plan_name', type=str, help='Name of the production plan to export')
        parser.add_argument('output_file', type=str, help='Path to the output CSV file')
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (Monday) for the timetable (YYYY-MM-DD). If not provided, uses a default reference week.',
        )

    def handle(self, *args, **options):
        plan_name = options['plan_name']
        output_file = options['output_file']
        start_date_str = options.get('start_date')

        # Get the production plan
        try:
            production_plan = WeeklyProductionPlan.objects.get(name=plan_name)
            self.stdout.write(self.style.SUCCESS(f'Found production plan: {plan_name}'))
        except WeeklyProductionPlan.DoesNotExist:
            raise CommandError(f'Production plan "{plan_name}" does not exist')

        # Get all processes for this plan
        processes = Process.objects.filter(production_plan=production_plan).order_by('name')
        
        if not processes.exists():
            raise CommandError(f'No processes found for production plan "{plan_name}"')

        # Determine date range - always export a full week (Monday to Sunday)
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            # Ensure start_date is a Monday
            days_since_monday = start_date.weekday()
            if days_since_monday != 0:
                start_date = start_date - timedelta(days=days_since_monday)
                self.stdout.write(self.style.WARNING(f'Adjusted start date to Monday: {start_date.date()}'))
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # Use default reference week
            start_date = settings.DEFAULT_PRODUCTION_STARTING_DATE.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Always export Monday to Sunday (full week)
        end_date = start_date + timedelta(days=6, hours=23, minutes=45)

        self.stdout.write(f'Date range: {start_date.date()} to {end_date.date()}')

        # Build the timetable
        timetable = self._build_timetable(production_plan, start_date, end_date)
        
        # Debug: Show shift information
        for process_name, shifts in timetable.items():
            for shift in shifts:
                self.stdout.write(f"  {process_name}: {shift['start'].strftime('%A %Y-%m-%d %H:%M')} to {shift['end'].strftime('%A %Y-%m-%d %H:%M')}")

        # Write CSV
        process_names = [p.name for p in processes]
        
        try:
            with open(output_file, 'w', newline='') as csvfile:
                fieldnames = ['Time'] + process_names
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                
                # Generate 15-minute intervals
                current_time = start_date
                rows_written = 0
                
                while current_time <= end_date:
                    row = {'Time': current_time.strftime('%Y-%m-%d %H:%M:%S')}
                    
                    for process_name in process_names:
                        # Check if any shift is active at this time
                        is_active = self._is_process_active(
                            timetable.get(process_name, []),
                            current_time
                        )
                        row[process_name] = 1 if is_active else 0
                    
                    writer.writerow(row)
                    rows_written += 1
                    current_time += timedelta(minutes=15)
                
            self.stdout.write(self.style.SUCCESS(f'\nExport complete:'))
            self.stdout.write(f'  Output file: {output_file}')
            self.stdout.write(f'  Processes: {len(process_names)}')
            self.stdout.write(f'  Rows written: {rows_written}')
            self.stdout.write(f'  Time range: {start_date} to {end_date}')
            
        except Exception as e:
            raise CommandError(f'Error writing CSV file: {str(e)}')



    def _build_timetable(self, production_plan, start_date, end_date):
        """Build a timetable dictionary with process names as keys and shift intervals as values."""
        timetable = defaultdict(list)
        
        processes = Process.objects.filter(production_plan=production_plan)
        
        # Find the Monday of the week containing start_date
        days_since_monday = start_date.weekday()  # 0 = Monday, 6 = Sunday
        week_start = start_date - timedelta(days=days_since_monday)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate how many weeks we need to cover
        total_days = (end_date - week_start).days + 1
        num_weeks = (total_days // 7) + 2  # Add extra weeks to ensure coverage
        
        for process in processes:
            shifts = Shift.objects.filter(process=process)
            
            for shift in shifts:
                # Generate shift instances for each week in the date range
                for week_offset in range(num_weeks):
                    week_base = week_start + timedelta(weeks=week_offset)
                    
                    # Calculate absolute datetime for shift based on weekday
                    # shift.start_day and shift.end_day are 0-6 (Monday-Sunday)
                    shift_start = week_base + timedelta(
                        days=shift.start_day,
                        hours=shift.start_hour,
                        minutes=shift.start_minutes
                    )
                    
                    shift_end = week_base + timedelta(
                        days=shift.end_day,
                        hours=shift.end_hour,
                        minutes=shift.end_minutes
                    )
                    
                    # Handle shifts that span across days or into the next week
                    # If end is before or equal to start, add days until it's after
                    while shift_end <= shift_start:
                        shift_end += timedelta(days=7)
                    
                    # Only include shifts that overlap with our date range
                    if shift_end > start_date and shift_start <= end_date:
                        timetable[process.name].append({
                            'start': shift_start,
                            'end': shift_end
                        })
        
        return timetable

    def _is_process_active(self, shifts, current_time):
        """Check if a process is active at the given time based on its shifts."""
        for shift in shifts:
            # Check if current_time is within this shift
            # The shift interval is inclusive at start, exclusive at end
            if shift['start'] <= current_time < shift['end']:
                return True
        return False
