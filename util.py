import functools
import time
from datetime import datetime, timedelta, timezone

DATE_FORMAT = '%Y-%m-%d'


def to_days(delta: timedelta):
    return delta / timedelta(days=1)


def ms_to_datetime(ms: float):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def timer(func):
    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        tic = time.perf_counter()
        value = func(*args, **kwargs)
        toc = time.perf_counter()
        elapsed_time = toc - tic
        print(f"Elapsed time {func.__name__}: {elapsed_time:0.4f} seconds")
        return value

    return wrapper_timer
