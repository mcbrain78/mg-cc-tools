<!-- DIATAXIS: how-to -->
<!-- AUDIENCE: end-users -->

# User Guide

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Overview
<!-- SYNTHESIZED: project_model.components, project_model.user_interfaces -->
<!-- PURPOSE: Introduce what this guide covers and what the reader will gain from it. This is a guide-level introduction -- NOT a product overview (that's OVERVIEW.md) and NOT audience routing (that's also OVERVIEW.md). Orient the reader within the end-user guide itself. -->
<!-- EXAMPLE:
This guide covers day-to-day portfolio management through the Road Runner Dashboard.
You will learn how to:

- **Track positions** -- add stocks to your portfolio and monitor their scores
- **Run scoring** -- evaluate your portfolio using configurable scoring models
- **Rebalance** -- interpret rebalancing signals and export reports for execution

By the end of this guide you will be comfortable managing portfolios, running
scoring pipelines, and exporting results through the Dashboard.

**What this guide does NOT cover:**
- Deploying or upgrading Road Runner -- see the [Operations Guide](../devops/OPERATIONS.md)
- REST API endpoints and webhook configuration -- see the [API Reference](../developers/API_REFERENCE.md)
- Configuring scoring model internals or agent pipelines -- see the [Developer Guide](../developers/DEVELOPER_GUIDE.md)
-->

## Key Concepts
<!-- SYNTHESIZED: project_model.components, project_model.entry_points -->
<!-- PURPOSE: Define domain and interaction concepts the user needs before tackling procedures. Bridge domain vocabulary (portfolio, scoring model, rebalancing signal) with user actions (scoring run, dashboard view). Keep definitions concrete -- "a portfolio is a set of stock positions you track" not "a portfolio is a collection entity." -->
<!-- EXAMPLE:
**Portfolio** -- A named set of stock positions you track together. Each portfolio
has its own scoring history and rebalancing signals. Example: your "Tech Growth"
portfolio contains AAPL, MSFT, and NVDA.

**Position** -- A single stock within a portfolio, identified by its ticker symbol.
Each position carries a composite score and per-factor breakdown.

**Scoring Model** -- The algorithm that evaluates each position. Road Runner ships
with four models: Balanced, Growth, Value, and Momentum. You select one per
portfolio in Settings.

**Scoring Run** -- The act of evaluating all positions in a portfolio against the
selected model. Triggered by clicking "Score Now" on the Portfolio page or
automatically on a schedule. A typical run takes 1-2 minutes.

**Rebalancing Signal** -- A recommendation generated after a scoring run when a
position's score crosses the configured alert threshold. Signals appear as badges
on the Portfolio page and in exported reports.
-->

## Workflows
<!-- SYNTHESIZED: project_model.entry_points, project_model.user_interfaces -->
<!-- PURPOSE: Map end-to-end user journeys. Each workflow is a named journey (e.g., "Quarterly Portfolio Review") with 3-5 high-level numbered steps that link to detailed procedures in Common Tasks. Workflows are a navigation layer -- not a duplication of procedures. -->
<!-- EXAMPLE:
### Quarterly Portfolio Review

