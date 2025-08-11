import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
import time

# =========================
# Config
# =========================
SHEET_ID = "1O39vIMeCq-Z5GEWzoMM4xjNwiQNCeBa-pzGdOvp2zwg"
ENFORCERS = ["", "Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"]
EXPECTED_HEADERS = ["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"]
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# =========================
# Page
# =========================
st.set_page_config(page_title="Environmental Enforcer Monitoring", layout="wide")
st.title("🌿 Environmental Enforcer Monitoring (Entry)")

# =========================
# Auth (cached)
# =========================
@st.cache_resource(show_spinner=False)
def get_client_and_sheet():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
    client = gspread.authorize(creds)
    for i in range(3):  # retry for transient 5xx
        try:
            return client, client.open_by_key(SHEET_ID)
        except Exception:
            if i == 2:
                raise
            time.sleep(1.2)

client, spreadsheet = get_client_and_sheet()

def get_or_create_ws(title: str):
    try:
        return spreadsheet.worksheet(title)
    except WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows="2000", cols="12")
        ws.append_row(EXPECTED_HEADERS)
        return ws

def ensure_headers(ws):
    values = ws.get_all_values()
    if not values:
        ws.append_row(EXPECTED_HEADERS)
    elif values[0] != EXPECTED_HEADERS:
        ws.insert_row(EXPECTED_HEADERS, index=1)

# =========================
# Counter helpers (safe with Streamlit state)
# =========================
def _inc(k):
    st.session_state[k] = int(st.session_state.get(k, 0)) + 1

def _dec(k):
    st.session_state[k] = max(0, int(st.session_state.get(k, 0)) - 1)

def _sync(src_key, dest_key):
    # copy number_input's value into the canonical counter
    st.session_state[dest_key] = int(st.session_state.get(src_key, 0))

# =========================
# UI
# =========================
name = st.selectbox("Select Your Name", ENFORCERS)
if not name:
    st.info("Please select your name to begin.")
    st.stop()

ws = get_or_create_ws(name)
ensure_headers(ws)

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
rows_to_save = []
st.markdown("---")

for cat, acts in categories.items():
    st.subheader(cat)
    for act in acts:
        # canonical counter key + separate widget key to avoid conflicts
        counter_key = f"{name}_{act}_qty"
        num_widget_key = f"{counter_key}_num"
        remark_key = f"{name}_{act}_remark"

        if counter_key not in st.session_state:
            st.session_state[counter_key] = 0

        c1, c2, c3 = st.columns([2.7, 1.6, 4])  # label | controls | remarks
        with c1:
            st.markdown(f"**{act}**")

        with c2:
            b1, ncol, b2 = st.columns([1, 2, 1])

            with b1:
                st.button("−", key=f"{counter_key}_minus", on_click=_dec, args=(counter_key,))

            with ncol:
                st.number_input(
                    f"{act}_qty",
                    key=num_widget_key,
                    min_value=0,
                    step=1,
                    value=int(st.session_state[counter_key]),
                    label_visibility="collapsed",
                    format="%d",
                    on_change=_sync,
                    args=(num_widget_key, counter_key),
                )

            with b2:
                st.button("+", key=f"{counter_key}_plus", on_click=_inc, args=(counter_key,))

        with c3:
            st.text_input(
                f"{act}_remark",
                key=remark_key,
                placeholder="Remarks or details",
                label_visibility="collapsed",
            )

        qty = int(st.session_state[counter_key])
        remark = st.session_state.get(remark_key, "")
        rows_to_save.append([today, name, cat, act, qty, remark])

# =========================
# Save & View
# =========================
if st.button("💾 Save Entry"):
    ws.append_rows(rows_to_save, value_input_option="USER_ENTERED")
    st.success(f"✅ Saved to sheet tab: {name}")

with st.expander("📄 View Submitted Data (this enforcer)"):
    df_self = pd.DataFrame(ws.get_all_records())
    if df_self.empty:
        st.info("No records yet.")
    else:
        st.dataframe(df_self, use_container_width=True)
