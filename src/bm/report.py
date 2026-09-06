"""
Console reporting for Bubble Monitor.

Generates human-readable reports of current premise status.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.table import Table

from bm.config import get_config
from bm.ledger import get_latest_verdicts, list_runs

logger = logging.getLogger(__name__)


@dataclass
class PremiseStatus:
    """Status of a single premise."""

    premise_id: str
    statement: str
    verdict: str | None
    indicator_id: str | None
    indicator_value: float | None
    threshold_anchor: float | None
    last_updated: str | None
    category: str


def get_premise_statuses(conn: sqlite3.Connection) -> list[PremiseStatus]:
    """
    Get current status of all premises.

    Args:
        conn: Database connection

    Returns:
        List of premise statuses
    """
    config = get_config()
    latest_verdicts = get_latest_verdicts(conn)

    statuses = []

    for premise_id in config.list_premises():
        premise_config = config.get_premise(premise_id)

        verdict_obj = latest_verdicts.get(premise_id)

        status = PremiseStatus(
            premise_id=premise_id,
            statement=premise_config["statement"],
            verdict=verdict_obj.verdict if verdict_obj else None,
            indicator_id=verdict_obj.indicator_id if verdict_obj else premise_config.get("indicator_id"),
            indicator_value=verdict_obj.indicator_value if verdict_obj else None,
            threshold_anchor=verdict_obj.threshold_anchor if verdict_obj else None,
            last_updated=None,  # TODO: get from ledger entry timestamp
            category=premise_config["category"],
        )

        statuses.append(status)

    return statuses


def print_premise_report(console: Console, conn: sqlite3.Connection) -> None:
    """
    Print premise status report to console.

    Args:
        console: Rich console
        conn: Database connection
    """
    statuses = get_premise_statuses(conn)

    # Group by category
    by_category: dict[str, list[PremiseStatus]] = {}
    for status in statuses:
        if status.category not in by_category:
            by_category[status.category] = []
        by_category[status.category].append(status)

    # Print header
    console.print()
    console.print("[bold]AI Bubble Debate Monitor - Premise Status Report[/bold]")
    console.print("=" * 80)
    console.print()

    # Get latest run info
    runs = list_runs(conn, include_superseded=False, limit=1)
    if runs:
        latest_run = runs[0]
        console.print(f"[dim]Latest run: {latest_run['id']} ({latest_run['run_type']}) "
                     f"as of {latest_run['as_of']}[/dim]")
        console.print()

    # Print each category
    category_names = {
        "A": "Self-Funding & Financial Sustainability",
        "B": "Revenue Validation",
        "C": "Market Structure",
        "D": "Commitment Concentration",
    }

    for category in sorted(by_category.keys()):
        console.print(f"[bold cyan]Category {category}: {category_names.get(category, 'Other')}[/bold cyan]")
        console.print()

        table = Table(show_header=True, box=None)
        table.add_column("ID", style="dim", width=10)
        table.add_column("Statement", width=50)
        table.add_column("Verdict", justify="center", width=12)
        table.add_column("Value", justify="right", width=10)

        for status in by_category[category]:
            # Color verdict
            if status.verdict:
                verdict_color = {
                    "confirmed": "red",
                    "refuted": "green",
                    "undetermined": "yellow",
                    "undecidable": "dim",
                }.get(status.verdict, "white")
                verdict_str = f"[{verdict_color}]{status.verdict}[/{verdict_color}]"
            else:
                verdict_str = "[dim]not evaluated[/dim]"

            # Format value
            if status.indicator_value is not None:
                value_str = f"{status.indicator_value:.4f}"
            else:
                value_str = "—"

            table.add_row(
                status.premise_id,
                status.statement[:47] + "..." if len(status.statement) > 50 else status.statement,
                verdict_str,
                value_str,
            )

        console.print(table)
        console.print()

    # Summary statistics
    console.print("[bold]Summary[/bold]")
    console.print()

    verdict_counts = {}
    for status in statuses:
        verdict = status.verdict or "not evaluated"
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    summary_table = Table(show_header=False, box=None)
    summary_table.add_column("Status", style="bold")
    summary_table.add_column("Count", justify="right")

    for verdict, count in sorted(verdict_counts.items()):
        color = {
            "confirmed": "red",
            "refuted": "green",
            "undetermined": "yellow",
            "undecidable": "dim",
            "not evaluated": "dim",
        }.get(verdict, "white")

        summary_table.add_row(
            f"[{color}]{verdict.capitalize()}[/{color}]",
            str(count),
        )

    console.print(summary_table)
    console.print()

    # Warnings
    undecidable_count = verdict_counts.get("undecidable", 0)
    not_evaluated_count = verdict_counts.get("not evaluated", 0)

    if undecidable_count > 0:
        console.print(
            f"[yellow]Note: {undecidable_count} premise(s) are semantically undecidable[/yellow]"
        )

    if not_evaluated_count > 0:
        console.print(
            f"[yellow]Note: {not_evaluated_count} premise(s) not yet evaluated "
            "(thresholds may be disabled)[/yellow]"
        )

    console.print()
