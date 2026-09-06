"""
Base collector class for Bubble Monitor.

All data collectors inherit from this base class.
"""

from __future__ import annotations

import logging
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any

from bm.db import insert_observation
from bm.http import HttpClient, get_http_client

logger = logging.getLogger(__name__)


class CollectorError(Exception):
    """Collector operation error."""

    pass


@dataclass
class Observation:
    """A single observation to be stored."""

    source: str
    ticker: str | None
    metric: str
    period_start: str  # ISO date
    period_end: str  # ISO date
    value: float
    known_at: str  # ISO date - when this fact became known
    unit: str | None = None
    revision: int = 1
    raw_payload: str | None = None


class BaseCollector(ABC):
    """
    Base class for data collectors.

    Collectors are responsible for:
    1. Fetching raw data from external sources
    2. Transforming data into observations
    3. Storing observations in the database
    """

    source_name: str = "base"

    def __init__(
        self,
        conn: sqlite3.Connection,
        http_client: HttpClient | None = None,
    ):
        self.conn = conn
        self.http = http_client or get_http_client()

    @abstractmethod
    def collect(
        self,
        tickers: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Observation]:
        """
        Collect data for given tickers.

        Args:
            tickers: List of stock tickers to collect
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of observations collected
        """
        pass

    def store(self, observations: list[Observation]) -> int:
        """
        Store observations in the database.

        Args:
            observations: List of observations to store

        Returns:
            Number of observations stored
        """
        count = 0
        for obs in observations:
            try:
                insert_observation(
                    self.conn,
                    source=obs.source,
                    ticker=obs.ticker,
                    metric=obs.metric,
                    period_start=obs.period_start,
                    period_end=obs.period_end,
                    value=obs.value,
                    known_at=obs.known_at,
                    unit=obs.unit,
                    revision=obs.revision,
                    raw_payload=obs.raw_payload,
                )
                count += 1
            except sqlite3.IntegrityError as e:
                # Duplicate observation - skip
                logger.debug(f"Skipping duplicate: {obs.ticker}/{obs.metric}/{obs.period_end}: {e}")

        logger.info(f"Stored {count}/{len(observations)} observations from {self.source_name}")
        return count

    def collect_and_store(
        self,
        tickers: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """
        Collect and store observations.

        Convenience method combining collect and store.
        """
        observations = self.collect(tickers, start_date, end_date)
        return self.store(observations)
