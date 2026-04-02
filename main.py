#!/usr/bin/env python3
"""
Fidelity 5-Day Alpha Calculator — Multi-Account
Reads all Fidelity CSVs in data/, fetches 5-day prices via yfinance,
calculates alpha vs SPY, and outputs a consolidated HTML report.
"""

import html as html_module
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

import os

from alpha_core import (
    parse_csv,
    analyze_account,
    get_ai_summary_text,
    get_ai_analysis_all,
    get_rule_based_analysis_all,
    save_ai_cache,
    DATA_DIR,
    REPORT_DIR,
)

# ── Terminal colors ─────────────────────────────────────────────────────────
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"







def print_account(account_name, results_df, total_value, portfolio_alpha, portfolio_return, spy_return):
    """Print a single account's report to the terminal."""
    print(f"\n{BOLD}{'═' * 105}{RESET}")
    print(f"{BOLD}  {account_name}{RESET}")
    print(f"{BOLD}{'═' * 105}{RESET}")

    header = (f"{'Symbol':<7} {'Qty':>10} {'Value':>13} {'Weight':>8} "
              f"{'5d Ret':>9} {'Alpha':>9} {'Wtd Alpha':>10}  {'Risk':<12} {'Action'}")
    print(f"\n{DIM}{header}{RESET}")
    print(f"{DIM}{'─' * 105}{RESET}")

    for _, r in results_df.sort_values("Alpha (%)", ascending=False, na_position="last").iterrows():
        ret = r["5-Day Return (%)"]
        alpha = r["Alpha (%)"]
        walpha = r["Weighted Alpha"]
        ret_str = f"{ret:>+8.2f}%" if pd.notna(ret) else "      N/A"
        alpha_str = f"{alpha:>+8.2f}%" if pd.notna(alpha) else "      N/A"
        walpha_str = f"{walpha:>+9.4f}%" if pd.notna(walpha) else "       N/A"

        a_color = GREEN if pd.notna(alpha) and alpha > 0 else RED if pd.notna(alpha) else ""
        a_reset = RESET if a_color else ""

        risk = r["Risk"]
        if risk == "CRITICAL":
            risk_str = f"{RED}{BOLD}▓▓ CRITICAL{RESET}"
        elif risk == "WARNING":
            risk_str = f"{YELLOW}▒▒ WARNING{RESET}"
        else:
            risk_str = f"{DIM}  ·        {RESET}"

        action = r.get("Action", "HOLD")
        if action == "BUY":
            action_str = f"{GREEN}{BOLD}  BUY{RESET}"
        elif action == "SELL":
            action_str = f"{RED}{BOLD}  SELL{RESET}"
        else:
            action_str = f"{DIM}  HOLD{RESET}"

        print(f"{CYAN}{r['Symbol']:<7}{RESET} {r['Quantity']:>10.4f} "
              f"${r['Current Value']:>12,.2f} {r['Weight (%)']:>7.1f}% "
              f"{a_color}{ret_str}{a_reset} {a_color}{alpha_str}{a_reset} "
              f"{a_color}{walpha_str}{a_reset}  {risk_str} {action_str}")

    print(f"{DIM}{'─' * 105}{RESET}")

    pa_color = GREEN if portfolio_alpha > 0 else RED
    pr_color = GREEN if portfolio_return > 0 else RED
    spy_color = GREEN if spy_return > 0 else RED

    print(f"\n{BOLD}  SUMMARY{RESET}")
    print(f"  {'Account Value:':<30} ${total_value:>14,.2f}")
    print(f"  {'Account 5-Day Return:':<30} {pr_color}{portfolio_return:>+14.2f}%{RESET}")
    print(f"  {'S&P 500 (SPY) 5-Day Return:':<30} {spy_color}{spy_return:>+14.2f}%{RESET}")
    print(f"  {'Account Alpha:':<30} {pa_color}{BOLD}{portfolio_alpha:>+14.2f}%{RESET}")

    # Alpha verdict
    print(f"\n{BOLD}  ALPHA VERDICT{RESET}")
    if portfolio_alpha > 0:
        print(f"  {GREEN}✓ Your stock picks beat the S&P 500 by {portfolio_alpha:+.2f}% — active management is adding value.{RESET}")
    elif portfolio_alpha == 0:
        print(f"  {YELLOW}— Your portfolio matched the S&P 500 exactly.{RESET}")
    else:
        diff_dollar = total_value * abs(portfolio_alpha) / 100
        print(f"  {RED}✗ You underperformed SPY by {abs(portfolio_alpha):.2f}% (≈${diff_dollar:,.0f}).")
        print(f"    You would have been better off just buying SPY over this period.{RESET}")

    concentrated = results_df[results_df["Risk"] != ""].sort_values("Weight (%)", ascending=False)
    if not concentrated.empty:
        print(f"\n{BOLD}  CONCENTRATION RISK ALERTS{RESET}")
        for _, r in concentrated.iterrows():
            tag = f"{RED}{BOLD}CRITICAL{RESET}" if r["Risk"] == "CRITICAL" else f"{YELLOW}WARNING{RESET}"
            print(f"  {tag}  {CYAN}{r['Symbol']:<6}{RESET}  {r['Weight (%)']:.1f}% of account")





