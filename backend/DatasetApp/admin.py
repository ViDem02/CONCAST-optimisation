from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.core.management import call_command
from django.utils.html import format_html
from io import StringIO
import os
from .models import (
    TemperatureDataset, TemperatureRecord,
    PricesDataset, PricesRecord,
    GenerationDataset, GenerationRecord
)


class TemperatureRecordInline(admin.TabularInline):
    model = TemperatureRecord
    extra = 1


@admin.register(TemperatureDataset)
class TemperatureDatasetAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at', 'record_count']
    list_filter = ['is_active']
    search_fields = ['name']
    ordering = ['-created_at']
    actions = ['import_temperature_records']
    readonly_fields = ['is_active']

    def record_count(self, obj):
        count = obj.records.count()
        return format_html('<b>{}</b>', count)
    record_count.short_description = 'Records'

    def import_temperature_records(self, request, queryset):
        """Import temperature records from CSV file."""
        if len(queryset) != 1:
            self.message_user(request, "Please select exactly one dataset to import records.", level=messages.ERROR)
            return

        dataset = queryset.first()

        if 'apply' in request.POST:
            csv_file = request.FILES.get('csv_file')
            clear_existing = request.POST.get('clear_existing') == 'on'
            skip_validation = request.POST.get('skip_validation') == 'on'

            if not csv_file:
                self.message_user(request, "Please upload a CSV file.", level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())

            temp_path = None
            try:
                # Save uploaded file temporarily
                import tempfile
                # Use /app if it exists (Docker), otherwise use system temp
                temp_dir = '/app' if os.path.exists('/app') else None
                temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv', dir=temp_dir)
                temp_path = temp_file.name
                
                for chunk in csv_file.chunks():
                    temp_file.write(chunk)
                temp_file.close()

                # Capture command output
                out = StringIO()
                err = StringIO()
                
                # Run the command
                call_command(
                    'import_temperature_records',
                    temp_path,
                    dataset.name,
                    stdout=out,
                    stderr=err,
                    clear=clear_existing,
                    skip_validation=skip_validation,
                )

                # Show success message with output
                output = out.getvalue()
                error_output = err.getvalue()
                
                if error_output:
                    self.message_user(request, f"Import completed with warnings:\n{error_output}\n\n{output}", level=messages.WARNING)
                else:
                    self.message_user(request, f"Import successful!\n\n{output}", level=messages.SUCCESS)
                
                return HttpResponseRedirect(request.get_full_path())

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                self.message_user(request, f"Import failed: {str(e)}\n\nDetails:\n{error_details}", level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())
            
            finally:
                # Clean up temp file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass

        # Show upload form
        context = {
            'dataset': dataset,
            'action': 'import_temperature_records',
            'title': 'Import Temperature Records',
            'help_text': 'Upload a CSV file with columns: Time, outside_temperature',
        }
        return render(request, 'admin/dataset_import.html', context)

    import_temperature_records.short_description = "Import records from CSV"


@admin.register(TemperatureRecord)
class TemperatureRecordAdmin(admin.ModelAdmin):
    list_display = ['temperature_dataset', 'timestamp', 'outside_temperature']
    list_filter = ['temperature_dataset']
    search_fields = ['temperature_dataset__name']
    ordering = ['-timestamp']


class PricesRecordInline(admin.TabularInline):
    model = PricesRecord
    extra = 1


