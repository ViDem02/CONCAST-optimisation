"""Django management command to run chiller simulations."""

from django.core.management.base import BaseCommand, CommandError
from ChillersApp.models import ChillerSimulation
from ChillersApp.chiller_control import run_chiller_simulation


class Command(BaseCommand):
    help = 'Run chiller simulation with PD control'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'simulation_id',
            nargs='?',
            type=int,
            help='ID of the chiller simulation to run'
        )
        parser.add_argument(
            '--simulation-name',
            type=str,
            help='Name of the chiller simulation to run'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Run all simulations that have no results yet'
        )
        parser.add_argument(
            '--export-csv',
            type=str,
            help='Export results to CSV file (provide file path)'
        )
    
    def handle(self, *args, **options):
        simulation_id = options.get('simulation_id')
        simulation_name = options.get('simulation_name')
        run_all = options.get('all')
        
        simulations_to_run = []
        
        if run_all:
            # Run all simulations without results
            simulations_to_run = ChillerSimulation.objects.filter(
                chiller_power_delivery__isnull=True
            ) | ChillerSimulation.objects.filter(
                calculated_temperature__isnull=True
            )
            
            if not simulations_to_run.exists():
                self.stdout.write(
                    self.style.WARNING('No simulations without results found')
                )
                return
            
            self.stdout.write(
                self.style.NOTICE(
                    f'Found {simulations_to_run.count()} simulation(s) to run'
                )
            )
        
        elif simulation_name:
            # Find by name
            try:
                simulation = ChillerSimulation.objects.get(name=simulation_name)
                simulations_to_run = [simulation]
            except ChillerSimulation.DoesNotExist:
                raise CommandError(
                    f'ChillerSimulation with name "{simulation_name}" does not exist'
                )
        
        elif simulation_id:
            # Find by ID
            try:
                simulation = ChillerSimulation.objects.get(id=simulation_id)
                simulations_to_run = [simulation]
            except ChillerSimulation.DoesNotExist:
                raise CommandError(
                    f'ChillerSimulation with ID {simulation_id} does not exist'
                )
        
        else:
            raise CommandError(
                'Please provide either a simulation_id, --simulation-name, or --all'
            )
        
        # Run simulations
        success_count = 0
        error_count = 0
        
        for simulation in simulations_to_run:
            try:
                self.stdout.write(f'\nRunning simulation: {simulation.name}')
                self.stdout.write(f'  Chiller: {simulation.chiller.name}')
                self.stdout.write(f'  Period: {simulation.start_date} to {simulation.end_date}')
                self.stdout.write(f'  Temperature range: {simulation.min_temperature}°C - {simulation.max_temperature}°C')
                
                result = run_chiller_simulation(simulation.id)
                
                # Display results
                temp_data = result.calculated_temperature
                power_data = result.chiller_power_delivery
                
                self.stdout.write(self.style.SUCCESS('\n✓ Simulation completed successfully'))
                self.stdout.write('\nTemperature Results:')
                self.stdout.write(f'  Min: {temp_data["min_temp"]:.2f}°C')
                self.stdout.write(f'  Max: {temp_data["max_temp"]:.2f}°C')
                self.stdout.write(f'  Average: {temp_data["avg_temp"]:.2f}°C')
                self.stdout.write(f'  Target: {temp_data["target_temp"]:.2f}°C')
                
                self.stdout.write('\nPower Consumption:')
                self.stdout.write(f'  Total Cooling Energy: {power_data["total_cooling_kWh"]:.2f} kWh')
                self.stdout.write(f'  Grid Consumption: {power_data["total_grid_consumption_kWh"]:.2f} kWh')
                self.stdout.write(f'  Wasted Energy: {power_data["total_wasted_kWh"]:.2f} kWh')
                
                # Export to CSV if requested
                csv_path = options.get('export_csv')
                if csv_path:
                    self._export_to_csv(result, csv_path)
                    self.stdout.write(self.style.SUCCESS(f'\n✓ Exported results to {csv_path}'))
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'\n✗ Error running simulation: {str(e)}')
                )
        
        # Summary
        self.stdout.write('\n' + '='*60)
        if success_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'✓ Completed {success_count} simulation(s)')
            )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'✗ Failed {error_count} simulation(s)')
            )
    
    def _export_to_csv(self, simulation, csv_path):
        """Export simulation results to CSV file."""
        import csv
        from datetime import datetime
        
        temp_data = simulation.calculated_temperature
        power_data = simulation.chiller_power_delivery
        
        with open(csv_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow([
                'Timestamp',
                'Temperature (°C)',
                'Power Delivery (kW)',
                'Grid Consumption (kW)',
                'Wasted Energy (kW)'
            ])
            
            # Write data rows
            for i, timestamp in enumerate(temp_data['timestamps']):
                # Parse ISO format and convert to desired format
                dt = datetime.fromisoformat(timestamp)
                formatted_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                
                writer.writerow([
                    formatted_timestamp,
                    temp_data['temperature_C'][i],
                    power_data['power_kW'][i],
                    power_data['grid_consumption_kW'][i],
                    power_data['wasted_energy_kW'][i]
                ])
