import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import altair as alt
import time
from datetime import timedelta

# -------------------
# Config
# -------------------
SHEET_ID = "1O39vIMeCq-Z5GEWzoMM4xjNwiQNCeBa-pzGdOvp2zwg"
ENFORCERS = ["Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"]
EXPECTED_HEADERS = ["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"]
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

st.set_page_config(page_title="Manager Dashboard", layout="wide")
st.title("📊 Manager Dashboard (All Enforcers)")

# -------------------
# Auth & Sheet
# -------------------
@st.cache_resource(show_spinner=False)
def get_spreadsheet():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], SCOPE
    )
    client = gspread.authorize(creds)
    for i in range(3):  # retry for transient 5xx
        try:
            return client.open_by_key(SHEET_ID)
        except Exception:
            if i == 2:
                raise
            time.sleep(1.2)

spreadsheet = get_spreadsheet()

# -------------------
# Load data (cached)
# -------------------
@st.cache_data(ttl=60)
def load_all():
    frames = []
    for title in ENFORCERS:  # read only the 5 tabs
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

    # clean types
    if "Quantity" in df.columns:
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df["Month"] = df["Date"].dt.strftime("%Y-%m")
    return df

df = load_all()

# ---------- KPI helpers (add-on) ----------
def pct_change(curr: int, prev: int):
    """Return % change rounded to 1 dp; None if prev==0 or missing."""
    if prev is None or prev == 0:
        return None
    return round((curr - prev) / prev * 100.0, 1)

def fmt_delta(p):
    """Format % change with arrow for Streamlit metric."""
    if p is None:
        return "—"
    arrow = "↑" if p > 0 else ("↓" if p < 0 else "→")
    return f"{arrow} {abs(p)}%"

def ytd_total(df_base: pd.DataFrame, end_dt: pd.Timestamp) -> int:
    """Cumulative total from Jan 1 to end_dt (inclusive)."""
    if pd.isna(end_dt):
        return 0
    start = pd.Timestamp(end_dt.year, 1, 1)
    m = (df_base["Date"] >= start) & (df_base["Date"] <= end_dt)
    return int(df_base.loc[m, "Quantity"].sum())

# -------------------
# Controls (persisted)
# -------------------
left, right = st.columns(2)
with left:
    view = st.radio("View", ["Daily", "Monthly"], horizontal=True)

# persist enforcer filter across reruns
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

# Treat empty selection as ALL
effective_selection = chosen if chosen else ENFORCERS
dfv = df[df["Enforcer"].isin(effective_selection)] if not df.empty else df

if dfv.empty:
    st.info("No data to display for the current selection.")
    st.stop()

# Base DF filtered only by enforcers (no date limits) for KPIs like yesterday/last month/YTD
df_enf = df[df["Enforcer"].isin(effective_selection)].copy()

def download_filtered(name: str, frame: pd.DataFrame):
    st.download_button(
        f"⬇️ Download {name} CSV",
        frame.to_csv(index=False),
        f"{name.lower().replace(' ', '_')}.csv",
        "text/csv",
    )

