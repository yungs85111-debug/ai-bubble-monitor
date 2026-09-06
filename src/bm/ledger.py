"""
Ledger management for Bubble Monitor.

High-level API for ledger operations and evidence validation.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bm.db import (
    create_ledger_run,
    complete_ledger_run,
    insert_ledger_entry,
    get_effective_ledger,
    get_runs,
    supersede_run,
)
from bm.rules.engine import Verdict

logger = logging.getLogger(__name__)


class LedgerError(Exception):
    """Ledger operation error."""

    pass


@dataclass
class LedgerEntry:
    """Ledger entry data model."""

    id: int
    run_id: int
    premise_id: str
    indicator_id: str | None
    verdict: str
    confidence: str | None
    evidence: dict[str, Any]
    threshold_anchor: float | None
    threshold_buffer: float | None
    indicator_value: float | None
    direction: str | None
    dwell_periods: int | None
    created_at: str

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> LedgerEntry:
        """Create LedgerEntry from database row."""
        # Parse evidence JSON
        evidence = {}
        if row.get("evidence"):
            try:
                evidence = json.loads(row["evidence"])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse evidence: {e}")

        return cls(
            id=row["id"],
            run_id=row["run_id"],
            premise_id=row["premise_id"],
            indicator_id=row.get("indicator_id"),
            verdict=row["verdict"],
            confidence=row.get("confidence"),
            evidence=evidence,
            threshold_anchor=row.get("threshold_anchor"),
            threshold_buffer=row.get("threshold_buffer"),
            indicator_value=row.get("indicator_value"),
            direction=row.get("direction"),
            dwell_periods=row.get("dwell_periods"),
            created_at=row["created_at"],
        )


def validate_evidence(evidence: dict[str, Any]) -> list[str]:
    """
    Validate evidence structure per §4.2.

    Evidence format:
    {
        "observed": [...],  # List of observation references
        "derived": [...],   # List of computed indicator references
        "rationale": "...",  # Optional rationale text
    }

    Args:
        evidence: Evidence dictionary

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    if not isinstance(evidence, dict):
        errors.append("Evidence must be a dictionary")
        return errors

    # Check required keys
    if "observed" not in evidence:
        errors.append("Evidence missing 'observed' key")

    if "derived" not in evidence:
        errors.append("Evidence missing 'derived' key")

    # Validate observed
    if "observed" in evidence:
        if not isinstance(evidence["observed"], list):
            errors.append("'observed' must be a list")

    # Validate derived
    if "derived" in evidence:
        if not isinstance(evidence["derived"], list):
            errors.append("'derived' must be a list")

    return errors


def write_verdicts_to_ledger(
    conn: sqlite3.Connection,
    run_id: int,
    verdicts: list[Verdict],
) -> int:
    """
    Write verdicts to ledger.

    Args:
        conn: Database connection
        run_id: Ledger run ID
        verdicts: List of verdicts to write

    Returns:
        Number of entries written
    """
    count = 0

    for verdict in verdicts:
        # Validate evidence
        errors = validate_evidence(verdict.evidence)
        if errors:
            logger.error(f"Invalid evidence for {verdict.premise_id}: {errors}")
            raise LedgerError(f"Evidence validation failed: {errors}")

        # Write to ledger
        insert_ledger_entry(
            conn,
            run_id=run_id,
            premise_id=verdict.premise_id,
            indicator_id=verdict.indicator_id,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            evidence=verdict.to_evidence_json(),
            threshold_anchor=verdict.threshold_anchor,
            threshold_buffer=verdict.threshold_buffer,
            indicator_value=verdict.indicator_value,
            direction=verdict.direction,
            dwell_periods=verdict.dwell_periods,
        )
        count += 1

    logger.info(f"Wrote {count} verdicts to ledger (run_id={run_id})")
    return count


def get_latest_verdicts(
    conn: sqlite3.Connection,
) -> dict[str, Verdict]:
    """
    Get latest verdict for each premise from effective ledger.

    Args:
        conn: Database connection

    Returns:
        Dict mapping premise_id to latest Verdict
    """
    # Get all effective ledger entries
    entries = get_effective_ledger(conn, limit=1000)  # Reasonable limit

    # Group by premise and keep latest
    latest: dict[str, dict[str, Any]] = {}

    for entry_dict in entries:
        premise_id = entry_dict["premise_id"]

        # Compare by created_at (latest wins)
        if premise_id not in latest:
            latest[premise_id] = entry_dict
        else:
            if entry_dict["created_at"] > latest[premise_id]["created_at"]:
                latest[premise_id] = entry_dict

    # Convert to Verdict objects
    verdicts: dict[str, Verdict] = {}

    for premise_id, entry_dict in latest.items():
        # Parse evidence
        evidence = {}
        if entry_dict.get("evidence"):
            try:
                evidence = json.loads(entry_dict["evidence"])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse evidence for {premise_id}")

        verdicts[premise_id] = Verdict(
            premise_id=premise_id,
            verdict=entry_dict["verdict"],
            indicator_id=entry_dict.get("indicator_id"),
            indicator_value=entry_dict.get("indicator_value"),
            threshold_anchor=entry_dict.get("threshold_anchor"),
            threshold_buffer=entry_dict.get("threshold_buffer"),
            direction=entry_dict.get("direction"),
            dwell_periods=entry_dict.get("dwell_periods", 0),
            confidence=entry_dict.get("confidence"),
            evidence=evidence,
        )

    return verdicts


def create_evaluation_run(
    conn: sqlite3.Connection,
    run_type: str,
    as_of: str,
    commit_hash: str | None = None,
) -> int:
    """
    Create a new evaluation run.

    Args:
        conn: Database connection
        run_type: Type of run ('live', 'backfill', 'correction')
        as_of: Evaluation timestamp (ISO format)
        commit_hash: Optional git commit hash for reproducibility

    Returns:
        Run ID
    """
    # Create config snapshot (optional, for reproducibility)
    config_snapshot = None  # TODO: serialize config if needed

    run_id = create_ledger_run(
        conn,
        run_type=run_type,
        as_of=as_of,
        commit_hash=commit_hash,
        config_snapshot=config_snapshot,
    )

    logger.info(f"Created {run_type} run {run_id} (as_of={as_of})")
    return run_id


def list_ledger_entries(
    conn: sqlite3.Connection,
    premise_id: str | None = None,
    limit: int = 50,
    include_superseded: bool = False,
) -> list[LedgerEntry]:
    """
    List ledger entries.

    Args:
        conn: Database connection
        premise_id: Filter by premise ID (optional)
        limit: Maximum entries to return
        include_superseded: If True, include entries from superseded runs

    Returns:
        List of ledger entries
    """
    if include_superseded:
        # Query from ledger table directly
        conditions = []
        params: list[Any] = []

        if premise_id:
            conditions.append("premise_id = ?")
            params.append(premise_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor = conn.execute(f"""
            SELECT * FROM ledger
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT {limit}
        """, params)

        rows = [dict(row) for row in cursor.fetchall()]
    else:
        # Use effective ledger
        rows = get_effective_ledger(conn, premise_id=premise_id, limit=limit)

    return [LedgerEntry.from_db_row(row) for row in rows]


def list_runs(
    conn: sqlite3.Connection,
    include_superseded: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    List evaluation runs.

    Args:
        conn: Database connection
        include_superseded: If True, include superseded runs
        limit: Maximum runs to return

    Returns:
        List of run dictionaries
    """
    return get_runs(conn, include_superseded=include_superseded, limit=limit)
