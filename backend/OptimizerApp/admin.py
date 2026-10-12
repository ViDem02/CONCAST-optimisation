from django.contrib import admin
from django.contrib import messages
from django.utils import timezone
from .models import Optimization
from SimulationApp.export_timeshifting import export_timeshifting_to_json


@admin.register(Optimization)
class OptimizationAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'optimizer',
        'reference_production_plan',
        'optimized_production_plan',
        'reference_week_start',
        'reference_week_end',
        'initial_cost_euros',
        'optimized_cost_euros',
        'cost_savings_euros',
        'cost_savings_percent',
        'is_completed',
        'created_at',
        'completed_at'
    ]
    list_filter = ['optimizer', 'created_at', 'completed_at']
    search_fields = ['name', 'notes']
    ordering = ['-created_at']
    readonly_fields = [
        'optimized_production_plan',
        'initial_cost_euros',
        'optimized_cost_euros',
        'cost_savings_euros',
        'cost_savings_percent',
        'optimization_data',
        'created_at',
        'completed_at'
    ]

    # DO NOT WRITE ANY FIELDSETS
    
    # fieldsets = (
    #     ('Basic Information', {
    #         'fields': ('name', 'notes')
    #     }),
    #     ('Production Plans', {
    #         'fields': ('reference_production_plan', 'optimized_production_plan')
    #     }),
    #     ('Reference Week', {
    #         'fields': ('reference_week_start', 'reference_week_end'),
    #         'description': 'Specify the week for which generation and prices data will be used'
    #     }),
    #     ('Results', {
    #         'fields': (
    #             'initial_cost_euros',
    #             'optimized_cost_euros',
    #             'cost_savings_euros',
    #             'cost_savings_percent',
    #             'optimization_data'
    #         )
    #     }),
    #     ('Timestamps', {
    #         'fields': ('created_at', 'completed_at')
    #     }),
    # )
    
    actions = ['run_optimization', 'export_timeshifting_structure']
    
    @admin.action(description='Export Time-Shifting Structure (JSON)')
    def export_timeshifting_structure(self, request, queryset):
        """Export time-shifting structure for selected optimizations"""
        # Filter to only completed optimizations
        completed_optimizations = queryset.filter(optimized_production_plan__isnull=False)
        
        if not completed_optimizations.exists():
            self.message_user(
                request,
                'No completed optimizations selected. Please select optimizations that have been run.',
                level=messages.WARNING
            )
            return
        
        try:
            response = export_timeshifting_to_json(completed_optimizations, as_response=True)
            self.message_user(
                request,
                f'Successfully exported time-shifting structure for {completed_optimizations.count()} optimization(s).',
                level=messages.SUCCESS
            )
            return response
        except Exception as e:
            self.message_user(
                request,
                f'Error exporting time-shifting structure: {str(e)}',
                level=messages.ERROR
            )
    
    def run_optimization(self, request, queryset):
        """Run optimization for selected optimization objects."""
        from .optimizer_packager import run_optimization
        
        success_count = 0
        error_count = 0
        
        for optimization in queryset:
            try:
                result = run_optimization(optimization.id)
                success_count += 1
                self.message_user(
                    request,
                    f"Successfully optimized '{optimization.name}'. "
                    f"Cost reduced from €{result.initial_cost_euros:.2f} to €{result.optimized_cost_euros:.2f} "
                    f"(savings: €{result.cost_savings_euros:.2f}, {result.cost_savings_percent:.2f}%)",
                    level=messages.SUCCESS
                )
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f"Failed to optimize '{optimization.name}': {str(e)}",
                    level=messages.ERROR
                )
        
        if success_count > 0:
            self.message_user(
                request,
                f"Successfully completed {success_count} optimization(s)",
                level=messages.SUCCESS
            )
        if error_count > 0:
            self.message_user(
                request,
                f"Failed to complete {error_count} optimization(s)",
                level=messages.ERROR
            )
    
    run_optimization.short_description = "Run optimization calculation"
