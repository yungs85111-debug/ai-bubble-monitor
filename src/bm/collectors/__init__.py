"""
Data collectors for Bubble Monitor.

Collectors fetch data from external sources and store observations.
"""

from bm.collectors.base import BaseCollector, CollectorError

__all__ = ["BaseCollector", "CollectorError"]
