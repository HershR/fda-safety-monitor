import json
import os

import pandas as pd
import streamlit as st
from google.cloud import storage
from google.oauth2 import service_account

project_id = os.getenv("GCP_PROJECT_ID")
bucket_name = os.getenv("GCP_BUCKET_NAME")
service_account_file_path = os.getenv("GCP_SERVICE_ACCOUNT_KEY")
file_name_prefix = "fda_recalls/"


def retrieve_data_from_gcs(
    service_account_key: str,
    project_id: str,
    bucket_name: str,
    file_name_prefix: str,
) -> dict:
    credentials = service_account.Credentials.from_service_account_file(
        service_account_key
    )
    client = storage.Client(project=project_id, credentials=credentials)
    bucket = client.bucket(bucket_name)
    tables = {}
    for blob in bucket.list_blobs(prefix=file_name_prefix):
        if blob.name.endswith(".json"):
            table_name = blob.name.split("/")[-1].removesuffix(".json")
            tables[table_name] = json.loads(blob.download_as_text())
    return tables


def summarize_distribution(df: pd.DataFrame, column_name: str, top_n: int = 10) -> dict:
    distr = df[column_name].value_counts()
    return distr.head(top_n).to_dict()


if __name__ == "__main__":
    gcs_data = retrieve_data_from_gcs(
        service_account_file_path, project_id, bucket_name, file_name_prefix
    )
    events = pd.DataFrame(gcs_data.get("recall_event", []))
    events["report_date"] = pd.to_datetime(events["report_date"])

    st.title("FDA Food Recall Monitor")

    with st.sidebar:
        st.write("Filter by Classification")
        unique_classes = sorted(events["classification"].dropna().unique())
        selected_classes = []

        for classification in unique_classes:
            if st.checkbox(
                classification, value=True, key=f"checkbox_{classification}"
            ):
                selected_classes.append(classification)

        filtered_df = events[events["classification"].isin(selected_classes)]
        filtered_df = filtered_df[
            [
                "report_date",
                "recalling_firm",
                "state_code",
                "classification",
                "status",
                "classification_lag_days",
            ]
        ]
        filtered_df = filtered_df.drop_duplicates()
        filtered_df = filtered_df.sort_values(
            by=["report_date", "recalling_firm"], ascending=[False, True]
        )

    st.metric("Recall events", len(filtered_df))
    st.dataframe(filtered_df, hide_index=True)

    st.subheader("Recall events per month")
    monthly_counts = filtered_df.set_index("report_date").resample("MS").size()
    st.bar_chart(monthly_counts)

    st.subheader("States with the most recall events")
    state_counts = summarize_distribution(filtered_df, "state_code")
    if state_counts:
        state_df = pd.DataFrame(
            {"count": state_counts.values()},
            index=pd.CategoricalIndex(
                state_counts.keys(), categories=state_counts.keys(), ordered=True
            ),
        )
        st.bar_chart(state_df)
