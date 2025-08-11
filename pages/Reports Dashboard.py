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

    # clean types
    if "Quantity" in df.columns:
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df["Month"] = df["Date"].dt.strftime("%Y-%m")
    return df

df = load_all()

# -------------------
# Controls
# -------------------
left, right = st.columns(2)
with left:
    view = st.radio("View", ["Daily", "Monthly"], horizontal=True)

with right:
    chosen = st.multiselect("Filter Enforcers", ENFORCERS, default=[])
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Select All"):
            chosen = ENFORCERS[:]
    with c2:
        if st.button("Clear"):
            chosen = []

effective_selection = chosen if chosen else ENFORCERS
dfv = df[df["Enforcer"].isin(effective_selection)] if not df.empty else df

if dfv.empty:
    st.info("No data to display for the current selection.")
    st.stop()

# -------------------
# Daily view
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

    k1, k2, k3 = st.columns(3)
    k1.metric("Total actions", int(dfv["Quantity"].sum()))
    k2.metric("Active enforcers", dfv["Enforcer"].nunique())
    k3.metric("Active days", dfv["Date"].nunique())

    daily_tot = dfv.groupby("Date", as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(daily_tot).mark_line(point=True).encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Quantity:Q", title="Total"),
            tooltip=["Date:T", "Quantity:Q"],
        ).properties(height=280, title="Total Actions per Day"),
        use_container_width=True,
    )

    cat_tot = dfv.groupby(["Category", "Enforcer"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(cat_tot).mark_bar().encode(
            x=alt.X("Quantity:Q", title="Total"),
            y=alt.Y("Category:N", sort="-x", title="Category"),
            color=alt.Color("Enforcer:N"),
            tooltip=["Category:N", "Enforcer:N", "Quantity:Q"],
        ).properties(height=320, title="Category Breakdown (stacked by Enforcer)"),
        use_container_width=True,
    )

# -------------------
# Monthly view
# -------------------
else:
    months = sorted(dfv["Month"].dropna().unique())
    sel = st.multiselect("Select Month(s)", months, default=months)
    if sel:
        dfv = dfv[dfv["Month"].isin(sel)]
    if dfv.empty:
        st.info("No data for the selected month(s).")
        st.stop()

    k1, k2, k3 = st.columns(3)
    k1.metric("Total actions (selected months)", int(dfv["Quantity"].sum()))
    k2.metric("Active enforcers", dfv["Enforcer"].nunique())
    k3.metric("Months selected", len(sel) if sel else len(months))

    month_tot = dfv.groupby("Month", as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(month_tot).mark_bar().encode(
            x=alt.X("Month:N", title="Month"),
            y=alt.Y("Quantity:Q", title="Total"),
            tooltip=["Month:N", "Quantity:Q"],
        ).properties(height=280, title="Total Actions per Month"),
        use_container_width=True,
    )

    cat_month = dfv.groupby(["Month", "Category"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(cat_month).mark_bar().encode(
            x=alt.X("Month:N", title="Month"),
            y=alt.Y("Quantity:Q"),
            column=alt.Column("Category:N", title=None),
            tooltip=["Month:N", "Category:N", "Quantity:Q"],
        ).properties(height=280, title="Category Breakdown by Month").resolve_scale(y="independent"),
        use_container_width=True,
    )

# -------------------
# Leaderboard + Donut (Always show at the bottom)
# -------------------
if not dfv.empty:
    st.markdown("### 📌 Summary Charts")

    col1, col2 = st.columns([1.5, 1])

    # Leaderboard chart
    with col1:
        leader = dfv.groupby("Enforcer", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
        bar_chart = (
            alt.Chart(leader)
            .mark_bar()
            .encode(
                x=alt.X("Quantity:Q", title="Total"),
                y=alt.Y("Enforcer:N", sort="-x", title="Enforcer"),
                tooltip=["Enforcer:N", "Quantity:Q"],
            )
            .properties(height=300, title="Leaderboard (Enforcer Totals)")
        )
        st.altair_chart(bar_chart, use_container_width=True)

    # Responsive donut chart
    with col2:
        cat_share = dfv.groupby("Category", as_index=False)["Quantity"].sum()
        donut = (
            alt.Chart(cat_share)
            .mark_arc(innerRadius=80, outerRadius=140)
            .encode(
                theta=alt.Theta("Quantity:Q", stack=True),
                color=alt.Color("Category:N", legend=alt.Legend(title="Category")),
                tooltip=["Category:N", "Quantity:Q"],
            )
            .properties(height=300, title="Category Share")
            .configure_view(stroke=None)
        )
        st.altair_chart(donut, use_container_width=True)
