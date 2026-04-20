<!-- DIATAXIS: reference + explanation -->
<!-- AUDIENCE: all -->

# {Project Name} Documentation

## System Purpose
<!-- PURPOSE: Explain what this project does and why it exists in 2-4 sentences.
     This is the first thing any reader sees. It must answer "what is this?" and
     "why should I care?" without requiring prior context. Avoid implementation
     details -- focus on the problem solved and the value delivered. -->
<!-- EXAMPLE:
Road Runner is a portfolio analytics platform that evaluates investment positions
against configurable scoring models. It ingests market data feeds, applies
multi-factor scoring algorithms, and produces risk-adjusted recommendations for
portfolio managers. The platform runs as a scheduled pipeline with an API layer
for on-demand queries.
-->

## Key Concepts
<!-- PURPOSE: Define the 4-8 core domain concepts that appear throughout the
     documentation. This section prevents every audience-specific document from
     re-explaining the same terms. Keep definitions brief -- the glossary has
     full details. Link to GLOSSARY.md for comprehensive terminology. -->
<!-- EXAMPLE:
| Concept | Definition |
|---------|-----------|
| **Position** | A holding in a specific security with quantity, cost basis, and current valuation. |
| **Scoring Model** | A configurable set of weighted factors (momentum, value, quality) used to evaluate positions. |
| **Rebalancing Signal** | An output recommendation to buy, hold, or sell a position based on its composite score. |
| **Pipeline Run** | A scheduled or manual execution that ingests data, scores positions, and produces signals. |
| **Risk Budget** | The maximum allowable portfolio exposure to a single sector, factor, or position. |

See [GLOSSARY.md](./GLOSSARY.md) for the complete terminology reference.
-->

## Architecture at a Glance
<!-- PURPOSE: Provide a high-level visual of how the system's major components
     connect. Use ASCII art for portability -- no external image dependencies.
     Show data flow direction. This gives every reader a shared mental model
     before they dive into audience-specific details. -->
<!-- EXAMPLE:
```
  Market Data Feeds          Config (YAML)
       |                        |
       v                        v
  +-----------+          +-----------+
  |  Ingester |--------->|  Scoring  |
  +-----------+          |  Engine   |
       |                 +-----------+
       |                      |
       v                      v
  +-----------+          +-----------+
  | Data Lake |          |  Signal   |
  | (Parquet) |          | Generator |
  +-----------+          +-----------+
                              |
                              v
                    +-------------------+
                    |   API Server      |
                    | (FastAPI, /score, |
                    |  /positions,      |
                    |  /signals)        |
                    +-------------------+
```

| Component | Technology | Responsibility |
|-----------|-----------|---------------|
| Ingester | Python + pandas | Fetches and normalizes market data into Parquet files |
| Scoring Engine | Python + NumPy | Applies scoring models to position data |
| Signal Generator | Python | Converts scores into actionable buy/hold/sell signals |
| API Server | FastAPI | Serves scores, positions, and signals via REST endpoints |
| Data Lake | Parquet on S3 | Stores normalized market data and historical scores |
-->

## Audience Guide
<!-- PURPOSE: Route readers to the documentation set that matches their role.
     Each audience has a dedicated subdirectory with documents tailored to their
     needs. This table prevents readers from wading through irrelevant content
     and ensures they find the right starting point. -->
<!-- EXAMPLE:
| Audience | Start Here | What You'll Find |
|----------|-----------|-----------------|
| **End Users** (portfolio managers, analysts) | [User Guide](./end-users/USER_GUIDE.md) | Task-oriented guides for running pipelines, reading scores, and configuring models. Plain language, no code. |
| **Developers** (engineers extending the codebase) | [Architecture](./developers/ARCHITECTURE.md) | System design, data flow, API reference, and developer setup. Code examples throughout. |
| **Agents** (LLM coding assistants) | [System Map](./agents/SYSTEM_MAP.md) | Machine-optimized project structure, conventions, gotchas, and testing patterns. YAML frontmatter, explicit constraints. |
| **DevOps** (operators deploying and monitoring) | [Operations Guide](./devops/OPERATIONS.md) | Deployment runbooks, service management, configuration reference, and troubleshooting procedures. Copy-paste-ready commands. |
-->
