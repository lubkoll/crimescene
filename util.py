from datetime import timedelta

DATE_FORMAT = '%Y-%m-%d'


def to_days(delta: timedelta):
    return delta / timedelta(days=1)