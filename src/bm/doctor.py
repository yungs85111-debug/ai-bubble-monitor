"""
Doctor command for Bubble Monitor.

Checks tag availability and data quality for cohort tickers.
"""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.table import Table

from bm.collectors.sec_xbrl import SecXbrlCollector, TAGS_SELF_FUNDING, TAGS_OFFBALANCE
from bm.config import get_config

logger = logging.getLogger(__name__)


def check_tag_availability(
    collector: SecXbrlCollector,
    tickers: list[str],
) -> dict[str, dict[str, list[str]]]:
    """
    Check which XBRL tags are available for each ticker.

    Args:
        collector: SEC XBRL collector instance
        tickers: List of tickers to check

    Returns:
        Dict mapping ticker to dict of metric -> available tags
    """
    availability: dict[str, dict[str, list[str]]] = {}

    for ticker in tickers:
        try:
            logger.info(f"Checking {ticker}...")
            tags = collector.get_available_tags(ticker)
            availability[ticker] = tags
        except Exception as e:
            logger.error(f"Failed to check {ticker}: {e}")
            availability[ticker] = {}

    return availability


def print_availability_table(
    console: Console,
    availability: dict[str, dict[str, list[str]]],
    metric_groups: dict[str, str],
) -> None:
    """
    Print availability table to console.

    Args:
        console: Rich console
        availability: Availability data
        metric_groups: Dict mapping metric name to group label
    """
    for group_name, metrics_dict in [
        ("Self-Funding Indicators (4 tags)", TAGS_SELF_FUNDING),
        ("Off-Balance Sheet (8 tags)", TAGS_OFFBALANCE),
    ]:
        table = Table(title=group_name, show_header=True, header_style="bold magenta")
        table.add_column("Ticker", style="cyan", width=8)

        # Add column for each metric
        metrics = list(metrics_dict.keys())
        for metric in metrics:
            table.add_column(metric, justify="center", width=12)

        # Add rows for each ticker
        for ticker, ticker_data in availability.items():
            row = [ticker]
            for metric in metrics:
                available_tags = ticker_data.get(metric, [])
                if available_tags:
                    # Show OK with count
                    symbol = f"OK ({len(available_tags)})"
                    style = "green"
                else:
                    symbol = "X"
                    style = "red"
                row.append(f"[{style}]{symbol}[/{style}]")
            table.add_row(*row)

        console.print(table)
        console.print()


def print_detailed_tags(
    console: Console,
    availability: dict[str, dict[str, list[str]]],
) -> None:
    """
    Print detailed tag information for each ticker.

    Args:
        console: Rich console
        availability: Availability data
    """
    console.print("[bold]Detailed Tag Information[/bold]")
    console.print()

    for ticker, ticker_data in availability.items():
        console.print(f"[bold cyan]{ticker}[/bold cyan]")

        for metric, tags in ticker_data.items():
            if tags:
                console.print(f"  {metric}: [green]{', '.join(tags)}[/green]")
            else:
                console.print(f"  {metric}: [red]No tags found[/red]")

        console.print()


def run_doctor(
    cohort_name: str | None = None,
    detailed: bool = False,
) -> int:
    """
    Run doctor checks.

    Args:
        cohort_name: Cohort to check (None = all cohorts)
        detailed: Show detailed tag information

    Returns:
        Exit code (0 = success)
    """
    config = get_config()
    console = Console()

    # Determine which cohorts to check
    if cohort_name:
        cohorts = [cohort_name]
    else:
        cohorts = config.list_cohorts()

    console.print(f"[yellow]Checking tag availability for cohorts: {', '.join(cohorts)}[/yellow]")
    console.print()

    # Collect all tickers
    all_tickers: set[str] = set()
    for cohort in cohorts:
        tickers = config.get_cohort_tickers(cohort)
        all_tickers.update(tickers)

    all_tickers_list = sorted(all_tickers)
    console.print(f"Tickers to check: {', '.join(all_tickers_list)}")
    console.print()

    # Check availability
    # Note: We create a temporary collector without database connection
    # since we're only using the API methods
    import sqlite3
    temp_conn = sqlite3.connect(":memory:")
    collector = SecXbrlCollector(temp_conn)

    availability = check_tag_availability(collector, all_tickers_list)
    temp_conn.close()

    # Print results
    metric_groups = {
        "Self-Funding": list(TAGS_SELF_FUNDING.keys()),
        "Off-Balance": list(TAGS_OFFBALANCE.keys()),
    }

    print_availability_table(console, availability, metric_groups)

    if detailed:
        print_detailed_tags(console, availability)

    # Summary
    total_tickers = len(availability)
    console.print(f"[bold]Summary:[/bold] Checked {total_tickers} tickers")

    # Count how many tickers have all self-funding tags
    self_funding_complete = 0
    for ticker, ticker_data in availability.items():
        has_all = all(
            ticker_data.get(metric, []) for metric in TAGS_SELF_FUNDING.keys()
        )
        if has_all:
            self_funding_complete += 1

    console.print(
        f"Tickers with all self-funding tags: {self_funding_complete}/{total_tickers}"
    )

    return 0
