from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Max, Min
from django.utils import timezone
from django.utils.html import format_html

from .importers import KINDS, DatasetFileError, read_csv, write_records
from .models import GenerationDataset, PricesDataset, TemperatureDataset


class DatasetForm(forms.ModelForm):
    """Dataset name plus the CSV file to import, validated before anything is saved."""
    kind = None  # Set by DatasetAdmin.get_form

    csv_file = forms.FileField(label='CSV file', required=False)
    replace = forms.BooleanField(
        label='Delete the existing hours first', required=False,
        help_text='Leave unticked to add the new hours and update the hours that already exist.'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parsed_rows = None
        if not self.instance.pk:
            self.fields['csv_file'].required = True
        self.fields['csv_file'].help_text = (
            'One row per hour with the columns ' + ', '.join(['Time', *KINDS[self.kind].columns]) + '.'
        )

    def clean_csv_file(self):
        csv_file = self.cleaned_data.get('csv_file')
        if csv_file:
            try:
                self.parsed_rows = read_csv(self.kind, csv_file)
            except DatasetFileError as e:
                raise forms.ValidationError(str(e))
        return csv_file


class DatasetAdmin(admin.ModelAdmin):
    kind = None
    form = DatasetForm
    list_display = ['name', 'coverage', 'hours', 'updated_at']
    search_fields = ['name']
    ordering = ['-created_at']
    readonly_fields = ['coverage', 'hours']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            first_record=Min('records__timestamp'), last_record=Max('records__timestamp'),
            record_count=Count('records'))

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        return type(form.__name__, (form,), {'kind': self.kind})

    def get_fieldsets(self, request, obj=None):
        example = format_html('Example of a valid file:<pre>{}</pre>', KINDS[self.kind].example)
        if obj is None:
            return [(None, {'fields': ['name', 'csv_file'], 'description': example})]
        return [
            (None, {'fields': ['name', 'coverage', 'hours']}),
            ('Upload more data', {'fields': ['csv_file', 'replace'], 'description': example}),
        ]

    @admin.display(description='Dates covered')
    def coverage(self, obj):
        if not getattr(obj, 'first_record', None):
            return 'No data yet'
        first, last = timezone.localtime(obj.first_record), timezone.localtime(obj.last_record)
        return f'{first:%d %b %Y %H:%M} → {last:%d %b %Y %H:%M}'

    @admin.display(description='Hours of data', ordering='record_count')
    def hours(self, obj):
        return f'{getattr(obj, "record_count", 0):,}'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.parsed_rows:
            count = write_records(self.kind, obj, form.parsed_rows, replace=form.cleaned_data.get('replace', False))
            self.message_user(request, f'Imported {count:,} hours of data into "{obj.name}".', messages.SUCCESS)

    def get_deleted_objects(self, objs, request):
        # Do not list every hourly record on the confirmation page
        to_delete, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        return [str(obj) for obj in objs], model_count, perms_needed, protected


@admin.register(GenerationDataset)
class GenerationDatasetAdmin(DatasetAdmin):
    kind = 'generation'


@admin.register(PricesDataset)
class PricesDatasetAdmin(DatasetAdmin):
    kind = 'prices'


@admin.register(TemperatureDataset)
class TemperatureDatasetAdmin(DatasetAdmin):
    kind = 'temperature'
