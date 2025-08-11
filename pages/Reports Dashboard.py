import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import altair as alt
import time
import math
from datetime import date, timedelta

# ======================
# Config
# ======================
SHEET_ID = "1O39vIMeCq-Z5GEWzoMM4xjNwiQNCeBa-pzGdOvp2zwg"
ENFORCERS = ["Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"]
EXPECTED_HEADERS = ["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"]
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

st.set_page_config(page_title="Manager Dashboard", layout="wide")
st.title("📊 Manager Dashboard (All Enforcers)")

# ======================
# Auth & Sheet
# ======================
@st.cache_resource(show_spinner=False)
def get_spreadsheet():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], SCOPE
    )
    client = gspread.authorize(creds)
    for i in range(3):
        try:
            return client.open_by_key(SHEET_ID)
        except Exception:
            if i == 2:
                raise
            time.sleep(1.2)

spreadsheet = get_spreadsheet()

# ======================
# Category normalization
# ======================
def canonicalize_category(s: str) -> str:
    """Collapse variants into one canonical label so duplicates (like two 'III…') merge."""
    if not isinstance(s, str):
        s = str(s)
    s = " ".join(s.strip().split())  # trim + collapse spaces

    # Known long official names (canonical)
    CANON_II = "II. Surveillance, Investigation, Monitoring, Documentation, and Inspection"
    CANON_III = "III. Information, Education, and Communication (IEC) Campaign"
    CANON_I = "I. Issuance of Citation Tickets"
    CANON_IV = "IV. Other Tasks"

    # Map by prefix to be robust to little differences/typos
    if s.startswith("II. Surveillance"):
        return CANON_II
    if s.startswith("III. Information, Education"):
        return CANON_III
    if s.startswith("I. Issuance of Citation Tickets"):
        return CANON_I
    if s.startswith("IV. Other"):
        return CANON_IV

    # Fallback: leave as-is
    return s

# Short labels for legend (cleaner, fits mobile). Tooltip still shows full canonical.
CATEGORY_SHORT = {
    "I. Issuance of Citation Tickets": "I. Citation Tickets",
    "II. Surveillance, Investigation, Monitoring, Documentation, and Inspection": "II. Surveillance & Inspection",
    "III. Information, Education, and Communication (IEC) Campaign": "III. IEC Campaign",
    "IV. Other Tasks": "IV. Other Tasks",
}

# ======================
# Load data (cached)
# ======================
@st.cache_data(ttl=60)
def load_all():
    frames = []
    for title in ENFORCERS:
        try:
            ws = spreadsheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            continue
        recs = ws.get_all_records()
        if recs:
            frames.append(pd.DataFrame(recs))

    if not frames:
        df = pd.DataFrame(columns=EXPECTED_HEADERS)
    else:
        df = pd.concat(frames, ignore_index=True)

    if "Quantity" in df.columns:
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df["Month"] = df["Date"].dt.strftime("%Y-%m")

    # Normalize / merge duplicate categories
    if "Category" in df.columns:
        df["Category"] = df["Category"].apply(canonicalize_category)
        df["CategoryShort"] = df["Category"].map(lambda x: CATEGORY_SHORT.get(x, x))

    return df

df = load_all()

# ======================
# Controls (persisted)
# ======================
left, right = st.columns(2)
with left:
    view = st.radio("View", ["Daily", "Monthly"], horizontal=True)

if "enf_filter" not in st.session_state:
    st.session_state.enf_filter = []

