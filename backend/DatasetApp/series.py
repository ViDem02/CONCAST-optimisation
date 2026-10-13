"""
Hourly datasets as 5-minute series, for the optimisation and the simulations.

Missing data must never silently become zero: a missing hour of generation
would look like a free hour of grid electricity, a missing price like free
electricity. hourly_values() therefore checks that every hour of the requested
period has a finite (and, where required, non-negative) value before any
calculation starts, and raises MissingDataError with a readable message
otherwise.

One gap is legitimate: the CSV files are in local time, so the hour repeated
when the clocks go back in October cannot be written in them. That hour takes
the value of the hour before.
"""

import math
from datetime import timedelta, timezone as dt_timezone

import numpy as np
from django.utils import timezone

STEP = timedelta(minutes=5)
HOUR = timedelta(hours=1)
MAX_LISTED = 3


class MissingDataError(ValueError):
    """The data do not cover the requested period; the message is meant for the user."""


def five_minute_grid(start_time, end_time):
    """Timestamps every 5 minutes from start_time while <= end_time."""
    timesteps, current = [], start_time
    while current <= end_time:
        timesteps.append(current)
        current += STEP
    return timesteps


def _hour(moment):
    """Start of the hour of `moment`, in UTC (absolute hours, whatever the time zone of `moment`)."""
    return moment.astimezone(dt_timezone.utc).replace(minute=0, second=0, microsecond=0)


def _local(moment):
    return timezone.localtime(moment).strftime('%d %b %Y %H:%M')


def _is_repeated_hour(moment):
    """True for the second occurrence of a wall-clock hour (end of daylight saving time)."""
    here, before = timezone.localtime(moment), timezone.localtime(moment - HOUR)
    return here.replace(tzinfo=None) == before.replace(tzinfo=None)


def hourly_values(records, fields, start_time, end_time, description, allow_negative=False):
    """
    Values of `fields` for every hour from the hour of start_time to the hour of end_time.

    Args:
        records: queryset of hourly records with a `timestamp` (already restricted to one dataset)
        fields: names of the value fields
        description: e.g. 'generation data "Generation 2024"', used in the error messages
        allow_negative: accept negative values (temperatures)

    Returns:
        {hour (UTC datetime): tuple of values}, including the hour after end_time when the
        dataset has it (used to interpolate the last hour).

    Raises:
        MissingDataError: an hour is missing, or a value is not finite or is negative.
    """
    first, last = _hour(start_time), _hour(end_time)
    rows = records.filter(timestamp__gte=first, timestamp__lte=last + HOUR).values_list('timestamp', *fields)
    values = {timestamp.astimezone(dt_timezone.utc): tuple(row) for timestamp, *row in rows}

    missing, invalid = [], []
    hour = first
    while hour <= last:
        if hour not in values:
            if _is_repeated_hour(hour) and (hour - HOUR) in values:
                values[hour] = values[hour - HOUR]
            else:
                missing.append(hour)
        hour += HOUR

    for hour, row in values.items():
        if any(v is None or not math.isfinite(v) for v in row):
            invalid.append((hour, 'is not a number'))
        elif not allow_negative and any(v < 0 for v in row):
            invalid.append((hour, 'is negative'))

    if missing:
        listed = ', '.join(_local(h) for h in missing[:MAX_LISTED])
        more = f' and {len(missing) - MAX_LISTED} more' if len(missing) > MAX_LISTED else ''
        raise MissingDataError(
            f'The {description} have no value for {len(missing)} hour(s) of the period '
            f'({_local(first)} to {_local(last)}): {listed}{more}. '
            f'Upload the missing hours or choose another period.')
    if invalid:
        hour, problem = sorted(invalid)[0]
        raise MissingDataError(f'The {description}: the value of {_local(hour)} {problem} '
                               f'({len(invalid)} invalid hour(s) in the period). Correct the data first.')
    return values


def to_steps(values, index, timesteps, linear):
    """
    One value per timestep from the hourly values returned by hourly_values().

    linear=True interpolates between the hour and the next one (generation);
    the last hour holds its value if the dataset has no next hour.
    linear=False holds the value of the hour (prices).
    """
    result = np.empty(len(timesteps))
    for i, moment in enumerate(timesteps):
        hour = _hour(moment)
        before = values[hour][index]
        if linear:
            after = values.get(hour + HOUR, values[hour])[index]
            result[i] = before + (after - before) * moment.minute / 60
        else:
            result[i] = before
    return result
