# UCR Scoring Field Reference

25 fields a data provider must supply. 5 additional scored fields are computed by the
ranker pipeline from these 25 — they are not listed here.

**Match categories for provider evaluation:**
- **DIRECT** — Provider supplies this field natively (exact or near-exact definition)
- **DERIVABLE** — Provider supplies the raw inputs; we compute it (see Substitutions)
- **SUBSTITUTE** — Provider has a similar field but the definition differs materially
- **NONE** — Provider cannot supply this field or its inputs

---

## Fields (25)

### Growth

| # | Field | Definition |
|---|-------|-----------|
| 1 | `Revenue YoY` | Revenue growth YoY: % change from TTM revenue vs the TTM period one year prior. Decimal (0.15 = 15%). |
| 2 | `Revenue FWD` | Forward revenue growth rate — consensus analyst estimate. Decimal. No derivation possible without analyst data. |
| 3 | `Revenue TTM` | Trailing twelve month revenue, absolute $. |
| 4 | `Revenue 3Y` | Revenue CAGR over 3 years. Decimal. |
| 5 | `Revenue 5Y` | Revenue CAGR over 5 years. Decimal. |
| 6 | `Revenue Surprise` | Revenue surprise vs consensus estimate, absolute $ amount. Positive = beat. |

### Valuation

| # | Field | Definition |
|---|-------|-----------|
| 7 | `EV / Sales` | Enterprise value ÷ TTM revenue. Ratio. |
| 8 | `PEG FWD` | Forward P/E ÷ forward 3–5 year consensus EPS growth rate. Requires analyst estimates. |
| 9 | `Market Cap` | Market capitalization: shares outstanding × price. Absolute $. |

### Profitability & Efficiency

| # | Field | Definition |
|---|-------|-----------|
| 10 | `EBITDA Margin` | EBITDA ÷ revenue, TTM. Decimal. |
| 11 | `FCF Margin` | Free cash flow ÷ revenue, TTM. Decimal. |
| 12 | `Profit Margin` | Gross profit margin, TTM. Decimal. |
| 13 | `Return on Total Capital` | Return on total capital, TTM. Decimal. |
| 14 | `Net Income / Employee` | Net income per employee, TTM. Absolute $. |
| 15 | `Asset Turnover` | Net sales ÷ average total assets, TTM. Ratio. |

### Balance Sheet

| # | Field | Definition |
|---|-------|-----------|
| 16 | `Debt to FCF` | Total debt ÷ free cash flow, TTM. Ratio. |
| 17 | `Interest Coverage Ratio` | EBIT ÷ interest expense. Ratio. |
| 18 | `Current Ratio` | Current assets ÷ current liabilities, TTM. Ratio. |
| 19 | `Quick Ratio` | (Cash + marketable securities + receivables) ÷ current liabilities, TTM. Ratio. |
| 20 | `Debt to Equity` | Total debt ÷ shareholder equity. Ratio. |
| 21 | `LT Debt to Total Capital` | Long-term debt ÷ (LT debt + equity). Ratio. |

### Market / Sentiment

| # | Field | Definition |
|---|-------|-----------|
| 22 | `Last Price Vs. 200D SMA` | % difference: `(Price / SMA200) − 1`. Decimal. |
| 23 | `Short Interest` | Shares sold short as % of shares outstanding. |
| 24 | `Institutional Percent` | Institutional ownership as % of shares outstanding. |
| 25 | `Insider %` | Insider ownership as % of shares outstanding. |

---

## Substitutions

When a provider doesn't supply a field directly, it can be derived from raw inputs.

| Field | Raw Inputs Needed |
|-------|-------------------|
| `Revenue YoY` (#1) | Quarterly revenue |
| `Revenue TTM` (#3) | Quarterly revenue |
| `Revenue 3Y` (#4) | Annual revenue |
| `Revenue 5Y` (#5) | Annual revenue |
| `Revenue Surprise` (#6) | Revenue actual + revenue estimate (earnings event) |
| `EV / Sales` (#7) | Enterprise value, revenue TTM |
| `PEG FWD` (#8) | Last price, forward EPS estimate, forward EPS growth rate (3-5Y) |
| `Market Cap` (#9) | Shares outstanding, last price |
| `EBITDA Margin` (#10) | Quarterly EBITDA, revenue TTM |
| `FCF Margin` (#11) | Quarterly operating cash flow + capex, revenue TTM |
| `Profit Margin` (#12) | Quarterly gross profit, revenue TTM |
| `Return on Total Capital` (#13) | EBIT (TTM), total debt, total equity |
| `Net Income / Employee` (#14) | Quarterly net income, employee count |
| `Asset Turnover` (#15) | Revenue TTM, total assets |
| `Debt to FCF` (#16) | Total debt, operating cash flow, capex |
| `Interest Coverage Ratio` (#17) | EBIT (TTM), interest expense (TTM) |
| `Current Ratio` (#18) | Current assets, current liabilities |
| `Quick Ratio` (#19) | Cash, marketable securities, receivables, current liabilities |
| `Debt to Equity` (#20) | Total debt, total equity |
| `LT Debt to Total Capital` (#21) | Long-term debt, total equity |
| `Last Price Vs. 200D SMA` (#22) | Last price, 200-day SMA (or daily closes) |
| `Short Interest` (#23) | Shares sold short (absolute), shares outstanding |
| `Institutional Percent` (#24) | Institutional shares held, shares outstanding |
| `Insider %` (#25) | Insider shares held, shares outstanding |

**No derivation possible:** `Revenue FWD` (#2) — requires analyst consensus estimates.

---

## Raw Inputs Summary

Minimal raw data a provider must expose when pre-computed ratios are unavailable.
All data needed with 3 years of history.

| Category | Fields |
|----------|--------|
| **Income Statement** | Revenue, EBITDA, EBIT (operating income), Interest Expense, Net Income, Gross Profit |
| **Balance Sheet** | Total Cash, Total Debt, LT Debt, Total Equity, Current Assets, Current Liabilities, Cash, Marketable Securities, Receivables |
| **Cash Flow** | Operating Cash Flow, Capital Expenditure |
| **Market Data** | Last Price, Shares Outstanding, Enterprise Value |
| **Technical** | 200-day SMA (or daily close prices) |
| **Analyst Estimates** | Revenue FWD growth, Forward EPS, Forward EPS growth (3-5Y), Revenue Estimate |
| **Earnings Events** | Revenue Actual, Revenue Estimate |
| **Ownership** | Shares Short, Institutional Shares, Insider Shares |
| **Reference** | Employee Count |
