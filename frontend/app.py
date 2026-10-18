import os

import altair as alt
import google.auth.transport.requests
import pandas as pd
import requests
import streamlit as st
from google.oauth2 import id_token

api_base_url = os.getenv("API_BASE_URL", "http://localhost:8080").rstrip("/")

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
funding_series = "FDA funding (inflation adjusted)"
series_colors = {
    funding_series: "#3987e5",
    "Recall events": "#d95926",
    "Human isolates": "#199e70",
    "Median days to classify": "#c98500",
}
series_dashes = {
    funding_series: [1, 0],
    "Recall events": [6, 3],
    "Human isolates": [2, 2],
    "Median days to classify": [8, 3, 2, 3],
}
state_fips = {
    "AL": 1,
    "AK": 2,
    "AZ": 4,
    "AR": 5,
    "CA": 6,
    "CO": 8,
    "CT": 9,
    "DE": 10,
    "DC": 11,
    "FL": 12,
    "GA": 13,
    "HI": 15,
    "ID": 16,
    "IL": 17,
    "IN": 18,
    "IA": 19,
    "KS": 20,
    "KY": 21,
    "LA": 22,
    "ME": 23,
    "MD": 24,
    "MA": 25,
    "MI": 26,
    "MN": 27,
    "MS": 28,
    "MO": 29,
    "MT": 30,
    "NE": 31,
    "NV": 32,
    "NH": 33,
    "NJ": 34,
    "NM": 35,
    "NY": 36,
    "NC": 37,
    "ND": 38,
    "OH": 39,
    "OK": 40,
    "OR": 41,
    "PA": 42,
    "RI": 44,
    "SC": 45,
    "SD": 46,
    "TN": 47,
    "TX": 48,
    "UT": 49,
    "VT": 50,
    "VA": 51,
    "WA": 53,
    "WV": 54,
    "WI": 55,
    "WY": 56,
    "PR": 72,
}
us_states_topojson = (
    "https://cdn.jsdelivr.net/npm/vega-datasets@v1.29.0/data/us-10m.json"
)


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


@st.cache_data(ttl=600)
def retrieve_illness(api_base_url: str, state_codes: tuple) -> pd.DataFrame:
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


def fill_months(
    monthly: pd.Series, start_fy: int, end_fy: int, last_month: pd.Timestamp
) -> pd.DataFrame:
    if monthly.empty:
        return pd.DataFrame({"month": [], "value": []})
    start = max(pd.Timestamp(start_fy - 1, 10, 1), monthly.index.min())
    end = min(pd.Timestamp(end_fy, 9, 1), last_month)
    months = pd.date_range(start, end, freq="MS")
    return (
        monthly.reindex(months, fill_value=0)
        .rename_axis("month")
        .reset_index(name="value")
    )


def monthly_line_chart(
    monthly: pd.DataFrame, y_title: str, color: str
) -> alt.Chart:
    return (
        alt.Chart(monthly)
        .mark_line(strokeWidth=2, color=color)
        .encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("value:Q", title=y_title),
            tooltip=[
                alt.Tooltip("month:T", title="Month", format="%b %Y"),
                alt.Tooltip("value:Q", title=y_title, format=","),
            ],
        )
    )


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
        by_year = events.groupby("fiscal_year")
        yearly["Recall events"] = by_year.size()
        yearly["Class I share"] = by_year["classification"].apply(
            lambda c: (c == "Class I").mean()
        )
        yearly["Median days to classify"] = by_year[
            "classification_lag_days"
        ].median()

    if not illness.empty:
        months = illness.groupby("fiscal_year")["year_month"].nunique()
        isolates = illness.groupby("fiscal_year")["isolate_count"].sum()
        yearly["Human isolates"] = isolates[months == 12]

    yearly.index.name = "fiscal_year"
    return yearly.sort_index()


