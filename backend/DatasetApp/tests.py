"""Tests of the CSV import of the hourly datasets."""

import io

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .importers import DatasetFileError, import_csv, read_csv
from .models import GenerationDataset, PricesDataset


def text(content):
    return io.StringIO(content)


class ReadCsvTests(TestCase):

    def test_reads_the_rows_and_ignores_extra_columns(self):
        rows = read_csv('prices', text('Time,electricity_price,methane_prices\n'
                                       '2024-01-01 00:00:00,0.18,0.05\n2024-01-01 01:00:00,0.17,0.05\n'))
        self.assertEqual([values for _, values in rows], [{'electricity_price': 0.18}, {'electricity_price': 0.17}])

    def test_missing_column_is_explained(self):
        with self.assertRaisesMessage(DatasetFileError, 'missing: solar_kWh'):
            read_csv('generation', text('Time,cogen_kWh\n2024-01-01 00:00:00,1\n'))

    def test_bad_values_report_the_line(self):
        with self.assertRaisesMessage(DatasetFileError, 'line 3'):
            read_csv('prices', text('Time,electricity_price\n2024-01-01 00:00:00,0.1\n2024-01-01 01:00:00,abc\n'))

    def test_missing_hours_are_rejected_unless_allowed(self):
        content = 'Time,electricity_price\n2024-01-01 00:00:00,0.1\n2024-01-01 03:00:00,0.1\n'
        with self.assertRaisesMessage(DatasetFileError, 'missing hours'):
            read_csv('prices', text(content))
        self.assertEqual(len(read_csv('prices', text(content), check_continuity=False)), 2)

    def test_negative_prices_are_rejected(self):
        with self.assertRaisesMessage(DatasetFileError, 'negative'):
            read_csv('prices', text('Time,electricity_price\n2024-01-01 00:00:00,-0.1\n'))


class ImportCsvTests(TestCase):
    CSV = 'Time,cogen_kWh,solar_kWh\n2024-01-01 00:00:00,10,0\n2024-01-01 01:00:00,20,0\n'

    def test_import_updates_existing_hours_and_replace_starts_over(self):
        dataset = GenerationDataset.objects.create(name='gen')
        import_csv('generation', dataset, text(self.CSV))
        import_csv('generation', dataset, text('Time,cogen_kWh,solar_kWh\n2024-01-01 01:00:00,99,0\n'
                                               '2024-01-01 02:00:00,30,0\n'))
        self.assertEqual(list(dataset.records.values_list('ele_generated_by_cogen_kWh', flat=True)), [10, 99, 30])
        import_csv('generation', dataset, text(self.CSV), replace=True)
        self.assertEqual(dataset.records.count(), 2)


class DatasetAdminTests(TestCase):

    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin', '', 'pw'))

    def test_dataset_is_created_with_its_file(self):
        upload = SimpleUploadedFile('prices.csv', b'Time,electricity_price\n2024-01-01 00:00:00,0.2\n'
                                                  b'2024-01-01 01:00:00,0.3\n')
        response = self.client.post('/admin/DatasetApp/pricesdataset/add/', {'name': 'p', 'csv_file': upload})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PricesDataset.objects.get(name='p').records.count(), 2)

    def test_invalid_file_is_shown_in_the_form_and_nothing_is_saved(self):
        upload = SimpleUploadedFile('prices.csv', b'Time,price\n2024-01-01 00:00:00,0.2\n')
        response = self.client.post('/admin/DatasetApp/pricesdataset/add/', {'name': 'p', 'csv_file': upload})
        self.assertContains(response, 'missing: electricity_price')
        self.assertFalse(PricesDataset.objects.exists())
