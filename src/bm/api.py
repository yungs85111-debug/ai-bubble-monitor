"""
Read-only API for Bubble Monitor.

FastAPI-based REST API for accessing ledger, indicators, and premises.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bm.config import get_config
from bm.db import get_connection
from bm.ledger import (
    get_latest_verdicts,
    list_ledger_entries,
    list_runs,
)
from bm.nowcast import get_nowcast_errors, get_uncertainty_band
from bm.report import get_premise_statuses

logger = logging.getLogger(__name__)


# Response models
class PremiseResponse(BaseModel):
    """Premise information."""

    premise_id: str
    statement: str
    category: str
    indicator_id: str | None
    undecidable: bool
    undecidable_rationale: str | None


class VerdictResponse(BaseModel):
    """Verdict information."""

    premise_id: str
    verdict: str
    indicator_id: str | None
    indicator_value: float | None
    threshold_anchor: float | None
    threshold_buffer: float | None
    direction: str | None
    dwell_periods: int
    confidence: str | None
    evidence: dict[str, Any]


class LedgerEntryResponse(BaseModel):
    """Ledger entry information."""

    id: int
    run_id: int
    premise_id: str
    indicator_id: str | None
    verdict: str
    confidence: str | None
    threshold_anchor: float | None
    threshold_buffer: float | None
    indicator_value: float | None
    direction: str | None
    dwell_periods: int | None
    created_at: str


class RunResponse(BaseModel):
    """Evaluation run information."""

    id: int
    run_type: str
    as_of: str
    started_at: str
    completed_at: str | None
    superseded_by: int | None
    supersede_reason: str | None
    commit_hash: str | None


class CruxResponse(BaseModel):
    """Crux (key issue) information."""

    premise_id: str
    statement: str
    kind: str  # 'interpretive', 'unobserved', 'observed_pending', 'verified'
    verdict: str | None
    indicator_id: str | None
    indicator_value: float | None
    last_updated: str | None
    origin: str  # Data source attribution


class IndicatorResponse(BaseModel):
    """Indicator information."""

    indicator_id: str
    latest_value: float | None
    latest_period: str | None
    threshold_anchor: float | None
    threshold_buffer: float | None
    enabled: bool
    direction: str | None


class NowcastResponse(BaseModel):
    """Nowcast error information."""

    id: int
    indicator_id: str
    target_period_end: str
    predicted_value: float
    actual_value: float | None
    error: float | None
    mae: float | None
    predicted_at: str


class UncertaintyBandResponse(BaseModel):
    """Uncertainty band information."""

    indicator_id: str
    period_end: str
    predicted_value: float
    lower_bound: float | None
    upper_bound: float | None
    mae: float | None
    sample_count: int


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="AI Bubble Monitor API",
        version="1.0.0",
        description="Read-only API for accessing AI bubble debate monitoring data",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["*"],
    )

    config = get_config()

    @app.get("/")
    def root():
        """Root endpoint."""
        return {
            "name": "AI Bubble Monitor API",
            "version": "1.0.0",
            "endpoints": [
                "/v1/premises",
                "/v1/cruxes",
                "/v1/indicators",
                "/v1/ledger",
                "/v1/runs",
                "/v1/nowcasts",
            ],
        }

    @app.get("/v1/premises", response_model=list[PremiseResponse])
    def list_premises(
        category: str | None = Query(None, description="Filter by category (A, B, C, D)")
    ):
        """
        List all premises.

        Args:
            category: Optional category filter

        Returns:
            List of premises
        """
        premises = []

        for premise_id in config.list_premises():
            premise_config = config.get_premise(premise_id)

            # Filter by category if specified
            if category and premise_config["category"] != category:
                continue

            premises.append(
                PremiseResponse(
                    premise_id=premise_id,
                    statement=premise_config["statement"],
                    category=premise_config["category"],
                    indicator_id=premise_config.get("indicator_id"),
                    undecidable=premise_config.get("undecidable", False),
                    undecidable_rationale=premise_config.get("undecidable_rationale"),
                )
            )

        return premises

    @app.get("/v1/cruxes", response_model=list[CruxResponse])
    def list_cruxes(
        kind: str | None = Query(
            None,
            description="Filter by kind: interpretive, unobserved, observed_pending, verified",
        )
    ):
        """
        List cruxes (key issues in the debate).

        Cruxes are categorized as:
        - interpretive: Semantically undecidable premises
        - unobserved: No indicator data available
        - observed_pending: Indicator exists but no verdict yet
        - verified: Has verdict from ledger

        Args:
            kind: Optional kind filter

        Returns:
            List of cruxes with origin attribution
        """
        conn = get_connection(config.database_path)

        try:
            latest_verdicts = get_latest_verdicts(conn)
            cruxes = []

            for premise_id in config.list_premises():
                premise_config = config.get_premise(premise_id)
                verdict_obj = latest_verdicts.get(premise_id)

                # Determine kind
                if premise_config.get("undecidable", False):
                    crux_kind = "interpretive"
                elif premise_config.get("indicator_id") is None:
                    crux_kind = "unobserved"
                elif verdict_obj is None:
                    crux_kind = "observed_pending"
                else:
                    crux_kind = "verified"

                # Filter by kind if specified
                if kind and crux_kind != kind:
                    continue

                # Determine origin (data source attribution)
                indicator_id = premise_config.get("indicator_id")
                if indicator_id:
                    # Map indicator to data source
                    if "self_funding" in indicator_id:
                        origin = "SEC EDGAR (XBRL)"
                    elif "supply_chain" in indicator_id:
                        origin = "Korea Customs Service / TWSE"
                    elif "offbalance" in indicator_id:
                        origin = "SEC EDGAR (Full-text)"
                    else:
                        origin = "Unknown"
                else:
                    origin = "N/A"

                cruxes.append(
                    CruxResponse(
                        premise_id=premise_id,
                        statement=premise_config["statement"],
                        kind=crux_kind,
                        verdict=verdict_obj.verdict if verdict_obj else None,
                        indicator_id=indicator_id,
                        indicator_value=(
                            verdict_obj.indicator_value if verdict_obj else None
                        ),
                        last_updated=None,  # TODO: Get from ledger timestamp
                        origin=origin,
                    )
                )

            return cruxes

        finally:
            conn.close()

    @app.get("/v1/indicators", response_model=list[IndicatorResponse])
    def list_indicators():
        """
        List all indicators with latest values.

        Returns:
            List of indicators
        """
        from bm.thresholds import get_threshold_manager

        conn = get_connection(config.database_path)

        try:
            latest_verdicts = get_latest_verdicts(conn)
            threshold_manager = get_threshold_manager()

            indicators = []

            for indicator_id, threshold in threshold_manager.thresholds.items():
                # Find latest verdict using this indicator
                latest_value = None
                latest_period = None

                for verdict in latest_verdicts.values():
                    if verdict.indicator_id == indicator_id:
                        latest_value = verdict.indicator_value
                        # TODO: Get period from verdict metadata
                        break

                indicators.append(
                    IndicatorResponse(
                        indicator_id=indicator_id,
                        latest_value=latest_value,
                        latest_period=latest_period,
                        threshold_anchor=threshold.anchor,
                        threshold_buffer=threshold.buffer,
                        enabled=threshold.enabled,
                        direction=threshold.direction,
                    )
                )

            return indicators

        finally:
            conn.close()

    @app.get("/v1/ledger", response_model=list[LedgerEntryResponse])
    def get_ledger(
        premise_id: str | None = Query(None, description="Filter by premise ID"),
        limit: int = Query(50, description="Maximum entries to return", le=1000),
        include_superseded: bool = Query(
            False, description="Include entries from superseded runs"
        ),
    ):
        """
        Get ledger entries.

        Args:
            premise_id: Optional premise filter
            limit: Maximum entries
            include_superseded: Include superseded runs

        Returns:
            List of ledger entries
        """
        conn = get_connection(config.database_path)

        try:
            entries = list_ledger_entries(
                conn,
                premise_id=premise_id,
                limit=limit,
                include_superseded=include_superseded,
            )

            return [
                LedgerEntryResponse(
                    id=entry.id,
                    run_id=entry.run_id,
                    premise_id=entry.premise_id,
                    indicator_id=entry.indicator_id,
                    verdict=entry.verdict,
                    confidence=entry.confidence,
                    threshold_anchor=entry.threshold_anchor,
                    threshold_buffer=entry.threshold_buffer,
                    indicator_value=entry.indicator_value,
                    direction=entry.direction,
                    dwell_periods=entry.dwell_periods,
                    created_at=entry.created_at,
                )
                for entry in entries
            ]

        finally:
            conn.close()

    @app.get("/v1/runs", response_model=list[RunResponse])
    def get_runs(
        include_superseded: bool = Query(
            False, description="Include superseded runs"
        ),
        limit: int = Query(20, description="Maximum runs to return", le=100),
    ):
        """
        Get evaluation runs.

        Args:
            include_superseded: Include superseded runs
            limit: Maximum runs

        Returns:
            List of evaluation runs
        """
        conn = get_connection(config.database_path)

        try:
            runs = list_runs(conn, include_superseded=include_superseded, limit=limit)

            return [
                RunResponse(
                    id=run["id"],
                    run_type=run["run_type"],
                    as_of=run["as_of"],
                    started_at=run["started_at"],
                    completed_at=run.get("completed_at"),
                    superseded_by=run.get("superseded_by"),
                    supersede_reason=run.get("supersede_reason"),
                    commit_hash=run.get("commit_hash"),
                )
                for run in runs
            ]

        finally:
            conn.close()

    @app.get("/v1/nowcasts", response_model=list[NowcastResponse])
    def get_nowcasts(
        indicator_id: str | None = Query(None, description="Filter by indicator"),
        limit: int = Query(50, description="Maximum records to return", le=1000),
    ):
        """
        Get nowcast error records.

        Args:
            indicator_id: Optional indicator filter
            limit: Maximum records

        Returns:
            List of nowcast records
        """
        conn = get_connection(config.database_path)

        try:
            records = get_nowcast_errors(conn, indicator_id=indicator_id, limit=limit)

            return [
                NowcastResponse(
                    id=record.id,
                    indicator_id=record.indicator_id,
                    target_period_end=record.target_period_end.isoformat(),
                    predicted_value=record.predicted_value,
                    actual_value=record.actual_value,
                    error=record.error,
                    mae=record.mae,
                    predicted_at=record.predicted_at.isoformat(),
                )
                for record in records
            ]

        finally:
            conn.close()

    @app.get(
        "/v1/nowcasts/{indicator_id}/{period_end}/band",
        response_model=UncertaintyBandResponse,
    )
    def get_band(indicator_id: str, period_end: str):
        """
        Get uncertainty band for a nowcast.

        Args:
            indicator_id: Indicator identifier
            period_end: Period end date (YYYY-MM-DD)

        Returns:
            Uncertainty band information
        """
        from datetime import date as date_parse

        conn = get_connection(config.database_path)

        try:
            period_date = date_parse.fromisoformat(period_end)
            band = get_uncertainty_band(conn, indicator_id, period_date)

            if band is None:
                raise HTTPException(status_code=404, detail="Nowcast not found")

            return UncertaintyBandResponse(
                indicator_id=band.indicator_id,
                period_end=band.period_end.isoformat(),
                predicted_value=band.predicted_value,
                lower_bound=band.lower_bound,
                upper_bound=band.upper_bound,
                mae=band.mae,
                sample_count=band.sample_count,
            )

        finally:
            conn.close()

    # IMPORTANT: No aggregate score endpoint (R1)
    # The API intentionally does not provide any combined/weighted score
    # Users must evaluate individual premises independently

    return app


app = create_app()
