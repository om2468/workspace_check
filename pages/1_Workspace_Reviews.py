import json
from collections import Counter
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


DATA_PATH = Path("workspace_office_reviews.csv")
LIST_COLUMNS = [
    "KeyComments",
    "PositiveThemes",
    "NegativeThemes",
    "PositiveCommentExamples",
    "NegativeCommentExamples",
]


st.set_page_config(page_title="Workspace Reviews", layout="wide")


def parse_json_list(value):
    if pd.isna(value) or value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return [item.strip() for item in str(value).split("|") if item.strip()]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [str(parsed).strip()] if str(parsed).strip() else []


@st.cache_data
def load_reviews(path: str) -> pd.DataFrame:
    reviews = pd.read_csv(path)
    for column in LIST_COLUMNS:
        reviews[column] = reviews[column].apply(parse_json_list)

    reviews["GoogleMapsRating"] = pd.to_numeric(reviews["GoogleMapsRating"], errors="coerce")
    reviews["GoogleMapsReviewCount"] = pd.to_numeric(reviews["GoogleMapsReviewCount"], errors="coerce")
    reviews["HasReviewData"] = reviews["GoogleMapsRating"].notna()
    reviews["GoogleMapsReviewCount"] = reviews["GoogleMapsReviewCount"].fillna(0).astype(int)
    reviews["ReviewSummary"] = reviews["ReviewSummary"].fillna("")
    reviews["ReviewNotes"] = reviews["ReviewNotes"].fillna("")
    reviews["PlaceStatus"] = reviews["PlaceStatus"].fillna("Unknown")
    reviews["AreaOfLondon"] = reviews["AreaOfLondon"].fillna("Other")

    ratings = reviews.loc[reviews["HasReviewData"], "GoogleMapsRating"]
    counts = reviews.loc[reviews["HasReviewData"], "GoogleMapsReviewCount"]
    global_mean = ratings.mean() if not ratings.empty else 0
    minimum_votes = counts.quantile(0.6) if not counts.empty else 0
    minimum_votes = max(float(minimum_votes), 1.0)

    votes = reviews["GoogleMapsReviewCount"].astype(float)
    ratings_full = reviews["GoogleMapsRating"].fillna(global_mean)
    reviews["WeightedRating"] = ((votes / (votes + minimum_votes)) * ratings_full) + (
        (minimum_votes / (votes + minimum_votes)) * global_mean
    )
    reviews.loc[~reviews["HasReviewData"], "WeightedRating"] = pd.NA
    reviews["PerformanceScore"] = (reviews["WeightedRating"] * 20).round(1)
    reviews["ReviewCoverage"] = reviews["GoogleMapsReviewCount"].where(reviews["HasReviewData"], 0)
    reviews["KeyCommentsJoined"] = reviews["KeyComments"].apply(lambda values: " | ".join(values))
    reviews["PositiveThemesJoined"] = reviews["PositiveThemes"].apply(lambda values: " | ".join(values))
    reviews["NegativeThemesJoined"] = reviews["NegativeThemes"].apply(lambda values: " | ".join(values))
    return reviews.sort_values(["PerformanceScore", "GoogleMapsRating", "GoogleMapsReviewCount", "Name"], ascending=[False, False, False, True])


