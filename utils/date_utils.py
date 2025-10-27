"""Date handling utilities."""
from datetime import datetime, timedelta
from typing import Tuple, Optional


def validate_date_range(start_date: str, end_date: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that dates are in correct format and end date is after start date.

    Args:
        start_date: Date string in YYYY-MM-DD format
        end_date: Date string in YYYY-MM-DD format

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        if end < start:
            return False, "End date must be after start date"

        return True, None
    except ValueError:
        return False, "Invalid date format. Use YYYY-MM-DD"


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Safely parse a date string.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        datetime object or None if invalid
    """
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def format_date(dt: datetime) -> str:
    """
    Format datetime to YYYY-MM-DD string.

    Args:
        dt: datetime object

    Returns:
        Formatted date string
    """
    return dt.strftime('%Y-%m-%d')


def get_default_date_range(days: int = 30) -> Tuple[str, str]:
    """
    Get default date range (today - N days to today).

    Args:
        days: Number of days to look back (default 30)

    Returns:
        Tuple of (start_date, end_date) as strings
    """
    today = datetime.now()
    start_date = (today - timedelta(days=days)).strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')
    return start_date, end_date


def calculate_period_dates(paperboy_start_date: datetime, before_days: int = 60,
                          after_start_days: int = 45, after_days: int = 60) -> dict:
    """
    Calculate before and after period dates based on Paperboy start date.

    Args:
        paperboy_start_date: The date Paperboy started working with client
        before_days: Days to look back before start (default 60)
        after_start_days: Days after start to begin "after" period (default 45)
        after_days: Length of after period in days (default 60)

    Returns:
        Dictionary with before and after period dates
    """
    before_start = paperboy_start_date - timedelta(days=before_days)
    before_end = paperboy_start_date

    after_start = paperboy_start_date + timedelta(days=after_start_days)
    after_end = after_start + timedelta(days=after_days)

    return {
        'before_start': format_date(before_start),
        'before_end': format_date(before_end),
        'after_start': format_date(after_start),
        'after_end': format_date(after_end),
        'before_days': before_days,
        'after_days': after_days
    }
