<!-- DIATAXIS: reference + how-to -->
<!-- AUDIENCE: end-users -->

# {Domain Area Title}

<!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

## Overview
<!-- PURPOSE: Explain what this domain area covers and why it matters to the
     user. This template is used for project-specific documents defined in
     config `custom_documents`. Each project fills it differently, so keep
     guidance generic but the exemplar concrete. The overview anchors the
     reader before diving into specifics. -->
<!-- EXAMPLE:
The scoring methodology determines how each position in your portfolio receives
a composite score from 0 to 100. Understanding the methodology helps you
interpret scores, choose the right scoring model, and make informed decisions
about which signals to act on.

This document covers the factors that make up a score, how they are weighted,
and how to read the factor breakdown in your reports.
-->

## Key Concepts
<!-- PURPOSE: Define the domain-specific terminology for this area. These terms
     may also appear in the project glossary, but here they are explained with
     more context and in relation to each other. Helps the user build a mental
     model before encountering these terms in procedures. -->
<!-- EXAMPLE:
| Concept | What It Means |
|---------|--------------|
| **Factor** | A single measurable attribute used to evaluate a position (e.g., momentum, value, quality). |
| **Weight** | How much influence a factor has on the composite score. Weights are defined in the scoring model and must sum to 100%. |
| **Composite Score** | The weighted sum of all factor scores for a position. Ranges from 0 (worst) to 100 (best). |
| **Lookback Period** | The historical time window used to calculate factor values. Default is 90 days. |
-->

## How It Works
<!-- PURPOSE: Provide a plain-language explanation of the process or system
     behind this domain area. Users need to understand the "what" and "why"
     before they follow procedures. Avoid implementation details -- focus on
     the user-visible behavior and logic. -->
<!-- EXAMPLE:
When you run a scoring pipeline, each position goes through three stages:

1. **Data collection** -- Historical price and volume data for the position's
   ticker is loaded from the data lake for the configured lookback period.

2. **Factor calculation** -- Each factor (momentum, value, quality) is
   calculated independently. Momentum measures price trend strength. Value
   compares current price to estimated fair value. Quality measures earnings
   consistency and balance sheet health.

3. **Score aggregation** -- Factor scores are combined using the weights from
   your selected scoring model. The composite score determines the position's
   overall ranking and whether a rebalancing signal is generated.

Positions scoring below 40 generate "sell" signals. Positions scoring above 70
generate "buy" signals. Everything in between is "hold."
-->

## Common Operations
<!-- PURPOSE: Task-oriented procedures specific to this domain area. Unlike the
     User Guide's common tasks, these are deeper operations that require
     understanding the domain concepts defined above. Follow the same format:
     numbered steps, one action per step, expected results. -->
<!-- EXAMPLE:
### Comparing Scoring Models

1. List available scoring models:
   ```bash
   python3 main.py list-models
   ```
2. Run the same portfolio against two different models:
   ```bash
   python3 main.py score --portfolio my-portfolio.yaml --model balanced
   python3 main.py score --portfolio my-portfolio.yaml --model growth
   ```
3. Compare results side by side:
   ```bash
   python3 main.py compare --runs latest-2
   ```
   You should see a table showing each position's score under both models, with
   differences highlighted.

### Adjusting Factor Weights

1. Copy the default model to create a custom model:
   ```bash
   cp models/balanced.yaml models/custom.yaml
   ```
2. Open `models/custom.yaml` and adjust the `weights` section. Weights must
   sum to 100:
   ```yaml
   weights:
     momentum: 40
     value: 35
     quality: 25
   ```
3. Run a pipeline with your custom model:
   ```bash
   python3 main.py score --portfolio my-portfolio.yaml --model custom
   ```
-->

## Reference
<!-- OPTIONAL -- delete if not applicable -->
<!-- PURPOSE: Detailed settings, parameters, or data definitions specific to
     this domain area. This is the lookup section for users who already
     understand the concepts and need exact values, ranges, or option lists.
     Use tables for quick scanning. -->
<!-- EXAMPLE:
### Factor Definitions

| Factor | Range | Calculation Period | Description |
|--------|-------|-------------------|-------------|
| Momentum | 0-100 | 90 days | Relative price strength vs. benchmark over the lookback period |
| Value | 0-100 | Current | Price-to-earnings ratio compared to sector median |
| Quality | 0-100 | 4 quarters | Earnings growth consistency and debt-to-equity ratio |

### Signal Thresholds

| Signal | Score Range | Meaning |
|--------|-----------|---------|
| Buy | 70-100 | Position is undervalued or has strong momentum |
| Hold | 40-69 | Position is fairly valued, no action recommended |
| Sell | 0-39 | Position is overvalued or has weakening fundamentals |
-->
