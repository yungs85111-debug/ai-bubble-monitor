"""
Command-line interface for Bubble Monitor.

Click-based CLI entry point providing all monitoring commands.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

from bm import __version__
from bm.config import get_config, reset_config
from bm.db import init_db as initialize_database, verify_append_only, AppendOnlyViolation, get_connection
from bm.collectors.sec_xbrl import SecXbrlCollector
from bm.doctor import run_doctor
from bm.thresholds import get_threshold_manager
from bm.ledger import list_ledger_entries, list_runs
from bm.backfill import run_backfill, validate_backfill_prerequisites
from bm.report import print_premise_report

console = Console()


def setup_logging(level: str) -> None:
    """Configure logging with rich handler."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.group()
@click.version_option(version=__version__, prog_name="bubble-monitor")
@click.option("--offline", is_flag=True, help="Run in offline mode (no network calls)")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--config", "config_file", type=click.Path(exists=True), help="Config file path")
@click.pass_context
def main(ctx: click.Context, offline: bool, verbose: bool, config_file: str | None) -> None:
    """AI Bubble Debate Monitor - Evidence-based premise tracking."""
    ctx.ensure_object(dict)

    # Reset config if custom file provided
    if config_file:
        reset_config()

    config = get_config()

    # Override offline mode from CLI
    if offline:
        config.offline = True

    # Setup logging
    log_level = "DEBUG" if verbose else config.log_level
    setup_logging(log_level)

    ctx.obj["config"] = config
    ctx.obj["console"] = console


@main.command()
@click.option("--cohort", help="Specific cohort to check (default: all)")
@click.option("--detailed", is_flag=True, help="Show detailed tag information")
@click.pass_context
def doctor(ctx: click.Context, cohort: str | None, detailed: bool) -> None:
    """Check tag availability for all cohort tickers."""
    config = ctx.obj["config"]

    if config.offline:
        console.print("[red]Cannot run doctor in offline mode (requires SEC API access)[/red]")
        sys.exit(1)

    exit_code = run_doctor(cohort_name=cohort, detailed=detailed)
    sys.exit(exit_code)


@main.command()
@click.option("--cohort", required=True, help="Cohort name to collect")
@click.option("--ticker", help="Specific ticker (optional)")
@click.pass_context
def collect(ctx: click.Context, cohort: str, ticker: str | None) -> None:
    """Collect SEC filings for a cohort."""
    config = ctx.obj["config"]

    if config.offline:
        console.print("[red]Cannot collect in offline mode[/red]")
        sys.exit(1)

    tickers = [ticker] if ticker else config.get_cohort_tickers(cohort)
    console.print(f"[green]Collecting SEC data for: {tickers}[/green]")

    # Initialize database and collector
    conn = get_connection(config.database_path)
    collector = SecXbrlCollector(conn)

    try:
        count = collector.collect_and_store(tickers)
        console.print(f"[green]Stored {count} observations[/green]")
    except Exception as e:
        console.print(f"[red]Collection failed: {e}[/red]")
        sys.exit(1)
    finally:
        conn.close()


@main.command()
@click.option("--as-of", help="Evaluation date (YYYY-MM-DD)")
@click.pass_context
def evaluate(ctx: click.Context, as_of: str | None) -> None:
    """Run rule engine evaluation."""
    console.print(f"[green]Evaluating as of: {as_of or 'latest'}[/green]")
    console.print("[dim]Full implementation in T9[/dim]")


@main.command()
@click.pass_context
def report(ctx: click.Context) -> None:
    """Show current premise status report."""
    config = ctx.obj["config"]
    conn = get_connection(config.database_path)

    try:
        print_premise_report(console, conn)
    finally:
        conn.close()


