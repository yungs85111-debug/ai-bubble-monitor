"""
Rule engine core for Bubble Monitor.

Executes rules to evaluate premises against indicators and thresholds.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from bm.clock import ReplayClock
from bm.config import get_config
from bm.models import IndicatorResult
from bm.thresholds import Threshold, ThresholdManager

logger = logging.getLogger(__name__)


@dataclass
class Verdict:
    """
    Verdict for a premise evaluation.

    Possible verdicts:
    - confirmed: Premise is supported by evidence
    - refuted: Premise is contradicted by evidence
    - undetermined: Insufficient data or inconclusive
    - undecidable: Premise is semantically undecidable (R3)
    """

    premise_id: str
    verdict: str  # 'confirmed', 'refuted', 'undetermined', 'undecidable'
    indicator_id: str | None
    indicator_value: float | None
    threshold_anchor: float | None
    threshold_buffer: float | None
    direction: str | None
    dwell_periods: int = 0
    confidence: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_evidence_json(self) -> str:
        """
        Serialize evidence for ledger storage.

        Format per §4.2:
        {
            "observed": [...],  # Observation IDs or references
            "derived": [...],   # Computed indicator references
        }
        """
        return json.dumps(self.evidence, sort_keys=True)


@dataclass
class RuleContext:
    """
    Context for rule execution.

    Provides access to:
    - ReplayClock for data access (with lookahead guard)
    - ThresholdManager for threshold configurations
    - Premise configuration
    - Previous verdict for change detection (R8)
    """

    clock: ReplayClock
    threshold_manager: ThresholdManager
    premise_id: str
    premise_config: dict[str, Any]
    previous_verdict: Verdict | None = None

    @property
    def indicator_id(self) -> str | None:
        """Get indicator ID for this premise."""
        return self.premise_config.get("indicator_id")

    @property
    def is_undecidable(self) -> bool:
        """Check if premise is semantically undecidable (R3)."""
        return self.premise_config.get("undecidable", False)

    def get_threshold(self) -> Threshold | None:
        """Get threshold for this premise's indicator."""
        if not self.indicator_id:
            return None
        return self.threshold_manager.get(self.indicator_id)