with right:
    chosen = st.multiselect(
        "Filter Enforcers",
        ENFORCERS,
        default=st.session_state.enf_filter,
        key="enf_filter",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Select All"):
            st.session_state.enf_filter = ENFORCERS[:]
            chosen = st.session_state.enf_filter
    with c2:
        if st.button("Clear"):
            st.session_state.enf_filter = []
            chosen = st.session_state.enf_filter

effective_selection = chosen if chosen else ENFORCERS
dfv = df[df["Enforcer"].isin(effective_selection)] if not df.empty else df

if dfv.empty:
    st.info("No data to display for the current selection.")
    st.stop()

# ======================
# Helpers
# ======================
def kpi_badge(delta_val: float, unit: str = "%"):
    """Render a compact up/down badge with color."""
    if pd.isna(delta_val):
        return ""
    arrow = "↔︎"
    bg = "#F0F2F6"
    if delta_val > 0:
        arrow, bg = "⬆️", "#E7F6EC"
    elif delta_val < 0:
        arrow, bg = "⬇️", "#FDECEC"
    sign = "+" if delta_val > 0 else ""
    label = f"{sign}{delta_val:.1f}{unit}"
    st.markdown(
        f"<span style='background:{bg}; padding:4px 8px; border-radius:20px; "
        f"font-size:0.9rem;'>{arrow} {label}</span>",
        unsafe_allow_html=True,
    )

def percent_change(curr: float, prev: float):
    if prev in (0, None) or pd.isna(prev):
        return None
    return ((curr - prev) / prev) * 100.0

def download_filtered(name: str, frame: pd.DataFrame):
    st.download_button(
        f"⬇️ Download {name} CSV",
        frame.to_csv(index=False),
        f"{name.lower().replace(' ', '_')}.csv",
        "text/csv",
    )

# ======================
# DAILY VIEW
# ======================
if view == "Daily":
    if dfv["Date"].isna().all():
        st.info("No valid dates found in the data.")
        st.stop()

    min_d, max_d = dfv["Date"].min().date(), dfv["Date"].max().date()
    d1, d2 = st.date_input(
        "Date range",
        (min_d, max_d),
        min_value=min_d,
        max_value=max_d,
    )

    dfv = dfv[(dfv["Date"] >= pd.to_datetime(d1)) & (dfv["Date"] <= pd.to_datetime(d2))]
    if dfv.empty:
        st.info("No data in the selected date range.")
        st.stop()

    # KPI calculations (Daily)
    total_today = int(dfv["Quantity"].sum())
    # previous day window (same length as selected range, shifted back)
    span_days = (pd.to_datetime(d2) - pd.to_datetime(d1)).days + 1
    prev_start = pd.to_datetime(d1) - pd.Timedelta(days=span_days)
    prev_end = pd.to_datetime(d1) - pd.Timedelta(days=1)
    prev_df = df[(df["Enforcer"].isin(effective_selection)) &
                 (df["Date"] >= prev_start) & (df["Date"] <= prev_end)]
    total_prev = int(prev_df["Quantity"].sum()) if not prev_df.empty else 0
    pct_vs_yday = percent_change(total_today, total_prev)

    # Most productive enforcer
    prod = (
        dfv.groupby("Enforcer", as_index=False)["Quantity"]
        .sum()
        .sort_values("Quantity", ascending=False)
    )
    top_enforcer = prod.iloc[0]["Enforcer"] if not prod.empty else "—"
    top_enforcer_actions = int(prod.iloc[0]["Quantity"]) if not prod.empty else 0

    # % of enforcers active
    pct_active = 100.0 * (dfv["Enforcer"].nunique() / len(effective_selection)) if len(effective_selection) else 0.0

    # YTD cumulative (for selected enforcers)
    year_start = pd.to_datetime(date.today().replace(month=1, day=1))
    ytd_df = df[(df["Enforcer"].isin(effective_selection)) & (df["Date"] >= year_start)]
    ytd_total = int(ytd_df["Quantity"].sum()) if not ytd_df.empty else 0

    # KPIs row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.caption("Most productive enforcer")
        st.subheader(f"{top_enforcer}")
        kpi_badge(top_enforcer_actions, unit=" actions")
    with c2:
        st.caption("% of enforcers active")
        st.subheader(f"{pct_active:.1f}%")
    with c3:
        st.caption("Change vs yesterday")
        st.subheader(f"{total_today} actions")
        if pct_vs_yday is not None:
            kpi_badge(pct_vs_yday)
    with c4:
        st.caption("Cumulative total (YTD)")
        st.subheader(f"{ytd_total}")

    # Total by day
    daily_tot = dfv.groupby("Date", as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(daily_tot)
        .mark_line(point=True)
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Quantity:Q", title="Total"),
            tooltip=["Date:T", "Quantity:Q"],
        )
        .properties(height=260, title="Total Actions per Day"),
        use_container_width=True,
    )

    # Category breakdown (stacked by Enforcer)
    cat_tot = dfv.groupby(["Category", "CategoryShort", "Enforcer"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(cat_tot)
        .mark_bar()
        .encode(
            x=alt.X("Quantity:Q", title="Total"),
            y=alt.Y("CategoryShort:N", sort="-x", title="Category"),
            color=alt.Color("Enforcer:N"),
            tooltip=["Category:N", "Enforcer:N", "Quantity:Q"],
        )
        .properties(height=320, title="Category Breakdown (stacked by Enforcer)"),
        use_container_width=True,
    )

    # Leaderboard
    st.markdown("### 📌 Summary Charts")
    leader = prod  # already computed
    st.altair_chart(
        alt.Chart(leader)
        .mark_bar()
        .encode(
            x=alt.X("Quantity:Q", title="Total"),
            y=alt.Y("Enforcer:N", sort="-x", title="Enforcer"),
            tooltip=["Enforcer:N", "Quantity:Q"],
        )
        .properties(height=320, title="Leaderboard (Enforcer Totals)")
        .configure_view(stroke=None),
        use_container_width=True,
    )

    # Donut — centered; legend on a new line (bottom)
    cat_share = (
        dfv.groupby(["Category", "CategoryShort"], as_index=False)["Quantity"].sum()
        .sort_values("Quantity", ascending=False)
    )
    donut = (
        alt.Chart(cat_share, title="Category Share")
        .mark_arc(innerRadius=90, outerRadius=140)
        .encode(
            theta=alt.Theta("Quantity:Q", stack=True, title=None),
            color=alt.Color(
                "CategoryShort:N",
                legend=alt.Legend(
                    title="Category",
                    orient="bottom",       # put legend on its own line
                    columns=1,             # single column to avoid truncation
                    labelLimit=10000       # never truncate labels
                ),
            ),
            tooltip=["Category:N", "Quantity:Q"],
        )
        .properties(
            width=520,  # fixed width so it's easy to center
            height=420,
            padding={"left": 0, "right": 0, "top": 0, "bottom": 0},
        )
        .configure_view(stroke=None)
    )
    left_pad, mid, right_pad = st.columns([1, 2, 1])  # center the donut block
    with mid:
        st.altair_chart(donut, use_container_width=False)

    # Heatmap: Category × Enforcer
    heat = dfv.groupby(["CategoryShort", "Enforcer"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(heat)
        .mark_rect()
        .encode(
            x=alt.X("Enforcer:N", title=None),
            y=alt.Y("CategoryShort:N", title=None),
            color=alt.Color("Quantity:Q", title="Qty"),
            tooltip=["CategoryShort:N", "Enforcer:N", "Quantity:Q"],
        )
        .properties(height=280, title="Heatmap: Category × Enforcer"),
        use_container_width=True,
    )

    download_filtered("Daily filtered", dfv)

# ======================
# MONTHLY VIEW
# ======================
else:
    months = sorted(dfv["Month"].dropna().unique())
    sel = st.multiselect("Select Month(s)", months, default=months)
    if sel:
        dfv = dfv[dfv["Month"].isin(sel)]
    if dfv.empty:
        st.info("No data for the selected month(s).")
        st.stop()

    # KPI calculations (Monthly)
    total_month = int(dfv["Quantity"].sum())

    # previous months block of equal length, immediately before earliest selected month
    if sel:
        # Treat selected months as a block; compare to preceding block of same length
        sel_sorted = sorted(sel)
        block_len = len(sel_sorted)
        # find previous month helper
        def prev_month(mstr):
            y, m = map(int, mstr.split("-"))
            if m == 1:
                return f"{y-1}-12"
            return f"{y}-{m-1:02d}"
        # end of previous block is month just before first selected
        prev_end_m = prev_month(sel_sorted[0])
        prev_block = []
        cur = prev_end_m
        for _ in range(block_len):
            prev_block.append(cur)
            cur = prev_month(cur)
        prev_block = list(reversed(prev_block))
        prev_df = df[(df["Enforcer"].isin(effective_selection)) & (df["Month"].isin(prev_block))]
        total_prev = int(prev_df["Quantity"].sum()) if not prev_df.empty else 0
    else:
        total_prev = 0

    pct_vs_prev_months = percent_change(total_month, total_prev)

    # Most productive enforcer (in the selected months)
    prod_m = (
        dfv.groupby("Enforcer", as_index=False)["Quantity"]
        .sum()
        .sort_values("Quantity", ascending=False)
    )
    top_enforcer_m = prod_m.iloc[0]["Enforcer"] if not prod_m.empty else "—"
    top_enforcer_actions_m = int(prod_m.iloc[0]["Quantity"]) if not prod_m.empty else 0

    # % of enforcers active
    pct_active_m = 100.0 * (dfv["Enforcer"].nunique() / len(effective_selection)) if len(effective_selection) else 0.0

    # YTD cumulative (for selected enforcers)
    year_start = pd.to_datetime(date.today().replace(month=1, day=1))
    ytd_df = df[(df["Enforcer"].isin(effective_selection)) & (df["Date"] >= year_start)]
    ytd_total = int(ytd_df["Quantity"].sum()) if not ytd_df.empty else 0

    # KPIs row (match Daily)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.caption("Most productive enforcer")
        st.subheader(f"{top_enforcer_m}")
        kpi_badge(top_enforcer_actions_m, unit=" actions")
    with c2:
        st.caption("% of enforcers active")
        st.subheader(f"{pct_active_m:.1f}%")
    with c3:
        st.caption("Change vs last month(s)")
        st.subheader(f"{total_month} actions")
        if pct_vs_prev_months is not None:
            kpi_badge(pct_vs_prev_months)
    with c4:
        st.caption("Cumulative total (YTD)")
        st.subheader(f"{ytd_total}")

    # Totals per month (by Enforcer)
    month_enf = dfv.groupby(["Month", "Enforcer"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(month_enf)
        .mark_bar()
        .encode(
            x=alt.X("Month:N", title="Month"),
            y=alt.Y("Quantity:Q", title="Total"),
            color=alt.Color("Enforcer:N"),
            tooltip=["Month:N", "Enforcer:N", "Quantity:Q"],
        )
        .properties(height=280, title="Total Actions per Month (by Enforcer)"),
        use_container_width=True,
    )

    # Category by month (stacked by Enforcer, faceted by Category)
    cat_month_enf = dfv.groupby(["Month", "Category", "CategoryShort", "Enforcer"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(cat_month_enf)
        .mark_bar()
        .encode(
            x=alt.X("Month:N", title="Month"),
            y=alt.Y("Quantity:Q"),
            color=alt.Color("Enforcer:N"),
            column=alt.Column("CategoryShort:N", title=None),
            tooltip=["Month:N", "Category:N", "Enforcer:N", "Quantity:Q"],
        )
        .properties(height=280, title="Category Breakdown by Month (stacked by Enforcer)")
        .resolve_scale(y="independent"),
        use_container_width=True,
    )

    # Donut (same layout & centering as Daily) for the selected months
    cat_share_m = (
        dfv.groupby(["Category", "CategoryShort"], as_index=False)["Quantity"].sum()
        .sort_values("Quantity", ascending=False)
    )
    donut_m = (
        alt.Chart(cat_share_m, title="Category Share (Selected Months)")
        .mark_arc(innerRadius=90, outerRadius=140)
        .encode(
            theta=alt.Theta("Quantity:Q", stack=True, title=None),
            color=alt.Color(
                "CategoryShort:N",
                legend=alt.Legend(
                    title="Category",
                    orient="bottom",
                    columns=1,
                    labelLimit=10000
                ),
            ),
            tooltip=["Category:N", "Quantity:Q"],
        )
        .properties(width=520, height=420, padding={"left": 0, "right": 0, "top": 0, "bottom": 0})
        .configure_view(stroke=None)
    )
    lp, mid, rp = st.columns([1, 2, 1])
    with mid:
        st.altair_chart(donut_m, use_container_width=False)

    download_filtered("Monthly filtered", dfv)
