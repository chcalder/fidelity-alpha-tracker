# Fidelity Alpha Tracker

Portfolio analytics tool that parses Fidelity CSV exports, calculates alpha vs the S&P 500 (SPY), flags concentration risk, and provides Buy/Hold/Sell recommendations — no API key required.

**Alpha** = your return minus the S&P 500's return over the same period. A holding with +6% return when SPY returned -3% has an alpha of +9% — it beat the market by 9 points. Portfolio alpha is the weighted sum across all holdings, answering one question: **are you beating the market, or would you be better off just buying SPY?**

## Features

- **Alpha calculation** — Per-holding and weighted portfolio alpha vs SPY
- **Concentration risk** — Flags holdings >15% (WARNING) and >20% (CRITICAL)
- **Rule-based recommendations** — Deterministic Buy/Hold/Sell actions based on concentration, alpha, and weight thresholds (no API key needed)
- **Optional AI enhancement** — Gemini-powered recommendations when an API key is provided
- **Shared analysis cache** — CLI report caches results so the dashboard reuses them without recomputation
- **Interactive dashboard** — Streamlit UI with charts, sortable tables, and time period picker
- **CLI report** — Terminal output + standalone dark-themed HTML report with recommendations
- **Multi-account** — Consolidates all Fidelity accounts into one view

## Setup

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set your Gemini API key (optional, for AI-enhanced recommendations):

```bash
export GEMINI_API_KEY='your-key-here'
```

Get a key at https://aistudio.google.com/apikey

## Usage

### Quick Start

```bash
source venv/bin/activate
python run.py
```

The interactive launcher will walk you through:
1. **Import** — Move Fidelity CSVs from `~/Downloads` into `data/`
2. **Choose output** — Dashboard, CLI report, or both

### Individual Scripts

| Script | Purpose |
|---|---|
| `run.py` | Interactive launcher (recommended) |
| `import_csv.py` | Import CSVs from `~/Downloads` → `data/` |
| `dashboard.py` | Streamlit dashboard (`streamlit run dashboard.py`) |
| `main.py` | CLI report + HTML output |

### Dashboard

```bash
streamlit run dashboard.py
```

Opens at http://localhost:8501 with:
- **Time period selector** (5d, 1mo, 3mo, 6mo, YTD, 1y, 2y, 5y) — changing the period re-downloads price data from Yahoo Finance and recalculates all returns, alpha, and weighted alpha for every holding and account in real time. This lets you quickly compare how your picks performed over the last week vs the last year without re-running anything.
- Account picker (individual or all combined)
- Allocation pie charts and alpha bar charts
- Sortable data tables with risk and action badges
- Advisor recommendations (rule-based by default; toggle on Gemini AI for enhanced analysis)

### CLI Report

```bash
python main.py
```

Prints a formatted report to the terminal and saves a static HTML file to `reports/`. The HTML report is a fixed 5-day snapshot — it does not support switching time periods or refreshing data. Analysis results are cached to `reports/ai_cache.json` for reuse by the dashboard. For interactive analysis with flexible time horizons, use the dashboard instead.

## Project Structure

```
fidelity-alpha-tracker/
├── run.py              # Interactive launcher
├── alpha_core.py       # Shared core (parsing, analysis, AI, caching)
├── dashboard.py        # Streamlit dashboard
├── main.py             # CLI + HTML report generator
├── import_csv.py       # CSV import utility
├── test_harness.py     # Validation test suite
├── requirements.txt    # Python dependencies
├── data/               # Fidelity CSV exports (gitignored)
├── reports/            # Generated HTML reports + AI cache (gitignored)
└── venv/               # Python virtual environment (gitignored)
```

## Testing

Run the test harness to validate all functionality:

```bash
source venv/bin/activate
python test_harness.py
```

The test suite covers 14 areas:

| # | Area | What it checks |
|---|------|----------------|
| 1 | Module imports | pandas, yfinance, streamlit, plotly, google-genai |
| 2 | Data files | `data/` exists, CSVs present and readable |
| 3 | CSV parsing | Every CSV parses correctly, money market filtered, columns exist |
| 4 | Market data | yfinance download, SPY present, return calculations |
| 5 | Account analysis | Values, weights sum to 100%, alpha, risk flags correct |
| 6 | AI summary text | Contains account name, holdings, SPY return |
| 7 | AI / Gemini | Live API call (if key set) or rule-based fallback |
| 8 | HTML report | Alpha verdict, table rows match, badges, structure |
| 9 | Terminal output | Summary, alpha verdict, SPY in output |
| 10–12 | Scripts compile | dashboard.py, run.py, import_csv.py syntax valid |
| 13 | Reports output | HTML files exist and are valid |
| 14 | 401K plan funds | Detected, included in value, alpha is N/A |

Set `GEMINI_API_KEY` before running to also validate AI recommendations; otherwise those tests are skipped gracefully.

## Data Privacy

- Portfolio data stays local — only ticker symbols and aggregated numbers are sent to Gemini when AI is enabled
- No account numbers, SSNs, or personal information is transmitted
- AI can be disabled entirely via the dashboard toggle or by omitting the API key
- Without an API key, the app is fully functional using rule-based analysis with zero external API calls (beyond Yahoo Finance for price data)
