"""
Nowcast error tracking for Bubble Monitor.

Tracks prediction accuracy for indicators and calculates uncertainty bands.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NowcastError:
    """Nowcast error record."""

    id: int | None
    indicator_id: str
    target_period_end: date
    predicted_value: float
    actual_value: float | None
    error: float | None
    error_pct: float | None
    predicted_at: datetime
    updated_at: datetime | None
    mae: float | None = None  # Calculated, not stored

    @property
    def absolute_error(self) -> float | None:
        """Calculate absolute error."""
        if self.actual_value is None:
            return None
        return abs(self.actual_value - self.predicted_value)


@dataclass
class UncertaintyBand:
    """Uncertainty band for nowcast visualization."""

    indicator_id: str
    period_end: date
    predicted_value: float
    lower_bound: float | None
    upper_bound: float | None
    mae: float | None
    sample_count: int
    elapsed_days: int
    period_days: int

    @property
    def band_width(self) -> float | None:
        """Calculate band width using formula: mae * (1 + elapsed_days / period_days)."""
        if self.mae is None:
            return None
        if self.period_days == 0:
            return self.mae
        return self.mae * (1 + self.elapsed_days / self.period_days)

    @property
    def has_sufficient_samples(self) -> bool:
        """Check if we have enough samples to show error (minimum 4)."""
        return self.sample_count >= 4


def insert_nowcast(
    conn: sqlite3.Connection,
    indicator_id: str,
    target_period_end: date,
    predicted_value: float,
) -> int:
    """
    Insert a nowcast prediction.

    Args:
        conn: Database connection
        indicator_id: Indicator identifier
        target_period_end: Period end date being predicted
        predicted_value: Predicted value

    Returns:
        Nowcast record ID
    """
    cursor = conn.execute(
        """
        INSERT INTO nowcast_error
        (indicator_id, target_period_end, predicted_value, predicted_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (indicator_id, target_period_end.isoformat(), predicted_value),
    )
    conn.commit()

    record_id = cursor.lastrowid
    logger.info(
        f"Inserted nowcast for {indicator_id} @ {target_period_end}: {predicted_value}"
    )

    return record_id


