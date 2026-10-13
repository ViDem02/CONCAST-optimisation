from urllib.parse import urlencode

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from SimulationApp.export_timeshifting import export_timeshifting_to_json
from simulator_project.admin_tools import RunButtonMixin, euros, frontend_link
from .models import Optimization


def describe_move(minutes):
    if minutes == 0:
        return 'not moved'
    hours, rest = divmod(abs(minutes), 60)
    amount = ' '.join(part for part in (f'{hours} h' if hours else '', f'{rest} min' if rest else '') if part)
    return f'{amount} {"later" if minutes > 0 else "earlier"}'


@admin.register(Optimization)
class OptimizationAdmin(RunButtonMixin, admin.ModelAdmin):
    list_display = ['name', 'reference_production_plan', 'reference_week_start', 'savings', 'calculated',
                    'completed_at']
    list_select_related = ['reference_production_plan']
    search_fields = ['name', 'notes']
    ordering = ['-created_at']

    # DO NOT WRITE ANY FIELDSETS

    # The optimizer is always the MILP for users of the admin; the legacy
    # "from-scratch" optimizer stays available to developers through
    # `manage.py run_optimization --optimizer from-scratch`.
    exclude = ['optimizer', 'optimization_data', 'optimized_production_plan', 'initial_cost_euros',
               'optimized_cost_euros', 'cost_savings_euros', 'cost_savings_percent', 'completed_at']
    readonly_fields = ['result']

    actions = ['run_selected', 'export_timeshifting_structure']
    run_button_label = 'Save and optimise'
    result_fields = ('optimized_plan_name',)

    def clear_results(self, obj):
        # The optimised plan is kept (other simulations may use it) and rewritten by the next run
        return Optimization.objects.filter(pk=obj.pk, completed_at__isnull=False).update(
            completed_at=None, initial_cost_euros=None, optimized_cost_euros=None,
            cost_savings_euros=None, cost_savings_percent=None, optimization_data=None) > 0

    def run_object(self, obj):
        from .optimizer_packager import run_optimization
        result = run_optimization(obj.pk)
        return (f'"{obj.name}" optimised: grid electricity cost of the reference week '
                f'{euros(result.initial_cost_euros)} → {euros(result.optimized_cost_euros)} '
                f'(saves {euros(result.cost_savings_euros)}, {result.cost_savings_percent:.1f}%). '
                f'New plan: "{result.optimized_production_plan.name}".')

    @admin.display(description='Saving on the reference week', ordering='cost_savings_euros')
    def savings(self, obj):
        if not obj.is_completed():
            return '–'
        return f'{euros(obj.cost_savings_euros)} ({obj.cost_savings_percent:.1f}%)'

    @admin.display(description='Calculated', boolean=True)
    def calculated(self, obj):
        return obj.is_completed()

    @admin.display(description='Result')
    def result(self, obj):
        if not obj.pk or not obj.is_completed():
            return 'Not optimised yet: press "Save and optimise".'
        data = obj.optimization_data or {}
        plan = obj.optimized_production_plan
        status = data.get('solver_status', '')
        if 'Optimal' in status:
            quality = format_html('<span class="sparc-ok">Best possible schedule (proven optimal)</span>')
        elif 'mip_gap' in data:
            quality = format_html('<span class="sparc-warn">Time limit reached: the cost is at most {}% above '
                                  'the best possible</span>', f'{100 * data["mip_gap"]:.1f}')
        elif status:
            quality = format_html('<span class="sparc-warn">{}</span>', status)
        else:
            quality = f'Computed with {obj.get_optimizer_display()}'

        rows = [
            ('Grid electricity cost, current plan', euros(obj.initial_cost_euros)),
            ('Grid electricity cost, optimised plan', euros(obj.optimized_cost_euros)),
            ('Saving on the reference week', f'{euros(obj.cost_savings_euros)} ({obj.cost_savings_percent:.1f}%)'),
            ('Quality of the solution', quality),
            ('Optimised plan', format_html('<a href="{}">{}</a>', reverse(
                'admin:PlanningApp_weeklyproductionplan_change', args=[plan.pk]), plan.name)),
        ]
        moved = [c for c in data.get('shift_changes', []) if c['shift_minutes']]
        moves = format_html_join('', '<tr><td>{}</td><td>run {}</td><td>{}</td></tr>',
                                 ((c['process_name'], c['run_number'], describe_move(c['shift_minutes']))
                                  for c in moved))
        check_url = reverse('admin:PlanningApp_simulation_add') + '?' + urlencode({
            'name': f'Check of {obj.name}',
            'original_production_plan': obj.reference_production_plan_id,
            'optimized_production_plan': plan.pk,
            'generation_dataset': obj.generation_dataset_id or '',
            'prices_dataset': obj.prices_dataset_id or '',
        })
        return format_html(
            '<div class="sparc-result"><table>{}</table>'
            '<p><strong>{} of {} shifts moved</strong> (the others are unchanged):</p><table>{}</table>'
            '<p>{} &nbsp;·&nbsp; <a href="{}">Check the optimised plan over a longer period</a> '
            '(opens a pre-filled cost simulation: choose the dates)</p></div>',
            format_html_join('', '<tr><th>{}</th><td>{}</td></tr>', rows),
            len(moved), len(data.get('shift_changes', [])), moves,
            frontend_link(f'optimizations/{obj.pk}', 'Show the charts'), check_url)

    @admin.action(description='Download the selected results as JSON (for MATLAB analysis)')
    def export_timeshifting_structure(self, request, queryset):
        completed_optimizations = queryset.filter(optimized_production_plan__isnull=False)
        if not completed_optimizations.exists():
            self.message_user(request, 'None of the selected optimisations has been calculated yet.',
                              level=messages.WARNING)
            return None
        return export_timeshifting_to_json(completed_optimizations, as_response=True)
