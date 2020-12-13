from datetime import datetime, timedelta, timezone

DATE_FORMAT = '%Y-%m-%d'


def to_days(delta: timedelta):
    return delta / timedelta(days=1)


def ms_to_datetime(ms: float):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)