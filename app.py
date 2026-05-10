from pathlib import Path

import duckdb
import pandas as pd
import pydeck as pdk
import streamlit as st


DB_PATH = "gym_locator.db"
OFFICE_COLOR = [255, 221, 87, 220]
PUREGYM_COLOR = [28, 99, 255, 180]
GYMGROUP_COLOR = [230, 57, 70, 180]
LONDON_CENTER = {"lat": 51.5074, "lon": -0.1278}
DATA_FILES = [
    ("Workspace office locations", Path("workspace_office_locations.csv")),
    ("PureGym geocoded results", Path("puregym_locations_geocoded.csv")),
    ("The Gym Group geocoded results", Path("gymgroup_locations_geocoded.csv")),
]


st.set_page_config(page_title="Workspace Gym Finder", layout="wide")


@st.cache_data
def load_data():
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        offices = con.execute(
            "SELECT office_name, address, lat, lon, postcode FROM offices ORDER BY office_name"
        ).df()
        gyms = con.execute(
            """
            SELECT Office, Name, Address, Duration, Distance, CrowFliesDistanceM, lat, lon,
                   CASE
                       WHEN source = 'puregym' THEN 'PureGym'
                       ELSE 'The Gym Group'
                   END AS Brand
            FROM (
                SELECT 'puregym' AS source, Office, Name, Address, Duration, Distance, CrowFliesDistanceM, lat, lon
                FROM puregym_gyms
                UNION ALL
                SELECT 'gymgroup' AS source, Office, Name, Address, Duration, Distance, CrowFliesDistanceM, lat, lon
                FROM gymgroup_gyms
            )
            """
        ).df()
    finally:
        con.close()

    for frame in (offices, gyms):
        for column in ["lat", "lon"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    for column in ["Duration", "Distance", "CrowFliesDistanceM"]:
        gyms[column] = pd.to_numeric(gyms[column], errors="coerce")

    gyms["color"] = gyms["Brand"].map(
        {
            "PureGym": PUREGYM_COLOR,
            "The Gym Group": GYMGROUP_COLOR,
        }
    )

    offices = offices.dropna(subset=["lat", "lon"])
    gyms = gyms.dropna(subset=["lat", "lon"])
    return offices, gyms


def build_office_points(offices: pd.DataFrame) -> pd.DataFrame:
    office_points = offices.copy()
    office_points["TooltipTitle"] = office_points["office_name"]
    office_points["TooltipType"] = "Office"
    office_points["TooltipMetric1"] = ""
    office_points["TooltipMetric2"] = ""
    office_points["TooltipMetric3"] = ""
    return office_points


def build_single_office_gym_points(gyms: pd.DataFrame) -> pd.DataFrame:
    gym_points = gyms.copy()
    gym_points["TooltipTitle"] = gym_points["Name"]
    gym_points["TooltipType"] = gym_points["Brand"]
    gym_points["TooltipMetric1"] = "Google Maps time: " + gym_points["Duration"].astype("Int64").astype(str) + " min"
    gym_points["TooltipMetric2"] = "Google Maps distance: " + gym_points["Distance"].astype("Int64").astype(str) + " m"
    gym_points["TooltipMetric3"] = "Crow-flies distance: " + gym_points["CrowFliesDistanceM"].astype("Int64").astype(str) + " m"
    return gym_points


def build_all_locations_gym_points(gyms: pd.DataFrame) -> pd.DataFrame:
    gym_points = (
        gyms.sort_values(["Brand", "Name", "Address"])
        .drop_duplicates(subset=["Brand", "Name", "Address", "lat", "lon"])
        .copy()
    )
    gym_points["TooltipTitle"] = gym_points["Name"]
    gym_points["TooltipType"] = gym_points["Brand"]
    gym_points["TooltipMetric1"] = gym_points["Address"]
    gym_points["TooltipMetric2"] = ""
    gym_points["TooltipMetric3"] = ""
    return gym_points


def render_map(office_points: pd.DataFrame, gym_points: pd.DataFrame, view_state: pdk.ViewState):
    tooltip = {
        "html": "<b>{TooltipTitle}</b><br/>{TooltipType}<br/>{TooltipMetric1}<br/>{TooltipMetric2}<br/>{TooltipMetric3}",
        "style": {"color": "white", "backgroundColor": "#111827"},
    }

    deck = pdk.Deck(
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=office_points,
                get_position=["lon", "lat"],
                get_fill_color=OFFICE_COLOR,
                get_radius=34,
                pickable=True,
            ),
            pdk.Layer(
                "ScatterplotLayer",
                data=gym_points,
                get_position=["lon", "lat"],
                get_fill_color="color",
                get_radius=24,
                pickable=True,
            ),
        ],
        initial_view_state=view_state,
        tooltip=tooltip,
    )
    st.pydeck_chart(deck, width="stretch")


