import os

import google.auth.transport.requests
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from google.oauth2 import id_token

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

api_base_url = os.getenv("API_BASE_URL", "http://localhost:8080").rstrip("/")


@st.cache_data(ttl=600)
def retrieve_data_from_api(api_base_url: str, path: str) -> list:
    headers = {}
    if os.getenv("K_SERVICE"):
        token = id_token.fetch_id_token(
            google.auth.transport.requests.Request(), api_base_url
        )
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(f"{api_base_url}{path}", headers=headers, timeout=60)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json()


def summarize_distribution(df: pd.DataFrame, column_name: str, top_n: int = 10) -> dict:
    distr = df[column_name].value_counts()
    return distr.head(top_n).to_dict()


if __name__ == "__main__":
    st.title("FDA Food Safety Monitor")

    try:
        states = pd.DataFrame(retrieve_data_from_api(api_base_url, "/states/"))
        funding = pd.DataFrame(retrieve_data_from_api(api_base_url, "/usaspending/"))
        events = pd.DataFrame(retrieve_data_from_api(api_base_url, "/fda-recalls/"))
    except requests.RequestException as e:
        st.error(
            f"Could not reach the API at {api_base_url}. Check that the backend "
            f"is running and that API_BASE_URL in frontend/.env is correct.\n\n{e}"
        )
        st.stop()

    with st.sidebar:
        state_names = dict(zip(states["state_code"], states["state_name"]))
        state_codes = sorted(state_names, key=state_names.get)
        selected_state = st.selectbox(
            "State for illness data",
            state_codes,
            index=state_codes.index("CA") if "CA" in state_codes else 0,
            format_func=state_names.get,
        )

        try:
            illness = pd.DataFrame(
                retrieve_data_from_api(api_base_url, f"/cdc/{selected_state}")
            )
        except requests.RequestException as e:
            st.error(f"Could not load illness data for {selected_state}.\n\n{e}")
            illness = pd.DataFrame()

        selected_pathogens = []
        if not illness.empty:
            st.write("Filter illness by Pathogen")
            for pathogen in sorted(illness["pathogen"].dropna().unique()):
                if st.checkbox(pathogen, value=True, key=f"checkbox_{pathogen}"):
                    selected_pathogens.append(pathogen)

        selected_classes = []
        if not events.empty:
            st.write("Filter recalls by Classification")
            for classification in sorted(events["classification"].dropna().unique()):
                if st.checkbox(
                    classification, value=True, key=f"checkbox_{classification}"
                ):
                    selected_classes.append(classification)

    st.header("Recalls")
    if events.empty:
        st.info(
            "No recall data from the API yet. The GET /fda-recalls/ endpoint is needed."
        )
    else:
        events["report_date"] = pd.to_datetime(events["report_date"])
        filtered_events = events[events["classification"].isin(selected_classes)]
        filtered_events = filtered_events.sort_values(
            by=["report_date", "recalling_firm"], ascending=[False, True]
        )
        table = filtered_events[
            [
                "report_date",
                "recalling_firm",
                "state_code",
                "classification",
                "status",
                "classification_lag_days",
            ]
        ].copy()
        table["report_date"] = table["report_date"].dt.date

        st.metric("Recall events", len(filtered_events))
        st.dataframe(
            table,
            hide_index=True,
            column_config={
                "report_date": "Report date",
                "recalling_firm": "Recalling firm",
                "state_code": "State",
                "classification": "Class",
                "status": "Status",
                "classification_lag_days": "Days to classify",
            },
        )

        st.subheader("Recall events per month")
        monthly_counts = (
            filtered_events["report_date"]
            .dt.strftime("%Y-%m")
            .value_counts()
            .sort_index()
        )
        st.bar_chart(monthly_counts, x_label="Month", y_label="Recall events")

        st.subheader("States with the most recall events")
        state_counts = summarize_distribution(filtered_events, "state_code")
        if state_counts:
            state_df = pd.DataFrame(
                {"count": state_counts.values()},
                index=pd.CategoricalIndex(
                    state_counts.keys(), categories=state_counts.keys(), ordered=True
                ),
            )
            st.bar_chart(state_df, x_label="State", y_label="Recall events")

    st.header(f"Foodborne illness in {state_names.get(selected_state)}")
    if illness.empty:
        st.info(f"No CDC illness data for {state_names.get(selected_state)} yet.")
    else:
        human = illness[
            (illness["source_type"].str.lower() == "human")
            & illness["pathogen"].isin(selected_pathogens)
        ]
        st.subheader("Human isolates per month")
        monthly_isolates = human.groupby("year_month")["isolate_count"].sum()
        st.bar_chart(monthly_isolates, x_label="Month", y_label="Human isolates")

    st.header("FDA funding")
    if funding.empty:
        st.info("No USAspending data yet.")
    else:
        latest_funding = funding.sort_values("collected_at").drop_duplicates(
            "fiscal_year", keep="last"
        )
        obligations = latest_funding.set_index(
            latest_funding["fiscal_year"].astype(str)
        )["total_obligations"].astype(float)
        st.subheader("FDA obligations by fiscal year ($ billions)")
        st.bar_chart(
            obligations / 1_000_000_000, x_label="Fiscal year", y_label="$ billions"
        )
