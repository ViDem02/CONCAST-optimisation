"""
Utility functions for SimulationApp.
"""

import csv
from datetime import datetime
from django.http import HttpResponse


def export_simulation_results_to_csv(results, output_file=None):
    """
    Export simulation results to CSV format.
    
    Args:
        results: SimulationResults object
        output_file: File path (string) or HttpResponse object for direct output
                    If None, returns HttpResponse for download
    
    Returns:
        HttpResponse if output_file is None, otherwise None
    """
    timestep_data = results.timestep_data
    
    if not timestep_data or 'timestamps' not in timestep_data:
        raise ValueError('No timestep data available in the results')
    
    # Extract data arrays
    timestamps = timestep_data['timestamps']
    total_demand_kWh = timestep_data.get('total_demand_kWh', [])
    solar_generation_kWh = timestep_data.get('solar_generation_kWh', [])
    cogen_generation_kWh = timestep_data.get('cogen_generation_kWh', [])
    total_generation_kWh = timestep_data.get('total_generation_kWh', [])
    grid_electricity_kWh = timestep_data.get('grid_electricity_kWh', [])
    wasted_energy_kWh = timestep_data.get('wasted_energy_kWh', [])
    electricity_price = timestep_data.get('electricity_price', [])
    grid_cost_euros = timestep_data.get('grid_cost_euros', [])
    original_cost_euros = timestep_data.get('original_cost_euros', [])
    optimized_cost_euros = timestep_data.get('optimized_cost_euros', [])
    
    # Calculate CO2 emissions per timestep (0.5 kg CO2 per kWh from grid)
    co2_factor = 0.5
    co2_emissions_kg = [grid_kWh * co2_factor for grid_kWh in grid_electricity_kWh]
    
    # Determine output target
    if output_file is None:
        # Create HTTP response for download
        # Sanitize filename by removing invalid characters
        import re
        filename = str(results)
        filename = re.sub(r'[^\w\s-]', '_', filename)
        filename = re.sub(r'[-\s]+', '_', filename)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        writer = csv.writer(response)
    elif isinstance(output_file, str):
        # Write to file path
        file_handle = open(output_file, 'w', newline='')
        writer = csv.writer(file_handle)
    else:
        # Assume it's a file-like object (HttpResponse, etc.)
        writer = csv.writer(output_file)
    
    # Write header
    writer.writerow([
        'time',
        'price_of_electricity',
        'cost_original_production_plan',
        'cost_optimized_production_plan',
        'co2_emissions',
        'generated_electricity_solar',
        'generated_electricity_cogenerator',
        'used_electricity_production_phases',
        'wasted_generated_electricity'
    ])
    
    # Write data rows
    for i in range(len(timestamps)):
        # Format timestamp from ISO format to 'YYYY-MM-DD HH:MM'
        timestamp_str = timestamps[i]
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            formatted_timestamp = dt.strftime('%Y-%m-%d %H:%M')
        except:
            formatted_timestamp = timestamp_str
        
        writer.writerow([
            formatted_timestamp,
            electricity_price[i] if i < len(electricity_price) else 0,
            original_cost_euros[i] if i < len(original_cost_euros) else (grid_cost_euros[i] if i < len(grid_cost_euros) else 0),
            optimized_cost_euros[i] if i < len(optimized_cost_euros) else (grid_cost_euros[i] if i < len(grid_cost_euros) else 0),
            co2_emissions_kg[i] if i < len(co2_emissions_kg) else 0,
            solar_generation_kWh[i] if i < len(solar_generation_kWh) else 0,
            cogen_generation_kWh[i] if i < len(cogen_generation_kWh) else 0,
            total_demand_kWh[i] if i < len(total_demand_kWh) else 0,
            wasted_energy_kWh[i] if i < len(wasted_energy_kWh) else 0,
        ])
    
    # Close file if we opened it
    if isinstance(output_file, str):
        file_handle.close()
        return None
    
    # Return response if creating download
    if output_file is None:
        return response