def update_nowcast_actual(
    conn: sqlite3.Connection,
    nowcast_id: int,
    actual_value: float,
) -> None:
    """
    Update nowcast with actual observed value.

    Calculates error and error_pct.

    Args:
        conn: Database connection
        nowcast_id: Nowcast record ID
        actual_value: Actual observed value
    """
    # Get predicted value
    cursor = conn.execute(
        "SELECT predicted_value FROM nowcast_error WHERE id = ?",
        (nowcast_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Nowcast {nowcast_id} not found")

    predicted_value = row[0]
    error = actual_value - predicted_value
    error_pct = (error / actual_value) if actual_value != 0 else None

    # Update record
    conn.execute(
        """
        UPDATE nowcast_error
        SET actual_value = ?,
            error = ?,
            error_pct = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (actual_value, error, error_pct, nowcast_id),
    )

    conn.commit()
    logger.info(f"Updated nowcast {nowcast_id} with actual: {actual_value}")


def get_nowcast_errors(
    conn: sqlite3.Connection,
    indicator_id: str | None = None,
    limit: int = 50,
) -> list[NowcastError]:
    """
    Get nowcast error records with calculated MAE.

    Args:
        conn: Database connection
        indicator_id: Filter by indicator (optional)
        limit: Maximum records to return

    Returns:
        List of nowcast error records
    """
    conditions = []
    params: list[Any] = []

    if indicator_id:
        conditions.append("indicator_id = ?")
        params.append(indicator_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    cursor = conn.execute(
        f"""
        SELECT id, indicator_id, target_period_end, predicted_value,
               actual_value, error, error_pct, predicted_at, updated_at
        FROM nowcast_error
        WHERE {where_clause}
        ORDER BY predicted_at DESC
        LIMIT {limit}
        """,
        params,
    )

    records = []
    for row in cursor.fetchall():
        record = NowcastError(
            id=row[0],
            indicator_id=row[1],
            target_period_end=date.fromisoformat(row[2]),
            predicted_value=row[3],
            actual_value=row[4],
            error=row[5],
            error_pct=row[6],
            predicted_at=datetime.fromisoformat(row[7]),
            updated_at=(
                datetime.fromisoformat(row[8]) if row[8] else None
            ),
        )
        records.append(record)

    # Calculate MAE for records with the same indicator
    if records:
        # Get MAE for this indicator
        mae = _calculate_mae(conn, records[0].indicator_id)
        for record in records:
            record.mae = mae

    return records


def _calculate_mae(conn: sqlite3.Connection, indicator_id: str) -> float | None:
    """
    Calculate MAE for an indicator from all observed nowcasts.

    Args:
        conn: Database connection
        indicator_id: Indicator identifier

    Returns:
        MAE value or None if no observations
    """
    cursor = conn.execute(
        """
        SELECT AVG(ABS(error))
        FROM nowcast_error
        WHERE indicator_id = ?
          AND actual_value IS NOT NULL
        """,
        (indicator_id,),
    )

    row = cursor.fetchone()
    return row[0] if row and row[0] is not None else None


def get_uncertainty_band(
    conn: sqlite3.Connection,
    indicator_id: str,
    target_period_end: date,
    as_of: date | None = None,
) -> UncertaintyBand | None:
    """
    Get uncertainty band for a nowcast.

    Band width formula: mae * (1 + elapsed_days / period_days)

    Args:
        conn: Database connection
        indicator_id: Indicator identifier
        target_period_end: Period end date
        as_of: Current date (defaults to today)

    Returns:
        Uncertainty band or None if nowcast not found
    """
    if as_of is None:
        as_of = date.today()

    # Get latest nowcast for this indicator and period
    cursor = conn.execute(
        """
        SELECT predicted_value, predicted_at
        FROM nowcast_error
        WHERE indicator_id = ?
          AND target_period_end = ?
        ORDER BY predicted_at DESC
        LIMIT 1
        """,
        (indicator_id, target_period_end.isoformat()),
    )

    row = cursor.fetchone()
    if not row:
        return None

    predicted_value = row[0]
    predicted_at = datetime.fromisoformat(row[1])

    # Calculate MAE
    mae = _calculate_mae(conn, indicator_id)

    # Count samples for this indicator
    cursor = conn.execute(
        """
        SELECT COUNT(*)
        FROM nowcast_error
        WHERE indicator_id = ?
          AND actual_value IS NOT NULL
        """,
        (indicator_id,),
    )
    sample_count = cursor.fetchone()[0]

    # Calculate elapsed days
    elapsed_days = (as_of - predicted_at.date()).days
    if elapsed_days < 0:
        elapsed_days = 0

    # Estimate period days (assume quarterly = 90 days)
    period_days = 90

    # Create band
    band = UncertaintyBand(
        indicator_id=indicator_id,
        period_end=target_period_end,
        predicted_value=predicted_value,
        mae=mae,
        sample_count=sample_count,
        elapsed_days=elapsed_days,
        period_days=period_days,
        lower_bound=None,
        upper_bound=None,
    )

    # Calculate bounds if sufficient samples
    if band.has_sufficient_samples and mae is not None:
        width = band.band_width
        if width is not None:
            band.lower_bound = predicted_value - width
            band.upper_bound = predicted_value + width

    return band


def get_nowcast_summary(
    conn: sqlite3.Connection,
    indicator_id: str,
) -> dict[str, Any]:
    """
    Get summary statistics for nowcast errors.

    Args:
        conn: Database connection
        indicator_id: Indicator identifier

    Returns:
        Summary dictionary with MAE, sample count, etc.
    """
    cursor = conn.execute(
        """
        SELECT
            COUNT(*) as total_nowcasts,
            COUNT(actual_value) as observed_nowcasts,
            AVG(ABS(error)) as mae,
            MIN(error) as min_error,
            MAX(error) as max_error,
            AVG(error) as mean_error
        FROM nowcast_error
        WHERE indicator_id = ?
        """,
        (indicator_id,),
    )

    row = cursor.fetchone()

    return {
        "indicator_id": indicator_id,
        "total_nowcasts": row[0],
        "observed_nowcasts": row[1],
        "mae": row[2],
        "min_error": row[3],
        "max_error": row[4],
        "mean_error": row[5],
        "has_sufficient_samples": row[1] >= 4,
    }
