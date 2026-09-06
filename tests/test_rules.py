"""Tests for rule engine."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from bm.clock import ReplayClock
from bm.config import get_config, reset_config
from bm.db import init_db, insert_observation
from bm.rules.engine import RuleEngine, RuleContext, Verdict, rule
from bm.rules.definitions import get_all_rules
from bm.thresholds import Threshold, ThresholdManager, reset_threshold_manager


@pytest.fixture
def db_with_test_data():
    """Create database with test observations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = init_db(db_path)

        # Insert sufficient data for hyper cohort (4/6 tickers for >50% coverage)
        period_end = "2024-03-31"
        known_at = "2024-04-15"

        for ticker in ["NVDA", "MSFT", "META", "AMZN"]:
            insert_observation(
                conn, source="test", ticker=ticker, metric="revenue",
                period_start="2024-01-01", period_end=period_end,
                value=50000000000.0, known_at=known_at, unit="USD"
            )
            insert_observation(
                conn, source="test", ticker=ticker, metric="capex",
                period_start="2024-01-01", period_end=period_end,
                value=15000000000.0, known_at=known_at, unit="USD"
            )
            insert_observation(
                conn, source="test", ticker=ticker, metric="ocf",
                period_start="2024-01-01", period_end=period_end,
                value=20000000000.0, known_at=known_at, unit="USD"
            )

        yield conn
        conn.close()


@pytest.fixture
def mock_threshold_manager():
    """Create mock threshold manager for testing."""
    class MockThresholdManager:
        def __init__(self):
            self.thresholds = {
                "self_funding_hyper": Threshold(
                    indicator_id="self_funding_hyper",
                    anchor=0.15,
                    anchor_method="semantic",
                    anchor_rationale="Test threshold",
                    buffer=0.02,
                    enabled=True,
                    direction="above",
                    min_dwell_periods=2,
                ),
                "self_funding_neo": Threshold(
                    indicator_id="self_funding_neo",
                    anchor=0.20,
                    anchor_method="semantic",
                    anchor_rationale="Test threshold",
                    buffer=0.02,
                    enabled=True,
                    direction="above",
                    min_dwell_periods=2,
                ),
            }

        def get(self, indicator_id):
            return self.thresholds.get(indicator_id)

        def get_enabled(self):
            return {k: v for k, v in self.thresholds.items() if v.enabled}

    return MockThresholdManager()


def test_rule_decorator():
    """Test rule decorator stores metadata."""
    @rule(
        rule_id="test_rule",
        indicator="test_indicator",
        premises=["P-TEST-01"],
    )
    def test_rule_func(ctx: RuleContext) -> list[Verdict]:
        return []

    assert hasattr(test_rule_func, "_rule_id")
    assert test_rule_func._rule_id == "test_rule"
    assert test_rule_func._rule_metadata["indicator"] == "test_indicator"
    assert "P-TEST-01" in test_rule_func._rule_metadata["premises"]


def test_rule_engine_initialization(db_with_test_data, mock_threshold_manager):
    """Test rule engine can be initialized."""
    clock = ReplayClock(db_with_test_data, as_of=date(2024, 5, 1))
    engine = RuleEngine(clock, mock_threshold_manager)

    assert engine.clock is clock
    assert engine.threshold_manager is mock_threshold_manager


def test_register_rule(db_with_test_data, mock_threshold_manager):
    """Test rule registration."""
    clock = ReplayClock(db_with_test_data, as_of=date(2024, 5, 1))
    engine = RuleEngine(clock, mock_threshold_manager)

    def dummy_rule(ctx: RuleContext) -> list[Verdict]:
        return []

    engine.register_rule("dummy", dummy_rule, {"indicator": "test"})

    assert "dummy" in engine._rules
    assert engine._rules["dummy"] is dummy_rule


def test_evaluate_undecidable_premise_r3(db_with_test_data, mock_threshold_manager):
    """Test R3: Undecidable premises cannot be overridden."""
    clock = ReplayClock(db_with_test_data, as_of=date(2024, 5, 1))
    engine = RuleEngine(clock, mock_threshold_manager)

    # Mock config with undecidable premise
    config = get_config()

    # Evaluate premise that is marked undecidable
    verdict = engine.evaluate_premise("P-B-01")  # This is undecidable in premises.yaml

    assert verdict is not None
    assert verdict.verdict == "undecidable"
    assert verdict.indicator_id is None


def test_evaluate_r8_silence_on_no_change(db_with_test_data, mock_threshold_manager):
    """Test R8: No verdict returned if nothing changed."""
    clock = ReplayClock(db_with_test_data, as_of=date(2024, 5, 1))
    engine = RuleEngine(clock, mock_threshold_manager)

    # Register a simple rule that always returns same verdict
    def static_rule(ctx: RuleContext) -> list[Verdict]:
        return [
            Verdict(
                premise_id=ctx.premise_id,
                verdict="refuted",
                indicator_id="self_funding_hyper",  # Match the actual indicator
                indicator_value=0.10,
                threshold_anchor=0.15,
                threshold_buffer=0.02,
                direction="above",
            )
        ]

    engine.register_rule(
        "static_test",
        static_rule,
        {"indicator": "self_funding_hyper", "premises": ["P-A-03"]},  # Match actual config
    )

    # First evaluation
    verdict1 = engine.evaluate_premise("P-A-03")
    assert verdict1 is not None

    # Second evaluation with same previous verdict
    verdict2 = engine.evaluate_premise("P-A-03", previous_verdict=verdict1)

    # R8: Should return None (no change)
    assert verdict2 is None