@admin.register(PricesDataset)
class PricesDatasetAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at', 'record_count']
    list_filter = ['is_active']
    search_fields = ['name']
    ordering = ['-created_at']
    actions = ['apply_coefficient', 'import_prices_records']

    def record_count(self, obj):
        count = obj.records.count()
        return format_html('<b>{}</b>', count)
    record_count.short_description = 'Records'

    def apply_coefficient(self, request, queryset):
        """Apply a coefficient to all price records in selected datasets."""
        if 'apply' in request.POST:
            # User has submitted the coefficient
            try:
                coefficient = float(request.POST.get('coefficient', 1.0))
                if coefficient <= 0:
                    self.message_user(request, "Coefficient must be greater than 0.", level=messages.ERROR)
                    return HttpResponseRedirect(request.get_full_path())
                
                total_updated = 0
                for dataset in queryset:
                    # Update all records for this dataset
                    records = PricesRecord.objects.filter(prices_dataset=dataset)
                    for record in records:
                        record.electricity_price *= coefficient
                        record.methane_price *= coefficient
                        record.save()
                    total_updated += records.count()
                
                self.message_user(
                    request,
                    f"Successfully applied coefficient {coefficient} to {total_updated} price records in {queryset.count()} dataset(s).",
                    level=messages.SUCCESS
                )
                return HttpResponseRedirect(request.get_full_path())
            
            except ValueError:
                self.message_user(request, "Invalid coefficient value. Please enter a valid number.", level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())
        
        # Show form to get coefficient
        context = {
            'datasets': queryset,
            'action': 'apply_coefficient',
        }
        return render(request, 'admin/apply_coefficient.html', context)
    
    apply_coefficient.short_description = "Apply coefficient to prices"

    def import_prices_records(self, request, queryset):
        """Import prices records from CSV file."""
        if len(queryset) != 1:
            self.message_user(request, "Please select exactly one dataset to import records.", level=messages.ERROR)
            return

        dataset = queryset.first()

        if 'apply' in request.POST:
            csv_file = request.FILES.get('csv_file')
            clear_existing = request.POST.get('clear_existing') == 'on'
            skip_validation = request.POST.get('skip_validation') == 'on'

            if not csv_file:
                self.message_user(request, "Please upload a CSV file.", level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())

            temp_path = None
            try:
                # Save uploaded file temporarily
                import tempfile
                # Use /app if it exists (Docker), otherwise use system temp
                temp_dir = '/app' if os.path.exists('/app') else None
                temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv', dir=temp_dir)
                temp_path = temp_file.name
                
                for chunk in csv_file.chunks():
                    temp_file.write(chunk)
                temp_file.close()

                # Capture command output
                out = StringIO()
                err = StringIO()
                
                # Run the command
                call_command(
                    'import_prices_records',
                    temp_path,
                    dataset.name,
                    stdout=out,
                    stderr=err,
                    clear=clear_existing,
                    skip_validation=skip_validation,
                )

                # Show success message with output
                output = out.getvalue()
                error_output = err.getvalue()
                
                if error_output:
                    self.message_user(request, f"Import completed with warnings:\n{error_output}\n\n{output}", level=messages.WARNING)
                else:
                    self.message_user(request, f"Import successful!\n\n{output}", level=messages.SUCCESS)
                
                return HttpResponseRedirect(request.get_full_path())

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                self.message_user(request, f"Import failed: {str(e)}\n\nDetails:\n{error_details}", level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())
            
            finally:
                # Clean up temp file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass

        # Show upload form
        context = {
            'dataset': dataset,
            'action': 'import_prices_records',
            'title': 'Import Prices Records',
            'help_text': 'Upload a CSV file with columns: Time, electricity_price, methane_prices',
        }
        return render(request, 'admin/dataset_import.html', context)

    import_prices_records.short_description = "Import records from CSV"


@admin.register(PricesRecord)
class PricesRecordAdmin(admin.ModelAdmin):
    list_display = ['prices_dataset', 'timestamp', 'electricity_price', 'methane_price']
    list_filter = ['prices_dataset']
    search_fields = ['prices_dataset__name']
    ordering = ['-timestamp']


class GenerationRecordInline(admin.TabularInline):
    model = GenerationRecord
    extra = 1


@admin.register(GenerationDataset)
class GenerationDatasetAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at', 'record_count']
    list_filter = ['is_active']
    search_fields = ['name']
    ordering = ['-created_at']
    actions = ['import_generation_records']

    def record_count(self, obj):
        count = obj.records.count()
        return format_html('<b>{}</b>', count)
    record_count.short_description = 'Records'

    def import_generation_records(self, request, queryset):
        """Import generation records from CSV file."""
        if len(queryset) != 1:
            self.message_user(request, "Please select exactly one dataset to import records.", level=messages.ERROR)
            return

        dataset = queryset.first()

        if 'apply' in request.POST:
            csv_file = request.FILES.get('csv_file')
            clear_existing = request.POST.get('clear_existing') == 'on'
            skip_validation = request.POST.get('skip_validation') == 'on'

            if not csv_file:
                self.message_user(request, "Please upload a CSV file.", level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())

            temp_path = None
            try:
                # Save uploaded file temporarily
                import tempfile
                # Use /app if it exists (Docker), otherwise use system temp
                temp_dir = '/app' if os.path.exists('/app') else None
                temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv', dir=temp_dir)
                temp_path = temp_file.name
                
                for chunk in csv_file.chunks():
                    temp_file.write(chunk)
                temp_file.close()

                # Capture command output
                out = StringIO()
                err = StringIO()
                
                # Run the command
                call_command(
                    'import_generation_records',
                    temp_path,
                    dataset.name,
                    stdout=out,
                    stderr=err,
                    clear=clear_existing,
                    skip_validation=skip_validation,
                )

                # Show success message with output
                output = out.getvalue()
                error_output = err.getvalue()
                
                if error_output:
                    self.message_user(request, f"Import completed with warnings:\n{error_output}\n\n{output}", level=messages.WARNING)
                else:
                    self.message_user(request, f"Import successful!\n\n{output}", level=messages.SUCCESS)
                
                return HttpResponseRedirect(request.get_full_path())

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                self.message_user(request, f"Import failed: {str(e)}\n\nDetails:\n{error_details}", level=messages.ERROR)
                return HttpResponseRedirect(request.get_full_path())
            
            finally:
                # Clean up temp file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass

        # Show upload form
        context = {
            'dataset': dataset,
            'action': 'import_generation_records',
            'title': 'Import Generation Records',
            'help_text': 'Upload a CSV file with columns: Time, cogen_kWh, solar_kWh',
        }
        return render(request, 'admin/dataset_import.html', context)

    import_generation_records.short_description = "Import records from CSV"


@admin.register(GenerationRecord)
class GenerationRecordAdmin(admin.ModelAdmin):
    list_display = ['generation_dataset', 'timestamp', 'ele_generated_by_solar_kWh', 'ele_generated_by_cogen_kWh']
    list_filter = ['generation_dataset']
    search_fields = ['generation_dataset__name']
    ordering = ['-timestamp']