def build_html_table_rows(results_df):
    """Build HTML table rows for one account."""
    sorted_df = results_df.sort_values("Alpha (%)", ascending=False, na_position="last")
    rows = ""
    for _, r in sorted_df.iterrows():
        ret = r["5-Day Return (%)"]
        alpha = r["Alpha (%)"]
        walpha = r["Weighted Alpha"]
        weight = r["Weight (%)"]
        ret_str = f"{ret:+.2f}%" if pd.notna(ret) else "N/A"
        alpha_str = f"{alpha:+.2f}%" if pd.notna(alpha) else "N/A"
        walpha_str = f"{walpha:+.4f}%" if pd.notna(walpha) else "N/A"
        alpha_class = "positive" if pd.notna(alpha) and alpha > 0 else "negative" if pd.notna(alpha) else ""
        ret_class = "positive" if pd.notna(ret) and ret > 0 else "negative" if pd.notna(ret) else ""

        if r["Risk"] == "CRITICAL":
            risk_badge = '<span class="badge critical">CRITICAL</span>'
        elif r["Risk"] == "WARNING":
            risk_badge = '<span class="badge warning">WARNING</span>'
        else:
            risk_badge = "<span class='muted'>—</span>"

        bar_width = min(weight, 100)

        action = r.get("Action", "HOLD")
        if action == "BUY":
            action_badge = '<span class="badge buy">BUY</span>'
        elif action == "SELL":
            action_badge = '<span class="badge sell">SELL</span>'
        else:
            action_badge = '<span class="badge hold">HOLD</span>'

        rows += f"""        <tr>
          <td class="symbol">{r['Symbol']}</td>
          <td class="num">{r['Quantity']:,.4f}</td>
          <td class="num">${r['Current Value']:,.2f}</td>
          <td class="num">
            <div class="weight-cell">
              <span>{weight:.1f}%</span>
              <div class="weight-bar" style="width:{bar_width}%"></div>
            </div>
          </td>
          <td class="num {ret_class}">{ret_str}</td>
          <td class="num {alpha_class}">{alpha_str}</td>
          <td class="num {alpha_class}">{walpha_str}</td>
          <td class="center">{risk_badge}</td>
          <td class="center">{action_badge}</td>
        </tr>
"""
    return rows


