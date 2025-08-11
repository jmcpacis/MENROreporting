import streamlit as st
import pandas as pd
import datetime

# App title
st.set_page_config(page_title="Environmental Enforcer Dashboard", layout="wide")
st.title("Environmental Enforcer Monitoring Dashboard")

# Sample structure
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
        "Binangonan Kalinisan Patrol (BKP) – Documentation of open dumping of waste in barangays",
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

# Session state to store counters and remarks
if "activity_data" not in st.session_state:
    st.session_state.activity_data = {}

# User login (for tracking individual input)
name = st.selectbox("Select Your Name", ["", "Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"])

if name:
    for cat, activities in categories.items():
        st.subheader(cat)
        for activity in activities:
            key_count = f"{name}_{activity}_count"
            key_remark = f"{name}_{activity}_remark"

            col1, col2 = st.columns([1, 3])
            with col1:
                st.number_input(
                    f"{activity} - Count",
                    min_value=0,
                    key=key_count,
                    step=1,
                    label_visibility="collapsed"
                )
            with col2:
                st.text_input(
                    f"{activity} - Remarks",
                    key=key_remark,
                    placeholder="Enter remarks or details here...",
                    label_visibility="collapsed"
                )

    if st.button("💾 Save Entry"):
        date_key = str(datetime.date.today())
        for cat, activities in categories.items():
            for activity in activities:
                count = st.session_state.get(f"{name}_{activity}_count", 0)
                remark = st.session_state.get(f"{name}_{activity}_remark", "")

                record = {
                    "Date": date_key,
                    "Enforcer": name,
                    "Category": cat,
                    "Activity": activity,
                    "Quantity": count,
                    "Remarks": remark
                }

                if date_key not in st.session_state.activity_data:
                    st.session_state.activity_data[date_key] = []

                st.session_state.activity_data[date_key].append(record)

        st.success("Entries saved successfully!")

    # View Report
    with st.expander("📊 View Today's Summary Report"):
        today_data = st.session_state.activity_data.get(str(datetime.date.today()), [])
        if today_data:
            df = pd.DataFrame(today_data)
            st.dataframe(df)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download CSV", data=csv, file_name="daily_environmental_report.csv", mime="text/csv")
        else:
            st.info("No data submitted yet today.")
else:
    st.warning("Please select your name to begin inputting your activities.")
