import os

import altair as alt
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
    response = requests.get(
        f"{api_base_url}{path}", headers=headers, timeout=60
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json()


def summarize_distribution(
    df: pd.DataFrame, column_name: str, top_n: int = 10
) -> dict:
    distr = df[column_name].value_counts()
    return distr.head(top_n).to_dict()


cpi_u_september = {
    2017: 246.819,
    2018: 252.439,
    2019: 256.759,
    2020: 260.280,
    2021: 274.310,
    2022: 296.808,
    2023: 307.789,
    2024: 315.301,
    2025: 324.800,
    2026: 336.940,
}
series_colors = {
    "FDA funding (inflation adjusted)": "#3987e5",
    "Recall events": "#d95926",
    "Human isolates": "#199e70",
    "Median days to classify": "#c98500",
}


@st.cache_data(ttl=600)
def retrieve_national_illness(
    api_base_url: str, state_codes: tuple
) -> pd.DataFrame:
    frames = [
        pd.DataFrame(
            retrieve_data_from_api(api_base_url, f"/cdc/{state_code}")
        )
        for state_code in state_codes
    ]
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def to_fiscal_year(dates: pd.Series) -> pd.Series:
    return dates.dt.year + (dates.dt.month >= 10).astype(int)


def build_yearly_summary(
    funding: pd.DataFrame, events: pd.DataFrame, illness: pd.DataFrame
) -> pd.DataFrame:
    latest_funding = funding.sort_values("collected_at").drop_duplicates(
        "fiscal_year", keep="last"
    )
    latest_funding = latest_funding[
        latest_funding["fiscal_year"].isin(cpi_u_september)
    ]
    base_year = max(cpi_u_september)
    nominal = latest_funding.set_index("fiscal_year")[
        "total_obligations"
    ].astype(float)
    cpi = nominal.index.map(cpi_u_september)
    yearly = pd.DataFrame(
        {
            "Nominal funding ($B)": nominal / 1_000_000_000,
            "Real funding ($B)": nominal
            * cpi_u_september[base_year]
            / cpi
            / 1_000_000_000,
        }
    )

    if not events.empty:
        recalls = events.copy()
        recalls["fiscal_year"] = to_fiscal_year(
            pd.to_datetime(recalls["recall_initiation_date"])
        )
        by_year = recalls.groupby("fiscal_year")
        yearly["Recall events"] = by_year.size()
        yearly["Class I share"] = by_year["classification"].apply(
            lambda c: (c == "Class I").mean()
        )
        yearly["Median days to classify"] = by_year[
            "classification_lag_days"
        ].median()

    if not illness.empty:
        human = illness[illness["source_type"].str.lower() == "human"].copy()
        human["fiscal_year"] = to_fiscal_year(
            pd.to_datetime(human["year_month"])
        )
        months = human.groupby("fiscal_year")["year_month"].nunique()
        isolates = human.groupby("fiscal_year")["isolate_count"].sum()
        yearly["Human isolates"] = isolates[months == 12]

    yearly.index.name = "fiscal_year"
    return yearly.sort_index()


if __name__ == "__main__":
    st.title("FDA Food Safety Monitor")

    try:
        states = pd.DataFrame(retrieve_data_from_api(api_base_url, "/states/"))
        funding = pd.DataFrame(
            retrieve_data_from_api(api_base_url, "/usaspending/")
        )
        events = pd.DataFrame(
            retrieve_data_from_api(api_base_url, "/fda-recalls/")
        )
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
            st.error(
                f"Could not load illness data for {selected_state}.\n\n{e}"
            )
            illness = pd.DataFrame()

        selected_pathogens = []
        if not illness.empty:
            st.write("Filter illness by Pathogen")
            for pathogen in sorted(illness["pathogen"].dropna().unique()):
                if st.checkbox(
                    pathogen, value=True, key=f"checkbox_{pathogen}"
                ):
                    selected_pathogens.append(pathogen)

        selected_classes = []
        if not events.empty:
            st.write("Filter recalls by Classification")
            for classification in sorted(
                events["classification"].dropna().unique()
            ):
                if st.checkbox(
                    classification,
                    value=True,
                    key=f"checkbox_{classification}",
                ):
                    selected_classes.append(classification)

    st.header("Recalls")
    if events.empty:
        st.info(
            "No recall data from the API yet. The GET /fda-recalls/ endpoint is needed."
        )
    else:
        events["report_date"] = pd.to_datetime(events["report_date"])
        filtered_events = events[
            events["classification"].isin(selected_classes)
        ]
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
                    state_counts.keys(),
                    categories=state_counts.keys(),
                    ordered=True,
                ),
            )
            st.bar_chart(state_df, x_label="State", y_label="Recall events")

    st.header(f"Foodborne illness in {state_names.get(selected_state)}")
    if illness.empty:
        st.info(
            f"No CDC illness data for {state_names.get(selected_state)} yet."
        )
    else:
        human = illness[
            (illness["source_type"].str.lower() == "human")
            & illness["pathogen"].isin(selected_pathogens)
        ]
        st.subheader("Human isolates per month")
        monthly_isolates = human.groupby("year_month")["isolate_count"].sum()
        st.bar_chart(
            monthly_isolates, x_label="Month", y_label="Human isolates"
        )

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
            obligations / 1_000_000_000,
            x_label="Fiscal year",
            y_label="$ billions",
        )

    st.header("Does FDA funding track food safety?")
    if funding.empty:
        st.info("No USAspending data yet.")
    else:
        try:
            national_illness = retrieve_national_illness(
                api_base_url, tuple(state_codes)
            )
        except requests.RequestException as e:
            st.error(f"Could not load national illness data.\n\n{e}")
            national_illness = pd.DataFrame()

        yearly = build_yearly_summary(funding, events, national_illness)
        base_year = max(cpi_u_september)
        st.caption(
            f"Funding is FDA obligations from USAspending, adjusted to FY{base_year} "
            "dollars with the CPI-U for September, the last month of each fiscal "
            "year (BLS). Recalls are grouped by the fiscal year they started. "
            "Human isolates are summed across all states, and only fiscal years "
            "with all 12 months of CDC data are shown."
        )

        st.subheader(
            f"FDA funding, nominal vs. inflation adjusted (FY{base_year} $)"
        )
        funding_long = (
            yearly[["Nominal funding ($B)", "Real funding ($B)"]]
            .reset_index()
            .melt("fiscal_year", var_name="series", value_name="billions")
        )
        funding_chart = (
            alt.Chart(funding_long)
            .mark_line(
                point=alt.OverlayMarkDef(size=70, filled=True), strokeWidth=2
            )
            .encode(
                x=alt.X("fiscal_year:O", title="Fiscal year"),
                y=alt.Y(
                    "billions:Q",
                    title="$ billions",
                    scale=alt.Scale(zero=False),
                ),
                color=alt.Color(
                    "series:N",
                    scale=alt.Scale(
                        domain=["Real funding ($B)", "Nominal funding ($B)"],
                        range=["#3987e5", "#8a8985"],
                    ),
                    legend=alt.Legend(title=None, orient="top"),
                ),
                strokeDash=alt.StrokeDash(
                    "series:N",
                    scale=alt.Scale(
                        domain=["Real funding ($B)", "Nominal funding ($B)"],
                        range=[[1, 0], [4, 3]],
                    ),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("fiscal_year:O", title="Fiscal year"),
                    alt.Tooltip("series:N", title="Series"),
                    alt.Tooltip(
                        "billions:Q", title="$ billions", format=".2f"
                    ),
                ],
            )
        )
        st.altair_chart(funding_chart, width="stretch")

        metrics = [
            m
            for m in series_colors
            if m == "FDA funding (inflation adjusted)" or m in yearly
        ]
        compare = yearly.rename(
            columns={"Real funding ($B)": "FDA funding (inflation adjusted)"}
        )[metrics].dropna()

        if len(compare) < 3 or len(metrics) < 2:
            st.info(
                "Not enough overlapping years of funding, recall and illness data "
                "to compare yet."
            )
        else:
            compare_base = compare.index.min()
            st.subheader(
                f"Funding vs. outcomes, indexed (FY{compare_base} = 100)"
            )
            indexed = (compare / compare.loc[compare_base] * 100).reset_index()
            indexed_long = indexed.melt(
                "fiscal_year", var_name="series", value_name="index"
            )
            indexed_long["actual"] = (
                compare.reset_index()
                .melt("fiscal_year", var_name="series", value_name="actual")[
                    "actual"
                ]
                .round(2)
            )
            color_scale = alt.Scale(
                domain=metrics, range=[series_colors[m] for m in metrics]
            )
            lines = (
                alt.Chart(indexed_long)
                .mark_line(
                    point=alt.OverlayMarkDef(size=70, filled=True),
                    strokeWidth=2,
                )
                .encode(
                    x=alt.X("fiscal_year:O", title="Fiscal year"),
                    y=alt.Y(
                        "index:Q",
                        title=f"Index (FY{compare_base} = 100)",
                        scale=alt.Scale(zero=False),
                    ),
                    color=alt.Color(
                        "series:N",
                        scale=color_scale,
                        legend=alt.Legend(
                            title=None, orient="top", labelLimit=260
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip("fiscal_year:O", title="Fiscal year"),
                        alt.Tooltip("series:N", title="Series"),
                        alt.Tooltip("actual:Q", title="Value"),
                        alt.Tooltip("index:Q", title="Index", format=".0f"),
                    ],
                )
            )
            baseline = (
                alt.Chart(pd.DataFrame({"index": [100]}))
                .mark_rule(strokeDash=[2, 2], opacity=0.5)
                .encode(y="index:Q")
            )
            st.altair_chart(baseline + lines, width="stretch")
            st.caption(
                "Each line starts at 100, so the lines show how much each measure "
                "rose or fell compared with the first year, on one scale."
            )

            st.subheader("Each fiscal year: funding vs. outcomes")
            outcomes = [
                m for m in metrics if m != "FDA funding (inflation adjusted)"
            ]
            scatter = compare.reset_index().melt(
                ["fiscal_year", "FDA funding (inflation adjusted)"],
                value_vars=outcomes,
                var_name="outcome",
                value_name="value",
            )
            scatter["label"] = (
                "FY" + scatter["fiscal_year"].astype(str).str[-2:]
            )
            scatter_base = alt.Chart().encode(
                x=alt.X(
                    "FDA funding (inflation adjusted):Q",
                    title=f"FDA funding (FY{base_year} $B)",
                    scale=alt.Scale(zero=False),
                ),
                y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False)),
            )
            points = scatter_base.mark_circle(size=90, opacity=0.9).encode(
                color=alt.Color("outcome:N", scale=color_scale, legend=None),
                tooltip=[
                    alt.Tooltip("fiscal_year:O", title="Fiscal year"),
                    alt.Tooltip(
                        "FDA funding (inflation adjusted):Q",
                        title="Funding ($B)",
                        format=".2f",
                    ),
                    alt.Tooltip("value:Q", title="Value"),
                ],
            )
            point_labels = scatter_base.mark_text(
                dy=-10, fontSize=10, color="#9b9a95"
            ).encode(text="label:N")
            scatter_chart = (
                alt.layer(points, point_labels, data=scatter)
                .properties(width=220, height=220)
                .facet(
                    facet=alt.Facet("outcome:N", title=None, sort=outcomes),
                    columns=3,
                )
                .resolve_scale(y="independent")
            )
            st.altair_chart(scatter_chart)

            correlations = pd.DataFrame(
                {
                    "Outcome": outcomes,
                    "Correlation with funding (r)": [
                        round(
                            compare["FDA funding (inflation adjusted)"].corr(
                                compare[m]
                            ),
                            2,
                        )
                        for m in outcomes
                    ],
                    "Fiscal years": len(compare),
                }
            )
            st.dataframe(correlations, hide_index=True)
            st.caption(
                "r runs from -1 to 1. A negative r means the outcome tends to be "
                "higher in years with less funding. With only a few fiscal years, "
                "these are signals to look into, not proof that funding caused the "
                "change."
            )

        with st.expander("Yearly numbers"):
            st.dataframe(yearly.round(2).reset_index(), hide_index=True)
