from django.core.management.base import BaseCommand, CommandError

from DatasetApp.importers import KINDS, DatasetFileError, import_csv
from DatasetApp.models import PricesDataset


class Command(BaseCommand):
    help = 'Import hourly prices records from a CSV file (columns: Time, ' + ', '.join(KINDS['prices'].columns) + ')'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')
        parser.add_argument('dataset_name', type=str, help='Name of the dataset (created if it does not exist)')
        parser.add_argument('--clear', action='store_true', help='Delete the existing records of the dataset first')
        parser.add_argument('--skip-validation', action='store_true',
                            help='Do not check that the file has no missing hours (not recommended)')

    def handle(self, *args, **options):
        dataset, created = PricesDataset.objects.get_or_create(name=options['dataset_name'])
        if created:
            self.stdout.write(f'Created dataset "{dataset.name}"')
        try:
            count = import_csv('prices', dataset, options['csv_file'], replace=options['clear'],
                               check_continuity=not options['skip_validation'])
        except FileNotFoundError:
            raise CommandError(f'File "{options["csv_file"]}" not found')
        except DatasetFileError as e:
            raise CommandError(str(e))
        self.stdout.write(self.style.SUCCESS(f'Imported {count} hourly records into "{dataset.name}"'))
