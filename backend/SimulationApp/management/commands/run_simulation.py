"""
Management command to run a simulation calculation.

Usage:
    python manage.py run_simulation <simulation_id>
    python manage.py run_simulation --simulation-name "My Simulation"
"""

from django.core.management.base import BaseCommand, CommandError
from PlanningApp.models import Simulation
from SimulationApp.simulation import run_simulation


class Command(BaseCommand):
    help = 'Run a simulation calculation and save results'

    def add_arguments(self, parser):
        parser.add_argument(
            'simulation_id',
            nargs='?',
            type=int,
            help='ID of the simulation to run'
        )
        parser.add_argument(
            '--simulation-name',
            type=str,
            help='Name of the simulation to run (alternative to ID)'
        )

    def handle(self, *args, **options):
        simulation_id = options.get('simulation_id')
        simulation_name = options.get('simulation_name')

        if not simulation_id and not simulation_name:
            raise CommandError('Either simulation_id or --simulation-name must be provided')

        try:
            if simulation_name:
                simulation = Simulation.objects.get(name=simulation_name)
                simulation_id = simulation.id
                self.stdout.write(f'Found simulation "{simulation_name}" with ID {simulation_id}')
            else:
                simulation = Simulation.objects.get(id=simulation_id)
                self.stdout.write(f'Running simulation: {simulation.name} (ID: {simulation_id})')

            # Run the simulation
            self.stdout.write('Starting simulation calculation...')
            results = run_simulation(simulation_id)

            # Display results
            self.stdout.write(self.style.SUCCESS('\nSimulation completed successfully!'))
            self.stdout.write('\n=== Results Summary ===')
            self.stdout.write(f'Total Electricity Used: {results.total_electricity_used_kWh:.2f} kWh')
            self.stdout.write(f'Grid Electricity Purchased: {results.grid_electricity_purchased_kWh:.2f} kWh')
            self.stdout.write(f'Solar Generated: {results.solar_generated_kWh:.2f} kWh')
            self.stdout.write(f'Cogen Generated: {results.cogen_generated_kWh:.2f} kWh')
            self.stdout.write(f'Wasted Energy: {results.wasted_energy_kWh:.2f} kWh')
            self.stdout.write(f'Total Cost: €{results.total_cost_euros:.2f}')
            self.stdout.write(f'Total CO2: {results.total_co2_kg:.2f} kg')
            self.stdout.write(f'Number of Timesteps: {results.num_timesteps}')

        except Simulation.DoesNotExist:
            raise CommandError(
                f'Simulation with {"name" if simulation_name else "ID"} '
                f'"{simulation_name or simulation_id}" does not exist'
            )
        except Exception as e:
            raise CommandError(f'Error running simulation: {str(e)}')