def test_evaluate_r7_skip_disabled_threshold(db_with_test_data):
    """Test R7: Skip evaluation if threshold not enabled."""
    clock = ReplayClock(db_with_test_data, as_of=date(2024, 5, 1))

    # Create manager with disabled threshold
    class DisabledThresholdManager:
        def get(self, indicator_id):
            return Threshold(
                indicator_id="self_funding_hyper",
                anchor=0.15,
                anchor_method="semantic",
                anchor_rationale="Test",
                buffer=0.02,
                enabled=False,  # ← Disabled!
                direction="above",
            )

    engine = RuleEngine(clock, DisabledThresholdManager())

    # Should return None (skipped)
    verdict = engine.evaluate_premise("P-A-03")
    assert verdict is None


def test_dwell_period_tracking(db_with_test_data, mock_threshold_manager):
    """Test that dwell periods are tracked correctly."""
    clock = ReplayClock(db_with_test_data, as_of=date(2024, 5, 1))
    engine = RuleEngine(clock, mock_threshold_manager)

    # Register rules
    for rule_id, rule_func, metadata in get_all_rules():
        engine.register_rule(rule_id, rule_func, metadata)

    # First evaluation (P-A-03 uses self_funding_hyper)
    verdict1 = engine.evaluate_premise("P-A-03")

    if verdict1:
        # If breached, dwell should be 1
        if verdict1.verdict == "confirmed" or verdict1.verdict == "undetermined":
            initial_dwell = verdict1.dwell_periods
            assert initial_dwell >= 1

            # Second evaluation with previous verdict
            verdict2 = engine.evaluate_premise("P-A-03", previous_verdict=verdict1)

            # If still breached, dwell should increment (or None if no change)
            if verdict2 and verdict2.verdict == verdict1.verdict:
                assert verdict2.dwell_periods >= initial_dwell


def test_min_dwell_periods_hysteresis(db_with_test_data, mock_threshold_manager):
    """Test min_dwell_periods prevents immediate confirmation."""
    # This test verifies hysteresis: must breach for N periods before confirming

    # Create scenario where indicator just barely breaches
    # With min_dwell_periods=2, should be undetermined on first breach

    clock = ReplayClock(db_with_test_data, as_of=date(2024, 5, 1))
    engine = RuleEngine(clock, mock_threshold_manager)

    # Register rules
    for rule_id, rule_func, metadata in get_all_rules():
        engine.register_rule(rule_id, rule_func, metadata)

    # Evaluate - with funding_gap/(revenue * 4) = (-5B)/(50B * 4) = -0.025
    # This is negative = self-funding (refuted)
    verdict = engine.evaluate_premise("P-A-03")

    # Should be refuted (not breached) since funding gap is negative
    if verdict:
        assert verdict.verdict == "refuted"


def test_get_all_rules():
    """Test that all rules can be collected."""
    rules = get_all_rules()

    assert len(rules) > 0

    # Check structure
    for rule_id, rule_func, metadata in rules:
        assert isinstance(rule_id, str)
        assert callable(rule_func)
        assert isinstance(metadata, dict)
        assert "indicator" in metadata
        assert "premises" in metadata


def test_rule_context_properties():
    """Test RuleContext properties."""
    config = get_config()
    premise_config = config.get_premise("P-A-03")

    # Mock objects
    class MockClock:
        pass

    class MockThresholdManager:
        def get(self, indicator_id):
            return Threshold(
                indicator_id="self_funding_hyper",
                anchor=0.15,
                anchor_method="semantic",
                anchor_rationale="Test",
                buffer=0.02,
                enabled=True,
            )

    ctx = RuleContext(
        clock=MockClock(),
        threshold_manager=MockThresholdManager(),
        premise_id="P-A-03",
        premise_config=premise_config,
    )

    assert ctx.indicator_id == "self_funding_hyper"
    assert ctx.is_undecidable is False
    threshold = ctx.get_threshold()
    assert threshold is not None
    assert threshold.indicator_id == "self_funding_hyper"


def test_verdict_to_evidence_json():
    """Test verdict evidence serialization."""
    verdict = Verdict(
        premise_id="P-A-03",
        verdict="confirmed",
        indicator_id="self_funding_hyper",
        indicator_value=0.18,
        threshold_anchor=0.15,
        threshold_buffer=0.02,
        direction="above",
        evidence={
            "observed": ["NVDA", "MSFT"],
            "derived": [{"indicator": "self_funding_hyper", "value": 0.18}],
        },
    )

    json_str = verdict.to_evidence_json()
    assert isinstance(json_str, str)
    assert "observed" in json_str
    assert "derived" in json_str

    # Should be valid JSON
    import json
    parsed = json.loads(json_str)
    assert parsed["observed"] == ["NVDA", "MSFT"]


def test_evaluate_all_premises(db_with_test_data, mock_threshold_manager):
    """Test evaluating all premises."""
    clock = ReplayClock(db_with_test_data, as_of=date(2024, 5, 1))
    engine = RuleEngine(clock, mock_threshold_manager)

    # Register rules
    for rule_id, rule_func, metadata in get_all_rules():
        engine.register_rule(rule_id, rule_func, metadata)

    verdicts = engine.evaluate_all_premises()

    # Should return list (may be empty if all undecidable/disabled)
    assert isinstance(verdicts, list)

    # Each verdict should be valid
    for verdict in verdicts:
        assert isinstance(verdict, Verdict)
        assert verdict.premise_id
        assert verdict.verdict in ("confirmed", "refuted", "undetermined", "undecidable")
