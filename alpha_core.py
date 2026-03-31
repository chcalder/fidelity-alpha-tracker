#!/usr/bin/env python3
"""
Fidelity Alpha Tracker — Shared Core
Common functions used by both main.py (CLI/report) and dashboard.py (Streamlit).
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)

AI_CACHE_FILE = REPORT_DIR / "ai_cache.json"


# ── CSV parsing ─────────────────────────────────────────────────────────────

def parse_csv(csv_path):
    """Parse a Fidelity CSV and return account_name, filtered DataFrame."""
    df = pd.read_csv(csv_path, index_col=False)
    account_name = (df["Account Name"].dropna().iloc[0] or "").strip()

    df = df[pd.to_numeric(df["Quantity"], errors="coerce").notna()].copy()
    df = df[df["Current Value"].replace(r"[\$,]", "", regex=True).apply(
        lambda x: pd.to_numeric(x, errors="coerce")).notna()]

    df = df[~df["Symbol"].fillna("").str.contains(r"\*|Pending", case=False)]
    df = df[~df["Description"].fillna("").str.match(r"^HELD IN MONEY MARKET$", case=False)]

    df["Symbol"] = df.apply(
        lambda r: r["Symbol"] if pd.notna(r["Symbol"]) and str(r["Symbol"]).strip()
        else str(r["Description"]).strip(), axis=1)

    df["Quantity"] = pd.to_numeric(df["Quantity"])
    df["Current Value"] = df["Current Value"].replace(r"[\$,]", "", regex=True).astype(float)

    return account_name, df


# ── Account analysis ────────────────────────────────────────────────────────

def analyze_account(df, returns_map, spy_return):
    """Build results table with concentration risk and portfolio-level stats."""
    total_value = df["Current Value"].sum()

    results = []
    for _, row in df.iterrows():
        sym = row["Symbol"]
        ret = returns_map.get(sym)
        alpha = ret - spy_return if pd.notna(ret) else None
        weight = row["Current Value"] / total_value * 100 if total_value else 0

        if weight > 20:
            risk_flag = "CRITICAL"
        elif weight > 15:
            risk_flag = "WARNING"
        else:
            risk_flag = ""

        results.append({
            "Symbol": sym,
            "Quantity": row["Quantity"],
            "Current Value": row["Current Value"],
            "Weight (%)": round(weight, 2),
            "5-Day Return (%)": round(ret, 2) if pd.notna(ret) else None,
            "Alpha (%)": round(alpha, 2) if alpha is not None else None,
            "Weighted Alpha": round(alpha * weight / 100, 4) if alpha is not None else None,
            "Risk": risk_flag,
        })

    results_df = pd.DataFrame(results)
    valid = results_df.dropna(subset=["Alpha (%)"])
    portfolio_alpha = valid["Weighted Alpha"].sum() if not valid.empty else 0
    portfolio_return = (valid["5-Day Return (%)"] * valid["Weight (%)"] / 100).sum() if not valid.empty else 0

    return results_df, total_value, portfolio_alpha, portfolio_return


# ── AI summary text ─────────────────────────────────────────────────────────

def get_ai_summary_text(account_name, results_df, total_value, portfolio_alpha, portfolio_return, spy_return):
    """Build the text summary sent to Gemini for one account."""
    concentrated = results_df[results_df["Risk"] != ""].sort_values("Weight (%)", ascending=False)
    risk_lines = []
    for _, r in concentrated.iterrows():
        risk_lines.append(f"  {r['Risk']}: {r['Symbol']} at {r['Weight (%)']:.1f}%")

    text = (
        f"Account: {account_name}\n"
        f"Total Value: ${total_value:,.2f}\n"
        f"5-Day Return: {portfolio_return:+.2f}%\n"
        f"SPY 5-Day Return: {spy_return:+.2f}%\n"
        f"Alpha: {portfolio_alpha:+.2f}%\n"
        f"\nConcentration Risk:\n" + ("\n".join(risk_lines) if risk_lines else "  None") + "\n"
        f"\nTop 5 Holdings:\n"
    )
    for _, r in results_df.nlargest(5, "Weight (%)").iterrows():
        ret_val = r["5-Day Return (%)"]
        alpha_val = r["Alpha (%)"]
        ret_str = f"{ret_val:+.2f}%" if pd.notna(ret_val) else "N/A"
        alpha_str = f"{alpha_val:+.2f}%" if pd.notna(alpha_val) else "N/A"
        text += f"  {r['Symbol']}: {r['Weight (%)']:.1f}% weight, 5d return {ret_str}, alpha {alpha_str}\n"
    return text


# ── Gemini AI analysis ──────────────────────────────────────────────────────

def _call_gemini(client, prompt, max_retries=2):
    """Call Gemini with automatic retry on rate limit."""
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) and attempt < max_retries:
                wait = 60 * (attempt + 1)
                print(f"  [Rate limited — waiting {wait}s before retry...]")
                time.sleep(wait)
            else:
                raise


def get_ai_analysis_all(account_summaries):
    """Single Gemini call for ALL accounts. Returns dict of account_name -> (recs_text, actions_dict).
    account_summaries: list of (account_name, summary_text, symbols_list)
    """
    try:
        import google.genai as genai
    except ImportError:
        return {name: ("[AI unavailable — google-genai not installed.]", {s: "HOLD" for s in syms})
                for name, _, syms in account_summaries}

    # Build default results for every account
    defaults = {}
    for name, _, symbols in account_summaries:
        defaults[name] = ("[AI unavailable]", {s: "HOLD" for s in symbols})

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        for name, _, symbols in account_summaries:
            defaults[name] = (
                "[Skipped] Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable to enable AI recommendations.",
                {s: "HOLD" for s in symbols},
            )
        return defaults

    client = genai.Client(api_key=api_key)

    # Build combined prompt with all accounts
    accounts_block = ""
    for name, summary, symbols in account_summaries:
        accounts_block += (
            f"--- ACCOUNT: {name} ---\n"
            f"{summary}\n"
            f"Tickers: {', '.join(symbols)}\n\n"
        )

    prompt = (
        "You are a conservative wealth advisor. I will give you data for MULTIPLE "
        "investment accounts. For EACH account, provide recommendations and actions.\n\n"
        "Rules for RECOMMENDATIONS (3 bullets per account):\n"
        "- If a stock is in the CRITICAL zone (>20% concentration), suggest specific "
        "trimming targets (e.g. reduce to 10-15%).\n"
        "- If a stock is in the WARNING zone (>15% concentration), flag the risk and "
        "suggest a target weight.\n"
        "- If Portfolio Alpha is negative, suggest moving some funds to defensive "
        "positions like SCHD or FSTA.\n"
        "- Keep each bullet to 1-2 sentences. Be specific with ticker names and numbers.\n\n"
        "Rules for ACTIONS (one per ticker per account):\n"
        "- SELL: concentration >20% (CRITICAL), or strongly negative alpha with large weight.\n"
        "- BUY: positive alpha, low weight, and defensive/value characteristics.\n"
        "- HOLD: everything else.\n"
        "- For plan funds without return data, default to HOLD.\n\n"
        f"{accounts_block}"
        "RESPONSE FORMAT (follow EXACTLY for each account, repeat this block per account):\n"
        "ACCOUNT: <exact account name>\n"
        "RECOMMENDATIONS\n"
        "- first bullet\n"
        "- second bullet\n"
        "- third bullet\n"
        "ACTIONS\n"
        '{"TICKER": "ACTION", ...}\n\n'
    )

    try:
        text = _call_gemini(client, prompt)

        # Parse per-account blocks from response
        results = dict(defaults)
        blocks = re.split(r'(?:^|\n)\s*ACCOUNT:\s*', text, flags=re.IGNORECASE)
        for block in blocks:
            if not block.strip():
                continue
            lines = block.strip().split("\n", 1)
            block_name_raw = lines[0].strip().rstrip(":")
            block_body = lines[1] if len(lines) > 1 else ""

            # Match to known account names
            matched_name = None
            for name, _, _ in account_summaries:
                if name.lower() in block_name_raw.lower() or block_name_raw.lower() in name.lower():
                    matched_name = name
                    break
            if not matched_name:
                for name, _, _ in account_summaries:
                    name_words = set(name.lower().split())
                    block_words = set(block_name_raw.lower().split())
                    if name_words & block_words:
                        matched_name = name
                        break
            if not matched_name:
                continue

            # Find symbols list for this account
            acct_symbols = []
            for name, _, symbols in account_summaries:
                if name == matched_name:
                    acct_symbols = symbols
                    break
            default_actions = {s: "HOLD" for s in acct_symbols}

            # Split body into recommendations and actions
            if "ACTIONS" in block_body:
                parts = block_body.split("ACTIONS", 1)
                recs_part = parts[0]
                actions_part = parts[1] if len(parts) > 1 else ""
            elif "actions" in block_body.lower():
                idx = block_body.lower().index("actions")
                recs_part = block_body[:idx]
                actions_part = block_body[idx + 7:]
            else:
                recs_part = block_body
                actions_part = ""

            # Extract bullet lines for recommendations
            recs_lines = []
            for line in recs_part.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    recs_lines.append(line[2:].strip())
            recs_text = "\n".join(f"- {l}" for l in recs_lines) if recs_lines else recs_part.strip()

            # Parse actions JSON
            actions_dict = default_actions
            if actions_part.strip():
                json_text = actions_part.strip()
                if "```" in json_text:
                    json_text = json_text.split("```")[1] if json_text.startswith("```") else json_text
                    json_text = json_text.split("```")[0]
                    if json_text.startswith("json"):
                        json_text = json_text[4:]
                start = json_text.find("{")
                end = json_text.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        parsed = json.loads(json_text[start:end])
                        actions_dict = {k: v.upper() if v.upper() in ("BUY", "HOLD", "SELL") else "HOLD"
                                        for k, v in parsed.items()}
                    except json.JSONDecodeError:
                        pass

            results[matched_name] = (recs_text, actions_dict)

        return results

    except Exception as e:
        for name in defaults:
            defaults[name] = (f"[AI unavailable — {e}]", defaults[name][1])
        return defaults


# ── AI cache persistence ────────────────────────────────────────────────────

def save_ai_cache(ai_results, period="5d"):
    """Save AI results to a JSON cache file for reuse by the dashboard."""
    cache = {
        "timestamp": datetime.now().isoformat(),
        "period": period,
        "accounts": {},
    }
    for name, (recs_text, actions_dict) in ai_results.items():
        cache["accounts"][name] = {
            "recommendations": recs_text,
            "actions": actions_dict,
        }
    AI_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def load_ai_cache(period="5d", max_age_hours=24):
    """Load cached AI results if they exist and are fresh enough.
    Returns dict of account_name -> (recs_text, actions_dict), or None if stale/missing.
    """
    if not AI_CACHE_FILE.exists():
        return None

    try:
        cache = json.loads(AI_CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Check period matches
    if cache.get("period") != period:
        return None

    # Check freshness
    try:
        cached_time = datetime.fromisoformat(cache["timestamp"])
        age = datetime.now() - cached_time
        if age.total_seconds() > max_age_hours * 3600:
            return None
    except (KeyError, ValueError):
        return None

    # Reconstruct the results dict
    results = {}
    for name, data in cache.get("accounts", {}).items():
        results[name] = (data["recommendations"], data["actions"])

    return results if results else None
