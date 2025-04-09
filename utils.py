from datetime import datetime, timedelta, timezone
from timelength import TimeLength
import dateparser


def ensure_utc_datetime(time):
    if isinstance(time, datetime):
        return time.astimezone(timezone.utc)
    elif isinstance(time, str):
        return dateparser.parse(time).astimezone(timezone.utc)
    else:
        return None


def ensure_timedelta(time_window):
    if isinstance(time_window, str):
        tl = TimeLength(time_window)
        if not tl.result.success:
            return None
        else:
            return tl.result.delta
    elif isinstance(time_window, timedelta):
        return time_window
    else:
        return None
