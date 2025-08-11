import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
import altair as alt

# =========================
# CONFIG
# =========================
SHEET_ID = "1O39vIMeCq-Z5GEWzoMM4xjNwiQNCeBa-pzGdOvp2zwg"   # << your spreadsheet ID
ENFORCERS = ["", "Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"]
PER_ENFORCER_REPORTS = True
REPORT_TABS = {"Daily Report", "Monthly Report"}

# =========================
# GOOGLE SHEETS AUTH
# =========================
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
client = gspread.authorize(CREDS)
spreadsheet = client.open_by_key(SHEET_ID)

# small helpers
def get_or_create_ws(title, rows="2000", cols="12"):
    try:
        return spreadsheet.worksheet(title)
    except WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

def overwrite(ws, df: pd.DataFrame):
    ws.clear()
    if df.empty:
        ws.update("A1", [["No data"]])
        return
    ws.update("A1", [df.columns.tolist()])
    ws.update("A2", df.astype(str).values.tolist())

def read_all_enforcer_data():
    frames = []
    for ws in spreadsheet.worksheets():
        title = ws.title
        if title in REPORT_TABS or (PER_ENFORCER_REPORTS and title.startswith(("Daily - ", "Monthly - "))):
            continue
        recs = ws.get_all_records()
        if recs:
            frames.append(pd.DataFrame(recs))
    if not frames:
        return pd.DataFrame(columns=["Date","Enforcer","Category","Activity","Quantity","Remarks"])
    df = pd.concat(frames, ignore_index=True)
    if "Quantity" in df.columns:
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Month"] = df["Date"].dt.strftime("%Y-%m")
    return df

def rebuild_global_reports():
    df = read_all_enforcer_data()
    daily_ws = get_or_create_ws("Daily Report")
    monthly_ws = get_or_create_ws("Monthly Report")

    if df.empty:
        overwrite(daily_ws, pd.DataFrame())
        overwrite(monthly_ws, pd.DataFrame())
        return

    daily = (
        df.groupby(["Date","Enforcer","Category","Activity"], as_index=False)["Quantity"].sum()
          .sort_values(["Date","Enforcer","Category","Activity"])
    )
    daily["Date"] = daily["Date"].dt.strftime("%Y-%m-%d")
    overwrite(daily_ws, daily)

    monthly = (
        df.groupby(["Month","Enforcer","Category","Activity"], as_index=False)["Quantity"].sum()
          .sort_values(["Month","Enforcer","Category","Activity"])
    )
    overwrite(monthly_ws, monthly)

def rebuild_per_enforcer_reports():
    if not PER_ENFORCER_REPORTS:
        return
    df = read_all_enforcer_data()
    if df.empty:
        return
    for person, sub in df.groupby("Enforcer"):
        dws = get_or_create_ws(f"Daily - {person}")
        mws = get_or_create_ws(f"Monthly - {person}")

        daily = (
            sub.groupby(["Date","Category","Activity"], as_index=False)["Quantity"].sum()
               .sort_values(["Date","Category","Activity"])
        )
        daily["Date"] = daily["Date"].dt.strftime("%Y-%m-%d")
        monthly = (
            sub.groupby(["Month","Category","Activity"], as_index=False)["Quantity"].sum()
               .sort_values(["Month","Category","Activity"])
        )
        overwrite(dws, daily)
        overwrite(mws, monthly)

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="Environmental Enforcer Monitoring", layout="wide")
st.title("🌿 Environmental Enforcer Monitoring Dashboard")

# --- ENFORCER INPUT AREA ---
name = st.selectbox("Select Your Name", ENFORCERS)
if not name:
    st.info("Please select your name to begin.")
    st.stop()

enforcer_ws = get_or_create_ws(name)
if not enforcer_ws.get_all_values():
    enforcer_ws.append_row(["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"])

categories = {
    "I. Issuance of Citation Tickets": [
        "No Tree-Cutting Permit",
        "Unregistered Chainsaw",
        "Violation of Plastics Ordinance",
        "Violation of Solid Waste Management Ordinance",
        "Open Dumping of Waste",
        "Violation of Tapat Ko, Linis Ko Program",
        "Violation of Anti-Littering Ordinance",
        "Violation of Open Burning Ordinance",
        "Other Environmental Ordinance Violations",
    ],
    "II. Surveillance, Investigation, Monitoring, Documentation, and Inspection": [
        "Binangonan Kalinisan Patrol (BKP)",
        "Handling of Environmental Complaints",
        "Response to Environmental Incidents",
        "Delivery of Letters and Notices",
        "Inspection of MRFs, Composting Facilities, and Eco-Gardens",
    ],
    "III. Information, Education, and Communication (IEC) Campaign": [
        "Dissemination of IEC Materials",
        "Assistance in Conducting IEC Campaign Activities",
    ],
    "IV. Other Tasks": [
        "Other duties assigned by the MENRO or LGU",
    ],
}

today = datetime.date.today().strftime("%Y-%m-%d")
to_append = []
st.markdown("---")

