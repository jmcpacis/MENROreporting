import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
import altair as alt
import time

# ---------------------------
# CONFIG
# ---------------------------
SHEET_ID = "1O39vIMeCq-Z5GEWzoMM4xjNwiQNCeBa-pzGdOvp2zwg"
ENFORCERS = ["", "Enforcer 1", "Enforcer 2", "Enforcer 3", "Enforcer 4", "Enforcer 5"]

# ---------------------------
# AUTH (cached to avoid re-auth each rerun)
# ---------------------------
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

@st.cache_resource(show_spinner=False)
def get_gs_client_and_file():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
    client = gspread.authorize(creds)
    # simple retry for occasional API hiccups
    for i in range(3):
        try:
            ss = client.open_by_key(SHEET_ID)
            return client, ss
        except Exception:
            if i == 2:
                raise
            time.sleep(1.5)
    return client, client.open_by_key(SHEET_ID)

client, spreadsheet = get_gs_client_and_file()

def get_or_create_ws(title, rows="2000", cols="12"):
    try:
        return spreadsheet.worksheet(title)
    except WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
        ws.append_row(["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"])
        return ws

# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title="Environmental Enforcer Monitoring", layout="wide")
st.title("🌿 Environmental Enforcer Monitoring Dashboard")

name = st.selectbox("Select Your Name", ENFORCERS)
if not name:
    st.info("Please select your name to begin.")
    st.stop()

ws = get_or_create_ws(name)
# ensure headers if user cleared tab
if not ws.get_all_values():
    ws.append_row(["Date", "Enforcer", "Category", "Activity", "Quantity", "Remarks"])

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
        rows_to_save.append([today, name, cat, act, qty, remark])

if st.button("💾 Save Entry"):
    ws.append_rows(rows_to_save, value_input_option="USER_ENTERED")
    st.success(f"✅ Saved to tab: {name}.")

with st.expander("📄 View Submitted Data (this enforcer)"):
    df_self = pd.DataFrame(ws.get_all_records())
    if not df_self.empty:
        st.dataframe(df_self, use_container_width=True)
        st.download_button("⬇️ Download CSV", df_self.to_csv(index=False), "monitoring_data.csv", "text/csv")
    else:
        st.info("No records yet.")

# ---------------------------
# MANAGER DASHBOARD (visuals only; no extra Sheets tabs)
# ---------------------------
st.markdown("## 📊 Manager Dashboard (All Enforcers)")

@st.cache_data(ttl=60)  # cache for 60s to cut API calls
def load_all_enforcer_data():
    frames = []
    for w in spreadsheet.worksheets():
        title = w.title
        # Only read Enforcer 1-5 tabs; ignore anything else in the file
        if title not in [e for e in ENFORCERS if e]:  # skip "" and non-enforcer tabs
            continue
        recs = w.get_all_records()
        if recs:
            frames.append(pd.DataFrame(recs))
    if not frames:
        return pd.DataFrame(columns=["Date","Enforcer","Category","Activity","Quantity","Remarks"])
    df = pd.concat(frames, ignore_index=True)
    df["Quantity"] = pd.to_numeric(df.get("Quantity", 0), errors="coerce").fillna(0).astype(int)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Month"] = df["Date"].dt.strftime("%Y-%m")
    return df

df_all = load_all_enforcer_data()

if df_all.empty:
    st.info("No data yet to visualize. Make a save first.")
else:
    colA, colB = st.columns(2)
    with colA:
        view = st.radio("View", ["Daily", "Monthly"], horizontal=True)
    with colB:
        enforce_opts = sorted(df_all["Enforcer"].dropna().unique())
        chosen = st.multiselect("Filter Enforcers", enforce_opts, enforce_opts)

    dfv = df_all[df_all["Enforcer"].isin(chosen)]

    if view == "Daily":
        min_d, max_d = dfv["Date"].min().date(), dfv["Date"].max().date()
        d1, d2 = st.date_input("Date range", (min_d, max_d), min_value=min_d, max_value=max_d)
        dfv = dfv[(dfv["Date"] >= pd.to_datetime(d1)) & (dfv["Date"] <= pd.to_datetime(d2))]

        k1, k2, k3 = st.columns(3)
        k1.metric("Total actions", int(dfv["Quantity"].sum()))
        k2.metric("Active enforcers", dfv["Enforcer"].nunique())
        k3.metric("Active days", dfv["Date"].nunique())

        # totals per day
        daily_tot = dfv.groupby("Date", as_index=False)["Quantity"].sum()
        st.altair_chart(
            alt.Chart(daily_tot).mark_line(point=True).encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("Quantity:Q", title="Total"),
                tooltip=["Date:T", "Quantity:Q"]
            ).properties(height=280, title="Total Actions per Day"),
            use_container_width=True
        )

        # category totals stacked by enforcer
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

    else:  # Monthly
        months = sorted(dfv["Month"].dropna().unique())
        chosen_months = st.multiselect("Select Month(s)", months, months[-1:] if months else [])
        if chosen_months:
            dfv = dfv[dfv["Month"].isin(chosen_months)]

        k1, k2, k3 = st.columns(3)
        k1.metric("Total actions (selected months)", int(dfv["Quantity"].sum()))
        k2.metric("Active enforcers", dfv["Enforcer"].nunique())
        k3.metric("Months selected", len(chosen_months))

        month_tot = dfv.groupby("Month", as_index=False)["Quantity"].sum()
        st.altair_chart(
            alt.Chart(month_tot).mark_bar().encode(
                x=alt.X("Month:N", title="Month"),
                y=alt.Y("Quantity:Q", title="Total"),
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
