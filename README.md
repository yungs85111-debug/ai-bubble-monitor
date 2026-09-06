# AI Bubble Debate Monitor

Evidence-based monitoring system for tracking AI bubble debate premises using public financial data.

🌐 **Live Dashboard**: [View Dashboard](https://yungs85111-debug.github.io/ai-bubble-monitor/)

## Features

- **SEC XBRL Collection**: Automated quarterly data collection from SEC EDGAR
- **Replay Clock**: Lookahead-free backtesting with `known_at` filtering
- **Append-Only Ledger**: Immutable audit trail for all premise verdicts
- **Rule Engine**: Configurable threshold-based premise evaluation
- **Interactive Dashboard**: UX-optimized web dashboard with category summaries

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd bubble-monitor

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Copy environment configuration
cp .env.example .env
# Edit .env with your SEC User-Agent email
```

## Quick Start

```bash
# Verify installation
bm --help

# Check data availability for cohort
bm doctor

# Collect SEC filings (requires network)
bm collect --cohort hyper

# Run evaluation (offline safe)
bm evaluate --as-of 2024-06-30

# View current status
bm report

# Backfill historical data (dry-run)
bm backfill --from 2024-01-01

# Commit backfill results
bm backfill --from 2024-01-01 --commit
```

## Configuration

### Cohorts (`data/cohorts.yaml`)

Define stock groupings for analysis:

```yaml
hyper:
  name: "AI Hyperscalers"
  tickers:
    - NVDA
    - MSFT
    - GOOGL
    - META
    - AMZN
```

### Premises (`data/premises.yaml`)

Define the debate premises to track:

```yaml
P-A-03:
  category: A
  statement: "AI capex exceeds sustainable self-funding levels"
  indicator_id: self_funding_hyper
```

### Thresholds (`data/thresholds.yaml`)

Define evaluation thresholds:

```yaml
self_funding_hyper:
  anchor: 0.15
  anchor_method: semantic
  anchor_rationale: "Historical median of tech sector funding gaps"
  buffer: 0.02
  enabled: false  # Set true after T12 review
```

## Commands

| Command | Description |
|---------|-------------|
| `bm --help` | Show all commands |
| `bm doctor` | Check tag availability |
| `bm collect` | Collect SEC filings |
| `bm evaluate` | Run rule engine |
| `bm report` | Show current status |
| `bm backfill` | Historical evaluation |
| `bm log` | View ledger entries |
| `bm runs` | View evaluation runs |
| `bm thresholds show` | Display thresholds |
| `bm thresholds derive` | Calculate buffer values |

## Architecture

```
src/bm/
  cli.py          # Click CLI entry point
  config.py       # Environment and YAML configuration
  db.py           # SQLite with append-only triggers
  clock.py        # ReplayClock for lookahead-free replay
  http.py         # Rate-limited HTTP client with caching
  collectors/     # Data collectors (SEC, FRED, etc.)
  indicators/     # Computed indicators
  rules/          # Rule engine and definitions
  ledger.py       # Ledger management
  report.py       # Console reporting
```

## Design Principles

1. **No Lookahead (R12)**: All evaluations use `known_at` filtering
2. **Append-Only (R5)**: Ledger entries are immutable
3. **Evidence Required**: Every verdict links to observable facts
4. **Undecidable Preserved (R3)**: Cannot override semantic undecidability
5. **No Composite Scores (R1)**: Individual premise tracking only

## Dashboard Deployment

### Quick Deploy

```bash
# Generate and deploy dashboard
./scripts/deploy.sh

# Windows users
scripts\deploy.bat
```

### Manual Deployment

```bash
# 1. Generate dashboard
python scripts/generate_debate_dashboard_v2.py

# 2. Create index.html for GitHub Pages
cp debate.html index.html

# 3. Commit and push
git add index.html debate.html
git commit -m "Update dashboard: $(date +%Y-%m-%d)"
git push origin main
```

### Quarterly Update Workflow

After each quarter's SEC filings are available:

```bash
# 1. Collect new data
bm collect --cohort hyper
bm collect --cohort bigtech
bm collect --cohort semicon

# 2. Run evaluation
bm evaluate --as-of 2024-09-30

# 3. Verify results
bm report

# 4. Deploy dashboard
./scripts/deploy.sh "Q3 2024 update"
```

Dashboard will be live at: `https://yungs85111-debug.github.io/ai-bubble-monitor/`

## License

MIT