for cat, acts in categories.items():
    st.subheader(cat)
    for act in acts:
        c1, c2, c3 = st.columns([2.5, 1, 4])
        with c1:
            st.markdown(f"**{act}**")
        with c2:
            qty = st.number_input(
                f"{act}_qty", min_value=0, step=1,
                key=f"{name}_{act}_qty", label_visibility="collapsed"
            )
        with c3:
            remark = st.text_input(
                f"{act}_remark", placeholder="Remarks or details",
                key=f"{name}_{act}_remark", label_visibility="collapsed"
            )
        to_append.append([today, name, cat, act, qty, remark])

if st.button("💾 Save Entry to Google Sheets"):
    enforcer_ws.append_rows(to_append, value_input_option="USER_ENTERED")
    st.success(f"✅ Entries saved to tab: {name}")
    with st.spinner("Updating Daily/Monthly reports…"):
        rebuild_global_reports()
        rebuild_per_enforcer_reports()
    st.success("📈 Reports refreshed.")

# --- VIEW (this enforcer) ---
with st.expander("📊 View Submitted Data (this enforcer only)"):
    recs = enforcer_ws.get_all_records()
    df_self = pd.DataFrame(recs)
    if not df_self.empty:
        st.dataframe(df_self, use_container_width=True)
        st.download_button("⬇️ Download CSV", df_self.to_csv(index=False), "monitoring_data.csv", "text/csv")
    else:
        st.info("No records yet in this tab.")

# =========================
# MANAGER DASHBOARD (VISUALS)
# =========================
st.markdown("## 📊 Manager Dashboard (All Enforcers)")
df_all = read_all_enforcer_data()

if df_all.empty:
    st.info("No data yet to visualize.")
else:
    left, right = st.columns(2)
    with left:
        view = st.radio("View", ["Daily", "Monthly"], horizontal=True)
    with right:
        enforcer_filter = st.multiselect("Filter Enforcers", sorted(df_all["Enforcer"].dropna().unique()), [])

    dfv = df_all.copy()
    if enforcer_filter:
        dfv = dfv[dfv["Enforcer"].isin(enforcer_filter)]

    if view == "Daily":
        # date range filter
        min_d, max_d = dfv["Date"].min().date(), dfv["Date"].max().date()
        d1, d2 = st.date_input("Date range", (min_d, max_d), min_value=min_d, max_value=max_d)
        dfv = dfv[(dfv["Date"] >= pd.to_datetime(d1)) & (dfv["Date"] <= pd.to_datetime(d2))]

        # KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Total actions", int(dfv["Quantity"].sum()))
        k2.metric("Active enforcers", dfv["Enforcer"].nunique())
        k3.metric("Active days", dfv["Date"].nunique())

        # line: totals per day
        daily_tot = dfv.groupby("Date", as_index=False)["Quantity"].sum()
        chart1 = alt.Chart(daily_tot).mark_line(point=True).encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Quantity:Q", title="Total"),
            tooltip=["Date:T", "Quantity:Q"]
        ).properties(height=280, title="Total Actions per Day")
        st.altair_chart(chart1, use_container_width=True)

        # bar: category totals (stack by enforcer)
        cat_tot = dfv.groupby(["Category","Enforcer"], as_index=False)["Quantity"].sum()
        chart2 = alt.Chart(cat_tot).mark_bar().encode(
            x=alt.X("Quantity:Q", title="Total"),
            y=alt.Y("Category:N", sort="-x", title="Category"),
            color=alt.Color("Enforcer:N"),
            tooltip=["Category:N","Enforcer:N","Quantity:Q"]
        ).properties(height=320, title="Category Breakdown (stacked by Enforcer)")
        st.altair_chart(chart2, use_container_width=True)

    else:  # Monthly
        months = sorted(dfv["Month"].dropna().unique())
        sel_months = st.multiselect("Select Month(s)", months, months[-1:] if months else [])
        if sel_months:
            dfv = dfv[dfv["Month"].isin(sel_months)]

        # KPIs
        k1, k2, k3 = st.columns(3)
        k1.metric("Total actions (selected months)", int(dfv["Quantity"].sum()))
        k2.metric("Active enforcers", dfv["Enforcer"].nunique())
        k3.metric("Months selected", len(sel_months))

        # bar: total per month
        month_tot = dfv.groupby("Month", as_index=False)["Quantity"].sum()
        chart3 = alt.Chart(month_tot).mark_bar().encode(
            x=alt.X("Month:N", sort=months, title="Month"),
            y=alt.Y("Quantity:Q", title="Total"),
            tooltip=["Month:N","Quantity:Q"]
        ).properties(height=280, title="Total Actions per Month")
        st.altair_chart(chart3, use_container_width=True)

        # grouped bar: category by month
        cat_month = dfv.groupby(["Month","Category"], as_index=False)["Quantity"].sum()
        chart4 = alt.Chart(cat_month).mark_bar().encode(
            x=alt.X("Month:N", title="Month"),
            y=alt.Y("Quantity:Q"),
            column=alt.Column("Category:N", title=None),
            tooltip=["Month:N","Category:N","Quantity:Q"]
        ).properties(height=280, title="Category Breakdown by Month").resolve_scale(y='independent')
        st.altair_chart(chart4, use_container_width=True)