@main.command()
@click.option("--from", "from_date", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--to", "to_date", help="End date (YYYY-MM-DD, default: today)")
@click.option("--commit", is_flag=True, help="Commit results to ledger")
@click.option("--supersede", type=int, help="Run ID to supersede")
@click.option("--reason", help="Reason for superseding (required with --supersede)")
@click.option("--validate-only", is_flag=True, help="Only validate prerequisites")
@click.pass_context
def backfill(
    ctx: click.Context,
    from_date: str,
    to_date: str | None,
    commit: bool,
    supersede: int | None,
    reason: str | None,
    validate_only: bool,
) -> None:
    """Backfill historical evaluations."""
    from datetime import date as date_type

    if supersede and not reason:
        console.print("[red]--reason is required when using --supersede[/red]")
        sys.exit(1)

    config = ctx.obj["config"]

    # Parse dates
    try:
        start_date = date_type.fromisoformat(from_date)
        end_date = date_type.fromisoformat(to_date) if to_date else date_type.today()
    except ValueError as e:
        console.print(f"[red]Invalid date format: {e}[/red]")
        sys.exit(1)

    mode = "[green]COMMIT[/green]" if commit else "[yellow]DRY-RUN[/yellow]"
    console.print(f"{mode} backfill from {start_date} to {end_date}")
    console.print()

    # Get database connection
    conn = get_connection(config.database_path)

    try:
        # Validate prerequisites
        console.print("[yellow]Validating prerequisites...[/yellow]")
        errors = validate_backfill_prerequisites(conn, start_date, end_date)

        if errors:
            console.print("[red]Validation failed:[/red]")
            for error in errors:
                console.print(f"  - {error}")
            sys.exit(1)

        console.print("[green]Prerequisites validated[/green]")
        console.print()

        if validate_only:
            console.print("[green]Validation complete (--validate-only)[/green]")
            return

        # Run backfill
        if not commit:
            console.print("[yellow]Running in DRY-RUN mode (no changes to ledger)[/yellow]")
            console.print("[dim]Use --commit to write results to ledger[/dim]")
            console.print()

        report = run_backfill(
            conn,
            start_date=start_date,
            end_date=end_date,
            commit=commit,
            supersede_run_id=supersede,
            supersede_reason=reason,
        )

        # Display report
        console.print()
        console.print("[bold]Backfill Report[/bold]")
        console.print("=" * 60)
        console.print(f"Date range: {report.start_date} to {report.end_date}")
        console.print(f"Total ticks: {report.total_ticks}")
        console.print(f"Successful: [green]{report.successful_ticks}[/green]")
        console.print(f"Failed: [red]{report.failed_ticks}[/red]")
        console.print(f"Success rate: {report.success_rate:.1%}")
        console.print()
        console.print(f"Total verdicts: {report.total_verdicts}")

        if report.verdict_counts:
            console.print("Verdict breakdown:")
            for verdict_type, count in sorted(report.verdict_counts.items()):
                color = {
                    "confirmed": "red",
                    "refuted": "green",
                    "undetermined": "yellow",
                    "undecidable": "dim",
                }.get(verdict_type, "white")
                console.print(f"  [{color}]{verdict_type}[/{color}]: {count}")

        if report.failed_ticks > 0:
            console.print()
            console.print("[red]Failed ticks:[/red]")
            for tick in report.ticks:
                if tick.error:
                    console.print(f"  {tick.as_of}: {tick.error}")

        if commit:
            console.print()
            console.print("[green]Results committed to ledger[/green]")
            console.print("View with: bm log")
        else:
            console.print()
            console.print("[yellow]DRY-RUN complete - no changes made[/yellow]")
            console.print("To commit results, run with --commit")

    finally:
        conn.close()


@main.command()
@click.option("--limit", default=50, help="Number of entries to show")
@click.option("--premise", help="Filter by premise ID")
@click.option("--include-superseded", is_flag=True, help="Include superseded runs")
@click.pass_context
def log(ctx: click.Context, limit: int, premise: str | None, include_superseded: bool) -> None:
    """View ledger entries."""
    from rich.table import Table

    config = ctx.obj["config"]
    conn = get_connection(config.database_path)

    try:
        entries = list_ledger_entries(
            conn,
            premise_id=premise,
            limit=limit,
            include_superseded=include_superseded,
        )

        if not entries:
            console.print("[yellow]No ledger entries found[/yellow]")
            return

        # Create table
        table = Table(title=f"Ledger Entries (showing {len(entries)})")
        table.add_column("ID", style="dim", width=6)
        table.add_column("Run", style="dim", width=6)
        table.add_column("Premise", style="cyan", width=10)
        table.add_column("Verdict", justify="center", width=12)
        table.add_column("Indicator", width=18)
        table.add_column("Value", justify="right", width=10)
        table.add_column("Created", style="dim", width=19)

        for entry in entries:
            # Color verdict
            verdict_color = {
                "confirmed": "red",
                "refuted": "green",
                "undetermined": "yellow",
                "undecidable": "dim",
            }.get(entry.verdict, "white")

            value_str = (
                f"{entry.indicator_value:.4f}"
                if entry.indicator_value is not None
                else "—"
            )

            table.add_row(
                str(entry.id),
                str(entry.run_id),
                entry.premise_id,
                f"[{verdict_color}]{entry.verdict}[/{verdict_color}]",
                entry.indicator_id or "—",
                value_str,
                entry.created_at,
            )

        console.print(table)

    finally:
        conn.close()


@main.command()
@click.option("--include-superseded", is_flag=True, help="Include superseded runs")
@click.option("--limit", default=20, help="Number of runs to show")
@click.pass_context
def runs(ctx: click.Context, include_superseded: bool, limit: int) -> None:
    """View evaluation runs."""
    from rich.table import Table

    config = ctx.obj["config"]
    conn = get_connection(config.database_path)

    try:
        run_list = list_runs(conn, include_superseded=include_superseded, limit=limit)

        if not run_list:
            console.print("[yellow]No runs found[/yellow]")
            return

        # Create table
        table = Table(title=f"Evaluation Runs (showing {len(run_list)})")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Type", width=10)
        table.add_column("As Of", width=19)
        table.add_column("Started", width=19)
        table.add_column("Completed", width=19)
        table.add_column("Status", width=12)

        for run in run_list:
            # Determine status
            if run.get("superseded_by"):
                status = f"[dim]superseded by {run['superseded_by']}[/dim]"
            elif run.get("completed_at"):
                status = "[green]completed[/green]"
            else:
                status = "[yellow]running[/yellow]"

            table.add_row(
                str(run["id"]),
                run["run_type"],
                run["as_of"],
                run["started_at"],
                run.get("completed_at") or "—",
                status,
            )

        console.print(table)

    finally:
        conn.close()


@main.group()
def nowcast() -> None:
    """Nowcast error tracking commands."""
    pass


@nowcast.command(name="list")
@click.option("--indicator", help="Filter by indicator ID")
@click.option("--limit", default=50, help="Number of records to show")
@click.pass_context
def nowcast_list(ctx: click.Context, indicator: str | None, limit: int) -> None:
    """List nowcast error records."""
    from rich.table import Table
    from bm.nowcast import get_nowcast_errors

    config = ctx.obj["config"]
    conn = get_connection(config.database_path)

    try:
        records = get_nowcast_errors(conn, indicator_id=indicator, limit=limit)

        if not records:
            console.print("[yellow]No nowcast records found[/yellow]")
            return

        # Create table
        table = Table(title=f"Nowcast Errors (showing {len(records)})")
        table.add_column("ID", style="dim", width=6)
        table.add_column("Indicator", style="cyan", width=20)
        table.add_column("Period End", width=12)
        table.add_column("Predicted", justify="right", width=12)
        table.add_column("Actual", justify="right", width=12)
        table.add_column("Error", justify="right", width=12)
        table.add_column("MAE", justify="right", width=10)
        table.add_column("Created", style="dim", width=19)

        for record in records:
            actual_str = (
                f"{record.actual_value:.4f}"
                if record.actual_value is not None
                else "[dim]pending[/dim]"
            )

            error_str = (
                f"{record.error:.4f}"
                if record.error is not None
                else "[dim]—[/dim]"
            )

            mae_str = (
                f"{record.mae:.4f}"
                if record.mae is not None
                else "[dim]—[/dim]"
            )

            table.add_row(
                str(record.id),
                record.indicator_id,
                str(record.period_end),
                f"{record.predicted_value:.4f}",
                actual_str,
                error_str,
                mae_str,
                record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            )

        console.print(table)

    finally:
        conn.close()


@nowcast.command(name="summary")
@click.argument("indicator_id")
@click.pass_context
def nowcast_summary(ctx: click.Context, indicator_id: str) -> None:
    """Show nowcast summary statistics for an indicator."""
    from bm.nowcast import get_nowcast_summary

    config = ctx.obj["config"]
    conn = get_connection(config.database_path)

    try:
        summary = get_nowcast_summary(conn, indicator_id)

        console.print()
        console.print(f"[bold]Nowcast Summary: {indicator_id}[/bold]")
        console.print("=" * 60)
        console.print(f"Total nowcasts: {summary['total_nowcasts']}")
        console.print(f"Observed nowcasts: {summary['observed_nowcasts']}")

        if summary['mae'] is not None:
            console.print(f"MAE: {summary['mae']:.4f}")
            console.print(f"Mean error: {summary['mean_error']:.4f}")
            console.print(f"Min error: {summary['min_error']:.4f}")
            console.print(f"Max error: {summary['max_error']:.4f}")
        else:
            console.print("MAE: [dim]not available (no observations)[/dim]")

        console.print()
        if summary['has_sufficient_samples']:
            console.print("[green]Sufficient samples for uncertainty bands (≥4)[/green]")
        else:
            console.print(
                f"[yellow]Insufficient samples ({summary['observed_nowcasts']}/4) - "
                "uncertainty bands not shown[/yellow]"
            )

    finally:
        conn.close()


@nowcast.command(name="add")
@click.argument("indicator_id")
@click.argument("period_end")
@click.argument("predicted_value", type=float)
@click.pass_context
def nowcast_add(ctx: click.Context, indicator_id: str, period_end: str, predicted_value: float) -> None:
    """Add a nowcast prediction."""
    from datetime import date as date_parse
    from bm.nowcast import insert_nowcast

    config = ctx.obj["config"]
    conn = get_connection(config.database_path)

    try:
        period_date = date_parse.fromisoformat(period_end)
        nowcast_id = insert_nowcast(conn, indicator_id, period_date, predicted_value)

        console.print(
            f"[green]Added nowcast {nowcast_id} for {indicator_id} @ {period_end}: "
            f"{predicted_value}[/green]"
        )

    finally:
        conn.close()


@nowcast.command(name="update")
@click.argument("nowcast_id", type=int)
@click.argument("actual_value", type=float)
@click.pass_context
def nowcast_update(ctx: click.Context, nowcast_id: int, actual_value: float) -> None:
    """Update a nowcast with actual observed value."""
    from bm.nowcast import update_nowcast_actual

    config = ctx.obj["config"]
    conn = get_connection(config.database_path)

    try:
        update_nowcast_actual(conn, nowcast_id, actual_value)

        console.print(
            f"[green]Updated nowcast {nowcast_id} with actual value: {actual_value}[/green]"
        )

    finally:
        conn.close()


@main.group()
def thresholds() -> None:
    """Threshold management commands."""
    pass


@thresholds.command(name="show")
@click.option("--validate", is_flag=True, help="Validate threshold configurations")
@click.pass_context
def thresholds_show(ctx: click.Context, validate: bool) -> None:
    """Display current thresholds."""
    from rich.table import Table

    manager = get_threshold_manager()

    # Validation check
    if validate:
        console.print("[yellow]Validating thresholds...[/yellow]")
        errors = manager.validate_all()

        if errors:
            console.print("[red]Validation errors found:[/red]")
            for indicator_id, error_list in errors.items():
                console.print(f"  [red]{indicator_id}:[/red]")
                for error in error_list:
                    console.print(f"    - {error}")
            console.print()
        else:
            console.print("[green]All thresholds valid[/green]")
            console.print()

        # Check enabled thresholds specifically (R13)
        enabled_errors = manager.validate_enabled()
        if enabled_errors:
            console.print("[red]CRITICAL: Enabled thresholds have errors (R13):[/red]")
            for indicator_id, error_list in enabled_errors.items():
                for error in error_list:
                    console.print(f"  - {error}")
            sys.exit(1)

    # Display table
    table = Table(title="Threshold Configurations", show_header=True)
    table.add_column("Indicator", style="cyan")
    table.add_column("Enabled", justify="center")
    table.add_column("Anchor", justify="right")
    table.add_column("Buffer", justify="right")
    table.add_column("Direction", justify="center")
    table.add_column("Dwell", justify="center")
    table.add_column("Has Rationale", justify="center")

    for indicator_id, threshold in manager.thresholds.items():
        enabled_str = "[green]✓[/green]" if threshold.enabled else "[dim]✗[/dim]"
        anchor_str = f"{threshold.anchor:.4f}" if threshold.anchor is not None else "[dim]—[/dim]"
        buffer_str = f"{threshold.buffer:.4f}" if threshold.buffer is not None else "[dim]—[/dim]"
        rationale_str = "[green]✓[/green]" if threshold.anchor_rationale else "[red]✗[/red]"

        table.add_row(
            indicator_id,
            enabled_str,
            anchor_str,
            buffer_str,
            threshold.direction,
            str(threshold.min_dwell_periods),
            rationale_str,
        )

    console.print(table)


@thresholds.command(name="derive")
@click.option("--indicator", help="Specific indicator to derive (default: all)")
@click.option("--min-periods", default=4, help="Minimum periods required (default: 4)")
@click.pass_context
def thresholds_derive(ctx: click.Context, indicator: str | None, min_periods: int) -> None:
    """Calculate buffer values from historical data."""
    from bm.thresholds import derive_buffer_from_history
    from bm.clock import create_clock
    from bm.indicators import (
        compute_self_funding_hyper,
        compute_self_funding_neo,
    )

    config = ctx.obj["config"]
    console.print("[yellow]Deriving buffer values from historical data...[/yellow]")
    console.print(f"Minimum periods required: {min_periods}")
    console.print()

    # For now, show placeholder implementation
    # Full implementation requires historical backfill first (T11)
    console.print("[yellow]Buffer derivation requires historical data.[/yellow]")
    console.print("Steps to derive buffers:")
    console.print("  1. Run: bm backfill --from 2023-01-01 --to 2024-12-31")
    console.print("  2. Run: bm thresholds derive")
    console.print()
    console.print("[dim]Example calculation:[/dim]")
    console.print("[dim]  buffer = median(|value(q) - value(q-1)|)[/dim]")
    console.print()
    console.print("[green]After T11 implementation, this command will:[/green]")
    console.print("  - Query historical indicator values")
    console.print("  - Calculate period-over-period differences")
    console.print("  - Compute median absolute difference as buffer")
    console.print("  - Suggest updated thresholds.yaml values")


@main.command()
@click.option("--verify", is_flag=True, help="Verify append-only triggers after init")
@click.pass_context
def init_db(ctx: click.Context, verify: bool) -> None:
    """Initialize the database schema."""
    config = ctx.obj["config"]
    config.ensure_directories()

    console.print(f"[green]Initializing database at: {config.database_path}[/green]")

    conn = initialize_database(config.database_path)

    if verify:
        console.print("[yellow]Verifying append-only triggers...[/yellow]")
        try:
            verify_append_only(conn)
            console.print("[green]Append-only triggers verified successfully[/green]")
        except AppendOnlyViolation as e:
            console.print(f"[red]Trigger verification failed: {e}[/red]")
            sys.exit(1)

    conn.close()
    console.print("[green]Database initialized successfully[/green]")


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to", type=int)
@click.option("--reload", is_flag=True, help="Enable auto-reload (development)")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, reload: bool) -> None:
    """Start the read-only API server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]FastAPI dependencies not installed[/red]")
        console.print("Install with: pip install -e .[api]")
        sys.exit(1)

    console.print()
    console.print("[bold]AI Bubble Monitor API Server[/bold]")
    console.print("=" * 60)
    console.print(f"Host: {host}")
    console.print(f"Port: {port}")
    console.print(f"URL: http://{host}:{port}")
    console.print()
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    console.print()

    uvicorn.run(
        "bm.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@main.command(name="rate-limits")
@click.option("--domain", help="Show rate limit for specific domain")
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
def rate_limits(domain: str | None, json_output: bool) -> None:
    """Display HTTP client rate limit settings.

    Shows the configured rate limits (requests per second) for different domains.
    Rate limits use a token bucket algorithm to ensure compliance with API requirements.
    """
    from bm.http import DOMAIN_RATE_LIMITS
    from rich.table import Table
    import json as json_module

    if json_output:
        # JSON output
        if domain:
            rate = DOMAIN_RATE_LIMITS.get(domain, DOMAIN_RATE_LIMITS.get("default"))
            output = {domain: rate}
        else:
            output = DOMAIN_RATE_LIMITS
        console.print(json_module.dumps(output, indent=2))
        return

    # Rich table output
    console.print()
    console.print("[bold]HTTP Client Rate Limits[/bold]")
    console.print("=" * 60)
    console.print()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Domain", style="dim")
    table.add_column("Requests/Second", justify="right")
    table.add_column("Notes", style="italic")

    if domain:
        # Show specific domain
        rate = DOMAIN_RATE_LIMITS.get(domain, DOMAIN_RATE_LIMITS.get("default"))
        notes = ""
        if domain == "default":
            notes = "Fallback rate for unspecified domains"
        elif "sec.gov" in domain:
            notes = "SEC requires max 10 req/s, using 8 for safety"
        elif domain == "api.stlouisfed.org":
            notes = "FRED API"

        table.add_row(domain, f"{rate:.1f}", notes)
    else:
        # Show all domains
        for dom, rate in sorted(DOMAIN_RATE_LIMITS.items()):
            notes = ""
            if dom == "default":
                notes = "Fallback rate for unspecified domains"
            elif "sec.gov" in dom:
                notes = "SEC requires max 10 req/s, using 8 for safety"
            elif dom == "api.stlouisfed.org":
                notes = "FRED API"

            table.add_row(dom, f"{rate:.1f}", notes)

    console.print(table)
    console.print()
    console.print("[dim]Rate limits use token bucket algorithm with exponential backoff retry[/dim]")
    console.print()


if __name__ == "__main__":
    main()