1. **Refresh market data** -- Open the Data page and click "Refresh Quarterly"
   (see [Updating Quarterly Data](#updating-quarterly-data) in Common Tasks).
2. **Run scoring** -- Navigate to your portfolio and click "Score Now". Wait for
   the run to complete (~2 minutes).
3. **Review signals** -- Check the Rebalancing Signals panel for positions that
   crossed your alert threshold.
4. **Export report** -- Click "Export" to download a PDF or CSV summary
   (see [Exporting a Portfolio Report](#exporting-a-portfolio-report) in Common Tasks).
5. **Archive the quarter** -- Click "Archive" on the Data page to snapshot the
   current scores for historical comparison.

### New Stock Evaluation

1. **Add the position** -- On the Portfolio page, click "Add Position" and enter
   the ticker symbol (see [Getting Started](#getting-started) for first-time setup).
2. **Wait for data** -- Road Runner fetches historical data for the new ticker.
   This takes approximately 1 minute.
3. **Run scoring** -- Click "Score Now" to evaluate the new position alongside
   existing holdings.
4. **Compare** -- Review the score card to see how the new stock ranks against
   your existing positions.
-->

## Getting Started
<!-- BOUNDARY: Infrastructure setup and installation belong in devops/OPERATIONS.md, not here. This section covers first use of a running system. -->
<!-- PURPOSE: Walk the user through their first interaction with the running system. Assume infrastructure is already deployed. Focus on the user's interface (web UI, CLI, etc.), not installation or deployment. -->
<!-- EXAMPLE:
### Your First Portfolio

1. Open the Road Runner Dashboard at the URL provided by your operations team
   (typically `https://roadrunner.internal/dashboard`).
2. Click **Portfolios** in the sidebar. You should see the Portfolios page with
   an empty list and a "Create Portfolio" button.
3. Click **Create Portfolio**, enter a name (e.g., "My First Portfolio"), and
   select a scoring model. Click **Save**.
   You should see your new portfolio appear in the list.
4. Click your portfolio name to open it. Click **Add Position** and enter a
   ticker symbol (e.g., `AAPL`). Click **Add**.
   The position appears in the table with "Awaiting data" status.
5. After ~1 minute the status changes to "Ready". Click **Score Now** to run
   your first scoring.
6. When the run completes, the score card appears showing the composite score
   and per-factor breakdown for each position.

> **Power user tip:** You can also create portfolios and add positions from the
> CLI: `rr portfolio create "My First Portfolio" --model balanced` followed by
> `rr position add AAPL --portfolio "My First Portfolio"`.
-->

## Common Tasks
<!-- PURPOSE: Cover the 3-5 operations users perform most frequently. For each task: state the goal first (what the user is accomplishing and why), explain what the system will do (duration, what happens), then give steps through the primary interface, then expected results. -->
<!-- EXAMPLE:
### Updating Quarterly Data

**Goal:** Refresh market data so that scoring runs use current prices and
fundamentals. You should do this at the start of each quarter or whenever you
need up-to-date scores.

**What happens:** Road Runner fetches the latest market data for all positions
across all portfolios. This typically takes 2-3 minutes depending on the number
of positions.

**Steps:**
1. Click **Data** in the sidebar to open the Data Management page.
2. Click **Refresh Quarterly** in the top-right corner.
3. Confirm the date range in the dialog (defaults to current quarter) and click
   **Start Refresh**.
4. A progress bar appears. Wait for it to reach 100%.

**Expected result:** The Data page shows "Last refreshed: [today's date]" and
all position scores update within 5 minutes.

### Exporting a Portfolio Report

**Goal:** Generate a downloadable report of your portfolio's current scores and
rebalancing signals for sharing with colleagues or archival.

**What happens:** Road Runner compiles the latest scoring data into your chosen
format (PDF or CSV). The export completes in a few seconds.

**Steps:**
1. Navigate to your portfolio page.
2. Click the **Export** button in the toolbar.
3. Select the format: **PDF** (formatted report) or **CSV** (raw data).
4. Click **Download**. The file saves to your browser's download folder.

**Expected result:** The downloaded file contains one row per position with
columns for ticker, composite score, per-factor scores, and any active
rebalancing signals.

> **Power user tip:** Export from the CLI with
> `rr export --portfolio "My Portfolio" --format csv --output report.csv`.
-->

## Configuration
<!-- BOUNDARY: System-level configuration (environment variables, service settings, database connections) belongs in devops/OPERATIONS.md. Only user-facing settings that affect the user's experience belong here. -->
<!-- PURPOSE: Document user-facing configuration options that affect the user's experience. Use a table for quick scanning. Show how to change settings through the user's interface. -->
<!-- EXAMPLE:
User settings are managed on the **Settings** page (click the gear icon in the
sidebar).

| Setting | Default | Description |
|---------|---------|-------------|
| Scoring Model | Balanced | Algorithm used to evaluate positions: Balanced, Growth, Value, or Momentum |
| Alert Threshold | 70 | Score below which a rebalancing signal is generated (0-100) |
| Portfolio Visibility | Private | Who can view your portfolios: Private (only you) or Team (all team members) |
| Default Export Format | PDF | Format used when clicking Export without selecting: PDF or CSV |
| Auto-Score Schedule | Off | Automatically run scoring daily, weekly, or off |

To change a setting, click the row, update the value, and click **Save**.
Changes take effect immediately for new scoring runs.

### Changing Tracked Stocks

To add a stock to a portfolio:
1. Open the portfolio and click **Add Position**.
2. Enter the ticker symbol and click **Add**.

To remove a stock:
1. Open the portfolio and find the position in the table.
2. Click the **...** menu on the position row and select **Remove**.
3. Confirm the removal in the dialog.

Removed positions are archived -- their historical scores are preserved but no
longer included in new scoring runs.
-->

## Troubleshooting
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Address the most common problems users encounter. Structure each entry as: what the user sees (symptom), likely cause, and what to do (steps through the user's interface). -->
<!-- EXAMPLE:
### "No data found for position"

**What you see:** The Dashboard shows "No data found" next to a position in
your portfolio.

**Likely cause:** The ticker symbol is not in the market data feed, or the data
has not been refreshed since the position was added.

**What to do:**
1. Open the **Positions** page and verify the ticker spelling is correct.
2. Navigate to **Data** > **Refresh** and click **Start Refresh**.
3. Wait 2 minutes for the refresh to complete.
4. Return to the portfolio page -- the position should now show a score.

If the issue persists, the ticker may not be supported. Check the supported
tickers list on the Data page under "Coverage."

### Scores show "N/A"

**What you see:** The scores column shows "N/A" for one or more positions
instead of a numeric score.

**Likely cause:** Insufficient historical data for the position (less than
30 days of price history), or a data refresh is currently in progress.

**What to do:**
1. Check the **Data** page for refresh status. If a refresh is in progress,
   wait for it to complete.
2. If the refresh is complete, open the position details and check the
   "History" tab. Positions need at least 30 days of data to produce a score.
3. For newly added positions, wait 24 hours for the overnight data backfill
   to complete, then re-run scoring.
-->

<!-- WRITER NOTE: Exemplars above demonstrate web-UI style as the reference case.
     If the project's primary interface is CLI or API, follow the same structure --
     functional context before procedure, expected results after steps -- but use
     commands/responses (CLI) or requests/responses (API) instead of click paths.
     Secondary interfaces appear as > **Power user tip:** callouts. -->
