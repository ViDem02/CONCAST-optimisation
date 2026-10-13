import csv
import re
from datetime import datetime

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.html import format_html, format_html_join

from simulator_project.admin_tools import RunButtonMixin, frontend_link
from .chiller_control import run_chiller_simulation
from .models import Chiller, ChillerSimulation


@admin.register(Chiller)
class ChillerAdmin(admin.ModelAdmin):
    list_display = ['name', 'surface_area', 'insulation_u_value', 'nominal_capacity_kW']
    search_fields = ['name']
    fieldsets = [
        (None, {'fields': ['name']}),
        ('Room', {'fields': ['surface_area', 'insulation_u_value']}),
        ('Refrigeration unit', {'fields': ['nominal_capacity_kW', 'nominal_cooling_rate', 'chiller_efficiency']}),
    ]


@admin.register(ChillerSimulation)
class ChillerSimulationAdmin(RunButtonMixin, admin.ModelAdmin):
    list_display = ['name', 'chiller', 'start_date', 'end_date', 'temperature_range', 'calculated']
    list_select_related = ['chiller']
    search_fields = ['name', 'chiller__name']
    ordering = ['-created_at']
    save_as = True  # "Save as new" to try other settings on a copy

    fieldsets = (
        (None, {
            'fields': ('name', 'chiller', 'start_date', 'end_date')
        }),
        ('Temperature to keep', {
            'fields': ('min_temperature', 'max_temperature', 'target_temperature')
        }),
        ('Energy', {
            'fields': ('generation_dataset', 'production_plan_result', 'allow_grid_power', 'temperature_dataset')
        }),
        ('Controller tuning (advanced)', {
            'fields': ('minimum_runtime_minutes', 'initial_window_hours', 'proportional_gain', 'derivative_gain'),
            'classes': ('collapse',),
        }),
        ('Result', {
            'fields': ('result',),
        }),
    )
    readonly_fields = ['result']
    actions = ['run_selected', 'export_to_csv']

    def clear_results(self, obj):
        return ChillerSimulation.objects.filter(pk=obj.pk, calculated_temperature__isnull=False).update(
            chiller_power_delivery=None, calculated_temperature=None) > 0

    def run_object(self, obj):
        simulation = run_chiller_simulation(obj.pk)
        power = simulation.chiller_power_delivery
        return (f'"{obj.name}" calculated: {power["total_cooling_kWh"]:,.0f} kWh used by the cold room, '
                f'{power["total_grid_consumption_kWh"]:,.0f} kWh of it from the grid.')

    @admin.display(description='Allowed temperature')
    def temperature_range(self, obj):
        return f"{obj.min_temperature}°C to {obj.max_temperature}°C"

    @staticmethod
    def has_results(obj):
        return bool(obj.chiller_power_delivery and obj.calculated_temperature)

    @admin.display(description='Calculated', boolean=True)
    def calculated(self, obj):
        return self.has_results(obj)

    @admin.display(description='Result')
    def result(self, obj):
        if not obj.pk or not self.has_results(obj):
            return 'Not calculated yet: press "Save and calculate".'
        temperature = obj.calculated_temperature
        power = obj.chiller_power_delivery
        rows = [
            ('Room temperature (min / average / max)',
             f"{temperature['min_temp']:.1f} / {temperature['avg_temp']:.1f} / {temperature['max_temp']:.1f} °C"),
            ('Electricity used by the cold room', f"{power['total_cooling_kWh']:,.0f} kWh"),
            ('of which bought from the grid', f"{power['total_grid_consumption_kWh']:,.0f} kWh"),
            ('Generation still left unused', f"{power['total_wasted_kWh']:,.0f} kWh"),
        ]
        table = format_html_join('', '<tr><th>{}</th><td>{}</td></tr>', rows)
        return format_html('<div class="sparc-result"><table>{}</table><p>{}</p></div>',
                           table, frontend_link(f'cold-rooms/{obj.pk}', 'Show the charts'))

    @admin.action(description='Download the results as CSV (one simulation)')
    def export_to_csv(self, request, queryset):
        """Export the results of one simulation to a CSV file."""
        simulations_with_results = [sim for sim in queryset if self.has_results(sim)]
        if len(simulations_with_results) != 1:
            self.message_user(request, 'Select exactly one calculated simulation to download.',
                              level=messages.WARNING)
            return None

        simulation = simulations_with_results[0]
        filename = re.sub(r'[-\s]+', '_', re.sub(r'[^\w\s-]', '_', str(simulation)))
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'

        writer = csv.writer(response)
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

        temp_data = simulation.calculated_temperature
        power_data = simulation.chiller_power_delivery
        outside = temp_data.get('outside_temperature_C') or [''] * len(temp_data['timestamps'])
        for i, timestamp in enumerate(temp_data['timestamps']):
            writer.writerow([
                datetime.fromisoformat(timestamp).strftime('%Y-%m-%d %H:%M'),
                power_data['power_kW'][i] - power_data['grid_consumption_kW'][i],
                power_data['grid_consumption_kW'][i],
                simulation.max_temperature,
                simulation.min_temperature,
                temp_data.get('target_temp'),
                temp_data['temperature_C'][i],
                outside[i],
            ])
        return response
