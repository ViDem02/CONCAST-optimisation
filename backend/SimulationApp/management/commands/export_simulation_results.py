"""
Management command to export simulation results to CSV format for MATLAB.

Usage:
    python manage.py export_simulation_results <results_id> <output_file>
    python manage.py export_simulation_results --simulation-name "My Simulation" <output_file>
"""

from django.core.management.base import BaseCommand, CommandError
from SimulationApp.models import SimulationResults
from PlanningApp.models import Simulation
from SimulationApp.utils import export_simulation_results_to_csv


class Command(BaseCommand):
    help = 'Export simulation results to CSV format for MATLAB'

    def add_arguments(self, parser):
        parser.add_argument(
            'output_file',
            type=str,
            help='Path to the output CSV file'
        )
        parser.add_argument(
            '--results-id',
            type=int,
            help='ID of the SimulationResults to export'
        )
        parser.add_argument(
            '--simulation-name',
            type=str,
            help='Name of the simulation to export (uses latest results)'
        )

    def handle(self, *args, **options):
        output_file = options['output_file']
        results_id = options.get('results_id')
        simulation_name = options.get('simulation_name')

        if not results_id and not simulation_name:
            raise CommandError('Either --results-id or --simulation-name must be provided')

        try:
            if simulation_name:
                simulation = Simulation.objects.get(name=simulation_name)
                try:
                    results = simulation.results
                    self.stdout.write(f'Found results for simulation "{simulation_name}" (Results ID: {results.id})')
                except SimulationResults.DoesNotExist:
                    raise CommandError(f'No results found for simulation "{simulation_name}". Run the simulation first.')
            else:
                results = SimulationResults.objects.get(id=results_id)
                self.stdout.write(f'Exporting results ID {results_id} for simulation: {results.simulation.name}')

            # Export using common utility function
            export_simulation_results_to_csv(results, output_file)
            
            num_rows = results.num_timesteps
            self.stdout.write(self.style.SUCCESS(f'\n✓ Successfully exported {num_rows} timesteps to {output_file}'))
            self.stdout.write(f'\nSummary:')
            self.stdout.write(f'  Simulation: {results.simulation.name}')
            self.stdout.write(f'  Period: {results.simulation.start_date} to {results.simulation.end_date}')
            self.stdout.write(f'  Timestep: {results.timestep_minutes} minutes')
            self.stdout.write(f'  Total rows: {num_rows}')
            self.stdout.write(f'  Total electricity used: {results.total_electricity_used_kWh:.2f} kWh')
            self.stdout.write(f'  Grid purchases: {results.grid_electricity_purchased_kWh:.2f} kWh')
            self.stdout.write(f'  Total cost: €{results.total_cost_euros:.2f}')

        except Simulation.DoesNotExist:
            raise CommandError(f'Simulation "{simulation_name}" does not exist')
        except SimulationResults.DoesNotExist:
            raise CommandError(f'SimulationResults with ID {results_id} does not exist')
        except Exception as e:
            raise CommandError(f'Error exporting results: {str(e)}')