def build_html_section(account_name, results_df, total_value, portfolio_alpha, portfolio_return,
                       spy_return, ai_recommendations, analysis_source="Gemini 2.5 Flash"):
    """Build one account section for the HTML report."""
    pa_class = "positive" if portfolio_alpha > 0 else "negative"
    pr_class = "positive" if portfolio_return > 0 else "negative"
    spy_class = "positive" if spy_return > 0 else "negative"
    table_rows = build_html_table_rows(results_df)

    ai_bullets = ""
    for line in ai_recommendations.split("\n"):
        line = line.strip().lstrip("- ").lstrip("* ").strip()
        if line:
            ai_bullets += f"        <li>{html_module.escape(line)}</li>\n"

    # Alpha verdict text
    if portfolio_alpha > 0:
        verdict_color = "color:var(--green)"
        verdict_text = f"✓ Your stock picks beat the S&amp;P 500 by {portfolio_alpha:+.2f}% &mdash; active management is adding value."
    elif portfolio_alpha < 0:
        verdict_color = "color:var(--red)"
        diff = total_value * abs(portfolio_alpha) / 100
        verdict_text = f"✗ You underperformed SPY by {abs(portfolio_alpha):.2f}% (&asymp;${diff:,.0f}). You would have been better off just buying SPY over this period."
    else:
        verdict_color = "color:var(--muted)"
        verdict_text = "&mdash; Your portfolio matched the S&amp;P 500 exactly."

    return f"""
  <div class="account-section">
    <h2 class="account-title">{html_module.escape(account_name)}</h2>

    <div class="summary">
      <div class="card">
        <div class="label">Account Value</div>
        <div class="value">${total_value:,.0f}</div>
      </div>
      <div class="card">
        <div class="label">5-Day Return</div>
        <div class="value {pr_class}">{portfolio_return:+.2f}%</div>
      </div>
      <div class="card">
        <div class="label">SPY 5-Day Return</div>
        <div class="value {spy_class}">{spy_return:+.2f}%</div>
      </div>
      <div class="card">
        <div class="label">Alpha</div>
        <div class="value {pa_class}">{portfolio_alpha:+.2f}%</div>
      </div>
      <div class="card">
        <div class="label">Holdings</div>
        <div class="value">{len(results_df)}</div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th class="num">Quantity</th>
          <th class="num">Current Value</th>
          <th class="num">Weight</th>
          <th class="num">5-Day Return</th>
          <th class="num">Alpha</th>
          <th class="num">Wtd Alpha</th>
          <th class="center">Risk</th>
          <th class="center">Action</th>
        </tr>
      </thead>
      <tbody>
{table_rows}      </tbody>
    </table>

    <div class="alpha-verdict" style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1rem 1.5rem;margin-top:1.5rem;">
      <h3 style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--muted);margin-bottom:0.5rem;">Alpha Verdict</h3>
      <p style="font-size:0.9rem;line-height:1.6;{verdict_color};">{verdict_text}</p>
    </div>

    <div class="ai-section">
      <h3>Advisor Recommendations <span class="ai-badge">{analysis_source}</span></h3>
      <ul>
{ai_bullets}      </ul>
    </div>
  </div>
"""


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════
csv_files = sorted(DATA_DIR.glob("*.csv"))
if not csv_files:
    print("No CSV files found in data/")
    exit(1)

# Parse all accounts and collect unique symbols
accounts = []
all_symbols = set()
for csv_path in csv_files:
    account_name, df = parse_csv(csv_path)
    if df.empty:
        continue
    all_symbols.update(df["Symbol"].tolist())
    accounts.append((account_name, df, csv_path))

print(f"Found {len(accounts)} account(s), {len(all_symbols)} unique symbols")

# Filter to only real ticker symbols (no spaces, reasonable length) for yfinance
ticker_symbols = {s for s in all_symbols if " " not in s and len(s) <= 12}
non_ticker_symbols = all_symbols - ticker_symbols
if non_ticker_symbols:
    print(f"  ({len(non_ticker_symbols)} plan fund(s) without tickers — values included, returns N/A)")

# Single bulk download for all symbols + SPY
all_tickers = sorted(ticker_symbols) + ["SPY"]
prices = yf.download(all_tickers, period="5d", progress=False)["Close"]
returns_map = (prices.iloc[-1] - prices.iloc[0]) / prices.iloc[0] * 100
spy_return = returns_map["SPY"]

# Process each account
report_date = datetime.now().strftime("%m%d%Y")
display_date = datetime.now().strftime("%B %d, %Y")
html_sections = ""
grand_total_value = 0
grand_weighted_return = 0
grand_weighted_alpha = 0
account_results = []

for account_name, df, csv_path in accounts:
    results_df, total_value, portfolio_alpha, portfolio_return = analyze_account(df, returns_map, spy_return)

    # Collect data for AI call
    summary_text = get_ai_summary_text(account_name, results_df, total_value, portfolio_alpha, portfolio_return, spy_return)
    symbols = results_df["Symbol"].tolist()
    account_results.append((account_name, df, csv_path, results_df, total_value, portfolio_alpha, portfolio_return, summary_text, symbols))

