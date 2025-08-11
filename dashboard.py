import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime

# --------------------------
# Google Sheets connection
# --------------------------
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
client = gspread.authorize(CREDS)

SHEET_ID = "1O39vIMeCq-Z5GEWzoMM4xjNwiQNCeBa-pzGdOvp2zwg"  # your spreadsheet id
spreadsheet = client.open_by_key(SHEET_ID)  # open the file (not a tab)

# --------------------------
# Streamlit UI
# --------------------------
st.set_page_config(page_title="Environmental Enforcer Monitoring", layout="wide")
st.title("🌿 Environmental Enforcer Monitoring Dashboard")

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
        "Other Environmental Ordinance Violations"
    ],
    "II. Surveillance, Investigation, Monitoring, Documentation, and Inspection": [
        "Binangonan Kalinisan Patrol (BKP)",
        "Handling of Environmental Complaints",
        "Response to Environmental Incidents",
        "Delivery of Letters and Notices",
        "Inspection of MRFs, Composting Facilities, and Eco-Gardens"
    ],
    "III. Information, Education, and Communication (IEC) Campaign)": [
        "Dissemination of IEC Materials",
        "Assistance in Conducting IEC Campaign Activities"
    ],
    "IV. Other Tasks": [
        "Other duties assigned by the MENRO or LGU"
    ]
}

ENFORCERS = ["", "Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"]
name = st.selectbox("Select Your Name", ENFORCERS)

# Stop until a name is chosen (prevents NameError and bad state)
if not name:
    st.info("Please select your name to begin.")
    st.stop()

# --------------------------
# Get/Create per-enforcer worksheet AFTER name exists
# --------------------------
try:
    sheet = spreadsheet.worksheet(name)
except WorksheetNotFound:
    sheet = spreadsheet.add_worksheet(title=name, rows="2000", cols="10")
    sheet.append_row(["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"])

# Ensure headers exist (in case the tab was empty)
if not sheet.get_all_values():
    sheet.append_row(["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"])

# --------------------------
# Input form
# --------------------------
user_data = []
st.markdown("---")

today = str(datetime.date.today())

for cat, activities in categories.items():
    st.subheader(cat)
    for activity in activities:
        c1, c2, c3 = st.columns([2.5, 1, 4])
        with c1:
            st.markdown(f"**{activity}**")
        with c2:
            # keys include the enforcer name to avoid collisions after reruns
            qty = st.number_input(
                f"{activity}_qty",
                min_value=0, step=1,
                key=f"{name}_{activity}_qty",
                label_visibility="collapsed"
            )
        with c3:
            remark = st.text_input(
                f"{activity}_remark",
                placeholder="Remarks or details",
                key=f"{name}_{activity}_remark",
                label_visibility="collapsed"
            )

        user_data.append([today, name, cat, activity, qty, remark])

if st.button("💾 Save Entry to Google Sheets"):
    # Append all rows at once; USER_ENTERED preserves numbers nicely
    sheet.append_rows(user_data, value_input_option="USER_ENTERED")
    st.success(f"✅ Entries saved to tab: {name}")

with st.expander("📊 View Submitted Data (this enforcer only)"):
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        st.download_button("⬇️ Download as CSV", df.to_csv(index=False), "monitoring_data.csv", "text/csv")
    else:
        st.info("No records yet in this tab.")
