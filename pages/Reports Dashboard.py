import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import altair as alt
import time

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

    # KPIs (expanded)
    total = int(dfv["Quantity"].sum())
    days = dfv["Date"].nunique()
    avg_per_day = round(total / days, 1) if days else 0
    top_act_row = (
        dfv.groupby("Activity", as_index=False)["Quantity"]
        .sum()
        .sort_values("Quantity", ascending=False)
        .head(1)
    )

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total actions", total)
    k2.metric("Active enforcers", dfv["Enforcer"].nunique())
    k3.metric("Active days", days)
    k4.metric("Avg / day", avg_per_day)
    k5.metric("Top activity", top_act_row.iloc[0]["Activity"] if not top_act_row.empty else "—")

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
                    orient="bottom",   # put legend below
                    columns=2,         # wrap into two columns
                    labelLimit=1000,   # effectively no truncation
                ),
            ),
            tooltip=["Category:N", "Quantity:Q"],
        )
        .properties(
            height=380,
            width=620,                 # wider so legend has room
            padding={"left": 10, "right": 10, "top": 10, "bottom": 10},
        )
        .configure_view(stroke=None)
    )
    
    # center the donut on its own row
    left_pad, mid, right_pad = st.columns([1, 3, 1])
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

    k1, k2, k3 = st.columns(3)
    k1.metric("Total actions (selected months)", int(dfv["Quantity"].sum()))
    k2.metric("Active enforcers", dfv["Enforcer"].nunique())
    k3.metric("Months selected", len(sel) if sel else len(months))

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
