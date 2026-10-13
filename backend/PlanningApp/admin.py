import datetime

from django import forms
from django.contrib import admin, messages
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from simulator_project.admin_tools import RunButtonMixin, euros, frontend_link
from .importers import PlanFileError, import_plan
from .models import Process, Shift, Simulation, WeeklyProductionPlan


# ----------------------------------------------------------------------------
# Production plans, processes and shifts
# ----------------------------------------------------------------------------

class ShiftForm(forms.ModelForm):
    """Shift with its start and end as time pickers instead of separate hour and minute numbers."""
    start_time = forms.TimeField(label='Starts at', widget=forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'step': 300}))
    end_time = forms.TimeField(label='Ends at', widget=forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'step': 300}))

    class Meta:
        model = Shift
        fields = ['name', 'start_day', 'start_time', 'end_day', 'end_time',
                  'max_backwards_minutes', 'max_forward_minutes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['start_time'] = datetime.time(self.instance.start_hour, self.instance.start_minutes)
            self.initial['end_time'] = datetime.time(self.instance.end_hour, self.instance.end_minutes)

    def clean(self):
        cleaned = super().clean()
        for prefix in ('start', 'end'):
            time = cleaned.get(f'{prefix}_time')
            if time is None:
                continue
            if time.minute % 5:
                self.add_error(f'{prefix}_time', 'Use a multiple of 5 minutes')
                continue
            setattr(self.instance, f'{prefix}_hour', time.hour)
            setattr(self.instance, f'{prefix}_minutes', time.minute)
        return cleaned


class ShiftInline(admin.TabularInline):
    model = Shift
    form = ShiftForm
    extra = 0


@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    """Reached from its production plan; not listed on the home page."""
    fields = ['production_plan', 'name', 'electricity_consumption_kWh']
    inlines = [ShiftInline]
    search_fields = ['name']

    def has_module_permission(self, request):
        return False

    def get_readonly_fields(self, request, obj=None):
        return ['production_plan'] if obj else []

    def _back_to_plan(self, request, obj, default):
        if '_continue' in request.POST or '_addanother' in request.POST:
            return default
        return HttpResponseRedirect(reverse('admin:PlanningApp_weeklyproductionplan_change', args=[obj.production_plan_id]))

    def response_change(self, request, obj):
        return self._back_to_plan(request, obj, super().response_change(request, obj))

    def response_add(self, request, obj, post_url_continue=None):
        return self._back_to_plan(request, obj, super().response_add(request, obj, post_url_continue))


class ProcessInline(admin.TabularInline):
    model = Process
    fields = ['name', 'electricity_consumption_kWh', 'shifts_summary']
    readonly_fields = ['shifts_summary']
    extra = 0
    show_change_link = True
    verbose_name_plural = 'processes (click "Change" to edit the shifts of a process)'

    @admin.display(description='Shifts')
    def shifts_summary(self, obj):
        shifts = list(obj.shifts.all()) if obj.pk else []
        if not shifts:
            return 'No shifts'
        moves = {(s.max_backwards_minutes, s.max_forward_minutes) for s in shifts}
        if moves == {(0, 0)}:
            flexibility = 'fixed'
        elif len(moves) == 1:
            backward, forward = moves.pop()
            flexibility = f'may start up to {backward} min earlier / {forward} min later'
        else:
            flexibility = 'flexibility varies by shift'
        return f'{len(shifts)} shift{"s" if len(shifts) > 1 else ""}, {flexibility}'


class PlanImportForm(forms.Form):
    name = forms.CharField(label='Name of the new plan', max_length=255)
    csv_file = forms.FileField(label='CSV timetable', help_text='Which processes run in every 15-minute interval of the week')
    yaml_file = forms.FileField(label='YAML file', help_text='Power and allowed shift movement of every process')
    replace = forms.BooleanField(label='Replace', required=False,
                                 help_text='Tick to overwrite an existing plan with the same name')


@admin.register(WeeklyProductionPlan)
class WeeklyProductionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'origin', 'process_count', 'shift_count', 'created_at']
    list_filter = ['is_optimized']
    search_fields = ['name']
    ordering = ['-created_at']
    fields = ['name', 'is_optimized', 'chart']
    readonly_fields = ['is_optimized', 'chart']
    inlines = [ProcessInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n_processes=Count('processes', distinct=True), n_shifts=Count('processes__shifts'))

    @admin.display(description='Origin', ordering='is_optimized')
    def origin(self, obj):
        return 'Created by an optimisation' if obj.is_optimized else 'Imported / entered'

    @admin.display(description='Processes', ordering='n_processes')
    def process_count(self, obj):
        return obj.n_processes

    @admin.display(description='Shifts', ordering='n_shifts')
    def shift_count(self, obj):
        return obj.n_shifts

    @admin.display(description='Weekly chart')
    def chart(self, obj):
        return frontend_link(f'plans/{obj.pk}', 'Show the week as a chart') if obj.pk else '–'

    def get_urls(self):
        return [path('import/', self.admin_site.admin_view(self.import_view),
                     name='PlanningApp_weeklyproductionplan_import')] + super().get_urls()

    def import_view(self, request):
        form = PlanImportForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            try:
                plan = import_plan(form.cleaned_data['csv_file'], form.cleaned_data['yaml_file'],
                                   form.cleaned_data['name'], replace=form.cleaned_data['replace'])
            except PlanFileError as e:
                form.add_error(None, str(e))
            else:
                self.message_user(request, f'Imported production plan "{plan.name}".', messages.SUCCESS)
                return HttpResponseRedirect(reverse('admin:PlanningApp_weeklyproductionplan_change', args=[plan.pk]))
        context = {
            **self.admin_site.each_context(request),
            'title': 'Import a production plan',
            'opts': self.model._meta,
            'form': form,
        }
        return render(request, 'admin/PlanningApp/plan_import.html', context)


