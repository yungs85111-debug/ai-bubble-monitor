"""Tests for CLI commands."""

from click.testing import CliRunner

from bm.cli import main


def test_cli_help():
    """Test that --help works."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "AI Bubble Debate Monitor" in result.output


def test_cli_version():
    """Test that --version works."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_doctor_command():
    """Test doctor command exists."""
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0


def test_thresholds_show():
    """Test thresholds show command."""
    runner = CliRunner()
    result = runner.invoke(main, ["thresholds", "show"])
    assert result.exit_code == 0