# Determine analysis mode: Gemini if API key is set, otherwise rule-based
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if api_key:
    print("Requesting AI analysis for all accounts (Gemini)...")
    account_summaries = [(name, summary, syms) for name, _, _, _, _, _, _, summary, syms in account_results]
    ai_results = get_ai_analysis_all(account_summaries)
    analysis_source = "Gemini 2.5 Flash"
else:
    print("No API key set — using rule-based analysis...")
    account_data = [(name, rdf, tv, pa, pr, spy_return)
                    for name, _, _, rdf, tv, pa, pr, _, _ in account_results]
    ai_results = get_rule_based_analysis_all(account_data)
    analysis_source = "Rule-Based"

# Cache results for dashboard reuse
save_ai_cache(ai_results, period="5d")
print(f"Analysis results cached ({analysis_source}).")

# Now output results per account
for account_name, df, csv_path, results_df, total_value, portfolio_alpha, portfolio_return, _, _ in account_results:
    ai_recs, actions = ai_results.get(account_name, ("[AI unavailable]", {}))

    results_df["Action"] = results_df["Symbol"].map(actions).fillna("HOLD")

    # Terminal output
    print_account(account_name, results_df, total_value, portfolio_alpha, portfolio_return, spy_return)
    print(f"\n{BOLD}  ADVISOR RECOMMENDATIONS ({analysis_source}){RESET}")
    print(f"{DIM}  {'─' * 70}{RESET}")
    for line in ai_recs.split("\n"):
        line = line.strip()
        if line:
            print(f"  {line}")

    # HTML section
    html_sections += build_html_section(account_name, results_df, total_value,
                                        portfolio_alpha, portfolio_return, spy_return, ai_recs,
                                        analysis_source)

    # Accumulate grand totals
    grand_total_value += total_value
    grand_weighted_return += portfolio_return * total_value
    grand_weighted_alpha += portfolio_alpha * total_value

# Grand portfolio totals
if grand_total_value > 0:
    grand_return = grand_weighted_return / grand_total_value
    grand_alpha = grand_weighted_alpha / grand_total_value
else:
    grand_return = grand_alpha = 0

ga_class = "positive" if grand_alpha > 0 else "negative"
gr_class = "positive" if grand_return > 0 else "negative"
spy_class = "positive" if spy_return > 0 else "negative"

# Print grand summary
print(f"\n{BOLD}{'═' * 95}{RESET}")
print(f"{BOLD}  COMBINED PORTFOLIO SUMMARY ({len(accounts)} accounts){RESET}")
print(f"{BOLD}{'═' * 95}{RESET}")
pa_color = GREEN if grand_alpha > 0 else RED
pr_color = GREEN if grand_return > 0 else RED
spy_color = GREEN if spy_return > 0 else RED
print(f"  {'Total Value (all accounts):':<30} ${grand_total_value:>14,.2f}")
print(f"  {'Combined 5-Day Return:':<30} {pr_color}{grand_return:>+14.2f}%{RESET}")
print(f"  {'S&P 500 (SPY) 5-Day Return:':<30} {spy_color}{spy_return:>+14.2f}%{RESET}")
print(f"  {'Combined Alpha:':<30} {pa_color}{BOLD}{grand_alpha:>+14.2f}%{RESET}")
print()

