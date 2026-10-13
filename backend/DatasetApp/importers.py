"""
CSV import of the hourly datasets, shared by the admin upload form and the
import_*_records management commands.

Reading is separated from writing so that the admin can validate a file in
the form (and show the errors next to the upload field) before saving.
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from .models import GenerationRecord, PricesRecord, TemperatureRecord
from .utils import check_dataset_continuity

TIME_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d-%m-%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M')
MAX_REPORTED_ERRORS = 5


@dataclass(frozen=True)
class DatasetKind:
    record_model: type
    dataset_field: str
    columns: dict  # CSV column -> record field
    example: str


KINDS = {
    'generation': DatasetKind(
        GenerationRecord, 'generation_dataset',
        {'cogen_kWh': 'ele_generated_by_cogen_kWh', 'solar_kWh': 'ele_generated_by_solar_kWh'},
        'Time,cogen_kWh,solar_kWh\n2024-01-01 00:00:00,350,0\n2024-01-01 01:00:00,350,0',
    ),
    'prices': DatasetKind(
        PricesRecord, 'prices_dataset',
        {'electricity_price': 'electricity_price'},
        'Time,electricity_price\n2024-01-01 00:00:00,0.18325\n2024-01-01 01:00:00,0.18025',
    ),
    'temperature': DatasetKind(
        TemperatureRecord, 'temperature_dataset',
        {'outside_temperature': 'outside_temperature'},
        'Time,outside_temperature\n2024-01-01 00:00:00,6.8\n2024-01-01 01:00:00,5.9',
    ),
}


class DatasetFileError(ValueError):
    """The file cannot be imported; the message is meant for the user."""


def _parse_time(text):
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            pass
    raise ValueError(f'unrecognised date/time "{text}" (expected e.g. 2024-01-31 13:00:00)')


def read_csv(kind, source, check_continuity=True):
    """
    Parse an hourly CSV file into a list of (aware timestamp, {field: value}).

    `source` is a path, a text stream or an uploaded (binary) file.
    Raises DatasetFileError with a readable message when the file is not valid.
    Extra columns (e.g. the old methane_prices column) are ignored.
    """
    spec = KINDS[kind]
    if isinstance(source, str):
        with open(source, newline='', encoding='utf-8-sig') as f:
            return read_csv(kind, f, check_continuity)
    if not isinstance(source, io.TextIOBase):  # Uploaded file: bytes
        source.seek(0)
        try:
            source = io.StringIO(source.read().decode('utf-8-sig'), newline='')
        except UnicodeDecodeError:
            raise DatasetFileError('The file is not a text CSV file (save it as "CSV UTF-8").')

    reader = csv.DictReader(source)
    required = ['Time', *spec.columns]
    missing = [c for c in required if c not in (reader.fieldnames or [])]
    if missing:
        raise DatasetFileError(
            f'The file must have the columns {", ".join(required)}; missing: {", ".join(missing)}.'
        )

    tz = timezone.get_current_timezone()
    rows, naive_times, errors = {}, [], []
    for line, row in enumerate(reader, start=2):
        try:
            naive = _parse_time(row['Time'])
            values = {field: float(row[column]) for column, field in spec.columns.items()}
        except (TypeError, ValueError) as e:
            errors.append(f'line {line}: {e}')
            continue
        if kind != 'temperature' and any(v < 0 for v in values.values()):
            errors.append(f'line {line}: values cannot be negative')
            continue
        naive_times.append(naive)
        # Duplicate times (e.g. the repeated hour when daylight saving time ends) keep the last value
        rows[timezone.make_aware(naive, tz)] = values

    if errors:
        more = f' (and {len(errors) - MAX_REPORTED_ERRORS} more)' if len(errors) > MAX_REPORTED_ERRORS else ''
        raise DatasetFileError('The file has invalid rows: ' + '; '.join(errors[:MAX_REPORTED_ERRORS]) + more + '.')
    if not rows:
        raise DatasetFileError('The file contains no data rows.')

    if check_continuity:
        ok, message = check_dataset_continuity(naive_times, expected_interval_minutes=60)
        if not ok:
            raise DatasetFileError(f'The file has missing hours, so results would be wrong. {message}')

    return sorted(rows.items())


@transaction.atomic
def write_records(kind, dataset, rows, replace=False):
    """Store parsed rows in `dataset`, updating times that already exist. Returns the number of rows."""
    spec = KINDS[kind]
    manager = spec.record_model.objects
    if replace:
        manager.filter(**{spec.dataset_field: dataset}).delete()
    manager.bulk_create(
        [spec.record_model(**{spec.dataset_field: dataset, 'timestamp': ts, **values}) for ts, values in rows],
        batch_size=2000,
        update_conflicts=True,
        unique_fields=[spec.dataset_field, 'timestamp'],
        update_fields=list(spec.columns.values()),
    )
    return len(rows)


def import_csv(kind, dataset, source, replace=False, check_continuity=True):
    """Read and store a CSV file in one step. Returns the number of hourly rows imported."""
    return write_records(kind, dataset, read_csv(kind, source, check_continuity), replace)
