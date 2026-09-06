"""
Database management for Bubble Monitor.

SQLite connection, migration runner, and data access utilities.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from bm.config import PROJECT_ROOT, get_config

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


class DatabaseError(Exception):
    """Database operation error."""

    pass


class AppendOnlyViolation(DatabaseError):
    """Attempted to modify append-only data."""

    pass


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Create a database connection with proper configuration.

    Args:
        db_path: Optional path override. Uses config default if not provided.

    Returns:
        Configured SQLite connection.
    """
    if db_path is None:
        config = get_config()
        db_path = config.database_path

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Cursor]:
    """
    Context manager for database transactions.

    Commits on success, rolls back on exception.
    """
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """
    Run all pending migrations.

    Args:
        conn: Database connection.

    Returns:
        List of applied migration names.
    """
    applied = []

    # Get list of migration files
    if not MIGRATIONS_DIR.exists():
        logger.warning(f"Migrations directory not found: {MIGRATIONS_DIR}")
        return applied

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for migration_file in migration_files:
        migration_name = migration_file.stem

        # Check if already applied
        cursor = conn.execute(
            "SELECT 1 FROM _migration WHERE name = ?", (migration_name,)
        )
        if cursor.fetchone():
            logger.debug(f"Migration already applied: {migration_name}")
            continue

        # Apply migration
        logger.info(f"Applying migration: {migration_name}")
        sql = migration_file.read_text(encoding="utf-8")

        try:
            conn.executescript(sql)
            applied.append(migration_name)
            logger.info(f"Migration applied: {migration_name}")
        except sqlite3.Error as e:
            raise DatabaseError(f"Migration failed: {migration_name}: {e}") from e

    return applied


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Initialize database with schema.

    Args:
        db_path: Optional path override.

    Returns:
        Initialized database connection.
    """
    conn = get_connection(db_path)

    # Create migration table if it doesn't exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migration (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # Run migrations
    applied = run_migrations(conn)
    if applied:
        logger.info(f"Applied {len(applied)} migrations")

    return conn


def verify_append_only(conn: sqlite3.Connection) -> bool:
    """
    Verify append-only triggers are functioning.

    Returns:
        True if triggers are properly blocking modifications.

    Raises:
        AppendOnlyViolation: If triggers are not functioning.
    """
    # Insert test data
    with transaction(conn) as cursor:
        cursor.execute("""
            INSERT INTO ledger_run (run_type, as_of)
            VALUES ('test', datetime('now'))
        """)
        run_id = cursor.lastrowid

        cursor.execute("""
            INSERT OR IGNORE INTO premise (id, category, statement)
            VALUES ('TEST-001', 'T', 'Test premise')
        """)

        cursor.execute("""
            INSERT INTO ledger (run_id, premise_id, verdict, evidence)
            VALUES (?, 'TEST-001', 'undetermined', '{}')
        """, (run_id,))
        ledger_id = cursor.lastrowid

    # Test UPDATE block
    try:
        conn.execute(
            "UPDATE ledger SET verdict = 'confirmed' WHERE id = ?",
            (ledger_id,)
        )
        conn.commit()
        raise AppendOnlyViolation("Ledger UPDATE trigger not functioning")
    except sqlite3.IntegrityError as e:
        if "append-only" not in str(e).lower():
            raise AppendOnlyViolation(f"Unexpected error: {e}") from e
        logger.debug("Ledger UPDATE trigger verified")

    # Test DELETE block
    try:
        conn.execute("DELETE FROM ledger WHERE id = ?", (ledger_id,))
        conn.commit()
        raise AppendOnlyViolation("Ledger DELETE trigger not functioning")
    except sqlite3.IntegrityError as e:
        if "append-only" not in str(e).lower():
            raise AppendOnlyViolation(f"Unexpected error: {e}") from e
        logger.debug("Ledger DELETE trigger verified")

    # Clean up test run (via supersede, which is allowed)
    conn.execute(
        "UPDATE ledger_run SET superseded_by = id WHERE id = ?",
        (run_id,)
    )
    conn.commit()

    return True


# ============================================================================
# Data Access Functions
# ============================================================================


def insert_observation(
    conn: sqlite3.Connection,
    *,
    source: str,
    ticker: str | None,
    metric: str,
    period_start: str,
    period_end: str,
    value: float,
    known_at: str,
    unit: str | None = None,
    revision: int = 1,
    raw_payload: str | None = None,
) -> int:
    """Insert an observation record."""
    with transaction(conn) as cursor:
        cursor.execute("""
            INSERT INTO observation
                (source, ticker, metric, period_start, period_end, value, unit, known_at, revision, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (source, ticker, metric, period_start, period_end, value, unit, known_at, revision, raw_payload))
        return cursor.lastrowid  # type: ignore


