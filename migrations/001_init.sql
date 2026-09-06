-- Migration 001: Initial Schema
-- Bubble Monitor Database Schema

-- Enable foreign key support
PRAGMA foreign_keys = ON;

-- ============================================================================
-- Core Tables
-- ============================================================================

-- Observations: Raw data collected from sources
CREATE TABLE IF NOT EXISTS observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                    -- e.g., 'sec_xbrl', 'fred', 'kcs_trade'
    ticker TEXT,                             -- Stock ticker (NULL for non-stock data)
    metric TEXT NOT NULL,                    -- e.g., 'capex', 'ocf', 'revenue'
    period_start TEXT NOT NULL,              -- ISO date YYYY-MM-DD
    period_end TEXT NOT NULL,                -- ISO date YYYY-MM-DD
    value REAL NOT NULL,                     -- Numeric value
    unit TEXT,                               -- e.g., 'USD', 'KRW', 'ratio'
    known_at TEXT NOT NULL,                  -- When this fact became known (filed date)
    revision INTEGER DEFAULT 1,              -- Revision number for corrections
    raw_payload TEXT,                        -- JSON of original data
    created_at TEXT DEFAULT (datetime('now')),

    UNIQUE(source, ticker, metric, period_start, period_end, revision)
);

CREATE INDEX IF NOT EXISTS idx_observation_ticker ON observation(ticker);
CREATE INDEX IF NOT EXISTS idx_observation_metric ON observation(metric);
CREATE INDEX IF NOT EXISTS idx_observation_known_at ON observation(known_at);
CREATE INDEX IF NOT EXISTS idx_observation_period ON observation(period_start, period_end);

