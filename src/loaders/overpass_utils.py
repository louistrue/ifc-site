"""
Shared utilities for OpenStreetMap Overpass API access

Provides rate limiting decorator to prevent API abuse.
"""

from functools import wraps
from threading import Lock
import time

# Rate limiting for Overpass API (10 requests per minute)
_rate_limit_lock = Lock()
_last_request_time = [0.0]
_min_request_interval = 6.0  # 6 seconds = 10 requests per minute


def rate_limit_overpass(func):
    """Thread-safe rate limiting decorator for Overpass API"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        global _last_request_time
        with _rate_limit_lock:
            elapsed = time.time() - _last_request_time[0]
            left_to_wait = _min_request_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            _last_request_time[0] = time.time()
        
        return func(*args, **kwargs)
    return wrapper

