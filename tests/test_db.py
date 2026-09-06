"""Tests for database module."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from bm.db import (
    AppendOnlyViolation,
    get_connection,
    init_db,
    insert_ledger_entry,
    insert_observation,
    create_ledger_run,
    verify_append_only,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)
        yield conn
        conn.close()


def test_init_db_creates_tables(temp_db):
    """Test that init_db creates all required tables."""
    cursor = temp_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = {row[0] for row in cursor.fetchall()}

    assert "observation" in tables
    assert "premise" in tables
    assert "ledger_run" in tables
    assert "ledger" in tables
    assert "nowcast_error" in tables
    assert "event_candidate" in tables
    assert "commitment" in tables
    assert "_migration" in tables


def test_init_db_creates_views(temp_db):
    """Test that init_db creates required views."""
    cursor = temp_db.execute(
        "SELECT name FROM sqlite_master WHERE type='view'"
    )
    views = {row[0] for row in cursor.fetchall()}

    assert "observation_current" in views
    assert "ledger_effective" in views


def test_ledger_update_blocked(temp_db):
    """Test that ledger UPDATE is blocked by trigger (R5)."""
    # Setup: create a run and ledger entry
    run_id = create_ledger_run(
        temp_db, run_type="test", as_of="2024-01-01"
    )

    temp_db.execute("""
        INSERT OR IGNORE INTO premise (id, category, statement)
        VALUES ('TEST-001', 'T', 'Test premise')
    """)
    temp_db.commit()

    entry_id = insert_ledger_entry(
        temp_db,
        run_id=run_id,
        premise_id="TEST-001",
        verdict="undetermined",
        evidence="{}",
    )

    # Attempt UPDATE - should fail
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        temp_db.execute(
            "UPDATE ledger SET verdict = 'confirmed' WHERE id = ?",
            (entry_id,)
        )

    assert "append-only" in str(exc_info.value).lower()


def test_ledger_delete_blocked(temp_db):
    """Test that ledger DELETE is blocked by trigger (R5)."""
    run_id = create_ledger_run(
        temp_db, run_type="test", as_of="2024-01-01"
    )

    temp_db.execute("""
        INSERT OR IGNORE INTO premise (id, category, statement)
        VALUES ('TEST-002', 'T', 'Test premise')
    """)
    temp_db.commit()

    entry_id = insert_ledger_entry(
        temp_db,
        run_id=run_id,
        premise_id="TEST-002",
        verdict="undetermined",
        evidence="{}",
    )

    # Attempt DELETE - should fail
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        temp_db.execute("DELETE FROM ledger WHERE id = ?", (entry_id,))

    assert "append-only" in str(exc_info.value).lower()


def test_observation_delete_blocked(temp_db):
    """Test that observation DELETE is blocked by trigger."""
    obs_id = insert_observation(
        temp_db,
        source="test",
        ticker="TEST",
        metric="revenue",
        period_start="2024-01-01",
        period_end="2024-03-31",
        value=1000000.0,
        known_at="2024-04-15",
    )

    # Attempt DELETE - should fail
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        temp_db.execute("DELETE FROM observation WHERE id = ?", (obs_id,))

    assert "append-only" in str(exc_info.value).lower()


def test_verify_append_only(temp_db):
    """Test that verify_append_only works correctly."""
    result = verify_append_only(temp_db)
    assert result is True


def test_observation_revisions(temp_db):
    """Test that observation revisions work correctly."""
    # Insert original
    insert_observation(
        temp_db,
        source="test",
        ticker="TEST",
        metric="revenue",
        period_start="2024-01-01",
        period_end="2024-03-31",
        value=1000000.0,
        known_at="2024-04-15",
        revision=1,
    )

    # Insert correction (revision 2)
    insert_observation(
        temp_db,
        source="test",
        ticker="TEST",
        metric="revenue",
        period_start="2024-01-01",
        period_end="2024-03-31",
        value=1100000.0,  # Corrected value
        known_at="2024-05-01",
        revision=2,
    )

    # Query current view - should only see revision 2
    cursor = temp_db.execute("""
        SELECT value FROM observation_current
        WHERE ticker = 'TEST' AND metric = 'revenue'
    """)
    result = cursor.fetchone()
    assert result[0] == 1100000.0
