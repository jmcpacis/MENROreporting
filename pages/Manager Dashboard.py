import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import altair as alt
import time

SHEET_ID = "1O39vIMeCq-Z5GEWzoMM4xjNwiQNCeBa-pzGdOvp2zwg"
ENFORCERS = ["Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"]
EXPECTED_HEADERS = ["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"]
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

st.set_page_config(page_title="Manager Dashboard", layout="wide")
st.title("📊 Manager Dashboard (All Enforcers)")

@st.cache_resource(show_spinner=False)
def get_spreadsheet():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
    client = gspread.authorize(creds)
    for i in range(3):
        try:
            return client.open_by_key(SHEET_ID)
        except Exception:
            if i == 2: raise
            time.sleep(1.5)

spreadsheet = get_spreadsheet()

@st.cache_data(ttl=60)
def load_all():
    frames = []
    for title in ENFORCERS:  # only read the 5 tabs
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
    return df

df = load_all()

# Filters
left, right = st.columns(2)
with left:
    view = st.radio("View", ["Daily", "Monthly"], horizontal=True)
with right:
    # always show all five enforcers
    chosen = st.multiselect("Filter Enforcers", ENFORCERS, ENFORCERS)

dfv = df[df["Enforcer"].isin(chosen)] if not df.empty else df

if dfv.empty:
    st.info("No data to display for the current selection.")
    st.stop()

if view == "Daily":
    min_d, max_d = dfv["Date"].min().date(), dfv["Date"].max().date()
    # guard against identical min/max or NaT
    if pd.isna(min_d) or pd.isna(max_d):
        st.info("No valid dates in data.")
        st.stop()
    d1, d2 = st.date_input("Date range", (min_d, max_d), min_value=min_d, max_value=max_d)
    dfv = dfv[(dfv["Date"] >= pd.to_datetime(d1)) & (dfv["Date"] <= pd.to_datetime(d2))]

    k1, k2, k3 = st.columns(3)
    k1.metric("Total actions", int(dfv["Quantity"].sum()))
    k2.metric("Active enforcers", dfv["Enforcer"].nunique())
    k3.metric("Active days", dfv["Date"].nunique())

    daily_tot = dfv.groupby("Date", as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(daily_tot).mark_line(point=True).encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Quantity:Q", title="Total"),
            tooltip=["Date:T","Quantity:Q"]
        ).properties(height=280, title="Total Actions per Day"),
        use_container_width=True
    )

    cat_tot = dfv.groupby(["Category","Enforcer"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(cat_tot).mark_bar().encode(
            x=alt.X("Quantity:Q", title="Total"),
            y=alt.Y("Category:N", sort="-x", title="Category"),
            color=alt.Color("Enforcer:N"),
            tooltip=["Category:N","Enforcer:N","Quantity:Q"]
        ).properties(height=320, title="Category Breakdown (stacked by Enforcer)"),
        use_container_width=True
    )

else:
    months = sorted(dfv["Month"].dropna().unique())
    sel = st.multiselect("Select Month(s)", months, months[-1:] if months else [])
    if sel:
        dfv = dfv[dfv["Month"].isin(sel)]

    k1, k2, k3 = st.columns(3)
    k1.metric("Total actions (selected months)", int(dfv["Quantity"].sum()))
    k2.metric("Active enforcers", dfv["Enforcer"].nunique())
    k3.metric("Months selected", len(sel))

    month_tot = dfv.groupby("Month", as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(month_tot).mark_bar().encode(
            x=alt.X("Month:N", title="Month"),
            y=alt.Y("Quantity:Q"),
            tooltip=["Month:N","Quantity:Q"]
        ).properties(height=280, title="Total Actions per Month"),
        use_container_width=True
    )

    cat_month = dfv.groupby(["Month","Category"], as_index=False)["Quantity"].sum()
    st.altair_chart(
        alt.Chart(cat_month).mark_bar().encode(
            x=alt.X("Month:N", title="Month"),
            y=alt.Y("Quantity:Q"),
            column=alt.Column("Category:N", title=None),
            tooltip=["Month:N","Category:N","Quantity:Q"]
        ).properties(height=280, title="Category Breakdown by Month").resolve_scale(y='independent'),
        use_container_width=True
    )