def extract_theme_counts(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    counter = Counter()
    for values in frame[column]:
        counter.update(values)
    if not counter:
        return pd.DataFrame(columns=["Theme", "Count"])
    return (
        pd.DataFrame(counter.items(), columns=["Theme", "Count"])
        .sort_values(["Count", "Theme"], ascending=[False, True])
        .reset_index(drop=True)
    )


def matches_selected_themes(values, selected_themes):
    if not selected_themes:
        return True
    return any(theme in values for theme in selected_themes)


def render_theme_list(title: str, values: list[str]):
    st.markdown(f"**{title}**")
    if values:
        st.caption(" | ".join(values))
    else:
        st.caption("No themes captured")


st.title("Workspace Office Reviews")
st.markdown("Google Maps-grounded review intelligence for each Workspace site, with ranking, theme analysis, and site-by-site drilldowns.")

if not DATA_PATH.exists():
    st.error("The review dataset is missing. Run `python build_workspace_reviews.py` from the project root to generate it.")
    st.stop()

reviews = load_reviews(str(DATA_PATH))

with DATA_PATH.open("rb") as file_handle:
    st.download_button(
        label="Download review dataset",
        data=file_handle.read(),
        file_name=DATA_PATH.name,
        mime="text/csv",
        width="stretch",
    )

all_positive_themes = sorted({theme for values in reviews["PositiveThemes"] for theme in values})
all_negative_themes = sorted({theme for values in reviews["NegativeThemes"] for theme in values})
all_areas = sorted(reviews["AreaOfLondon"].dropna().unique().tolist())
all_statuses = sorted(reviews["PlaceStatus"].dropna().unique().tolist())
max_reviews = int(reviews["GoogleMapsReviewCount"].max()) if len(reviews) else 0

st.sidebar.header("Review Filters")
selected_areas = st.sidebar.multiselect("Area of London", all_areas, default=all_areas)
selected_statuses = st.sidebar.multiselect("Place status", all_statuses, default=all_statuses)
require_review_data = st.sidebar.toggle("Only show sites with review data", value=False)
min_review_count = st.sidebar.slider("Minimum review count", 0, max_reviews, 0)
selected_positive_themes = st.sidebar.multiselect("Positive factors", all_positive_themes)
selected_negative_themes = st.sidebar.multiselect("Negative factors", all_negative_themes)
search_text = st.sidebar.text_input("Search site or address")

filtered = reviews.loc[
    reviews["AreaOfLondon"].isin(selected_areas)
    & reviews["PlaceStatus"].isin(selected_statuses)
    & (reviews["GoogleMapsReviewCount"] >= min_review_count)
].copy()

if require_review_data:
    filtered = filtered.loc[filtered["HasReviewData"]].copy()

if selected_positive_themes:
    filtered = filtered.loc[filtered["PositiveThemes"].apply(matches_selected_themes, args=(selected_positive_themes,))]

if selected_negative_themes:
    filtered = filtered.loc[filtered["NegativeThemes"].apply(matches_selected_themes, args=(selected_negative_themes,))]

if search_text.strip():
    query = search_text.strip().lower()
    filtered = filtered.loc[
        filtered["Name"].str.lower().str.contains(query)
        | filtered["GroundedName"].fillna("").str.lower().str.contains(query)
        | filtered["Address"].fillna("").str.lower().str.contains(query)
        | filtered["Postcode"].fillna("").str.lower().str.contains(query)
    ]

positive_theme_counts = extract_theme_counts(filtered, "PositiveThemes")
negative_theme_counts = extract_theme_counts(filtered, "NegativeThemes")
reviewed_sites = filtered.loc[filtered["HasReviewData"]].copy()

metric_columns = st.columns(5)
metric_columns[0].metric("Sites in scope", f"{len(filtered)}")
metric_columns[1].metric("Sites with reviews", f"{int(filtered['HasReviewData'].sum())}")
metric_columns[2].metric(
    "Average rating",
    f"{reviewed_sites['GoogleMapsRating'].mean():.2f}" if len(reviewed_sites) else "N/A",
)
metric_columns[3].metric(
    "Average review count",
    f"{reviewed_sites['GoogleMapsReviewCount'].mean():.0f}" if len(reviewed_sites) else "N/A",
)
metric_columns[4].metric(
    "Top area by score",
    (
        filtered.dropna(subset=["PerformanceScore"]).groupby("AreaOfLondon")["PerformanceScore"].mean().sort_values(ascending=False).index[0]
        if filtered["PerformanceScore"].notna().any()
        else "N/A"
    ),
)

overview_tab, ranking_tab, themes_tab, site_tab = st.tabs(["Overview", "Best to Worst", "Theme Breakdown", "Site Drilldown"])

with overview_tab:
    left_col, right_col = st.columns([1.3, 1])
    with left_col:
        st.markdown("### Rating vs Review Volume")
        if len(reviewed_sites):
            scatter = (
                alt.Chart(reviewed_sites)
                .mark_circle(size=120, opacity=0.85)
                .encode(
                    x=alt.X("GoogleMapsReviewCount:Q", title="Review count"),
                    y=alt.Y("GoogleMapsRating:Q", title="Google Maps rating", scale=alt.Scale(domain=[0, 5])),
                    color=alt.Color("AreaOfLondon:N", title="Area"),
                    tooltip=[
                        alt.Tooltip("Name:N", title="Site"),
                        alt.Tooltip("AreaOfLondon:N", title="Area"),
                        alt.Tooltip("GoogleMapsRating:Q", title="Rating", format=".2f"),
                        alt.Tooltip("GoogleMapsReviewCount:Q", title="Reviews"),
                        alt.Tooltip("PerformanceScore:Q", title="Performance", format=".1f"),
                    ],
                )
            )
            st.altair_chart(scatter, width="stretch")
        else:
            st.info("No reviewed sites match the current filters.")

    with right_col:
        st.markdown("### Area Snapshot")
        area_summary = (
            filtered.groupby("AreaOfLondon")
            .agg(
                sites=("Name", "count"),
                reviewed_sites=("HasReviewData", "sum"),
                avg_rating=("GoogleMapsRating", "mean"),
                avg_performance=("PerformanceScore", "mean"),
            )
            .reset_index()
            .sort_values(["avg_performance", "sites"], ascending=[False, False])
        )
        st.dataframe(area_summary, width="stretch", hide_index=True)

with ranking_tab:
    st.markdown("### Performance Ranking")
    ranking_frame = filtered.copy()
    ranking_frame["RankingLabel"] = ranking_frame["Name"] + " (" + ranking_frame["AreaOfLondon"] + ")"
    ranking_chart_frame = ranking_frame.dropna(subset=["PerformanceScore"]).head(30)
    if len(ranking_chart_frame):
        ranking_chart = (
            alt.Chart(ranking_chart_frame)
            .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
            .encode(
                x=alt.X("PerformanceScore:Q", title="Performance score"),
                y=alt.Y("RankingLabel:N", sort="-x", title="Site"),
                color=alt.Color("AreaOfLondon:N", title="Area"),
                tooltip=[
                    alt.Tooltip("Name:N", title="Site"),
                    alt.Tooltip("AreaOfLondon:N", title="Area"),
                    alt.Tooltip("GoogleMapsRating:Q", title="Rating", format=".2f"),
                    alt.Tooltip("GoogleMapsReviewCount:Q", title="Reviews"),
                    alt.Tooltip("PerformanceScore:Q", title="Performance", format=".1f"),
                ],
            )
        )
        st.altair_chart(ranking_chart, width="stretch")
    else:
        st.info("No ranked sites are available for the current filters.")

    st.dataframe(
        ranking_frame[
            [
                "Name",
                "GroundedName",
                "AreaOfLondon",
                "PlaceStatus",
                "GoogleMapsRating",
                "GoogleMapsReviewCount",
                "PerformanceScore",
                "PositiveThemesJoined",
                "NegativeThemesJoined",
            ]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "PerformanceScore": st.column_config.ProgressColumn(
                "Performance score", min_value=0, max_value=100, format="%.1f"
            )
        },
    )

with themes_tab:
    left_col, right_col = st.columns(2)
    with left_col:
        st.markdown("### Positive Drivers")
        if len(positive_theme_counts):
            positive_chart = (
                alt.Chart(positive_theme_counts.head(12))
                .mark_bar(color="#1f8a70", cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    x=alt.X("Count:Q", title="Mentions"),
                    y=alt.Y("Theme:N", sort="-x", title="Theme"),
                    tooltip=["Theme", "Count"],
                )
            )
            st.altair_chart(positive_chart, width="stretch")
        else:
            st.info("No positive themes match the current filters.")

    with right_col:
        st.markdown("### Friction Points")
        if len(negative_theme_counts):
            negative_chart = (
                alt.Chart(negative_theme_counts.head(12))
                .mark_bar(color="#c44536", cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    x=alt.X("Count:Q", title="Mentions"),
                    y=alt.Y("Theme:N", sort="-x", title="Theme"),
                    tooltip=["Theme", "Count"],
                )
            )
            st.altair_chart(negative_chart, width="stretch")
        else:
            st.info("No negative themes match the current filters.")

    st.markdown("### Theme Tables")
    theme_table_left, theme_table_right = st.columns(2)
    with theme_table_left:
        st.dataframe(positive_theme_counts, width="stretch", hide_index=True)
    with theme_table_right:
        st.dataframe(negative_theme_counts, width="stretch", hide_index=True)

with site_tab:
    if filtered.empty:
        st.info("No sites match the current filters.")
    else:
        selected_site = st.selectbox("Choose a site", filtered["Name"].tolist())
        site = filtered.loc[filtered["Name"] == selected_site].iloc[0]

        info_columns = st.columns(4)
        info_columns[0].metric("Google rating", f"{site['GoogleMapsRating']:.2f}" if pd.notna(site["GoogleMapsRating"]) else "N/A")
        info_columns[1].metric("Review count", f"{int(site['GoogleMapsReviewCount'])}")
        info_columns[2].metric("Performance score", f"{site['PerformanceScore']:.1f}" if pd.notna(site["PerformanceScore"]) else "N/A")
        info_columns[3].metric("Status", site["PlaceStatus"])

        st.markdown("### Summary")
        st.write(site["ReviewSummary"] or "No summary available.")

        st.markdown("### Signals")
        signals_left, signals_right = st.columns(2)
        with signals_left:
            render_theme_list("Positive themes", site["PositiveThemes"])
            st.markdown("**Positive comment examples**")
            if site["PositiveCommentExamples"]:
                for comment in site["PositiveCommentExamples"]:
                    st.write(f"- {comment}")
            else:
                st.caption("No positive examples captured")
        with signals_right:
            render_theme_list("Negative themes", site["NegativeThemes"])
            st.markdown("**Negative comment examples**")
            if site["NegativeCommentExamples"]:
                for comment in site["NegativeCommentExamples"]:
                    st.write(f"- {comment}")
            else:
                st.caption("No negative examples captured")

        st.markdown("### Key Comments")
        if site["KeyComments"]:
            for comment in site["KeyComments"]:
                st.write(f"- {comment}")
        else:
            st.caption("No key comments captured")

        st.markdown("### Grounding Notes")
        st.caption(site["ReviewNotes"] or "No grounding notes available.")