# ----------------------------------------------------------------------------
# Cost simulations
# ----------------------------------------------------------------------------

@admin.register(Simulation)
class SimulationAdmin(RunButtonMixin, admin.ModelAdmin):
    list_display = ['name', 'original_production_plan', 'optimized_production_plan', 'start_date', 'end_date',
                    'savings', 'calculated']
    search_fields = ['name', 'notes']
    ordering = ['-created_at']
    list_select_related = ['original_production_plan', 'optimized_production_plan', 'results']
    readonly_fields = ['result']
    fieldsets = [
        ('What to simulate', {'fields': ['name', 'original_production_plan', 'optimized_production_plan',
                                         'start_date', 'end_date']}),
        ('Data', {'fields': ['generation_dataset', 'prices_dataset']}),
        ('Notes', {'fields': ['notes'], 'classes': ['collapse']}),
        ('Result', {'fields': ['result']}),
    ]
    actions = ['run_selected', 'download_csv']

    def clear_results(self, obj):
        from SimulationApp.models import SimulationResults
        return SimulationResults.objects.filter(simulation=obj).delete()[0] > 0

    def run_object(self, obj):
        from SimulationApp.simulation import run_simulation
        results = run_simulation(obj.pk)
        message = f'"{obj.name}" calculated: current plan {euros(results.original_cost_euros)}'
        if results.savings_euros is not None:
            message += (f', plan to compare {euros(results.optimized_cost_euros)} '
                        f'(saves {euros(results.savings_euros)}, {results.savings_percent:.1f}%)')
        return message + '.'

    @staticmethod
    def _results(obj):
        return getattr(obj, 'results', None) if obj.pk else None

    @admin.display(description='Saving')
    def savings(self, obj):
        results = self._results(obj)
        if not results or results.savings_euros is None:
            return '–'
        return f'{euros(results.savings_euros)} ({results.savings_percent:.1f}%)'

    @admin.display(description='Calculated', boolean=True)
    def calculated(self, obj):
        return self._results(obj) is not None

    @admin.display(description='Result')
    def result(self, obj):
        results = self._results(obj)
        if not results:
            return 'Not calculated yet: press "Save and calculate".'
        rows = [('Grid electricity cost of the current plan', euros(results.original_cost_euros))]
        if results.optimized_cost_euros is not None:
            rows += [('Grid electricity cost of the plan to compare', euros(results.optimized_cost_euros)),
                     ('Saving', f'{euros(results.savings_euros)} ({results.savings_percent:.1f}%)')]
        label = 'plan to compare' if results.optimized_cost_euros is not None else 'current plan'
        rows += [
            (f'Electricity used ({label})', f'{results.total_electricity_used_kWh:,.0f} kWh'),
            (f'Bought from the grid ({label})', f'{results.grid_electricity_purchased_kWh:,.0f} kWh'),
            (f'Generation left unused ({label})', f'{results.wasted_energy_kWh:,.0f} kWh'),
            ('Calculated on', f'{results.calculated_at:%d %b %Y %H:%M}'),
        ]
        table = format_html_join('', '<tr><th>{}</th><td>{}</td></tr>', rows)
        return format_html('<div class="sparc-result"><table>{}</table><p>{}</p></div>', table,
                           frontend_link(f'simulations/{obj.pk}', 'Show the charts'))

    @admin.action(description='Download the 5-minute results as CSV (one simulation)')
    def download_csv(self, request, queryset):
        from SimulationApp.utils import export_simulation_results_to_csv
        if queryset.count() != 1:
            self.message_user(request, 'Select exactly one simulation to download.', messages.WARNING)
            return None
        results = self._results(queryset.first())
        if not results:
            self.message_user(request, 'This simulation has not been calculated yet.', messages.WARNING)
            return None
        return export_simulation_results_to_csv(results)
