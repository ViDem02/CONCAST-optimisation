"""
Utility functions for dataset validation and import operations.
"""
from datetime import datetime, timedelta
from typing import List, Tuple, Optional


def check_dataset_continuity(
    timestamps: List[datetime],
    expected_interval_minutes: int = 60,
    allow_gaps: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Check if a dataset has continuous timestamps without holes.
    
    Args:
        timestamps: List of datetime objects sorted in chronological order
        expected_interval_minutes: Expected interval between records in minutes (default: 60 for hourly)
        allow_gaps: If True, only report gaps, don't fail validation
    
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if no holes found or allow_gaps=True
        - error_message: Description of gaps found, or None if no gaps
    """
    if not timestamps:
        return True, None
    
    if len(timestamps) == 1:
        return True, None
    
    # Sort timestamps to ensure chronological order
    sorted_timestamps = sorted(timestamps)
    
    gaps = []
    expected_delta = timedelta(minutes=expected_interval_minutes)
    
    for i in range(len(sorted_timestamps) - 1):
        current = sorted_timestamps[i]
        next_timestamp = sorted_timestamps[i + 1]
        actual_delta = next_timestamp - current
        
        if actual_delta != expected_delta:
            # Found a gap or unexpected interval
            if actual_delta > expected_delta:
                # Gap (missing records)
                missing_records = int(actual_delta.total_seconds() / (expected_interval_minutes * 60)) - 1
                gaps.append(
                    f"Gap between {current.strftime('%Y-%m-%d %H:%M:%S')} and "
                    f"{next_timestamp.strftime('%Y-%m-%d %H:%M:%S')}: "
                    f"missing {missing_records} record(s)"
                )
            elif actual_delta < expected_delta:
                # Duplicate or overlapping records
                gaps.append(
                    f"Unexpected interval between {current.strftime('%Y-%m-%d %H:%M:%S')} and "
                    f"{next_timestamp.strftime('%Y-%m-%d %H:%M:%S')}: "
                    f"{actual_delta.total_seconds() / 60:.0f} minutes (expected {expected_interval_minutes})"
                )
    
    if gaps:
        error_message = f"Found {len(gaps)} discontinuity issue(s):\n" + "\n".join(f"  - {gap}" for gap in gaps)
        return allow_gaps, error_message
    
    return True, None


def validate_timestamp_range(
    timestamps: List[datetime],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate that timestamps fall within an expected range.
    
    Args:
        timestamps: List of datetime objects
        start_date: Expected start date (inclusive)
        end_date: Expected end date (inclusive)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not timestamps:
        return True, None
    
    sorted_timestamps = sorted(timestamps)
    actual_start = sorted_timestamps[0]
    actual_end = sorted_timestamps[-1]
    
    errors = []
    
    if start_date and actual_start < start_date:
        errors.append(f"Dataset starts at {actual_start.strftime('%Y-%m-%d %H:%M:%S')} "
                     f"but expected to start at or after {start_date.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if end_date and actual_end > end_date:
        errors.append(f"Dataset ends at {actual_end.strftime('%Y-%m-%d %H:%M:%S')} "
                     f"but expected to end at or before {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if errors:
        return False, "\n".join(errors)
    
    return True, None


def detect_interval(timestamps: List[datetime]) -> Optional[int]:
    """
    Auto-detect the interval between timestamps in minutes.
    
    Args:
        timestamps: List of datetime objects sorted in chronological order
    
    Returns:
        Most common interval in minutes, or None if cannot be determined
    """
    if len(timestamps) < 2:
        return None
    
    sorted_timestamps = sorted(timestamps)
    intervals = []
    
    for i in range(min(10, len(sorted_timestamps) - 1)):  # Check first 10 intervals
        delta = sorted_timestamps[i + 1] - sorted_timestamps[i]
        interval_minutes = int(delta.total_seconds() / 60)
        intervals.append(interval_minutes)
    
    # Return most common interval
    if intervals:
        return max(set(intervals), key=intervals.count)
    
    return None
