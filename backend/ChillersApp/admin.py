from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html

from .models import Chiller, ChillerSimulation
from .chiller_control import run_chiller_simulation


@admin.register(Chiller)
class ChillerAdmin(admin.ModelAdmin):
    list_display = ['name', 'insulation_u_value', 'surface_area', 'created_at']
    search_fields = ['name']
    list_filter = ['created_at']
    ordering = ['-created_at']


@admin.register(ChillerSimulation)
class ChillerSimulationAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'chiller', 'start_date', 'end_date',
        'temperature_range', 'has_results', 'created_at'
    ]
    search_fields = ['name', 'chiller__name']
    list_filter = ['start_date', 'end_date', 'created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'chiller', 'start_date', 'end_date')
        }),
        ('Temperature Control', {
            'fields': (
                'min_temperature', 'max_temperature', 
                'initial_window_hours', 'target_temperature'
            )
        }),
        ('Datasets', {
            'fields': (
                'generation_dataset', 'prices_dataset', 
                'temperature_dataset'
            )
        }),
        ('PD Controller Parameters', {
            'fields': ('proportional_gain', 'derivative_gain')
        }),
        ('Production Plan Integration (Optional)', {
            'fields': ('production_plan_result',),
            'description': 'Link to a production plan result. If set, available generation will be the wasted energy from that production plan instead of full generation from datasets.'
        }),
        ('Results (Read-Only)', {
            'fields': ('display_results_summary',),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['display_results_summary']
    
    actions = ['run_simulation', 'export_to_csv']
    
    def save_as_new(self, request, obj):
        """Override save_as_new to customize behavior"""
        pass
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Add 'Save as new' button in change view"""
        extra_context = extra_context or {}
        extra_context['show_save_as_new'] = True
        return super().change_view(request, object_id, form_url, extra_context=extra_context)
    
    save_as = True  # Enable 'Save as new' functionality
    
    def temperature_range(self, obj):
        """Display temperature range."""
        return f"{obj.min_temperature}°C - {obj.max_temperature}°C"
    temperature_range.short_description = 'Temp Range'
    
    def has_results(self, obj):
        """Check if simulation has results."""
        has_data = bool(obj.chiller_power_delivery and obj.calculated_temperature)
        if has_data:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: gray;">✗</span>')
    has_results.short_description = 'Results'
    
    def display_results_summary(self, obj):
        """Display summary of simulation results."""
        if not obj.chiller_power_delivery or not obj.calculated_temperature:
            return "No results yet. Run simulation to generate results."
        
        power_data = obj.chiller_power_delivery
        temp_data = obj.calculated_temperature
        
        html = f"""
        <div style="font-family: monospace; line-height: 1.6;">
            <h3>Temperature Results:</h3>
            <ul>
                <li>Min: {temp_data.get('min_temp', 'N/A'):.2f}°C</li>
                <li>Max: {temp_data.get('max_temp', 'N/A'):.2f}°C</li>
                <li>Average: {temp_data.get('avg_temp', 'N/A'):.2f}°C</li>
                <li>Target: {temp_data.get('target_temp', 'N/A'):.2f}°C</li>
            </ul>
            
            <h3>Power Consumption:</h3>
            <ul>
                <li>Total Cooling Energy: {power_data.get('total_cooling_kWh', 'N/A'):.2f} kWh</li>
                <li>Grid Consumption: {power_data.get('total_grid_consumption_kWh', 'N/A'):.2f} kWh</li>
                <li>Wasted Energy: {power_data.get('total_wasted_kWh', 'N/A'):.2f} kWh</li>
            </ul>
        </div>
        """
        return format_html(html)
    display_results_summary.short_description = 'Results Summary'
    
    @admin.action(description='Run chiller simulation with PD control')
    def run_simulation(self, request, queryset):
        """Run chiller simulation for selected simulations."""
        success_count = 0
        error_count = 0
        
        for simulation in queryset:
            try:
                run_chiller_simulation(simulation.id)
                success_count += 1
                self.message_user(
                    request,
                    f"Successfully ran simulation '{simulation.name}'",
                    level=messages.SUCCESS
                )
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f"Error running simulation '{simulation.name}': {str(e)}",
                    level=messages.ERROR
                )
        
        if success_count > 0:
            self.message_user(
                request,
                f"Completed {success_count} simulation(s)",
                level=messages.SUCCESS
            )
        if error_count > 0:
            self.message_user(
                request,
                f"Failed {error_count} simulation(s)",
                level=messages.ERROR
            )
    
    @admin.action(description='Export simulation results to CSV')
    def export_to_csv(self, request, queryset):
        """Export selected simulation results to CSV file."""
        import csv
        from django.http import HttpResponse
        
        # Check if any simulations have results
        simulations_with_results = [
            sim for sim in queryset 
            if sim.chiller_power_delivery and sim.calculated_temperature
        ]
        
        if not simulations_with_results:
            self.message_user(
                request,
                "No simulations with results found. Run simulations first.",
                level=messages.WARNING
            )
            return
        
        # If multiple simulations, export the first one with a warning
        if len(simulations_with_results) > 1:
            self.message_user(
                request,
                f"Exporting only the first simulation: {simulations_with_results[0].name}",
                level=messages.INFO
            )
        
        simulation = simulations_with_results[0]
        
        # Create HTTP response with CSV content
        # Sanitize filename by removing invalid characters
        import re
        filename = str(simulation)
        filename = re.sub(r'[^\w\s-]', '_', filename)
        filename = re.sub(r'[-\s]+', '_', filename)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'time',
            'pw_used_by_chiller_from_generated_sources',
            'pw_used_by_chiller_from_grid',
            'chiller_max_temp',
            'chiller_min_temp',
            'chiller_target_temp',
            'chiller_actual_temp',
            'outside_temp_c'
        ])
        
        # Write data
        temp_data = simulation.calculated_temperature
        power_data = simulation.chiller_power_delivery
        
        from datetime import datetime
        for i, timestamp in enumerate(temp_data['timestamps']):
            # Parse ISO format and convert to desired format
            dt = datetime.fromisoformat(timestamp)
            formatted_timestamp = dt.strftime('%Y-%m-%d %H:%M')
            
            writer.writerow([
                formatted_timestamp,
                power_data['power_kW'][i],
                power_data['grid_consumption_kW'][i],
                simulation.max_temperature,
                simulation.min_temperature,
                temp_data.get('target_temp', simulation.min_temperature + (simulation.max_temperature - simulation.min_temperature) / 2),
                temp_data['temperature_C'][i],
                temp_data.get('outside_temperature_C', [None] * len(temp_data['timestamps']))[i] if 'outside_temperature_C' in temp_data else ''
            ])
        
        self.message_user(
            request,
            f"Exported simulation '{simulation.name}' to CSV",
            level=messages.SUCCESS
        )
        
        return response
