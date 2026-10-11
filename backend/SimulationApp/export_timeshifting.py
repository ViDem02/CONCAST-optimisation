"""
Export time-shifting data structure for optimizations.

This module generates the hierarchical data structure for production optimization
results, organized by year, season, and analysis type (time_shifting).
"""

from datetime import datetime
from django.http import JsonResponse, HttpResponse
import json


def get_season_from_date(date):
    """
    Determine season from a date.
    
    Args:
        date: datetime.date object
    
    Returns:
        str: 'winter', 'spring', 'summer', or 'fall'
    """
    month = date.month
    
    if month in [1, 2, 3]:
        return 'winter'
    elif month in [4, 5, 6]:
        return 'spring'
    elif month in [7, 8, 9]:
        return 'summer'
    else:  # 10, 11, 12
        return 'fall'


def extract_phase_shifts(optimization):
    """
    Extract phase shift information from an optimization.
    
    Args:
        optimization: Optimization object
    
    Returns:
        dict: Phase-by-phase shift details
    """
    from OptimizerApp.models import Optimization
    from PlanningApp.models import Process, Shift
    
    if not optimization.is_completed():
        return {}
    
    reference_plan = optimization.reference_production_plan
    optimized_plan = optimization.optimized_production_plan
    
    # Get optimization data for shift information
    optimization_data = optimization.optimization_data or {}
    shift_steps = optimization_data.get('shift_steps', {})
    
    phases = {}
    
    # Group processes by phase (assuming process names contain phase info)
    # Or use all processes as separate phases
    for process in reference_plan.processes.all():
        phase_name = process.name
        
        # Get original and optimized shifts for this process
        original_shifts = list(process.shifts.all().order_by('start_day', 'start_hour', 'start_minutes'))
        
        if not original_shifts:
            continue
        
        # Try to find corresponding optimized process
        try:
            optimized_process = optimized_plan.processes.get(name=process.name)
            optimized_shifts = list(optimized_process.shifts.all().order_by('start_day', 'start_hour', 'start_minutes'))
        except Exception as e:
            print(f"Could not find optimized process for {process.name}: {e}")
            continue
        
        if not optimized_shifts or len(original_shifts) != len(optimized_shifts):
            print(f"Shift count mismatch for {process.name}: {len(original_shifts)} vs {len(optimized_shifts)}")
            continue
        
        shifts_data = []
        
        # Match original and optimized shifts
        for idx, (orig_shift, opt_shift) in enumerate(zip(original_shifts, optimized_shifts)):
            # Calculate original start/end timestamps (using reference week)
            from datetime import timedelta
            
            ref_start = optimization.reference_week_start
            
            # Original timing - calculate absolute datetime from week start + day offset
            original_start = datetime.combine(
                ref_start + timedelta(days=orig_shift.start_day),
                datetime.min.time()
            ).replace(
                hour=orig_shift.start_hour,
                minute=orig_shift.start_minutes
            )
            
            original_end = datetime.combine(
                ref_start + timedelta(days=orig_shift.end_day),
                datetime.min.time()
            ).replace(
                hour=orig_shift.end_hour,
                minute=orig_shift.end_minutes
            )
            
            # Optimized timing - use the same day offsets but optimized times
            shifted_start = datetime.combine(
                ref_start + timedelta(days=opt_shift.start_day),
                datetime.min.time()
            ).replace(
                hour=opt_shift.start_hour,
                minute=opt_shift.start_minutes
            )
            
            shifted_end = datetime.combine(
                ref_start + timedelta(days=opt_shift.end_day),
                datetime.min.time()
            ).replace(
                hour=opt_shift.end_hour,
                minute=opt_shift.end_minutes
            )
            
            # Calculate shift in minutes
            shift_minutes = int((shifted_start - original_start).total_seconds() / 60)
            
            shifts_data.append({
                'id': idx + 1,
                'name': orig_shift.name,
                'original_start': original_start.isoformat(),
                'original_end': original_end.isoformat(),
                'shifted_start': shifted_start.isoformat(),
                'shifted_end': shifted_end.isoformat(),
                'shift_minutes': shift_minutes
            })
        
        if shifts_data:
            phases[phase_name] = {
                'shifts': shifts_data
            }
    
    return {'phases': phases}


def generate_timeshifting_structure(optimizations):
    """
    Generate the hierarchical time_shifting data structure.
    
    Args:
        optimizations: QuerySet of Optimization objects
    
    Returns:
        dict: Nested structure organized by year/season/optimization
    """
    result = {}
    
    for optimization in optimizations:
        if not optimization.is_completed():
            continue
        
        # Extract year and season from reference week
        year = optimization.reference_week_start.year
        season = get_season_from_date(optimization.reference_week_start)
        
        # Initialize nested structure
        if year not in result:
            result[year] = {}
        
        if season not in result[year]:
            result[year][season] = {}
        
        # Compute savings strictly from Simulation results (not Optimization fields)
        initial_cost = 0.0
        optimized_cost = 0.0
        # Defer imports to avoid circular dependencies
        try:
            from PlanningApp.models import Simulation as SimCfg
            from SimulationApp.models import SimulationResults
            # Try to locate a Simulation that ran the same week and plans
            sim_qs = SimCfg.objects.filter(
                original_production_plan=optimization.reference_production_plan,
                optimized_production_plan=optimization.optimized_production_plan,
                start_date=optimization.reference_week_start,
                end_date=optimization.reference_week_end,
            )
            sim = sim_qs.first()
            if sim and hasattr(sim, 'results') and sim.results:
                initial_cost = float(sim.results.original_cost_euros or 0.0)
                optimized_cost = float(sim.results.optimized_cost_euros or 0.0)
        except Exception as e:
            # If simulations are not available, keep zeros; do not fall back to Optimization fields
            print(f"Simulation-based cost lookup failed for optimization {optimization.id}: {e}")

        computed_savings_euros = max(0.0, initial_cost - optimized_cost)
        computed_savings_percent = (computed_savings_euros / initial_cost * 100.0) if initial_cost > 0 else 0.0
        computed_savings_percent = round(max(0.0, min(100.0, computed_savings_percent)), 2)
        computed_savings_euros = round(computed_savings_euros, 2)

        # Add time_shifting data
        optimization_name = optimization.name
        result[year][season][optimization_name] = {
            'time_shifting': extract_phase_shifts(optimization),
            'metadata': {
                'optimization_id': optimization.id,
                'reference_week_start': optimization.reference_week_start.isoformat(),
                'reference_week_end': optimization.reference_week_end.isoformat(),
                'initial_cost_euros': initial_cost,
                'optimized_cost_euros': optimized_cost,
                'cost_savings_euros': computed_savings_euros,
                'cost_savings_percent': computed_savings_percent,
            }
        }
    
    return result


def export_timeshifting_to_json(optimizations, as_response=True):
    """
    Export time-shifting structure to JSON.
    
    Args:
        optimizations: QuerySet of Optimization objects
        as_response: If True, return HttpResponse; if False, return dict
    
    Returns:
        HttpResponse or dict
    """
    structure = generate_timeshifting_structure(optimizations)
    
    if as_response:
        response = HttpResponse(
            json.dumps(structure, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="timeshifting_structure.json"'
        return response
    else:
        return structure