-- Premises: Definition of debate premises (loaded from YAML, cached)
CREATE TABLE IF NOT EXISTS premise (
    id TEXT PRIMARY KEY,                     -- e.g., 'P-A-03'
    category TEXT NOT NULL,                  -- e.g., 'A', 'B', 'C', 'D'
    statement TEXT NOT NULL,                 -- The premise statement
    indicator_id TEXT,                       -- Linked indicator (NULL if undecidable)
    undecidable INTEGER DEFAULT 0,           -- 1 if semantically undecidable
    undecidable_rationale TEXT,              -- Reason for undecidability
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Ledger Runs: Each evaluation run
CREATE TABLE IF NOT EXISTS ledger_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,                  -- 'live', 'backfill', 'correction'
    as_of TEXT NOT NULL,                     -- Evaluation timestamp
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    superseded_by INTEGER,                   -- If superseded, points to new run
    superseded_at TEXT,
    supersede_reason TEXT,
    commit_hash TEXT,                        -- Git commit for reproducibility
    config_snapshot TEXT,                    -- JSON of config at run time

    FOREIGN KEY (superseded_by) REFERENCES ledger_run(id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_run_as_of ON ledger_run(as_of);
CREATE INDEX IF NOT EXISTS idx_ledger_run_superseded ON ledger_run(superseded_by);

-- Ledger: Append-only record of premise verdicts
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    premise_id TEXT NOT NULL,
    indicator_id TEXT,                       -- Indicator used for evaluation
    verdict TEXT NOT NULL,                   -- 'confirmed', 'refuted', 'undetermined', 'undecidable'
    confidence TEXT,                         -- 'high', 'medium', 'low' (optional)
    evidence TEXT NOT NULL,                  -- JSON: {observed: [...], derived: [...]}
    threshold_anchor REAL,                   -- Threshold value used
    threshold_buffer REAL,                   -- Buffer value used
    indicator_value REAL,                    -- Computed indicator value
    direction TEXT,                          -- 'above' or 'below'
    dwell_periods INTEGER,                   -- Consecutive periods in this state
    created_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (run_id) REFERENCES ledger_run(id),
    FOREIGN KEY (premise_id) REFERENCES premise(id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_run ON ledger(run_id);
CREATE INDEX IF NOT EXISTS idx_ledger_premise ON ledger(premise_id);
CREATE INDEX IF NOT EXISTS idx_ledger_verdict ON ledger(verdict);

-- Nowcast Error: Tracking prediction accuracy
CREATE TABLE IF NOT EXISTS nowcast_error (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator_id TEXT NOT NULL,
    predicted_at TEXT NOT NULL,              -- When prediction was made
    target_period_end TEXT NOT NULL,         -- Period being predicted
    predicted_value REAL NOT NULL,
    actual_value REAL,                       -- Filled in when actual becomes known
    error REAL,                              -- actual - predicted
    error_pct REAL,                          -- (actual - predicted) / actual
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_nowcast_indicator ON nowcast_error(indicator_id);
CREATE INDEX IF NOT EXISTS idx_nowcast_target ON nowcast_error(target_period_end);

-- Event Candidates: Potential events requiring human review (R9)
CREATE TABLE IF NOT EXISTS event_candidate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                    -- e.g., 'sec_fts', 'news'
    document_id TEXT,                        -- Source document identifier
    title TEXT NOT NULL,
    summary TEXT,
    detected_at TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'pending',           -- 'pending', 'approved', 'rejected'
    suggested_kind TEXT,                     -- 'interpretive', 'unobserved', etc.
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_notes TEXT,
    linked_premise_id TEXT,

    FOREIGN KEY (linked_premise_id) REFERENCES premise(id)
);

CREATE INDEX IF NOT EXISTS idx_event_status ON event_candidate(status);
CREATE INDEX IF NOT EXISTS idx_event_premise ON event_candidate(linked_premise_id);

-- Commitments: Purchase commitments from disclosures
CREATE TABLE IF NOT EXISTS commitment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    counterparty TEXT,                       -- Supplier/vendor name if disclosed
    commitment_type TEXT NOT NULL,           -- 'purchase', 'lease', 'other'
    total_amount REAL NOT NULL,
    currency TEXT DEFAULT 'USD',
    period_start TEXT,                       -- Commitment period start
    period_end TEXT,                         -- Commitment period end
    filed_at TEXT NOT NULL,                  -- When disclosed
    source_document TEXT,                    -- Filing reference
    known_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_commitment_ticker ON commitment(ticker);
CREATE INDEX IF NOT EXISTS idx_commitment_known_at ON commitment(known_at);

-- ============================================================================
-- Views
-- ============================================================================

-- Current observations: Latest revision for each observation
CREATE VIEW IF NOT EXISTS observation_current AS
SELECT o.*
FROM observation o
INNER JOIN (
    SELECT source, ticker, metric, period_start, period_end, MAX(revision) as max_rev
    FROM observation
    GROUP BY source, ticker, metric, period_start, period_end
) latest ON o.source = latest.source
    AND (o.ticker = latest.ticker OR (o.ticker IS NULL AND latest.ticker IS NULL))
    AND o.metric = latest.metric
    AND o.period_start = latest.period_start
    AND o.period_end = latest.period_end
    AND o.revision = latest.max_rev;

-- Effective ledger: Excludes entries from superseded runs
CREATE VIEW IF NOT EXISTS ledger_effective AS
SELECT l.*
FROM ledger l
INNER JOIN ledger_run r ON l.run_id = r.id
WHERE r.superseded_by IS NULL;

-- ============================================================================
-- Append-Only Triggers (R5)
-- ============================================================================

-- Prevent UPDATE on ledger
CREATE TRIGGER IF NOT EXISTS ledger_no_update
BEFORE UPDATE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'Ledger is append-only: UPDATE not allowed (R5)');
END;

-- Prevent DELETE on ledger
CREATE TRIGGER IF NOT EXISTS ledger_no_delete
BEFORE DELETE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'Ledger is append-only: DELETE not allowed (R5)');
END;

-- Prevent DELETE on observation (corrections use new revision)
CREATE TRIGGER IF NOT EXISTS observation_no_delete
BEFORE DELETE ON observation
BEGIN
    SELECT RAISE(ABORT, 'Observation is append-only: DELETE not allowed. Use new revision for corrections.');
END;

-- ============================================================================
-- Migration Tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS _migration (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO _migration (id, name) VALUES (1, '001_init');