class RuleEngine:
    """
    Rule engine for evaluating premises.

    Features:
    - Executes rules to generate verdicts
    - Enforces R3 (undecidable immutability)
    - Enforces R7 (skip inactive indicators)
    - Enforces R8 (silence on no change)
    - Enforces R10 (expiry on missing data)
    - Tracks dwell periods for hysteresis
    """

    def __init__(
        self,
        clock: ReplayClock,
        threshold_manager: ThresholdManager,
    ):
        self.clock = clock
        self.threshold_manager = threshold_manager
        self.config = get_config()
        self._rules: dict[str, Callable[[RuleContext], list[Verdict]]] = {}
        self._rule_metadata: dict[str, dict[str, Any]] = {}

    def register_rule(
        self,
        rule_id: str,
        rule_func: Callable[[RuleContext], list[Verdict]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Register a rule function.

        Args:
            rule_id: Unique rule identifier
            rule_func: Rule function that takes RuleContext and returns list of Verdicts
            metadata: Optional metadata (indicator, premises, etc.)
        """
        self._rules[rule_id] = rule_func
        self._rule_metadata[rule_id] = metadata or {}
        logger.debug(f"Registered rule: {rule_id}")

    def evaluate_premise(
        self,
        premise_id: str,
        previous_verdict: Verdict | None = None,
    ) -> Verdict | None:
        """
        Evaluate a single premise.

        Args:
            premise_id: Premise to evaluate
            previous_verdict: Previous verdict for change detection (R8)

        Returns:
            Verdict or None if no change (R8: silence on no change)
        """
        # Load premise config
        premise_config = self.config.get_premise(premise_id)

        # R3: Undecidable premises cannot be overridden
        if premise_config.get("undecidable", False):
            logger.debug(f"{premise_id}: Undecidable (R3)")
            verdict = Verdict(
                premise_id=premise_id,
                verdict="undecidable",
                indicator_id=None,
                indicator_value=None,
                threshold_anchor=None,
                threshold_buffer=None,
                direction=None,
                evidence={
                    "observed": [],
                    "derived": [],
                    "rationale": premise_config.get("undecidable_rationale", ""),
                },
                metadata={"reason": "semantic_undecidability", "rule": "R3"},
            )

            # R8: Check for change
            if previous_verdict and previous_verdict.verdict == "undecidable":
                logger.debug(f"{premise_id}: No change (R8)")
                return None

            return verdict

        # Get indicator
        indicator_id = premise_config.get("indicator_id")
        if not indicator_id:
            logger.warning(f"{premise_id}: No indicator configured")
            return Verdict(
                premise_id=premise_id,
                verdict="undetermined",
                indicator_id=None,
                indicator_value=None,
                threshold_anchor=None,
                threshold_buffer=None,
                direction=None,
                evidence={"observed": [], "derived": []},
                metadata={"reason": "no_indicator"},
            )

        # Get threshold
        threshold = self.threshold_manager.get(indicator_id)
        if not threshold:
            logger.warning(f"{premise_id}: No threshold for {indicator_id}")
            return Verdict(
                premise_id=premise_id,
                verdict="undetermined",
                indicator_id=indicator_id,
                indicator_value=None,
                threshold_anchor=None,
                threshold_buffer=None,
                direction=None,
                evidence={"observed": [], "derived": []},
                metadata={"reason": "no_threshold"},
            )

        # R7: Skip if threshold not enabled
        if not threshold.enabled:
            logger.debug(f"{premise_id}: Threshold not enabled (R7)")
            return None

        # Create context
        context = RuleContext(
            clock=self.clock,
            threshold_manager=self.threshold_manager,
            premise_id=premise_id,
            premise_config=premise_config,
            previous_verdict=previous_verdict,
        )

        # Find and execute rule
        rule_func = self._find_rule_for_premise(premise_id, indicator_id)
        if not rule_func:
            logger.warning(f"{premise_id}: No rule found for {indicator_id}")
            return Verdict(
                premise_id=premise_id,
                verdict="undetermined",
                indicator_id=indicator_id,
                indicator_value=None,
                threshold_anchor=None,
                threshold_buffer=None,
                direction=None,
                evidence={"observed": [], "derived": []},
                metadata={"reason": "no_rule"},
            )

        # Execute rule
        verdicts = rule_func(context)

        if not verdicts:
            # R8: No verdict = no change
            logger.debug(f"{premise_id}: Rule returned no verdict (R8)")
            return None

        # Take first verdict (rules should return list for future multi-verdict support)
        verdict = verdicts[0]

        # R8: Check if verdict changed
        if previous_verdict and self._verdicts_equal(verdict, previous_verdict):
            logger.debug(f"{premise_id}: No change (R8)")
            return None

        return verdict

    def _find_rule_for_premise(
        self,
        premise_id: str,
        indicator_id: str,
    ) -> Callable[[RuleContext], list[Verdict]] | None:
        """Find rule function for a premise/indicator."""
        # Look for rule with matching indicator
        for rule_id, metadata in self._rule_metadata.items():
            if metadata.get("indicator") == indicator_id:
                # Check if this premise is in the rule's premise list
                premises = metadata.get("premises", [])
                if premise_id in premises:
                    return self._rules[rule_id]

        return None

    def _verdicts_equal(self, v1: Verdict, v2: Verdict) -> bool:
        """
        Check if two verdicts are equal (for R8: silence on no change).

        Only compares verdict type and indicator value, not evidence details.
        """
        return (
            v1.verdict == v2.verdict
            and v1.indicator_value == v2.indicator_value
            and v1.threshold_anchor == v2.threshold_anchor
        )

    def evaluate_all_premises(
        self,
        previous_verdicts: dict[str, Verdict] | None = None,
    ) -> list[Verdict]:
        """
        Evaluate all configured premises.

        Args:
            previous_verdicts: Dict mapping premise_id to previous verdict (for R8)

        Returns:
            List of verdicts (only includes changed verdicts per R8)
        """
        previous_verdicts = previous_verdicts or {}
        verdicts = []

        for premise_id in self.config.list_premises():
            previous = previous_verdicts.get(premise_id)
            verdict = self.evaluate_premise(premise_id, previous)

            if verdict:
                verdicts.append(verdict)

        logger.info(f"Evaluated {len(self.config.list_premises())} premises, "
                   f"{len(verdicts)} changed")

        return verdicts


# Rule decorator for easy rule registration
def rule(
    rule_id: str,
    indicator: str,
    premises: list[str],
    **metadata: Any,
) -> Callable[[Callable[[RuleContext], list[Verdict]]], Callable[[RuleContext], list[Verdict]]]:
    """
    Decorator for rule functions.

    Usage:
        @rule(
            rule_id="self_funding_threshold",
            indicator="self_funding_hyper",
            premises=["P-A-03"],
        )
        def self_funding_threshold(ctx: RuleContext) -> list[Verdict]:
            # Rule logic here
            return [verdict]
    """
    def decorator(
        func: Callable[[RuleContext], list[Verdict]]
    ) -> Callable[[RuleContext], list[Verdict]]:
        # Store metadata on function for later registration
        func._rule_id = rule_id  # type: ignore
        func._rule_metadata = {  # type: ignore
            "indicator": indicator,
            "premises": premises,
            **metadata,
        }
        return func

    return decorator
