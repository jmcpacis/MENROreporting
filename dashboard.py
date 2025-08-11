import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime

# =========================
# CONFIG
# =========================
SHEET_ID = "1O39vIMeCq-Z5GEWzoMM4xjNwiQNCeBa-pzGdOvp2zwg"  # << your spreadsheet ID
ENFORCERS = ["", "Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"]
PER_ENFORCER_REPORTS = False  # set False if you don't want separate per-enforcer reports

REPORT_TABS = {"Daily Report", "Monthly Report"}  # global (all enforcers) report tabs

# =========================
# GOOGLE SHEETS AUTH
# =========================
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
client = gspread.authorize(CREDS)
spreadsheet = client.open_by_key(SHEET_ID)

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="Environmental Enforcer Monitoring", layout="wide")
st.title("🌿 Environmental Enforcer Monitoring Dashboard")

name = st.selectbox("Select Your Name", ENFORCERS)
if not name:
    st.info("Please select your name to begin.")
    st.stop()

# Get/Create the enforcer's worksheet AFTER name exists
def get_or_create_ws(title, rows="2000", cols="12"):
    try:
        return spreadsheet.worksheet(title)
    except WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

enforcer_ws = get_or_create_ws(name)
# Ensure headers exist
if not enforcer_ws.get_all_values():
    enforcer_ws.append_row(["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"])

# =========================
# CATEGORIES
# =========================
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

# =========================
# INPUT FORM
# =========================
today = str(datetime.date.today())
user_rows = []
st.markdown("---")

for cat, acts in categories.items():
    st.subheader(cat)
    for act in acts:
        c1, c2, c3 = st.columns([2.5, 1, 4])
        with c1:
            st.markdown(f"**{act}**")
        with c2:
            qty = st.number_input(
                f"{act}_qty",
                min_value=0, step=1,
                key=f"{name}_{act}_qty",
                label_visibility="collapsed",
            )
        with c3:
            remark = st.text_input(
                f"{act}_remark",
                placeholder="Remarks or details",
                key=f"{name}_{act}_remark",
                label_visibility="collapsed",
            )
        user_rows.append([today, name, cat, act, qty, remark])

# =========================
# REPORT HELPERS
# =========================
GLOBAL_DAILY = "Daily Report"
GLOBAL_MONTHLY = "Monthly Report"

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
    # Clean types
    if "Quantity" in df.columns:
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    return df

def overwrite(ws, df: pd.DataFrame):
    ws.clear()
    if df.empty:
        ws.update("A1", [["No data"]])
        return
    ws.update("A1", [df.columns.tolist()])
    ws.update("A2", df.astype(str).values.tolist())

def rebuild_global_reports():
    df = read_all_enforcer_data()
    # Ensure sheets exist
    daily_ws = get_or_create_ws(GLOBAL_DAILY)
    monthly_ws = get_or_create_ws(GLOBAL_MONTHLY)

    if df.empty:
        overwrite(daily_ws, pd.DataFrame())
        overwrite(monthly_ws, pd.DataFrame())
        return

    # Daily (all enforcers)
    daily = (
        df.groupby(["Date","Enforcer","Category","Activity"], as_index=False)["Quantity"].sum()
          .sort_values(["Date","Enforcer","Category","Activity"])
    )
    overwrite(daily_ws, daily)

    # Monthly (all enforcers)
    df["Month"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m")
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
    df["Month"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m")
    for person, sub in df.groupby("Enforcer"):
        dws = get_or_create_ws(f"Daily - {person}")
        mws = get_or_create_ws(f"Monthly - {person}")

        daily = (
            sub.groupby(["Date","Category","Activity"], as_index=False)["Quantity"].sum()
               .sort_values(["Date","Category","Activity"])
        )
        monthly = (
            sub.groupby(["Month","Category","Activity"], as_index=False)["Quantity"].sum()
               .sort_values(["Month","Category","Activity"])
        )
        overwrite(dws, daily)
        overwrite(mws, monthly)

# =========================
# SAVE + REPORT REBUILD
# =========================
if st.button("💾 Save Entry to Google Sheets"):
    enforcer_ws.append_rows(user_rows, value_input_option="USER_ENTERED")
    st.success(f"✅ Entries saved to tab: {name}")

    with st.spinner("Updating Daily/Monthly reports…"):
        rebuild_global_reports()        # summaries across ALL enforcers
        rebuild_per_enforcer_reports()  # optional per-enforcer tabs
    st.success("📈 Reports refreshed.")

# =========================
# VIEW (this enforcer)
# =========================
with st.expander("📊 View Submitted Data (this enforcer only)"):
    recs = enforcer_ws.get_all_records()
    df_self = pd.DataFrame(recs)
    if not df_self.empty:
        st.dataframe(df_self, use_container_width=True)
        st.download_button(
            "⬇️ Download CSV",
            df_self.to_csv(index=False),
            "monitoring_data.csv",
            "text/csv",
        )
    else:
        st.info("No records yet in this tab.")