if __name__ == "__main__":
    st.set_page_config(page_title="FDA Food Safety Monitor", layout="wide")
    st.title("FDA Food Safety Monitor")
    st.write(
        "This dashboard compares FDA funding with food recalls and "
        "foodborne illness to see whether budget changes line up with fewer "
        "or slower recalls and more people getting sick. Use the sidebar to "
        "filter by fiscal year, state, recall class and pathogen."
    )
    st.caption(
        "Recalls are counted by the date FDA reported them. Fiscal years run "
        "October to September. Funding is shown in inflation-adjusted dollars "
        "where noted."
    )

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
            f"is running.\n\n{e}"
        )
        st.stop()

    state_names = dict(zip(states["state_code"], states["state_name"]))
    state_codes = sorted(state_names, key=state_names.get)

    if not events.empty:
        events["report_date"] = pd.to_datetime(events["report_date"])
        events["fiscal_year"] = to_fiscal_year(events["report_date"])

    known_years = []
    if not events.empty:
        known_years += events["fiscal_year"].dropna().astype(int).tolist()
    if not funding.empty:
        known_years += funding["fiscal_year"].astype(int).tolist()
    min_fy = min(known_years) if known_years else 2017
    max_fy = max(known_years) if known_years else max(cpi_u_september)

    with st.sidebar:
        st.header("Filters")
        if min_fy < max_fy:
            start_fy, end_fy = st.slider(
                "Fiscal years", min_fy, max_fy, (min_fy, max_fy)
            )
        else:
            start_fy, end_fy = min_fy, max_fy

        selected_states = st.multiselect(
            "States",
            state_codes,
            format_func=state_names.get,
            placeholder="All states",
        )
        chosen_states = selected_states or state_codes

        class_options = (
            sorted(events["classification"].dropna().unique())
            if not events.empty
            else []
        )
        selected_classes = st.multiselect(
            "Recall class", class_options, default=class_options
        )

        try:
            illness = retrieve_illness(api_base_url, tuple(chosen_states))
        except requests.RequestException as e:
            st.error(f"Could not load illness data.\n\n{e}")
            illness = pd.DataFrame()

        pathogen_options = (
            sorted(illness["pathogen"].dropna().unique())
            if not illness.empty
            else []
        )
        selected_pathogens = st.multiselect(
            "Pathogen", pathogen_options, default=pathogen_options
        )

        firm_search = st.text_input(
            "Search recalling firm", placeholder="e.g. Kraft"
        )

    state_label = (
        ", ".join(state_names[code] for code in selected_states)
        if selected_states
        else "all states"
    )

    filtered_events = pd.DataFrame()
    if not events.empty:
        filtered_events = events[
            events["classification"].isin(selected_classes)
            & events["fiscal_year"].between(start_fy, end_fy)
        ]
        if selected_states:
            filtered_events = filtered_events[
                filtered_events["state_code"].isin(selected_states)
            ]
        if firm_search:
            filtered_events = filtered_events[
                filtered_events["recalling_firm"].str.contains(
                    firm_search, case=False, regex=False, na=False
                )
            ]
        filtered_events = filtered_events.sort_values(
            by=["report_date", "recalling_firm"], ascending=[False, True]
        )

    human_illness = pd.DataFrame()
    if not illness.empty:
        human_illness = illness[
            (illness["source_type"].str.lower() == "human")
            & illness["pathogen"].isin(selected_pathogens)
        ].copy()
        human_illness["month"] = pd.to_datetime(human_illness["year_month"])
        human_illness["fiscal_year"] = to_fiscal_year(human_illness["month"])
        human_illness = human_illness[
            human_illness["fiscal_year"].between(start_fy, end_fy)
        ]

    yearly = pd.DataFrame()
    if not funding.empty:
        yearly = build_yearly_summary(funding, filtered_events, human_illness)
        yearly = yearly[(yearly.index >= start_fy) & (yearly.index <= end_fy)]
        missing_cpi = sorted(
            set(funding["fiscal_year"].astype(int)) - set(cpi_u_september)
        )
        if missing_cpi:
            st.warning(
                "No inflation value yet for FY"
                + ", FY".join(str(year) for year in missing_cpi)
                + ", so those years are left out of the funding charts. Add "
                "the September CPI-U to cpi_u_september in frontend/app.py."
            )

    metric_columns = st.columns(4)
    metric_columns[0].metric("Recall events", f"{len(filtered_events):,}")
    if not filtered_events.empty:
        class_i_share = (filtered_events["classification"] == "Class I").mean()
        median_lag = filtered_events["classification_lag_days"].median()
        metric_columns[1].metric("Class I share", f"{class_i_share:.0%}")
        metric_columns[2].metric(
            "Median days to classify",
            "n/a" if pd.isna(median_lag) else f"{median_lag:.0f}",
        )
    real_funding = (
        yearly["Real funding ($B)"].dropna()
        if "Real funding ($B)" in yearly
        else pd.Series(dtype=float)
    )
    if not real_funding.empty:
        latest_year = real_funding.index.max()
        change = None
        if latest_year - 1 in real_funding.index:
            previous = real_funding.loc[latest_year - 1]
            change = f"{(real_funding.loc[latest_year] / previous - 1):+.1%}"
        metric_columns[3].metric(
            f"FDA funding FY{latest_year} (FY{max(cpi_u_september)} $)",
            f"${real_funding.loc[latest_year]:.2f}B",
            delta=change,
            help="Change from the previous fiscal year, after inflation.",
        )

    recalls_tab, illness_tab, outcomes_tab = st.tabs(
        ["Recalls", "Illness", "Funding vs. outcomes"]
    )

    with recalls_tab:
        if events.empty:
            st.info(
                "No recall data yet. Run the recall collector "
                "(POST /fda-recalls/scrape/) to load it."
            )
        elif filtered_events.empty:
            st.info("No recalls match these filters.")
        else:
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
            st.subheader(f"Recall events in {state_label}")
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
            st.download_button(
                "Download these recalls (CSV)",
                table.to_csv(index=False),
                file_name=f"fda_recalls_FY{start_fy}-FY{end_fy}.csv",
                mime="text/csv",
            )

            st.subheader("Recall events per month")
            monthly_counts = (
                filtered_events["report_date"]
                .dt.to_period("M")
                .dt.to_timestamp()
                .value_counts()
                .sort_index()
            )
            st.altair_chart(
                monthly_line_chart(
                    fill_months(
                        monthly_counts,
                        start_fy,
                        end_fy,
                        events["report_date"]
                        .max()
                        .to_period("M")
                        .to_timestamp(),
                    ),
                    "Recall events",
                    series_colors["Recall events"],
                ),
                width="stretch",
            )

            st.subheader("Share of recalls that are Class I, by fiscal year")
            class_i_by_year = (
                filtered_events.groupby("fiscal_year")["classification"]
                .apply(lambda c: (c == "Class I").mean())
                .reset_index(name="share")
            )
            st.altair_chart(
                alt.Chart(class_i_by_year)
                .mark_line(
                    point=alt.OverlayMarkDef(
                        size=70,
                        filled=True,
                        color=series_colors["Recall events"],
                    ),
                    strokeWidth=2,
                    color=series_colors["Recall events"],
                )
                .encode(
                    x=alt.X("fiscal_year:O", title="Fiscal year"),
                    y=alt.Y(
                        "share:Q",
                        title="Class I share",
                        axis=alt.Axis(format="%"),
                    ),
                    tooltip=[
                        alt.Tooltip("fiscal_year:O", title="Fiscal year"),
                        alt.Tooltip("share:Q", title="Class I", format=".0%"),
                    ],
                ),
                width="stretch",
            )
            st.caption(
                "Class I recalls are the most serious: the product could cause "
                "serious illness or death."
            )

            state_counts = (
                filtered_events["state_code"]
                .dropna()
                .value_counts()
                .rename_axis("state_code")
                .reset_index(name="recall_events")
            )
            state_counts["state_name"] = (
                state_counts["state_code"]
                .map(state_names)
                .fillna(state_counts["state_code"])
            )

            map_column, bar_column = st.columns(2)
            with map_column:
                st.subheader("Recall events by state")
                map_data = pd.DataFrame(
                    {
                        "state_code": list(state_fips),
                        "id": list(state_fips.values()),
                    }
                ).merge(state_counts, on="state_code", how="left")
                map_data["recall_events"] = (
                    map_data["recall_events"].fillna(0).astype(int)
                )
                map_data["state_name"] = (
                    map_data["state_code"]
                    .map(state_names)
                    .fillna(map_data["state_code"])
                )
                st.altair_chart(
                    alt.Chart(alt.topo_feature(us_states_topojson, "states"))
                    .mark_geoshape(stroke="#8a8985", strokeWidth=0.5)
                    .encode(
                        color=alt.Color(
                            "recall_events:Q",
                            title="Recall events",
                            scale=alt.Scale(scheme="blues"),
                        ),
                        tooltip=[
                            alt.Tooltip("state_name:N", title="State"),
                            alt.Tooltip(
                                "recall_events:Q", title="Recall events"
                            ),
                        ],
                    )
                    .transform_lookup(
                        lookup="id",
                        from_=alt.LookupData(
                            map_data, "id", ["recall_events", "state_name"]
                        ),
                    )
                    .project(type="albersUsa")
                    .properties(height=380),
                    width="stretch",
                )

            with bar_column:
                st.subheader("States with the most recall events")
                top_states = state_counts.head(10)
                st.altair_chart(
                    alt.Chart(top_states)
                    .mark_bar(
                        color=series_colors[funding_series],
                        cornerRadiusEnd=4,
                    )
                    .encode(
                        x=alt.X("recall_events:Q", title="Recall events"),
                        y=alt.Y("state_name:N", title=None, sort="-x"),
                        tooltip=[
                            alt.Tooltip("state_name:N", title="State"),
                            alt.Tooltip(
                                "recall_events:Q", title="Recall events"
                            ),
                        ],
                    )
                    .properties(height=380),
                    width="stretch",
                )
            st.caption(
                "Counts are by the recalling firm's state and aren't adjusted "
                "for population, so states with more food companies rank "
                "higher. Firms outside the US have no state and are left out."
            )

        st.subheader("Recall announcements not yet in openFDA (Experimental)")
        try:
            unmatched = pd.DataFrame(
                retrieve_data_from_api(
                    api_base_url, "/fda-recalls/announcements/unmatched/"
                )
            )
        except requests.RequestException as e:
            st.error(f"Could not load recall announcements.\n\n{e}")
            unmatched = pd.DataFrame()

        if unmatched.empty:
            st.info("No unmatched recall announcements.")
        else:
            st.caption(
                "Companies post these announcements when a recall starts. "
                "They may not be in openFDA yet, or the company name didn't "
                "match an openFDA recall."
            )

            unmatched["announce_date"] = pd.to_datetime(
                unmatched["announce_date"]
            ).dt.date

            st.metric("Unmatched announcements", len(unmatched))
            st.dataframe(
                unmatched[
                    [
                        "announce_date",
                        "company",
                        "brand",
                        "product",
                        "reason",
                        "detail_url",
                    ]
                ],
                hide_index=True,
                column_config={
                    "announce_date": "Announced",
                    "company": "Company",
                    "brand": "Brand",
                    "product": "Product",
                    "reason": "Reason",
                    "detail_url": st.column_config.LinkColumn(
                        "FDA page", display_text="View"
                    ),
                },
            )

    with illness_tab:
        st.subheader(f"Human isolates per month in {state_label}")
        if illness.empty:
            st.info(
                "No CDC illness data yet. Run the CDC collector "
                "(POST /cdc/scrape/) to load it."
            )
        elif human_illness.empty:
            st.info("No illness data matches these filters.")
        else:
            monthly_isolates = human_illness.groupby("month")[
                "isolate_count"
            ].sum()
            last_month = pd.to_datetime(illness["year_month"]).max()
            st.altair_chart(
                monthly_line_chart(
                    fill_months(
                        monthly_isolates, start_fy, end_fy, last_month
                    ),
                    "Human isolates",
                    series_colors["Human isolates"],
                ),
                width="stretch",
            )
            st.caption(
                "Lab-confirmed samples from people, for the pathogens selected "
                "in the sidebar. The latest month may still be incomplete."
            )

    with outcomes_tab:
        st.subheader("Does FDA funding track food safety?")
        if funding.empty:
            st.info(
                "No FDA funding data yet. Run the USAspending collector "
                "(POST /usaspending/scrape/) to load it."
            )
        elif yearly.empty:
            st.info("No funding data in the selected fiscal years.")
        else:
            base_year = max(cpi_u_september)
            st.caption(
                f"Funding is FDA obligations from USAspending, adjusted to "
                f"FY{base_year} dollars with the CPI-U for September, the last "
                "month of each fiscal year (BLS). Funding is national. Recalls "
                "and illness follow the sidebar filters. Only fiscal years "
                "with all 12 months of CDC data are compared."
            )

            st.subheader(
                f"FDA funding, nominal vs. inflation adjusted (FY{base_year} $)"
            )
            funding_long = (
                yearly[["Nominal funding ($B)", "Real funding ($B)"]]
                .reset_index()
                .melt("fiscal_year", var_name="series", value_name="billions")
            )
            funding_domain = ["Real funding ($B)", "Nominal funding ($B)"]
            st.altair_chart(
                alt.Chart(funding_long)
                .mark_line(
                    point=alt.OverlayMarkDef(size=70, filled=True),
                    strokeWidth=2,
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
                            domain=funding_domain,
                            range=["#3987e5", "#8a8985"],
                        ),
                        legend=alt.Legend(title=None, orient="top"),
                    ),
                    strokeDash=alt.StrokeDash(
                        "series:N",
                        scale=alt.Scale(
                            domain=funding_domain, range=[[1, 0], [4, 3]]
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
                ),
                width="stretch",
            )

            metrics = [
                m for m in series_colors if m == funding_series or m in yearly
            ]
            compare = yearly.rename(
                columns={"Real funding ($B)": funding_series}
            )[metrics].dropna()

            if len(compare) < 3 or len(metrics) < 2:
                st.info(
                    "Not enough overlapping years of funding, recall and "
                    "illness data to compare. Try a wider fiscal year range "
                    "or fewer filters."
                )
            else:
                compare_base = compare.index.min()
                year_range = f"FY{compare_base}–FY{compare.index.max()}"
                st.subheader(
                    f"Funding vs. outcomes, indexed (FY{compare_base} = 100)"
                )
                indexed = (
                    compare / compare.loc[compare_base] * 100
                ).reset_index()
                indexed_long = indexed.melt(
                    "fiscal_year", var_name="series", value_name="index"
                )
                indexed_long["actual"] = (
                    compare.reset_index()
                    .melt(
                        "fiscal_year", var_name="series", value_name="actual"
                    )["actual"]
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
                        strokeDash=alt.StrokeDash(
                            "series:N",
                            scale=alt.Scale(
                                domain=metrics,
                                range=[series_dashes[m] for m in metrics],
                            ),
                            legend=None,
                        ),
                        tooltip=[
                            alt.Tooltip("fiscal_year:O", title="Fiscal year"),
                            alt.Tooltip("series:N", title="Series"),
                            alt.Tooltip("actual:Q", title="Value"),
                            alt.Tooltip(
                                "index:Q", title="Index", format=".0f"
                            ),
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
                    "Each line starts at 100, so the lines show how much each "
                    "measure rose or fell compared with the first year, on one "
                    "scale. Line styles differ so the chart doesn't rely on "
                    "color alone."
                )

                st.subheader("Each fiscal year: funding vs. outcomes")
                outcomes = [m for m in metrics if m != funding_series]
                scatter = compare.reset_index().melt(
                    ["fiscal_year", funding_series],
                    value_vars=outcomes,
                    var_name="outcome",
                    value_name="value",
                )
                scatter["label"] = (
                    "FY" + scatter["fiscal_year"].astype(str).str[-2:]
                )
                scatter_base = alt.Chart().encode(
                    x=alt.X(
                        f"{funding_series}:Q",
                        title=f"FDA funding (FY{base_year} $B)",
                        scale=alt.Scale(zero=False),
                    ),
                    y=alt.Y(
                        "value:Q", title=None, scale=alt.Scale(zero=False)
                    ),
                )
                points = scatter_base.mark_circle(size=90, opacity=0.9).encode(
                    color=alt.Color(
                        "outcome:N", scale=color_scale, legend=None
                    ),
                    tooltip=[
                        alt.Tooltip("fiscal_year:O", title="Fiscal year"),
                        alt.Tooltip(
                            f"{funding_series}:Q",
                            title="Funding ($B)",
                            format=".2f",
                        ),
                        alt.Tooltip("value:Q", title="Value"),
                    ],
                )
                point_labels = scatter_base.mark_text(
                    dy=-10, fontSize=10, color="#9b9a95"
                ).encode(text="label:N")
                st.altair_chart(
                    alt.layer(points, point_labels, data=scatter)
                    .properties(width=220, height=220)
                    .facet(
                        facet=alt.Facet(
                            "outcome:N", title=None, sort=outcomes
                        ),
                        columns=3,
                    )
                    .resolve_scale(y="independent")
                )

                correlations = pd.DataFrame(
                    {
                        "Outcome": outcomes,
                        "Correlation with funding (r)": [
                            round(compare[funding_series].corr(compare[m]), 2)
                            for m in outcomes
                        ],
                        "Fiscal years": f"{year_range} ({len(compare)} years)",
                    }
                )
                st.dataframe(correlations, hide_index=True)
                st.caption(
                    "r runs from -1 to 1. A negative r means the outcome tends "
                    "to be higher in years with less funding. With only a few "
                    "fiscal years, these are signals to look into, not proof "
                    "that funding caused the change."
                )

            with st.expander("Yearly numbers"):
                st.dataframe(yearly.round(2).reset_index(), hide_index=True)
