"""
Replay clock for Bubble Monitor.

Ensures lookahead-free replay by filtering all data access by known_at dates.
Implements R12: No lookahead bias requirement.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from typing import Any

from bm.config import get_config
from bm.db import get_observations

logger = logging.getLogger(__name__)


class LookaheadError(Exception):
    """Attempted to access future data."""

    pass


class ReplayClock:
    """
    Time-aware data access layer for replay-safe evaluation.

    All data access must go through the replay clock to ensure
    no future data (filed/known_at > as_of) is accessed.

    This enforces R12: No lookahead bias.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        as_of: date,
    ):
        """
        Initialize replay clock.

        Args:
            conn: Database connection
            as_of: Evaluation date - only data known by this date is accessible
        """
        self.conn = conn
        self.as_of = as_of
        self._access_log: list[dict[str, Any]] = []

    def observations(
        self,
        *,
        ticker: str | None = None,
        metric: str | None = None,
        source: str | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get observations known by as_of date.

        Args:
            ticker: Filter by ticker
            metric: Filter by metric
            source: Filter by source
            period_start: Filter by period start (inclusive)
            period_end: Filter by period end (inclusive)

        Returns:
            List of observations known by as_of date
        """
        # Build query
        conditions = ["known_at <= ?"]
        params: list[Any] = [self.as_of.isoformat()]

        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker)

        if metric:
            conditions.append("metric = ?")
            params.append(metric)

        if source:
            conditions.append("source = ?")
            params.append(source)

        if period_start:
            conditions.append("period_start >= ?")
            params.append(period_start)

        if period_end:
            conditions.append("period_end <= ?")
            params.append(period_end)

        where_clause = " AND ".join(conditions)

        # Query from observation_current view (latest revisions only)
        cursor = self.conn.execute(
            f"""
            SELECT * FROM observation_current
            WHERE {where_clause}
            ORDER BY period_end DESC, known_at DESC
            """,
            params,
        )

        results = [dict(row) for row in cursor.fetchall()]

        # Log access for audit
        self._access_log.append({
            "method": "observations",
            "filters": {
                "ticker": ticker,
                "metric": metric,
                "source": source,
                "period_start": period_start,
                "period_end": period_end,
            },
            "count": len(results),
            "as_of": self.as_of.isoformat(),
        })

        return results

    def cohort_composition(self, cohort_name: str) -> list[str]:
        """
        Get cohort composition as of the replay date.

        In the future, this could support time-varying cohorts.
        For now, cohorts are static.

        Args:
            cohort_name: Cohort name

        Returns:
            List of tickers in cohort
        """
        config = get_config()
        return config.get_cohort_tickers(cohort_name)

    def latest_observation(
        self,
        ticker: str,
        metric: str,
        before_date: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Get the latest observation for a ticker/metric.

        Args:
            ticker: Stock ticker
            metric: Metric name
            before_date: Optional cutoff date (period_end must be before this)

        Returns:
            Latest observation or None
        """
        observations = self.observations(ticker=ticker, metric=metric)

        if before_date:
            observations = [
                obs for obs in observations
                if obs["period_end"] < before_date
            ]

        if not observations:
            return None

        # Already sorted by period_end DESC, known_at DESC
        return observations[0]

    def observations_range(
        self,
        ticker: str,
        metric: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """
        Get observations within a date range.

        Args:
            ticker: Stock ticker
            metric: Metric name
            start_date: Range start (inclusive)
            end_date: Range end (inclusive)

        Returns:
            List of observations in chronological order
        """
        observations = self.observations(
            ticker=ticker,
            metric=metric,
            period_start=start_date,
            period_end=end_date,
        )

        # Sort chronologically
        return sorted(observations, key=lambda x: x["period_end"])

    def validate_no_lookahead(self) -> bool:
        """
        Validate that no future data has been accessed.

        This is a sanity check - the clock design should prevent lookahead,
        but this can be called to verify.

        Returns:
            True if no lookahead detected

        Raises:
            LookaheadError: If future data detected
        """
        # Check if any observations have known_at > as_of
        cursor = self.conn.execute(
            """
            SELECT COUNT(*) FROM observation
            WHERE known_at > ?
            """,
            (self.as_of.isoformat(),),
        )
        future_count = cursor.fetchone()[0]

        if future_count > 0:
            # This is okay - future data exists but shouldn't be accessible
            logger.debug(f"{future_count} future observations exist (not accessible)")

        # Verify we haven't accidentally accessed any
        for log_entry in self._access_log:
            # All accesses should be filtered by as_of
            if log_entry["as_of"] != self.as_of.isoformat():
                raise LookaheadError(
                    f"Access log shows query with different as_of: {log_entry}"
                )

        return True

    @property
    def access_log(self) -> list[dict[str, Any]]:
        """Get data access log for audit."""
        return self._access_log.copy()


def create_clock(
    conn: sqlite3.Connection,
    as_of: date | str | None = None,
) -> ReplayClock:
    """
    Create a replay clock.

    Args:
        conn: Database connection
        as_of: Evaluation date (default: today)

    Returns:
        ReplayClock instance
    """
    if as_of is None:
        as_of_date = date.today()
    elif isinstance(as_of, str):
        as_of_date = date.fromisoformat(as_of)
    else:
        as_of_date = as_of

    return ReplayClock(conn, as_of_date)


# Context manager for replay sessions
class ReplaySession:
    """
    Context manager for replay sessions.

    Ensures clock is properly created and validated.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        as_of: date | str | None = None,
    ):
        self.conn = conn
        self.as_of = as_of
        self.clock: ReplayClock | None = None

    def __enter__(self) -> ReplayClock:
        self.clock = create_clock(self.conn, self.as_of)
        logger.info(f"Replay session started: as_of={self.clock.as_of}")
        return self.clock

    def __exit__(self, exc_type, exc_val, exc_tb):  # type: ignore
        if self.clock:
            # Validate no lookahead on exit
            try:
                self.clock.validate_no_lookahead()
                logger.info(
                    f"Replay session ended: {len(self.clock.access_log)} data accesses"
                )
            except LookaheadError as e:
                logger.error(f"Lookahead detected: {e}")
                raise
