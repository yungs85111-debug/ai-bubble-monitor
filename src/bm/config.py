"""
Configuration management for Bubble Monitor.

Loads settings from environment variables and YAML configuration files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def _get_project_root() -> Path:
    """Find the project root directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()


PROJECT_ROOT = _get_project_root()


@dataclass
class Config:
    """Application configuration."""

    database_path: Path
    cache_dir: Path
    sec_user_agent: str
    sec_rate_limit: int
    fred_api_key: str | None
    offline: bool
    log_level: str
    cohorts_path: Path
    premises_path: Path
    thresholds_path: Path

    # Loaded data
    _cohorts: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    _premises: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    _thresholds: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, env_file: Path | None = None) -> Config:
        """Load configuration from environment and files."""
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv(PROJECT_ROOT / ".env")

        config = cls(
            database_path=Path(
                os.getenv("BM_DATABASE_PATH", PROJECT_ROOT / "data" / "bubble_monitor.db")
            ),
            cache_dir=Path(os.getenv("BM_CACHE_DIR", PROJECT_ROOT / ".cache")),
            sec_user_agent=os.getenv("SEC_USER_AGENT", "bubble-monitor@example.com"),
            sec_rate_limit=int(os.getenv("SEC_RATE_LIMIT", "8")),
            fred_api_key=os.getenv("FRED_API_KEY") or None,
            offline=os.getenv("BM_OFFLINE", "0") == "1",
            log_level=os.getenv("BM_LOG_LEVEL", "INFO"),
            cohorts_path=Path(
                os.getenv("BM_COHORTS_PATH", PROJECT_ROOT / "data" / "cohorts.yaml")
            ),
            premises_path=Path(
                os.getenv("BM_PREMISES_PATH", PROJECT_ROOT / "data" / "premises.yaml")
            ),
            thresholds_path=Path(
                os.getenv("BM_THRESHOLDS_PATH", PROJECT_ROOT / "data" / "thresholds.yaml")
            ),
        )

        config._load_yaml_configs()
        return config

    def _load_yaml_configs(self) -> None:
        """Load YAML configuration files."""
        if self.cohorts_path.exists():
            with open(self.cohorts_path, encoding="utf-8") as f:
                self._cohorts = yaml.safe_load(f) or {}

        if self.premises_path.exists():
            with open(self.premises_path, encoding="utf-8") as f:
                self._premises = yaml.safe_load(f) or {}

        if self.thresholds_path.exists():
            with open(self.thresholds_path, encoding="utf-8") as f:
                self._thresholds = yaml.safe_load(f) or {}

    def get_cohort(self, name: str) -> dict[str, Any]:
        """Get cohort configuration by name."""
        if name not in self._cohorts:
            raise ValueError(f"Unknown cohort: {name}")
        return self._cohorts[name]

    def get_cohort_tickers(self, name: str) -> list[str]:
        """Get list of tickers for a cohort."""
        cohort = self.get_cohort(name)
        return cohort.get("tickers", [])

    def list_cohorts(self) -> list[str]:
        """List all available cohort names."""
        return list(self._cohorts.keys())

    def get_premise(self, premise_id: str) -> dict[str, Any]:
        """Get premise configuration by ID."""
        if premise_id not in self._premises:
            raise ValueError(f"Unknown premise: {premise_id}")
        return self._premises[premise_id]

    def list_premises(self) -> list[str]:
        """List all premise IDs."""
        return list(self._premises.keys())

    def get_threshold(self, indicator_id: str) -> dict[str, Any] | None:
        """Get threshold configuration for an indicator."""
        return self._thresholds.get(indicator_id)

    def list_thresholds(self) -> dict[str, dict[str, Any]]:
        """Get all threshold configurations."""
        return self._thresholds.copy()

    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


# Global config instance (lazy loaded)
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def reset_config() -> None:
    """Reset the global configuration (for testing)."""
    global _config
    _config = None
