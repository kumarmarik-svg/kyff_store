"""
Timezone utilities for KYFF Store.

The backend stores ALL timestamps in UTC (datetime.utcnow()).
Templates convert them to Indian Standard Time (IST, UTC+5:30)
using the `ist` Jinja filter registered in create_app().

Usage in templates:
    {{ order.created_at | ist }}
    {{ order.created_at | ist | strftime("%d %B %Y at %I:%M %p") }}
"""

from datetime import timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def utc_to_ist(dt):
    """Convert a naive UTC datetime to an IST-aware datetime."""
    if not dt:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(IST)


def strftime(dt, fmt):
    """Format a datetime using a strftime format string."""
    if not dt:
        return ""
    return dt.strftime(fmt)
