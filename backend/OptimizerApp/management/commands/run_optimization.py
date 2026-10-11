"""
Management command to run an optimization calculation.

Usage:
    python manage.py run_optimization <optimization_id>
    python manage.py run_optimization --optimization-name "My Optimization"
"""

from django.core.management.base import BaseCommand, CommandError
from OptimizerApp.models import Optimization
from OptimizerApp.optimizer import run_optimization


class Command(BaseCommand):
    help = 'Run an optimization calculation and create optimized production plan'

    def add_arguments(self, parser):
        parser.add_argument(
            'optimization_id',
            nargs='?',
            type=int,
            help='ID of the optimization to run'
        )
        parser.add_argument(
            '--optimization-name',
            type=str,
            help='Name of the optimization to run (alternative to ID)'
        )

    def handle(self, *args, **options):
        optimization_id = options.get('optimization_id')
        optimization_name = options.get('optimization_name')

        if not optimization_id and not optimization_name:
            raise CommandError('Either optimization_id or --optimization-name must be provided')

        try:
            if optimization_name:
                optimization = Optimization.objects.get(name=optimization_name)
                optimization_id = optimization.id
                self.stdout.write(f'Found optimization "{optimization_name}" with ID {optimization_id}')
            else:
                optimization = Optimization.objects.get(id=optimization_id)
                self.stdout.write(f'Running optimization: {optimization.name} (ID: {optimization_id})')

            # Run the optimization
            self.stdout.write('Starting optimization calculation...')
            result = run_optimization(optimization_id)

            # Display results
            self.stdout.write(self.style.SUCCESS('\nOptimization completed successfully!'))
            self.stdout.write('\n=== Results Summary ===')
            self.stdout.write(f'Reference Production Plan: {result.reference_production_plan.name}')
            self.stdout.write(f'Optimized Production Plan: {result.optimized_production_plan.name}')
            self.stdout.write(f'Initial Cost: €{result.initial_cost_euros:.2f}')
            self.stdout.write(f'Optimized Cost: €{result.optimized_cost_euros:.2f}')
            self.stdout.write(f'Cost Savings: €{result.cost_savings_euros:.2f} ({result.cost_savings_percent:.2f}%)')
            
            if result.optimization_data:
                data = result.optimization_data
                self.stdout.write(f'\nLSQR Iterations: {data.get("lsqr_iterations", "N/A")}')
                self.stdout.write(f'Coordinate Descent Iterations: {data.get("coordinate_descent_iterations", "N/A")}')
                self.stdout.write(f'Number of Runs Optimized: {data.get("num_runs_optimized", "N/A")}')
                self.stdout.write(f'Total Wasted Energy: {data.get("total_wasted_energy", 0):.2f} kWh')
                
                if 'shift_changes' in data:
                    self.stdout.write('\n=== Shift Changes ===')
                    for change in data['shift_changes']:
                        direction = "delayed" if change['shift_minutes'] > 0 else "advanced" if change['shift_minutes'] < 0 else "unchanged"
                        self.stdout.write(
                            f"{change['process_name']}_run{change['run_number']}: "
                            f"{direction} by {abs(change['shift_minutes'])} minutes"
                        )

        except Optimization.DoesNotExist:
            raise CommandError(
                f'Optimization with {"name" if optimization_name else "ID"} '
                f'"{optimization_name or optimization_id}" does not exist'
            )
        except Exception as e:
            raise CommandError(f'Error running optimization: {str(e)}')
