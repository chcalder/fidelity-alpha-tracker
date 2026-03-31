#!/usr/bin/env python3
"""
Fidelity Alpha Tracker — Streamlit Dashboard
Interactive portfolio analytics with charts, filtering, and AI recommendations.
"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from alpha_core import (
    parse_csv,
    analyze_account,
    get_ai_summary_text,
    get_ai_analysis_all,
    load_ai_cache,
    DATA_DIR,
)

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fidelity Alpha Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Data loading (cached) ──────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner="Loading market data...")
def load_data(period):
    """Parse all CSVs, download market data, and analyze all accounts."""
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    if not csv_files:
        return None, None, None

    accounts_raw = []
    all_symbols = set()
    for csv_path in csv_files:
        account_name, df = parse_csv(csv_path)
        if df.empty:
            continue
        all_symbols.update(df["Symbol"].tolist())
        accounts_raw.append((account_name, df))

    ticker_symbols = {s for s in all_symbols if " " not in s and len(s) <= 12}

    all_tickers = sorted(ticker_symbols) + ["SPY"]
    prices = yf.download(all_tickers, period=period, progress=False)["Close"]
    returns_map = (prices.iloc[-1] - prices.iloc[0]) / prices.iloc[0] * 100
    spy_return = float(returns_map["SPY"])

    accounts = []
    for account_name, df in accounts_raw:
        results_df, total_value, portfolio_alpha, portfolio_return = analyze_account(df, returns_map, spy_return)
        accounts.append({
            "name": account_name,
            "results_df": results_df,
            "total_value": total_value,
            "portfolio_alpha": portfolio_alpha,
            "portfolio_return": portfolio_return,
        })

    return accounts, spy_return, returns_map


# ── Custom CSS ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.3rem; }
    .stDataFrame { border-radius: 8px; }
    div[data-testid="stExpander"] { border: 1px solid #2a2d3e; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Settings")

    period = st.selectbox(
        "Time Period",
        options=["5d", "1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y"],
        index=0,
        help="Select the lookback period for return calculations"
    )

    period_labels = {
        "5d": "5-Day", "1mo": "1-Month", "3mo": "3-Month", "6mo": "6-Month",
        "ytd": "Year-to-Date", "1y": "1-Year", "2y": "2-Year", "5y": "5-Year"
    }
    period_label = period_labels[period]

    st.divider()

    enable_ai = st.toggle(
        "AI Recommendations",
        value=bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        help="Requires GEMINI_API_KEY environment variable"
    )

    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── Load data ───────────────────────────────────────────────────────────────

accounts, spy_return, returns_map = load_data(period)

if accounts is None:
    st.error("No CSV files found in `data/` directory. Run `python run.py` to import from Fidelity.")
    st.stop()

# ── Header + Grand Summary ──────────────────────────────────────────────────

st.title("📊 Fidelity Alpha Tracker")

grand_total = sum(a["total_value"] for a in accounts)
grand_return = sum(a["portfolio_return"] * a["total_value"] for a in accounts) / grand_total if grand_total else 0
grand_alpha = sum(a["portfolio_alpha"] * a["total_value"] for a in accounts) / grand_total if grand_total else 0
total_holdings = sum(len(a["results_df"]) for a in accounts)

cols = st.columns(5)
cols[0].metric("Total Value", f"${grand_total:,.0f}")
cols[1].metric(f"{period_label} Return", f"{grand_return:+.2f}%",
               delta=f"{grand_return:+.2f}%",
               delta_color="normal")
cols[2].metric(f"SPY {period_label}", f"{spy_return:+.2f}%",
               delta=f"{spy_return:+.2f}%",
               delta_color="normal")
cols[3].metric("Alpha vs SPY", f"{grand_alpha:+.2f}%",
               delta=f"{grand_alpha:+.2f}%",
               delta_color="normal")
cols[4].metric("Accounts / Holdings", f"{len(accounts)} / {total_holdings}")

st.divider()

# ── Account selector ────────────────────────────────────────────────────────

account_names = ["All Accounts"] + [a["name"] for a in accounts]

with st.sidebar:
    st.divider()
    selected_account = st.radio(
        "📂 Account",
        account_names,
        index=0,
    )

if selected_account == "All Accounts":
    display_accounts = accounts
else:
    display_accounts = [a for a in accounts if a["name"] == selected_account]


# ── Combined allocation chart (all accounts) ───────────────────────────────

if selected_account == "All Accounts":
    # Account allocation pie
    acct_alloc = pd.DataFrame([
        {"Account": a["name"], "Value": a["total_value"]}
        for a in accounts
    ])
    fig_acct = px.pie(
        acct_alloc, values="Value", names="Account",
        title="Allocation by Account",
        hole=0.45,
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig_acct.update_traces(textinfo="label+percent", textposition="outside")
    fig_acct.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e1e4ed"),
        showlegend=False,
        margin=dict(t=40, b=20, l=20, r=20),
    )
    st.plotly_chart(fig_acct, use_container_width=True)

st.divider()

# ── Per-account sections ────────────────────────────────────────────────────

# AI analysis (try cache first, then single combined call for all displayed accounts)
if enable_ai:
    ai_key = f"ai_all_{period}_{'+'.join(a['name'] for a in display_accounts)}"
    if ai_key not in st.session_state:
        # Try loading cached results from the CLI report
        cached = load_ai_cache(period=period)
        if cached and all(a["name"] in cached for a in display_accounts):
            st.session_state[ai_key] = cached
        else:
            with st.spinner("Getting AI recommendations for all accounts (single call)..."):
                account_data_list = []
                for a in display_accounts:
                    summary = get_ai_summary_text(a["name"], a["results_df"], a["total_value"],
                                                  a["portfolio_alpha"], a["portfolio_return"], spy_return)
                    symbols = a["results_df"]["Symbol"].tolist()
                    account_data_list.append((a["name"], summary, symbols))
                st.session_state[ai_key] = get_ai_analysis_all(account_data_list)
    ai_results = st.session_state[ai_key]
else:
    ai_results = {}

for acct in display_accounts:
    name = acct["name"]
    rdf = acct["results_df"].copy()
    total_value = acct["total_value"]
    p_alpha = acct["portfolio_alpha"]
    p_return = acct["portfolio_return"]

    st.subheader(f"🏦 {name}")

    # Summary cards
    mc = st.columns(4)
    mc[0].metric("Account Value", f"${total_value:,.0f}")
    mc[1].metric(f"{period_label} Return", f"{p_return:+.2f}%")
    mc[2].metric("Alpha vs SPY", f"{p_alpha:+.2f}%",
                 delta=f"{p_alpha:+.2f}%", delta_color="normal")
    mc[3].metric("Holdings", len(rdf))

    # Apply AI results for this account
    if enable_ai and name in ai_results:
        recs, actions = ai_results[name]
        rdf["Action"] = rdf["Symbol"].map(actions).fillna("HOLD")
    else:
        rdf["Action"] = "HOLD"
        recs = None

    # Charts side by side
    chart_left, chart_right = st.columns(2)

    with chart_left:
        # Allocation pie chart
        fig_pie = px.pie(
            rdf, values="Current Value", names="Symbol",
            title="Holdings Allocation",
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig_pie.update_traces(textinfo="label+percent", textposition="outside")
        fig_pie.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e1e4ed"),
            showlegend=False,
            margin=dict(t=40, b=20, l=20, r=20),
            height=400,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with chart_right:
        # Alpha bar chart
        alpha_df = rdf.dropna(subset=["Alpha (%)"]).sort_values("Alpha (%)")
        colors = ["#34d399" if a > 0 else "#f87171" for a in alpha_df["Alpha (%)"]]
        fig_bar = go.Figure(go.Bar(
            x=alpha_df["Alpha (%)"],
            y=alpha_df["Symbol"],
            orientation="h",
            marker_color=colors,
            text=[f"{a:+.2f}%" for a in alpha_df["Alpha (%)"]],
            textposition="outside",
        ))
        fig_bar.update_layout(
            title=f"{period_label} Alpha vs SPY",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e1e4ed"),
            xaxis=dict(title="Alpha (%)", gridcolor="rgba(255,255,255,0.05)", zeroline=True,
                       zerolinecolor="rgba(255,255,255,0.2)"),
            yaxis=dict(title=""),
            margin=dict(t=40, b=40, l=10, r=60),
            height=400,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # Data table
    display_df = rdf.sort_values("Alpha (%)", ascending=False, na_position="last").copy()
    display_df["Current Value"] = display_df["Current Value"].apply(lambda x: f"${x:,.2f}")
    display_df["Weight (%)"] = display_df["Weight (%)"].apply(lambda x: f"{x:.1f}%")
    display_df["5-Day Return (%)"] = display_df["5-Day Return (%)"].apply(
        lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")
    display_df["Alpha (%)"] = display_df["Alpha (%)"].apply(
        lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")
    display_df["Weighted Alpha"] = display_df["Weighted Alpha"].apply(
        lambda x: f"{x:+.4f}%" if pd.notna(x) else "N/A")

    st.dataframe(
        display_df[["Symbol", "Quantity", "Current Value", "Weight (%)",
                     "5-Day Return (%)", "Alpha (%)", "Weighted Alpha", "Risk", "Action"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Symbol": st.column_config.TextColumn("Symbol", width="small"),
            "Action": st.column_config.TextColumn("Action", width="small"),
            "Risk": st.column_config.TextColumn("Risk", width="small"),
        },
    )

    # Alpha verdict
    if p_alpha > 0:
        st.success(f"**✓ Alpha Verdict:** Your stock picks beat the S&P 500 by {p_alpha:+.2f}% — active management is adding value.")
    elif p_alpha == 0:
        st.info("**— Alpha Verdict:** Your portfolio matched the S&P 500 exactly.")
    else:
        diff_dollar = total_value * abs(p_alpha) / 100
        st.error(f"**✗ Alpha Verdict:** You underperformed SPY by {abs(p_alpha):.2f}% (≈${diff_dollar:,.0f}). You would have been better off just buying SPY over this period.")

    # Concentration risk alerts
    concentrated = rdf[rdf["Risk"] != ""].sort_values("Weight (%)", ascending=False)
    if not concentrated.empty:
        for _, r in concentrated.iterrows():
            if r["Risk"] == "CRITICAL":
                st.error(f"🔴 **CRITICAL** — {r['Symbol']} at {r['Weight (%)']:.1f}% of account")
            else:
                st.warning(f"🟡 **WARNING** — {r['Symbol']} at {r['Weight (%)']:.1f}% of account")

    # AI recommendations
    if recs:
        with st.expander("🤖 AI Advisor Recommendations (Gemini 2.5 Flash)", expanded=True):
            st.markdown(recs)

    st.divider()
