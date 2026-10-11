import csv
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from DatasetApp.models import GenerationDataset, GenerationRecord
from DatasetApp.utils import check_dataset_continuity, detect_interval
from django.db import IntegrityError, transaction
from django.utils import timezone


class Command(BaseCommand):
    help = 'Import generation records from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')
        parser.add_argument('dataset_name', type=str, help='Name of the GenerationDataset')
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing records for this dataset before importing',
        )
        parser.add_argument(
            '--skip-validation',
            action='store_true',
            help='Skip continuity validation (not recommended)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        csv_file = options['csv_file']
        dataset_name = options['dataset_name']
        clear_existing = options['clear']
        skip_validation = options['skip_validation']

        # Get or create the dataset
        try:
            dataset = GenerationDataset.objects.get(name=dataset_name)
            self.stdout.write(self.style.SUCCESS(f'Found dataset: {dataset_name}'))
        except GenerationDataset.DoesNotExist:
            raise CommandError(f'GenerationDataset "{dataset_name}" does not exist. Please create it first.')

        # Clear existing records if requested
        if clear_existing:
            count = GenerationRecord.objects.filter(generation_dataset=dataset).count()
            GenerationRecord.objects.filter(generation_dataset=dataset).delete()
            self.stdout.write(self.style.WARNING(f'Deleted {count} existing records'))

        # Read and import CSV
        records_created = 0
        records_updated = 0
        errors = 0
        timestamps = []

        try:
            with open(csv_file, 'r') as file:
                reader = csv.DictReader(file)
                
                # Validate headers
                expected_headers = {'Time', 'cogen_kWh', 'solar_kWh'}
                if not expected_headers.issubset(set(reader.fieldnames)):
                    raise CommandError(f'CSV must contain headers: {expected_headers}')

                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Parse timestamp
                        timestamp = datetime.strptime(row['Time'], '%Y-%m-%d %H:%M:%S')
                        timestamps.append(timestamp)
                        
                        # Parse values
                        cogen_kWh = float(row['cogen_kWh'])
                        solar_kWh = float(row['solar_kWh'])

                        # Create or update record
                        record, created = GenerationRecord.objects.update_or_create(
                            generation_dataset=dataset,
                            timestamp=timezone.make_aware(timestamp, timezone.get_current_timezone()),
                            defaults={
                                'ele_generated_by_cogen_kWh': cogen_kWh,
                                'ele_generated_by_solar_kWh': solar_kWh,
                            }
                        )

                        if created:
                            records_created += 1
                        else:
                            records_updated += 1

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'Error on row {row_num}: {str(e)}')
                        )
                        errors += 1

        except FileNotFoundError:
            raise CommandError(f'File "{csv_file}" not found')
        except Exception as e:
            raise CommandError(f'Error reading CSV file: {str(e)}')

        # Validate dataset continuity
        if not skip_validation and timestamps:
            self.stdout.write('\nValidating dataset continuity...')
            
            # Auto-detect interval
            interval = detect_interval(timestamps)
            if interval:
                self.stdout.write(f'Detected interval: {interval} minutes')
            else:
                interval = 60  # Default to hourly
                self.stdout.write(f'Using default interval: {interval} minutes')
            
            is_valid, error_message = check_dataset_continuity(timestamps, interval)
            
            if not is_valid:
                self.stdout.write(self.style.ERROR('\n' + error_message))
                raise CommandError('Dataset validation failed: dataset contains holes or discontinuities')
            elif error_message:
                self.stdout.write(self.style.WARNING('\n' + error_message))
            else:
                self.stdout.write(self.style.SUCCESS('✓ Dataset is continuous with no holes'))

        # Summary
        self.stdout.write(self.style.SUCCESS(f'\nImport complete:'))
        self.stdout.write(f'  Records created: {records_created}')
        self.stdout.write(f'  Records updated: {records_updated}')
        if errors > 0:
            self.stdout.write(self.style.ERROR(f'  Errors: {errors}'))