def get_observations(
    conn: sqlite3.Connection,
    *,
    ticker: str | None = None,
    metric: str | None = None,
    known_at_max: str | None = None,
    current_only: bool = True,
) -> list[dict[str, Any]]:
    """
    Query observations with optional filters.

    Args:
        ticker: Filter by ticker.
        metric: Filter by metric name.
        known_at_max: Only include observations known by this date (for replay).
        current_only: If True, use observation_current view (latest revisions only).
    """
    table = "observation_current" if current_only else "observation"
    conditions = []
    params: list[Any] = []

    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker)

    if metric:
        conditions.append("metric = ?")
        params.append(metric)

    if known_at_max:
        conditions.append("known_at <= ?")
        params.append(known_at_max)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    cursor = conn.execute(
        f"SELECT * FROM {table} WHERE {where_clause} ORDER BY period_end DESC, known_at DESC",
        params,
    )

    return [dict(row) for row in cursor.fetchall()]


def create_ledger_run(
    conn: sqlite3.Connection,
    *,
    run_type: str,
    as_of: str,
    commit_hash: str | None = None,
    config_snapshot: str | None = None,
) -> int:
    """Create a new ledger run."""
    with transaction(conn) as cursor:
        cursor.execute("""
            INSERT INTO ledger_run (run_type, as_of, commit_hash, config_snapshot)
            VALUES (?, ?, ?, ?)
        """, (run_type, as_of, commit_hash, config_snapshot))
        return cursor.lastrowid  # type: ignore


def complete_ledger_run(conn: sqlite3.Connection, run_id: int) -> None:
    """Mark a ledger run as completed."""
    conn.execute(
        "UPDATE ledger_run SET completed_at = datetime('now') WHERE id = ?",
        (run_id,)
    )
    conn.commit()


def supersede_run(
    conn: sqlite3.Connection,
    old_run_id: int,
    new_run_id: int,
    reason: str,
) -> None:
    """Mark a run as superseded by another run."""
    conn.execute("""
        UPDATE ledger_run
        SET superseded_by = ?, superseded_at = datetime('now'), supersede_reason = ?
        WHERE id = ?
    """, (new_run_id, reason, old_run_id))
    conn.commit()


def insert_ledger_entry(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    premise_id: str,
    verdict: str,
    evidence: str,
    indicator_id: str | None = None,
    confidence: str | None = None,
    threshold_anchor: float | None = None,
    threshold_buffer: float | None = None,
    indicator_value: float | None = None,
    direction: str | None = None,
    dwell_periods: int | None = None,
) -> int:
    """Insert a ledger entry (append-only)."""
    with transaction(conn) as cursor:
        cursor.execute("""
            INSERT INTO ledger (
                run_id, premise_id, indicator_id, verdict, confidence, evidence,
                threshold_anchor, threshold_buffer, indicator_value, direction, dwell_periods
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, premise_id, indicator_id, verdict, confidence, evidence,
            threshold_anchor, threshold_buffer, indicator_value, direction, dwell_periods
        ))
        return cursor.lastrowid  # type: ignore


def get_effective_ledger(
    conn: sqlite3.Connection,
    *,
    premise_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Get effective ledger entries (excluding superseded runs).

    Args:
        premise_id: Filter by premise ID.
        limit: Maximum number of entries to return.
    """
    conditions = []
    params: list[Any] = []

    if premise_id:
        conditions.append("premise_id = ?")
        params.append(premise_id)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    limit_clause = f"LIMIT {limit}" if limit else ""

    cursor = conn.execute(f"""
        SELECT * FROM ledger_effective
        WHERE {where_clause}
        ORDER BY created_at DESC
        {limit_clause}
    """, params)

    return [dict(row) for row in cursor.fetchall()]


def get_runs(
    conn: sqlite3.Connection,
    *,
    include_superseded: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Get ledger runs."""
    conditions = []
    if not include_superseded:
        conditions.append("superseded_by IS NULL")

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    limit_clause = f"LIMIT {limit}" if limit else ""

    cursor = conn.execute(f"""
        SELECT * FROM ledger_run
        WHERE {where_clause}
        ORDER BY started_at DESC
        {limit_clause}
    """)

    return [dict(row) for row in cursor.fetchall()]
