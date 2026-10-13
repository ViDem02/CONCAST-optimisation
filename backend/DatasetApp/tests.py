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


class SeriesTests(TestCase):
    """Hourly data as 5-minute series: complete periods only, never silent zeros."""

    def setUp(self):
        from datetime import datetime, timedelta
        from django.utils import timezone
        self.dataset = GenerationDataset.objects.create(name='g')
        self.tz = timezone.get_current_timezone()
        self.aware = lambda *args: timezone.make_aware(datetime(*args), self.tz)
        self.timedelta = timedelta

    def add(self, naive_times, value=lambda t: 10.0):
        from .models import GenerationRecord
        from django.utils import timezone
        GenerationRecord.objects.bulk_create(
            GenerationRecord(generation_dataset=self.dataset, timestamp=timezone.make_aware(t, self.tz),
                             ele_generated_by_solar_kWh=value(t), ele_generated_by_cogen_kWh=0) for t in naive_times)

    def values(self, start, end):
        from .series import hourly_values
        return hourly_values(self.dataset.records.all(), ['ele_generated_by_solar_kWh'], start, end, 'generation data "g"')

    def test_last_hour_interpolates_towards_the_next_hour_or_holds(self):
        from datetime import datetime
        from .series import five_minute_grid, to_steps
        start, end = self.aware(2024, 7, 8, 0, 0), self.aware(2024, 7, 8, 1, 59)
        self.add([datetime(2024, 7, 8, h) for h in range(2)], value=lambda t: 12.0)
        grid = five_minute_grid(start, end)
        # No record after the period: the last hour holds its value instead of falling to zero
        self.assertEqual(list(to_steps(self.values(start, end), 0, grid, linear=True)), [12.0] * 24)
        self.add([datetime(2024, 7, 8, 2)], value=lambda t: 0.0)
        series = to_steps(self.values(start, end), 0, grid, linear=True)
        self.assertAlmostEqual(series[12], 12.0)       # 01:00
        self.assertAlmostEqual(series[18], 6.0)        # 01:30, half-way to the 02:00 value
        self.assertEqual(len(grid), 24)

    def test_missing_hours_are_refused_with_their_time(self):
        from datetime import datetime
        from .series import MissingDataError
        self.add([datetime(2024, 7, 8, h) for h in range(24) if h not in (5, 6)])
        with self.assertRaisesMessage(MissingDataError, 'no value for 2 hour(s) of the period '
                                                        '(08 Jul 2024 00:00 to 08 Jul 2024 23:00): '
                                                        '08 Jul 2024 05:00, 08 Jul 2024 06:00'):
            self.values(self.aware(2024, 7, 8, 0, 0), self.aware(2024, 7, 8, 23, 59))

    def test_the_hour_repeated_when_clocks_go_back_takes_the_value_of_the_hour_before(self):
        # A local-time CSV has 24 rows on 27 Oct 2024; the day has 25 hours, 02:00 happens twice
        from datetime import datetime
        self.add([datetime(2024, 10, 27, h) for h in range(24)], value=lambda t: float(t.hour))
        start, end = self.aware(2024, 10, 27, 0, 0), self.aware(2024, 10, 27, 23, 59)
        values = self.values(start, end)
        hours = sorted(h for h in values if start <= h <= end)
        self.assertEqual(len(hours), 25)
        self.assertEqual([values[h][0] for h in hours[:5]], [0.0, 1.0, 2.0, 2.0, 3.0])

    def test_any_other_gap_on_that_day_is_still_refused(self):
        from datetime import datetime
        from .series import MissingDataError
        self.add([datetime(2024, 10, 27, h) for h in range(24) if h != 10])
        with self.assertRaisesMessage(MissingDataError, '27 Oct 2024 10:00'):
            self.values(self.aware(2024, 10, 27, 0, 0), self.aware(2024, 10, 27, 23, 59))


class NonFiniteImportTests(TestCase):

    def test_nan_and_infinite_values_are_refused(self):
        for value in ('nan', 'inf', '-inf'):
            with self.subTest(value=value):
                with self.assertRaisesMessage(DatasetFileError, 'not NaN or infinite'):
                    read_csv('prices', text(f'Time,electricity_price\n2024-01-01 00:00:00,{value}\n'))
