from django.contrib import admin
from django.contrib import messages
from .models import SimulationResults
from .utils import export_simulation_results_to_csv
from .export_timeshifting import export_timeshifting_to_json


@admin.register(SimulationResults)
class SimulationResultsAdmin(admin.ModelAdmin):
    list_display = [
        'simulation',
        'total_electricity_used_kWh',
        'grid_electricity_purchased_kWh',
        'original_cost_euros',
        'optimized_cost_euros',
        'cost_savings',
        'wasted_energy_kWh',
        'total_co2_kg',
        'num_timesteps',
        'calculated_at',
    ]
    
    def cost_savings(self, obj):
        """Calculate and display cost savings."""
        if obj.original_cost_euros and obj.optimized_cost_euros:
            savings = obj.original_cost_euros - obj.optimized_cost_euros
            if savings > 0:
                return f"€{savings:.2f} ({savings/obj.original_cost_euros*100:.1f}%)"
            return "€0.00 (0%)"
        return "-"
    cost_savings.short_description = "Cost Savings"
    
    list_filter = [
        'calculated_at',
        'timestep_minutes',
    ]
    
    search_fields = [
        'simulation__name',
        'simulation__notes',
    ]
    
    readonly_fields = [
        'calculated_at',
        'simulation',
        'total_electricity_used_kWh',
        'grid_electricity_purchased_kWh',
        'solar_generated_kWh',
        'cogen_generated_kWh',
        'wasted_energy_kWh',
        'total_cost_euros',
        'total_co2_kg',
        'timestep_minutes',
        'num_timesteps',
        'timestep_data',
        'original_cost_euros',
        'optimized_cost_euros',
    ]
    
    fieldsets = (
        ('Simulation', {
            'fields': ('simulation', 'calculated_at')
        }),
        ('Aggregated Metrics', {
            'fields': (
                'total_electricity_used_kWh',
                'grid_electricity_purchased_kWh',
                'solar_generated_kWh',
                'cogen_generated_kWh',
                'wasted_energy_kWh',
                'total_cost_euros',
                'total_co2_kg',
                'original_cost_euros',
                'optimized_cost_euros', 
            )
        }),
        ('Timestep Details', {
            'fields': ('timestep_minutes', 'num_timesteps', 'timestep_data'),
            'classes': ('collapse',),
        }),
    )
    
    actions = ['export_to_csv', 'export_timeshifting_structure']
    
    @admin.action(description='Export Time-Shifting Structure (JSON)')
    def export_timeshifting_structure(self, request, queryset):
        """Export time-shifting structure for all related optimizations"""
        from OptimizerApp.models import Optimization
        
        # Get all optimizations (we'll organize them by year/season)
        optimizations = Optimization.objects.filter(optimized_production_plan__isnull=False)
        
        if not optimizations.exists():
            self.message_user(
                request,
                'No completed optimizations found to export.',
                level=messages.WARNING
            )
            return
        
        try:
            response = export_timeshifting_to_json(optimizations, as_response=True)
            self.message_user(
                request,
                f'Successfully exported time-shifting structure for {optimizations.count()} optimizations.',
                level=messages.SUCCESS
            )
            return response
        except Exception as e:
            self.message_user(
                request,
                f'Error exporting time-shifting structure: {str(e)}',
                level=messages.ERROR
            )
    
    @admin.action(description='Export to CSV for MATLAB')
    def export_to_csv(self, request, queryset):
        """Export selected simulation results to CSV files"""
        if queryset.count() == 1:
            # Single selection - download directly
            results = queryset.first()
            try:
                response = export_simulation_results_to_csv(results)
                return response
            except Exception as e:
                self.message_user(
                    request,
                    f'Error exporting results: {str(e)}',
                    level=messages.ERROR
                )
        else:
            # Multiple selections - inform user
            self.message_user(
                request,
                'Please select only one simulation result at a time for CSV export.',
                level=messages.WARNING
            )
    
    def has_add_permission(self, request):
        # Results should only be created through simulation calculations
        return False
