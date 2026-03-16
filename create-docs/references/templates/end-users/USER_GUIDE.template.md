<!-- DIATAXIS: how-to -->
<!-- AUDIENCE: end-users -->

# User Guide

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Getting Started
<!-- PURPOSE: Walk the user through first-time setup and their first successful
     interaction with the system. This section answers "how do I start using
     this?" Prerequisites should be clearly listed before any steps. Every step
     must have an expected result so users know they did it right. -->
<!-- EXAMPLE:
### Prerequisites

- Python 3.10 or later installed
- Access to the company VPN (required for market data feeds)
- Your API credentials (request from the platform team via Slack #road-runner)

### First-Time Setup

1. Clone the project repository:
   ```bash
   git clone https://github.com/company/road-runner.git
   cd road-runner
   ```
   You should see the project files in your terminal.

2. Run the setup script:
   ```bash
   bash setup.sh
   ```
   You should see: "Setup complete. Configuration written to config.yaml."

3. Add your API credentials:
   Open `config.yaml` and set your `api_key` value.

4. Verify the installation:
   ```bash
   python3 main.py --check
   ```
   You should see: "All systems operational. Ready to score."
-->

## Common Tasks
<!-- PURPOSE: Cover the 3-5 operations users perform most frequently. These are
     the daily-use workflows that justify the tool's existence. Organize by
     user intent ("How do I...") rather than by system module. Keep each task
     to a maximum of 7 numbered steps with one action per step. -->
<!-- EXAMPLE:
### Running a Scoring Pipeline

1. Open your terminal and navigate to the project directory.
2. Run the scoring pipeline:
   ```bash
   python3 main.py score --portfolio my-portfolio.yaml
   ```
3. Wait for the pipeline to complete. You should see:
   ```
   Scoring complete: 47 positions evaluated, 3 rebalancing signals generated.
   ```
4. View the results:
   ```bash
   python3 main.py report --latest
   ```
   This opens a summary showing each position's score and any recommended actions.

### Viewing Position Scores

1. Run the query command with a position name:
   ```bash
   python3 main.py query --position "AAPL"
   ```
2. You should see the current score, factor breakdown, and last update time:
   ```
   AAPL: Score 78/100
     Momentum: 82  |  Value: 71  |  Quality: 80
     Last scored: 2026-03-15 14:30 UTC
   ```

### Exporting Results to CSV

1. Run the export command:
   ```bash
   python3 main.py export --format csv --output results.csv
   ```
2. You should see: "Exported 47 positions to results.csv."
3. Open the file in your spreadsheet application.
-->

## Configuration
<!-- PURPOSE: Document the user-facing configuration options. Users need to know
     what they can change, where to change it, and what each option does.
     Exclude internal/developer settings -- only include options that affect
     the user experience. Use a table for quick scanning. -->
<!-- EXAMPLE:
Configuration is stored in `config.yaml` in the project root.

| Setting | Default | Description |
|---------|---------|-------------|
| `portfolio_path` | `portfolios/default.yaml` | Path to your portfolio definition file |
| `output_format` | `table` | How results are displayed: `table`, `csv`, or `json` |
| `scoring_model` | `balanced` | Which scoring model to use: `balanced`, `growth`, `value`, `momentum` |
| `lookback_days` | `90` | Number of days of historical data to include in scoring |
| `auto_export` | `false` | Automatically export results to CSV after each run |

To change a setting, open `config.yaml` in any text editor and modify the value.
Changes take effect on the next pipeline run -- no restart required.
-->

## Troubleshooting
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Address the most common problems users encounter. Structure each
     entry as symptom, cause, and fix. This section reduces support requests by
     giving users self-service answers to predictable issues. -->
<!-- EXAMPLE:
### "No data found for position"

**Cause:** The position ticker symbol is not in the market data feed, or the
data feed has not been updated recently.

**Fix:**
1. Check that the ticker symbol is correct (case-sensitive):
   ```bash
   python3 main.py list-tickers | grep -i "aapl"
   ```
2. If the ticker exists, refresh the data feed:
   ```bash
   python3 main.py refresh-data
   ```
3. Try the query again.

### "Configuration file not found"

**Cause:** The `config.yaml` file is missing from the project root, or you are
running the command from the wrong directory.

**Fix:**
1. Verify you are in the project root:
   ```bash
   ls config.yaml
   ```
2. If the file is missing, regenerate the default configuration:
   ```bash
   python3 main.py init-config
   ```

### Pipeline exits with "Scoring model not found"

**Cause:** The `scoring_model` value in `config.yaml` does not match any
available model.

**Fix:** Check available models and update your config:
```bash
python3 main.py list-models
```
Set `scoring_model` in `config.yaml` to one of the listed model names.
-->