def render_downloads():
    st.markdown("### Data Files")
    columns = st.columns(len(DATA_FILES))
    for column, (label, path) in zip(columns, DATA_FILES):
        if path.exists():
            with path.open("rb") as file_handle:
                column.download_button(
                    label=label,
                    data=file_handle.read(),
                    file_name=path.name,
                    mime="text/csv",
                    width="stretch",
                )
        else:
            column.caption(f"Missing: {path.name}")


offices, gyms = load_data()

st.title("Workspace Gym Finder")
st.markdown("Find the closest PureGym and The Gym Group locations for each Workspace office.")
render_downloads()

st.sidebar.header("Navigation")
view_mode = st.sidebar.radio("View Mode", ["Single Office", "All Locations"])

if view_mode == "Single Office":
    selected_office_name = st.sidebar.selectbox("Select an Office", offices["office_name"].tolist())
    selected_office = offices.loc[offices["office_name"] == selected_office_name].iloc[0]
    office_gyms = gyms.loc[gyms["Office"] == selected_office_name].copy()
    office_gyms = office_gyms.sort_values(["Duration", "Distance", "CrowFliesDistanceM", "Name"])

    st.subheader(selected_office_name)
    if pd.notna(selected_office.get("address", None)) and str(selected_office["address"]).strip():
        st.write(f"Address: {selected_office['address']}")
    st.write(f"Postcode: {selected_office['postcode']}")

    st.markdown("### Nearby Gyms")
    if office_gyms.empty:
        st.warning("No gyms found for this office in the database.")
    else:
        table = office_gyms[
            ["Name", "Brand", "Address", "Duration", "Distance", "CrowFliesDistanceM"]
        ].rename(
            columns={
                "Duration": "Google Maps Time (min)",
                "Distance": "Google Maps Distance (m)",
                "CrowFliesDistanceM": "Crow-Flies Distance (m)",
            }
        )
        st.dataframe(table.reset_index(drop=True), width="stretch")

    st.markdown("### Map")
    render_map(
        build_office_points(offices.loc[offices["office_name"] == selected_office_name]),
        build_single_office_gym_points(office_gyms),
        pdk.ViewState(latitude=selected_office["lat"], longitude=selected_office["lon"], zoom=15, pitch=0),
    )
else:
    st.subheader("All Locations")
    st.markdown("All offices and distinct gym sites across London.")
    all_gym_points = build_all_locations_gym_points(gyms)
    summary = all_gym_points[["Name", "Brand", "Address"]].sort_values(["Brand", "Name", "Address"])
    st.dataframe(summary.reset_index(drop=True), width="stretch")
    render_map(
        build_office_points(offices),
        all_gym_points,
        pdk.ViewState(latitude=LONDON_CENTER["lat"], longitude=LONDON_CENTER["lon"], zoom=11, pitch=0),
    )

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
**Legend:**
- Yellow: Office
- Blue: PureGym
- Red: The Gym Group
"""
)