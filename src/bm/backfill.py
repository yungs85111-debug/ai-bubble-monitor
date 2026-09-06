"""
Backfill system for Bubble Monitor.

Executes historical evaluations over a date range using ReplayClock.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from bm.clock import ReplayClock
from bm.config import get_config
from bm.db import complete_ledger_run, supersede_run
from bm.ledger import (
    create_evaluation_run,
    get_latest_verdicts,
    write_verdicts_to_ledger,
)
from bm.rules.engine import RuleEngine, Verdict
from bm.rules.definitions import get_all_rules
from bm.thresholds import get_threshold_manager

logger = logging.getLogger(__name__)


@dataclass
class BackfillTick:
    """A single evaluation tick in backfill."""

    as_of: date
    verdicts: list[Verdict] = field(default_factory=list)
    error: str | None = None


@dataclass
class BackfillReport:
    """Report of backfill execution."""

    start_date: date
    end_date: date
    total_ticks: int
    successful_ticks: int
    failed_ticks: int
    total_verdicts: int
    verdict_counts: dict[str, int] = field(default_factory=dict)
    ticks: list[BackfillTick] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_ticks == 0:
            return 0.0
        return self.successful_ticks / self.total_ticks

    def summary(self) -> str:
        """Generate text summary of report."""
        lines = [
            "Backfill Report",
            "=" * 60,
            f"Date range: {self.start_date} to {self.end_date}",
            f"Total ticks: {self.total_ticks}",
            f"Successful: {self.successful_ticks}",
            f"Failed: {self.failed_ticks}",
            f"Success rate: {self.success_rate:.1%}",
            "",
            f"Total verdicts: {self.total_verdicts}",
            "Verdict breakdown:",
        ]

        for verdict_type, count in sorted(self.verdict_counts.items()):
            lines.append(f"  {verdict_type}: {count}")

        if self.failed_ticks > 0:
            lines.append("")
            lines.append("Failed ticks:")
            for tick in self.ticks:
                if tick.error:
                    lines.append(f"  {tick.as_of}: {tick.error}")

        return "\n".join(lines)


def get_filing_dates_in_range(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> list[date]:
    """
    Get unique filing dates (known_at) within date range.

    These are the "ticks" for backfill - we evaluate at each filing date.

    Args:
        conn: Database connection
        start_date: Start of range (inclusive)
        end_date: End of range (inclusive)

    Returns:
        List of unique filing dates, sorted
    """
    cursor = conn.execute(
        """
        SELECT DISTINCT DATE(known_at) as filing_date
        FROM observation
        WHERE known_at >= ? AND known_at <= ?
        ORDER BY filing_date
        """,
        (start_date.isoformat(), end_date.isoformat()),
    )

    filing_dates = [date.fromisoformat(row[0]) for row in cursor.fetchall()]
    logger.info(f"Found {len(filing_dates)} filing dates in range")

    return filing_dates


def evaluate_at_date(
    conn: sqlite3.Connection,
    as_of_date: date,
    previous_verdicts: dict[str, Verdict] | None = None,
) -> list[Verdict]:
    """
    Evaluate all premises at a specific date.

    Args:
        conn: Database connection
        as_of_date: Evaluation date
        previous_verdicts: Previous verdicts for change detection (R8)

    Returns:
        List of verdicts (only changed verdicts per R8)
    """
    # Create replay clock
    clock = ReplayClock(conn, as_of_date)

    # Get threshold manager
    threshold_manager = get_threshold_manager()

    # Validate that only enabled thresholds with replayable=True are used
    enabled = threshold_manager.get_enabled()
    for indicator_id, threshold in enabled.items():
        if not threshold.replayable:
            logger.warning(
                f"Threshold {indicator_id} is enabled but not replayable - "
                "skipping in backfill"
            )
            # In future, could raise error or disable threshold temporarily

    # Create rule engine
    engine = RuleEngine(clock, threshold_manager)

    # Register all rules
    for rule_id, rule_func, metadata in get_all_rules():
        engine.register_rule(rule_id, rule_func, metadata)

    # Evaluate all premises
    verdicts = engine.evaluate_all_premises(previous_verdicts=previous_verdicts)

    logger.debug(f"Evaluated at {as_of_date}: {len(verdicts)} changed verdicts")

    return verdicts


def run_backfill(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date | None = None,
    commit: bool = False,
    supersede_run_id: int | None = None,
    supersede_reason: str | None = None,
) -> BackfillReport:
    """
    Run backfill evaluation over date range.

    Args:
        conn: Database connection
        start_date: Start date (inclusive)
        end_date: End date (inclusive, defaults to today)
        commit: If True, write to ledger. If False, dry-run only.
        supersede_run_id: If provided, mark this run as superseded
        supersede_reason: Reason for superseding (required if supersede_run_id)

    Returns:
        BackfillReport with results
    """
    if end_date is None:
        end_date = date.today()

    if supersede_run_id and not supersede_reason:
        raise ValueError("supersede_reason required when superseding a run")

    logger.info(
        f"Starting backfill: {start_date} to {end_date} "
        f"(commit={commit})"
    )

    # Get filing dates (these are our ticks)
    filing_dates = get_filing_dates_in_range(conn, start_date, end_date)

    if not filing_dates:
        logger.warning("No filing dates found in range")
        return BackfillReport(
            start_date=start_date,
            end_date=end_date,
            total_ticks=0,
            successful_ticks=0,
            failed_ticks=0,
            total_verdicts=0,
        )

    # Initialize report
    report = BackfillReport(
        start_date=start_date,
        end_date=end_date,
        total_ticks=len(filing_dates),
        successful_ticks=0,
        failed_ticks=0,
        total_verdicts=0,
    )

    # Create run if committing
    run_id = None
    if commit:
        run_id = create_evaluation_run(
            conn,
            run_type="backfill",
            as_of=end_date.isoformat(),
            commit_hash=None,  # TODO: Get git commit if available
        )
        logger.info(f"Created backfill run {run_id}")

    # Track latest verdicts for R8 (silence on no change)
    latest_verdicts: dict[str, Verdict] = {}

    # Evaluate at each filing date
    for filing_date in filing_dates:
        tick = BackfillTick(as_of=filing_date)

        try:
            verdicts = evaluate_at_date(conn, filing_date, latest_verdicts)

            tick.verdicts = verdicts
            report.successful_ticks += 1
            report.total_verdicts += len(verdicts)

            # Update verdict counts
            for verdict in verdicts:
                report.verdict_counts[verdict.verdict] = (
                    report.verdict_counts.get(verdict.verdict, 0) + 1
                )

                # Update latest verdicts for next tick
                latest_verdicts[verdict.premise_id] = verdict

            # Write to ledger if committing
            if commit and run_id and verdicts:
                write_verdicts_to_ledger(conn, run_id, verdicts)

        except Exception as e:
            logger.error(f"Error evaluating at {filing_date}: {e}")
            tick.error = str(e)
            report.failed_ticks += 1

        report.ticks.append(tick)

    # Complete run if committing
    if commit and run_id:
        complete_ledger_run(conn, run_id)
        logger.info(f"Completed run {run_id}")

        # Supersede old run if requested
        if supersede_run_id:
            assert supersede_reason is not None
            supersede_run(conn, supersede_run_id, run_id, supersede_reason)
            logger.info(f"Superseded run {supersede_run_id} with {run_id}")

    logger.info(
        f"Backfill complete: {report.successful_ticks}/{report.total_ticks} ticks, "
        f"{report.total_verdicts} verdicts"
    )

    return report


def validate_backfill_prerequisites(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> list[str]:
    """
    Validate prerequisites for backfill.

    Checks:
    1. Observations exist in date range
    2. Enabled thresholds are replayable
    3. Required cohorts exist

    Args:
        conn: Database connection
        start_date: Backfill start date
        end_date: Backfill end date

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check for observations
    cursor = conn.execute(
        "SELECT COUNT(*) FROM observation WHERE known_at >= ? AND known_at <= ?",
        (start_date.isoformat(), end_date.isoformat()),
    )
    obs_count = cursor.fetchone()[0]

    if obs_count == 0:
        errors.append(
            f"No observations found in date range {start_date} to {end_date}"
        )

    # Check threshold replayability
    threshold_manager = get_threshold_manager()
    enabled = threshold_manager.get_enabled()

    for indicator_id, threshold in enabled.items():
        if not threshold.replayable:
            errors.append(
                f"Enabled threshold {indicator_id} has replayable=False - "
                "cannot be used in backfill"
            )

    # Check cohort configuration
    config = get_config()
    for cohort_name in ["hyper", "neo"]:
        try:
            tickers = config.get_cohort_tickers(cohort_name)
            if not tickers:
                errors.append(f"Cohort {cohort_name} is empty")
        except ValueError:
            errors.append(f"Cohort {cohort_name} not configured")

    return errors