# ── Generate consolidated HTML ──────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alpha Report — All Accounts — {display_date}</title>
<style>
  :root {{
    --bg: #0f1117;
    --card: #1a1d2e;
    --border: #2a2d3e;
    --text: #e1e4ed;
    --muted: #8b8fa3;
    --green: #34d399;
    --red: #f87171;
    --accent: #818cf8;
    --yellow: #fbbf24;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 2rem;
    line-height: 1.5;
  }}
  .container {{ max-width: 1000px; margin: 0 auto; }}
  header {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }}
  h1 {{ font-size: 1.4rem; font-weight: 600; }}
  .date {{ color: var(--muted); font-size: 0.85rem; }}
  .summary {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
  }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.2rem;
  }}
  .card .label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
  .card .value {{ font-size: 1.4rem; font-weight: 700; margin-top: 0.2rem; }}
  .account-section {{
    margin-bottom: 3rem;
    padding-top: 2rem;
    border-top: 1px solid var(--border);
  }}
  .account-section:first-of-type {{ border-top: none; padding-top: 0; }}
  .account-title {{
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--accent);
    margin-bottom: 1rem;
    text-transform: none;
    letter-spacing: 0;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: var(--card);
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--border);
  }}
  th {{
    text-align: left;
    padding: 0.6rem 0.8rem;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    background: var(--card);
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 0.5rem 0.8rem;
    font-size: 0.82rem;
    border-bottom: 1px solid var(--border);
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ background: rgba(129, 140, 248, 0.04); }}
  .symbol {{ font-weight: 600; color: var(--accent); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  th.num {{ text-align: right; }}
  .positive {{ color: var(--green); }}
  .negative {{ color: var(--red); }}
  .center {{ text-align: center; }}
  .muted {{ color: var(--muted); }}
  .badge {{
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }}
  .badge.critical {{ background: rgba(248, 113, 113, 0.15); color: var(--red); border: 1px solid rgba(248, 113, 113, 0.3); }}
  .badge.warning {{ background: rgba(251, 191, 36, 0.15); color: var(--yellow); border: 1px solid rgba(251, 191, 36, 0.3); }}
  .badge.buy {{ background: rgba(52, 211, 153, 0.15); color: var(--green); border: 1px solid rgba(52, 211, 153, 0.3); }}
  .badge.sell {{ background: rgba(248, 113, 113, 0.15); color: var(--red); border: 1px solid rgba(248, 113, 113, 0.3); }}
  .badge.hold {{ background: rgba(139, 143, 163, 0.1); color: var(--muted); border: 1px solid rgba(139, 143, 163, 0.2); }}
  .weight-cell {{ position: relative; }}
  .weight-cell span {{ position: relative; z-index: 1; }}
  .weight-bar {{
    position: absolute;
    top: 0; left: 0; bottom: 0;
    background: rgba(129, 140, 248, 0.08);
    border-radius: 3px;
  }}
  h2 {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin: 1.5rem 0 0.75rem; }}
  .ai-section {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.2rem 1.5rem;
    margin-top: 1.5rem;
  }}
  .ai-section h3 {{
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-bottom: 0.75rem;
  }}
  .ai-section ul {{ list-style: none; padding: 0; }}
  .ai-section li {{
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.85rem;
    line-height: 1.6;
  }}
  .ai-section li:last-child {{ border-bottom: none; }}
  .ai-section li::before {{
    content: '\\27A4';
    margin-right: 0.6rem;
    color: var(--accent);
  }}
  .ai-badge {{
    display: inline-block;
    background: rgba(129, 140, 248, 0.12);
    border: 1px solid rgba(129, 140, 248, 0.25);
    color: var(--accent);
    font-size: 0.55rem;
    font-weight: 600;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-left: 0.5rem;
    vertical-align: middle;
  }}
  footer {{
    text-align: center;
    margin-top: 2rem;
    font-size: 0.75rem;
    color: var(--muted);
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Fidelity Alpha Report — All Accounts</h1>
    <span class="date">{display_date}</span>
  </header>

  <div class="summary">
    <div class="card">
      <div class="label">Total Value ({len(accounts)} accounts)</div>
      <div class="value">${grand_total_value:,.0f}</div>
    </div>
    <div class="card">
      <div class="label">Combined 5-Day Return</div>
      <div class="value {gr_class}">{grand_return:+.2f}%</div>
    </div>
    <div class="card">
      <div class="label">SPY 5-Day Return</div>
      <div class="value {spy_class}">{spy_return:+.2f}%</div>
    </div>
    <div class="card">
      <div class="label">Combined Alpha</div>
      <div class="value {ga_class}">{grand_alpha:+.2f}%</div>
    </div>
  </div>

{html_sections}

  <footer>
    Generated from Fidelity exports &middot; Benchmark: SPY &middot; Data via yfinance &middot; AI by Google Gemini
  </footer>
</div>
</body>
</html>"""

output_file = REPORT_DIR / f"{report_date}_All_Accounts.html"
output_file.write_text(html)
print(f"HTML report saved to: {output_file}")