# -------------------
# DAILY VIEW
# -------------------
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

    # ---------- KPIs (Daily) ----------
    # Most productive enforcer (within current selected date range)
    leader_tbl = (
        dfv.groupby("Enforcer", as_index=False)["Quantity"]
           .sum()
           .sort_values("Quantity", ascending=False)
    )
    top_name = leader_tbl.iloc[0]["Enforcer"] if not leader_tbl.empty else "—"
    top_qty  = int(leader_tbl.iloc[0]["Quantity"]) if not leader_tbl.empty else 0

    # % of Enforcers Active (in current selection/range)
    active_enf = dfv["Enforcer"].nunique()
    pct_active = round(100.0 * active_enf / len(ENFORCERS), 1) if ENFORCERS else 0

    # Change vs YESTERDAY (compare latest date in view vs previous calendar day)
    end_dt = pd.to_datetime(dfv["Date"].max())  # last date in the current view
    curr_day_total = int(df_enf.loc[df_enf["Date"] == end_dt, "Quantity"].sum())
    prev_day_total = int(df_enf.loc[df_enf["Date"] == (end_dt - timedelta(days=1)), "Quantity"].sum())
    delta_pct = pct_change(curr_day_total, prev_day_total)
    delta_str = fmt_delta(delta_pct)

    # Cumulative YTD (to end_dt), filtered by enforcers
    ytd = ytd_total(df_enf, end_dt)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Most productive enforcer", f"{top_name}", f"{top_qty} actions")
    k2.metric("% of enforcers active", f"{pct_active}%")
    k3.metric("Change vs yesterday", f"{curr_day_total} actions", delta_str)
    k4.metric("Cumulative total (YTD)", f"{ytd}")

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

    # Category breakdown stacked by Enforcer
    cat_tot = dfv.groupby(["Category", "Enforcer"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(cat_tot)
        .mark_bar()
        .encode(
            x=alt.X("Quantity:Q", title="Total"),
            y=alt.Y("Category:N", sort="-x", title="Category"),
            color=alt.Color("Enforcer:N"),
            tooltip=["Category:N", "Enforcer:N", "Quantity:Q"],
        )
        .properties(height=320, title="Category Breakdown (stacked by Enforcer)"),
        use_container_width=True,
    )

    # Summary: Leaderboard (full width)
    st.markdown("### 📌 Summary Charts")
    leader = (
        dfv.groupby("Enforcer", as_index=False)["Quantity"]
        .sum()
        .sort_values("Quantity", ascending=False)
    )
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

    # New line: centered donut with wide, wrapped legend (no truncation)
    cat_share = dfv.groupby("Category", as_index=False)["Quantity"].sum()
    donut = (
        alt.Chart(cat_share, title="Category Share")
        .mark_arc(innerRadius=80, outerRadius=140)
        .encode(
            theta=alt.Theta("Quantity:Q", stack=True, title=""),
            color=alt.Color(
                "Category:N",
                legend=alt.Legend(
                    title="Category",
                    orient="bottom",
                    columns=2,
                    labelLimit=10000,
                ),
            ),
            tooltip=["Category:N", "Quantity:Q"],
        )
        .properties(
            height=380,
            width=820,
            padding={"left": 10, "right": 10, "top": 10, "bottom": 10},
        )
        .configure_view(stroke=None)
    )
    left_pad, mid, right_pad = st.columns([1, 3, 1])  # center the donut
    with mid:
        st.altair_chart(donut, use_container_width=False)

    # Heatmap: Category × Enforcer
    heat = dfv.groupby(["Category", "Enforcer"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(heat)
        .mark_rect()
        .encode(
            x=alt.X("Enforcer:N", title=None),
            y=alt.Y("Category:N", title=None),
            color=alt.Color("Quantity:Q", title="Qty"),
            tooltip=["Category:N", "Enforcer:N", "Quantity:Q"],
        )
        .properties(height=280, title="Heatmap: Category × Enforcer"),
        use_container_width=True,
    )

    download_filtered("Daily filtered", dfv)

# -------------------
# MONTHLY VIEW
# -------------------
else:
    months = sorted(dfv["Month"].dropna().unique())
    sel = st.multiselect("Select Month(s)", months, default=months)  # ALL months by default
    if sel:
        dfv = dfv[dfv["Month"].isin(sel)]
    if dfv.empty:
        st.info("No data for the selected month(s).")
        st.stop()

    # show who is included
    selected_names = ", ".join(sorted(dfv["Enforcer"].unique()))
    st.caption(f"Showing data for: **{selected_names or '—'}**")

    # ---------- KPIs (Monthly) ----------
    # Most productive enforcer (within selected months)
    leader_tbl = (
        dfv.groupby("Enforcer", as_index=False)["Quantity"]
           .sum()
           .sort_values("Quantity", ascending=False)
    )
    top_name = leader_tbl.iloc[0]["Enforcer"] if not leader_tbl.empty else "—"
    top_qty  = int(leader_tbl.iloc[0]["Quantity"]) if not leader_tbl.empty else 0

    # % of Enforcers Active (in selected months)
    active_enf = dfv["Enforcer"].nunique()
    pct_active = round(100.0 * active_enf / len(ENFORCERS), 1) if ENFORCERS else 0

    # Change vs LAST MONTH (based on latest month present in dfv)
    if dfv["Date"].notna().any():
        last_dt = pd.to_datetime(dfv["Date"].max())
        curr_period = last_dt.to_period("M")
        prev_period = curr_period - 1

        curr_month_total = int(df_enf.loc[df_enf["Date"].dt.to_period("M") == curr_period, "Quantity"].sum())
        prev_month_total = int(df_enf.loc[df_enf["Date"].dt.to_period("M") == prev_period, "Quantity"].sum())
        end_of_month_dt = pd.Timestamp(curr_period.end_time)
    else:
        curr_month_total = 0
        prev_month_total = 0
        end_of_month_dt = pd.Timestamp.today()

    delta_pct = pct_change(curr_month_total, prev_month_total)
    delta_str = fmt_delta(delta_pct)

    # Cumulative YTD (to the end of latest month)
    ytd = ytd_total(df_enf, end_of_month_dt)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Most productive enforcer", f"{top_name}", f"{top_qty} actions")
    k2.metric("% of enforcers active", f"{pct_active}%")
    k3.metric("Change vs last month", f"{curr_month_total} actions", delta_str)
    k4.metric("Cumulative total (YTD)", f"{ytd}")

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
    cat_month_enf = dfv.groupby(["Month", "Category", "Enforcer"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(cat_month_enf)
        .mark_bar()
        .encode(
            x=alt.X("Month:N", title="Month"),
            y=alt.Y("Quantity:Q"),
            color=alt.Color("Enforcer:N"),
            column=alt.Column("Category:N", title=None),
            tooltip=["Month:N", "Category:N", "Enforcer:N", "Quantity:Q"],
        )
        .properties(height=280, title="Category Breakdown by Month (stacked by Enforcer)")
        .resolve_scale(y="independent"),
        use_container_width=True,
    )

    download_filtered("Monthly filtered", dfv)
