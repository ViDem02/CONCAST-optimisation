from django.contrib import admin
from django.contrib import messages
from django.core.management import call_command
from django.utils.html import format_html
from io import StringIO
import os
import tempfile
import traceback
from .models import WeeklyProductionPlan, Process, Shift, Simulation


@admin.register(WeeklyProductionPlan)
class WeeklyProductionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_optimized', 'process_count', 'shift_count', 'created_at']
    list_filter = ['is_optimized']
    search_fields = ['name']
    ordering = ['-created_at']
    readonly_fields = ['is_optimized']
    actions = ['import_production_plan', 'adjust_shift_ranges_to_prevent_overlaps']
    
    def changelist_view(self, request, extra_context=None):
        """Override to allow import action without selecting items"""
        if 'action' in request.POST and request.POST['action'] == 'import_production_plan':
            # Allow the action regardless of whether items are selected
            return self.import_production_plan(request, self.model.objects.none())
        return super().changelist_view(request, extra_context)
    
    def process_count(self, obj):
        """Display the number of processes in the plan"""
        count = obj.processes.count()
        return format_html('<span style="color: #28a745;">{}</span>', count)
    process_count.short_description = 'Processes'
    
    def shift_count(self, obj):
        """Display the total number of shifts across all processes"""
        count = sum(process.shifts.count() for process in obj.processes.all())
        return format_html('<span style="color: #007bff;">{}</span>', count)
    shift_count.short_description = 'Shifts'
    
    @admin.action(description='Import production plan from CSV and YAML')
    def import_production_plan(self, request, queryset):
        """Import production plan from CSV timetable and YAML configuration"""
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        
        if 'apply' in request.POST:
            # Process the file upload
            csv_file = request.FILES.get('csv_file')
            yaml_file = request.FILES.get('yaml_file')
            plan_name = request.POST.get('plan_name')
            clear_existing = request.POST.get('clear_existing') == 'on'
            
            if not csv_file:
                self.message_user(request, 'Please select a CSV file', level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())
            
            if not yaml_file:
                self.message_user(request, 'Please select a YAML file', level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())
            
            if not plan_name:
                self.message_user(request, 'Please provide a plan name', level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())
            
            # Validate file extensions
            if not csv_file.name.endswith('.csv'):
                self.message_user(request, 'CSV file must have .csv extension', level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())
            
            if not (yaml_file.name.endswith('.yaml') or yaml_file.name.endswith('.yml')):
                self.message_user(request, 'YAML file must have .yaml or .yml extension', level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())
            
            csv_temp_file = None
            yaml_temp_file = None
            
            try:
                # Determine temporary directory
                temp_dir = '/app' if os.path.exists('/app') else None
                
                # Save uploaded files to temporary files
                csv_temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False, dir=temp_dir)
                yaml_temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.yaml', delete=False, dir=temp_dir)
                
                for chunk in csv_file.chunks():
                    csv_temp_file.write(chunk)
                csv_temp_file.close()
                
                for chunk in yaml_file.chunks():
                    yaml_temp_file.write(chunk)
                yaml_temp_file.close()
                
                # Capture command output
                out = StringIO()
                err = StringIO()
                
                # Build command arguments - pass positional args and boolean flag separately
                command_args = [csv_temp_file.name, yaml_temp_file.name, plan_name]
                
                # Call the management command
                if clear_existing:
                    call_command('import_production_plan', *command_args, clear=True, stdout=out, stderr=err)
                else:
                    call_command('import_production_plan', *command_args, stdout=out, stderr=err)
                
                # Get output
                output = out.getvalue()
                error_output = err.getvalue()
                
                if error_output:
                    self.message_user(
                        request,
                        f'Import completed with warnings:\n{error_output}\n\nOutput:\n{output}',
                        level=messages.WARNING
                    )
                else:
                    self.message_user(
                        request,
                        f'Successfully imported production plan',
                        level=messages.SUCCESS
                    )
                
                return HttpResponseRedirect(reverse('admin:PlanningApp_weeklyproductionplan_changelist'))
                
            except Exception as e:
                error_trace = traceback.format_exc()
                self.message_user(
                    request,
                    f'Error importing production plan: {str(e)}\n\nTraceback:\n{error_trace}',
                    level=messages.ERROR
                )
                return HttpResponseRedirect(request.get_full_path())
            
            finally:
                # Clean up temporary files
                if csv_temp_file:
                    try:
                        os.unlink(csv_temp_file.name)
                    except:
                        pass
                if yaml_temp_file:
                    try:
                        os.unlink(yaml_temp_file.name)
                    except:
                        pass
        
        # Show the file upload form
        from django.shortcuts import render
        context = {
            'title': 'Import Production Plan',
            'action_name': 'import_production_plan',
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
        }
        return render(request, 'admin/planning_import.html', context)
    
    @admin.action(description='Adjust shift ranges to prevent overlaps')
    def adjust_shift_ranges_to_prevent_overlaps(self, request, queryset):
        """
        Adjust max_forward_minutes and max_backwards_minutes for all shifts
        in selected production plans to prevent overlaps between shifts.
        """
        total_shifts_updated = 0
        total_plans_processed = 0
        
        for plan in queryset:
            shifts_updated = 0
            
            # Get all processes for this plan
            for process in plan.processes.all():
                # Get all shifts for this process, ordered by start time
                shifts = list(process.shifts.order_by('start_day', 'start_hour', 'start_minutes'))
                
                if len(shifts) <= 1:
                    # No need to adjust if there's only one shift or no shifts
                    continue
                
                for i, shift in enumerate(shifts):
                    # Calculate shift start and end in minutes from week start
                    shift_start_minutes = (shift.start_day * 24 * 60) + (shift.start_hour * 60) + shift.start_minutes
                    shift_end_minutes = (shift.end_day * 24 * 60) + (shift.end_hour * 60) + shift.end_minutes
                    
                    # Handle case where end is before start (crosses week boundary)
                    if shift_end_minutes <= shift_start_minutes:
                        shift_end_minutes += 7 * 24 * 60
                    
                    # Find maximum backward movement (limited by previous shift)
                    max_backward = shift_start_minutes  # Can't go before week start
                    if i > 0:
                        prev_shift = shifts[i - 1]
                        prev_end_minutes = (prev_shift.end_day * 24 * 60) + (prev_shift.end_hour * 60) + prev_shift.end_minutes
                        
                        if prev_end_minutes <= (prev_shift.start_day * 24 * 60) + (prev_shift.start_hour * 60) + prev_shift.start_minutes:
                            prev_end_minutes += 7 * 24 * 60
                        
                        # Maximum backward is distance to previous shift end
                        gap_to_previous = shift_start_minutes - prev_end_minutes
                        max_backward = max(0, gap_to_previous)
                    else:
                        # First shift - can move back to start of week
                        max_backward = shift_start_minutes
                    
                    # Find maximum forward movement (limited by next shift)
                    max_forward = (7 * 24 * 60) - shift_end_minutes  # Can't go beyond week end
                    if i < len(shifts) - 1:
                        next_shift = shifts[i + 1]
                        next_start_minutes = (next_shift.start_day * 24 * 60) + (next_shift.start_hour * 60) + next_shift.start_minutes
                        
                        # Maximum forward is distance to next shift start
                        gap_to_next = next_start_minutes - shift_end_minutes
                        max_forward = max(0, gap_to_next)
                    else:
                        # Last shift - can move forward to end of week
                        max_forward = (7 * 24 * 60) - shift_end_minutes
                    
                    # Round down to nearest 5 minutes
                    max_backward = (max_backward // 5) * 5
                    max_forward = (max_forward // 5) * 5
                    
                    # Ensure no negative values
                    max_backward = max(0, max_backward)
                    max_forward = max(0, max_forward)
                    
                    # Limit to original values - never exceed what was originally set
                    max_backward = min(max_backward, shift.max_backwards_minutes)
                    max_forward = min(max_forward, shift.max_forward_minutes)
                    
                    # Update the shift if values changed
                    if shift.max_backwards_minutes != max_backward or shift.max_forward_minutes != max_forward:
                        old_backward = shift.max_backwards_minutes
                        old_forward = shift.max_forward_minutes
                        
                        shift.max_backwards_minutes = max_backward
                        shift.max_forward_minutes = max_forward
                        shift.save(update_fields=['max_backwards_minutes', 'max_forward_minutes'])
                        
                        shifts_updated += 1
                        
                        # Log the change
                        self.message_user(
                            request,
                            f'✓ Updated "{shift.name}" in process "{process.name}": '
                            f'backward {old_backward}→{max_backward} min, '
                            f'forward {old_forward}→{max_forward} min',
                            level=messages.INFO
                        )
            
            if shifts_updated > 0:
                total_shifts_updated += shifts_updated
                total_plans_processed += 1
                self.message_user(
                    request,
                    f'✓ Plan "{plan.name}": Updated {shifts_updated} shift(s)',
                    level=messages.SUCCESS
                )
            else:
                self.message_user(
                    request,
                    f'ℹ Plan "{plan.name}": No shifts needed adjustment',
                    level=messages.INFO
                )
        
        # Final summary
        if total_shifts_updated > 0:
            self.message_user(
                request,
                f'Successfully adjusted {total_shifts_updated} shift(s) across {total_plans_processed} plan(s) to prevent overlaps',
                level=messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                'No shifts needed adjustment in the selected plan(s)',
                level=messages.INFO
            )


@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ['name', 'electricity_consumption_kWh', 'production_plan', 'created_at']
    list_filter = ['production_plan']
    search_fields = ['name']
    ordering = ['name']


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ['name', 'process', 'start_day', 'start_hour', 'start_minutes', 'end_day', 'end_hour', 'end_minutes', 'max_backwards_minutes', 'max_forward_minutes']
    list_filter = ['start_day', 'end_day', 'process', 'process__production_plan']
    search_fields = ['name']
    ordering = ['start_day', 'start_hour', 'start_minutes']


@admin.register(Simulation)
class SimulationAdmin(admin.ModelAdmin):
    list_display = ['name','original_production_plan', 'optimized_production_plan', 'reference_production_plan', 'start_date', 'end_date', 'created_at']
    list_filter = ['start_date', 'end_date']
    search_fields = ['name', 'notes']
    ordering = ['-created_at']
    actions = ['run_simulation', 'switch_plans']
    
    @admin.action(description='Run simulation calculation')
    def run_simulation(self, request, queryset):
        """Run simulation calculation for selected simulations"""
        from SimulationApp.simulation import run_simulation
        
        success_count = 0
        error_count = 0
        
        for simulation in queryset:
            try:
                results = run_simulation(simulation.id)
                success_count += 1
                self.message_user(
                    request,
                    f'✓ Simulation "{simulation.name}": Total cost €{results.total_cost_euros:.2f}, '
                    f'Grid electricity {results.grid_electricity_purchased_kWh:.2f} kWh',
                    level=messages.SUCCESS
                )
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f'✗ Failed to run simulation "{simulation.name}": {str(e)}',
                    level=messages.ERROR
                )
        
        if success_count > 0:
            self.message_user(
                request,
                f'Successfully ran {success_count} simulation(s)',
                level=messages.SUCCESS
            )
        if error_count > 0:
            self.message_user(
                request,
                f'Failed to run {error_count} simulation(s)',
                level=messages.ERROR
            )
    
    @admin.action(description='Switch reference ↔ optimized production plans')
    def switch_plans(self, request, queryset):
        """Switch the reference_production_plan with optimized_production_plan for selected simulations"""
        success_count = 0
        skipped_count = 0
        
        for simulation in queryset:
            # Check if we have both original and optimized plans
            if simulation.original_production_plan and simulation.optimized_production_plan:
                # Swap original and optimized plans
                temp = simulation.original_production_plan
                simulation.original_production_plan = simulation.optimized_production_plan
                simulation.optimized_production_plan = temp
                simulation.save()
                success_count += 1
                
                self.message_user(
                    request,
                    f'✓ Switched plans for "{simulation.name}": '
                    f'{temp.name} ↔ {simulation.original_production_plan.name}',
                    level=messages.SUCCESS
                )
            elif simulation.reference_production_plan and simulation.optimized_production_plan:
                # Legacy mode: swap reference with optimized
                temp = simulation.reference_production_plan
                simulation.reference_production_plan = simulation.optimized_production_plan
                simulation.optimized_production_plan = temp
                simulation.save()
                success_count += 1
                
                self.message_user(
                    request,
                    f'✓ Switched plans for "{simulation.name}": '
                    f'{temp.name} ↔ {simulation.reference_production_plan.name}',
                    level=messages.SUCCESS
                )
            else:
                skipped_count += 1
                self.message_user(
                    request,
                    f'⊘ Skipped "{simulation.name}": Missing one or both production plans',
                    level=messages.WARNING
                )
        
        if success_count > 0:
            self.message_user(
                request,
                f'Successfully switched plans for {success_count} simulation(s)',
                level=messages.SUCCESS
            )
        if skipped_count > 0:
            self.message_user(
                request,
                f'Skipped {skipped_count} simulation(s) due to missing plans',
                level=messages.WARNING
            )


