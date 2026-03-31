#!/usr/bin/env python3
"""
Test harness for Fidelity Alpha Tracker.
Validates all core functionality end-to-end using actual data files.

Usage:
    source venv/bin/activate
    python test_harness.py
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ── Helpers ─────────────────────────────────────────────────────────────────

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
SKIP = "\033[93m⊘ SKIP\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0
skipped = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  {PASS}  {name}")
    else:
        failed += 1
        msg = f" — {detail}" if detail else ""
        print(f"  {FAIL}  {name}{msg}")


def skip(name, reason=""):
    global skipped
    skipped += 1
    msg = f" — {reason}" if reason else ""
    print(f"  {SKIP}  {name}{msg}")


def section(title):
    print(f"\n{BOLD}{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}{RESET}")


# ── Import checks ──────────────────────────────────────────────────────────

section("1. Module Imports")

try:
    import pandas as pd
    test("pandas imports", True)
except ImportError:
    test("pandas imports", False, "pip install pandas")

try:
    import yfinance as yf
    test("yfinance imports", True)
except ImportError:
    test("yfinance imports", False, "pip install yfinance")

try:
    import streamlit as st
    test("streamlit imports", True)
except ImportError:
    test("streamlit imports", False, "pip install streamlit")

try:
    import plotly
    test("plotly imports", True)
except ImportError:
    test("plotly imports", False, "pip install plotly")

try:
    import google.genai as genai
    test("google-genai imports", True)
except ImportError:
    test("google-genai imports", False, "pip install google-genai")


# ── Data files ──────────────────────────────────────────────────────────────

section("2. Data Files")

DATA_DIR = Path("data")
test("data/ directory exists", DATA_DIR.is_dir())

csv_files = sorted(DATA_DIR.glob("*.csv")) if DATA_DIR.is_dir() else []
test(f"CSV files present ({len(csv_files)} found)", len(csv_files) > 0)

for f in csv_files:
    size = f.stat().st_size
    test(f"  {f.name} readable ({size:,} bytes)", size > 100)


# ── CSV Parsing ─────────────────────────────────────────────────────────────

section("3. CSV Parsing (parse_csv)")

# Import parse_csv from main.py
sys.path.insert(0, str(Path(__file__).parent))
import main as main_module

for csv_path in csv_files:
    account_name, df = main_module.parse_csv(csv_path)
    test(f"  {csv_path.name} → \"{account_name}\"", bool(account_name))
    test(f"    has rows ({len(df)})", len(df) > 0)
    test(f"    has Symbol column", "Symbol" in df.columns)
    test(f"    has Current Value column", "Current Value" in df.columns)
    test(f"    has Quantity column", "Quantity" in df.columns)
    test(f"    no SPAXX/money market rows", not df["Symbol"].str.contains(r"\*", na=False).any())
    test(f"    all Current Values numeric", pd.to_numeric(df["Current Value"], errors="coerce").notna().all())


# ── Market Data Download ────────────────────────────────────────────────────

section("4. Market Data (yfinance)")

# Collect all symbols from all accounts
all_symbols = set()
accounts_parsed = []
for csv_path in csv_files:
    account_name, df = main_module.parse_csv(csv_path)
    all_symbols.update(df["Symbol"].tolist())
    accounts_parsed.append((account_name, df))

ticker_symbols = {s for s in all_symbols if " " not in s and len(s) <= 12}
non_ticker = all_symbols - ticker_symbols

test(f"Unique symbols collected ({len(all_symbols)})", len(all_symbols) > 0)
test(f"Ticker symbols for yfinance ({len(ticker_symbols)})", len(ticker_symbols) > 0)
test(f"Plan funds identified ({len(non_ticker)})", True)

all_tickers = sorted(ticker_symbols) + ["SPY"]
prices = yf.download(all_tickers, period="5d", progress=False)["Close"]
returns_map = (prices.iloc[-1] - prices.iloc[0]) / prices.iloc[0] * 100

test("yfinance download succeeded", not prices.empty)
test("SPY data present", "SPY" in prices.columns)
spy_return = float(returns_map["SPY"])
test(f"SPY return is numeric ({spy_return:+.2f}%)", isinstance(spy_return, float))

# Check how many tickers got data
tickers_with_data = sum(1 for t in ticker_symbols if pd.notna(returns_map.get(t)))
test(f"Tickers with return data ({tickers_with_data}/{len(ticker_symbols)})", tickers_with_data > 0)


# ── Account Analysis ────────────────────────────────────────────────────────

section("5. Account Analysis (analyze_account)")

for account_name, df in accounts_parsed:
    results_df, total_value, portfolio_alpha, portfolio_return = main_module.analyze_account(df, returns_map, spy_return)

    test(f"  {account_name}", True)
    test(f"    total value > 0 (${total_value:,.0f})", total_value > 0)
    test(f"    results_df has rows ({len(results_df)})", len(results_df) > 0)
    test(f"    has Weight column", "Weight (%)" in results_df.columns)
    test(f"    has Alpha column", "Alpha (%)" in results_df.columns)
    test(f"    has Risk column", "Risk" in results_df.columns)
    test(f"    weights sum to ~100%",
         abs(results_df["Weight (%)"].sum() - 100) < 0.1,
         f"got {results_df['Weight (%)'].sum():.2f}%")
    test(f"    portfolio_alpha is numeric ({portfolio_alpha:+.2f}%)", isinstance(portfolio_alpha, (int, float)))
    test(f"    portfolio_return is numeric ({portfolio_return:+.2f}%)", isinstance(portfolio_return, (int, float)))

    # Concentration risk flags
    critical = results_df[results_df["Risk"] == "CRITICAL"]
    warning = results_df[results_df["Risk"] == "WARNING"]
    for _, r in critical.iterrows():
        test(f"    CRITICAL flag correct: {r['Symbol']} at {r['Weight (%)']:.1f}%", r["Weight (%)"] > 20)
    for _, r in warning.iterrows():
        test(f"    WARNING flag correct: {r['Symbol']} at {r['Weight (%)']:.1f}%", 15 < r["Weight (%)"] <= 20)


# ── AI Summary Text ─────────────────────────────────────────────────────────

section("6. AI Summary Text (get_ai_summary_text)")

for account_name, df in accounts_parsed[:1]:  # test with first account only
    results_df, total_value, portfolio_alpha, portfolio_return = main_module.analyze_account(df, returns_map, spy_return)
    summary = main_module.get_ai_summary_text(account_name, results_df, total_value, portfolio_alpha, portfolio_return, spy_return)
    test("Summary text generated", len(summary) > 100)
    test("Contains account name", account_name in summary)
    test("Contains total value", "$" in summary)
    test("Contains SPY return", "SPY" in summary)
    test("Contains top holdings", "Top 5" in summary)


# ── AI Analysis (Gemini) ───────────────────────────────────────────────────

section("7. AI Analysis (Gemini)")

api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

if api_key:
    for account_name, df in accounts_parsed[:1]:  # test one account
        results_df, total_value, portfolio_alpha, portfolio_return = main_module.analyze_account(df, returns_map, spy_return)
        summary = main_module.get_ai_summary_text(account_name, results_df, total_value, portfolio_alpha, portfolio_return, spy_return)
        symbols = results_df["Symbol"].tolist()

        ai_results = main_module.get_ai_analysis_all([(account_name, summary, symbols)])
        recs, actions = ai_results[account_name]

        test("Recommendations returned", len(recs) > 10)
        test("Recommendations not error", "unavailable" not in recs.lower())
        test("Actions dict returned", isinstance(actions, dict))
        test(f"Actions count matches symbols ({len(actions)}/{len(symbols)})",
             len(actions) >= len(symbols) * 0.8)

        valid_actions = all(v in ("BUY", "HOLD", "SELL") for v in actions.values())
        test("All actions are BUY/HOLD/SELL", valid_actions)
else:
    skip("Gemini AI test", "GEMINI_API_KEY not set")

    # Test fallback behavior
    for account_name, df in accounts_parsed[:1]:
        results_df, total_value, portfolio_alpha, portfolio_return = main_module.analyze_account(df, returns_map, spy_return)
        symbols = results_df["Symbol"].tolist()

        old_key = os.environ.pop("GEMINI_API_KEY", None)
        old_key2 = os.environ.pop("GOOGLE_API_KEY", None)
        ai_results = main_module.get_ai_analysis_all([("test_account", "test", symbols)])
        recs, actions = ai_results["test_account"]
        if old_key:
            os.environ["GEMINI_API_KEY"] = old_key
        if old_key2:
            os.environ["GOOGLE_API_KEY"] = old_key2

        test("Fallback: returns skip message", "Skipped" in recs or "unavailable" in recs.lower())
        test("Fallback: all actions default to HOLD", all(v == "HOLD" for v in actions.values()))


# ── HTML Report Generation ──────────────────────────────────────────────────

section("8. HTML Report Generation")

for account_name, df in accounts_parsed[:1]:
    results_df, total_value, portfolio_alpha, portfolio_return = main_module.analyze_account(df, returns_map, spy_return)
    results_df["Action"] = "HOLD"

    html = main_module.build_html_section(
        account_name, results_df, total_value, portfolio_alpha, portfolio_return, spy_return,
        "- Test recommendation one\n- Test recommendation two\n- Test recommendation three"
    )

    test("HTML section generated", len(html) > 500)
    test("Contains account name", account_name in html)
    test("Contains table tags", "<table>" in html and "</table>" in html)
    test("Contains summary cards", "Account Value" in html)
    test("Contains alpha verdict", "Alpha Verdict" in html)
    test("Contains AI section", "AI Advisor" in html)
    test("Contains action badges", "badge" in html)

    # Check table rows
    row_count = html.count("<tr>") - 1  # minus header row
    test(f"Table rows match holdings ({row_count}/{len(results_df)})", row_count == len(results_df))


# ── Terminal Output (print_account) ─────────────────────────────────────────

section("9. Terminal Output (print_account)")

import io
from contextlib import redirect_stdout

for account_name, df in accounts_parsed[:1]:
    results_df, total_value, portfolio_alpha, portfolio_return = main_module.analyze_account(df, returns_map, spy_return)
    results_df["Action"] = "HOLD"

    buf = io.StringIO()
    with redirect_stdout(buf):
        main_module.print_account(account_name, results_df, total_value, portfolio_alpha, portfolio_return, spy_return)

    output = buf.getvalue()
    test("Terminal output generated", len(output) > 200)
    test("Contains account name", account_name in output)
    test("Contains SUMMARY", "SUMMARY" in output)
    test("Contains ALPHA VERDICT", "ALPHA VERDICT" in output)
    test("Contains SPY return", "SPY" in output)


# ── Dashboard Syntax Check ──────────────────────────────────────────────────

section("10. Dashboard (dashboard.py)")

result = subprocess.run(
    [sys.executable, "-c", "import py_compile; py_compile.compile('dashboard.py', doraise=True)"],
    capture_output=True, text=True
)
test("dashboard.py compiles without errors", result.returncode == 0, result.stderr.strip())


# ── Run Script Syntax Check ─────────────────────────────────────────────────

section("11. Launcher (run.py)")

result = subprocess.run(
    [sys.executable, "-c", "import py_compile; py_compile.compile('run.py', doraise=True)"],
    capture_output=True, text=True
)
test("run.py compiles without errors", result.returncode == 0, result.stderr.strip())


# ── Import Script Logic ─────────────────────────────────────────────────────

section("12. Import Script (import_csv.py)")

result = subprocess.run(
    [sys.executable, "-c", "import py_compile; py_compile.compile('import_csv.py', doraise=True)"],
    capture_output=True, text=True
)
test("import_csv.py compiles without errors", result.returncode == 0, result.stderr.strip())

# Simulate import with a temp file
tmp_dir = tempfile.mkdtemp()
try:
    # Create a fake Fidelity CSV in a temp "downloads" folder
    fake_csv = Path(tmp_dir) / "Portfolio_Positions_Test.csv"
    fake_csv.write_text(
        "Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value\n"
        "Z123,Test Account,AAPL,APPLE INC,10,$150.00,\"$1,500.00\"\n"
    )
    test("Test CSV created for import simulation", fake_csv.exists())

    # Parse it with parse_csv to validate format
    account_name, df = main_module.parse_csv(fake_csv)
    test("Fake CSV parses correctly", account_name == "Test Account" and len(df) == 1)
    test("Fake CSV symbol correct", df.iloc[0]["Symbol"] == "AAPL")
finally:
    shutil.rmtree(tmp_dir)


# ── Reports Directory ──────────────────────────────────────────────────────

section("13. Reports Output")

REPORT_DIR = Path("reports")
test("reports/ directory exists", REPORT_DIR.is_dir())

html_files = list(REPORT_DIR.glob("*.html"))
test(f"HTML reports present ({len(html_files)} found)", len(html_files) > 0)

for f in html_files:
    content = f.read_text()
    test(f"  {f.name} is valid HTML", "<!DOCTYPE html>" in content and "</html>" in content)


# ── 401K Plan Fund Handling ─────────────────────────────────────────────────

section("14. 401K Plan Fund Handling")

k401_files = [f for f in csv_files if "401K" in f.name.upper()]
if k401_files:
    account_name, df = main_module.parse_csv(k401_files[0])
    plan_funds = df[df["Symbol"].str.contains(" ", na=False)]
    test(f"401K account parsed: {account_name}", bool(account_name))
    test(f"Plan funds detected ({len(plan_funds)})", len(plan_funds) > 0)
    for _, r in plan_funds.iterrows():
        test(f"  \"{r['Symbol']}\" has value (${r['Current Value']:,.0f})", r["Current Value"] > 0)

    results_df, total_value, _, _ = main_module.analyze_account(df, returns_map, spy_return)
    test(f"401K total value includes plan funds (${total_value:,.0f})", total_value > 500000)
    plan_in_results = results_df[results_df["Symbol"].str.contains(" ", na=False)]
    test(f"Plan funds in results ({len(plan_in_results)})", len(plan_in_results) > 0)
    for _, r in plan_in_results.iterrows():
        test(f"  \"{r['Symbol']}\" alpha is N/A (no ticker)", pd.isna(r["Alpha (%)"]))
else:
    skip("401K plan fund tests", "No 401K CSV found")


# ── Summary ─────────────────────────────────────────────────────────────────

section("RESULTS")

total = passed + failed + skipped
print(f"\n  {BOLD}{passed}{RESET} passed, ", end="")
if failed:
    print(f"\033[91m{BOLD}{failed}{RESET}\033[91m failed\033[0m, ", end="")
else:
    print(f"{BOLD}0{RESET} failed, ", end="")
print(f"{BOLD}{skipped}{RESET} skipped  ({total} total)")

if failed:
    print(f"\n  \033[91mSome tests failed. Review output above.\033[0m\n")
    sys.exit(1)
else:
    print(f"\n  \033[92mAll tests passed!\033[0m\n")
    sys.exit(0)
