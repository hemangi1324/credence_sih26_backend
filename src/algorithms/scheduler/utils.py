import datetime

def time_to_minutes(t: datetime.time) -> int:
    """Converts datetime.time to minutes since midnight."""
    if not t:
        return 0
    return t.hour * 60 + t.minute

def minutes_to_time(m: int) -> datetime.time:
    """Converts minutes since midnight to datetime.time."""
    m = m % 1440
    hour = m // 60
    minute = m % 60
    return datetime.time(hour, minute)
