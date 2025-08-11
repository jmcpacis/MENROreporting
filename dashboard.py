import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime

# Connect to Google Sheet
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
client = gspread.authorize(CREDS)

SHEET_ID = "https://docs.google.com/spreadsheets/d/1O39vIMeCq-Z5GEWzoMM4xjNwiQNCeBa-pzGdOvp2zwg/edit?usp=sharing"
sheet = client.open_by_key(SHEET_ID).sheet1

st.set_page_config(page_title="Environmental Enforcer Monitoring", layout="wide")
st.title("🌿 Environmental Enforcer Monitoring Dashboard (Google Sheets Version)")

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
    "III. Information, Education, and Communication (IEC) Campaign": [
        "Dissemination of IEC Materials",
        "Assistance in Conducting IEC Campaign Activities"
    ],
    "IV. Other Tasks": [
        "Other duties assigned by the MENRO or LGU"
    ]
}

name = st.selectbox("Select Your Name", ["", "Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"])

if name:
    user_data = []
    st.markdown("---")

    for cat, activities in categories.items():
        st.subheader(cat)
        for activity in activities:
            col1, col2, col3 = st.columns([2.5, 1, 4])
            with col1:
                st.markdown(f"**{activity}**")
            with col2:
                qty = st.number_input(f"{activity}_qty", label_visibility="collapsed", min_value=0, step=1, key=f"{activity}_qty")
            with col3:
                remark = st.text_input(f"{activity}_remark", label_visibility="collapsed", placeholder="Remarks or details", key=f"{activity}_remark")

            user_data.append([str(datetime.date.today()), name, cat, activity, qty, remark])

    if st.button("💾 Save Entry to Google Sheets"):
        sheet.append_rows(user_data, value_input_option="USER_ENTERED")
        st.success("✅ Entries successfully saved to Google Sheet!")

    with st.expander("📊 View Submitted Data"):
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        st.dataframe(df)
        st.download_button("⬇️ Download as CSV", df.to_csv(index=False), "monitoring_data.csv", "text/csv")
else:
    st.warning("Please select your name to begin inputting data.")
