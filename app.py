from pathlib import Path
from html import escape

import duckdb
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium


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


def build_tooltip_html(row: pd.Series) -> str:
    lines = [
        f"<strong>{escape(str(row['TooltipTitle']))}</strong>",
        escape(str(row["TooltipType"])),
    ]
    for field in ["TooltipMetric1", "TooltipMetric2", "TooltipMetric3"]:
        value = str(row[field]).strip()
        if value:
            lines.append(escape(value))
    return "<br/>".join(lines)


def render_map(office_points: pd.DataFrame, gym_points: pd.DataFrame, map_center: dict, zoom: int):
    folium_map = folium.Map(
        location=[map_center["lat"], map_center["lon"]],
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    for _, office in office_points.iterrows():
        folium.CircleMarker(
            location=[office["lat"], office["lon"]],
            radius=8,
            color="#ffdd57",
            weight=2,
            fill=True,
            fill_color="#ffdd57",
            fill_opacity=0.9,
            tooltip=folium.Tooltip(build_tooltip_html(office), sticky=True),
        ).add_to(folium_map)

    for _, gym in gym_points.iterrows():
        color = gym.get("color", PUREGYM_COLOR)
        hex_color = f"#{int(color[0]):02x}{int(color[1]):02x}{int(color[2]):02x}"
        folium.CircleMarker(
            location=[gym["lat"], gym["lon"]],
            radius=6,
            color=hex_color,
            weight=2,
            fill=True,
            fill_color=hex_color,
            fill_opacity=0.8,
            tooltip=folium.Tooltip(build_tooltip_html(gym), sticky=True),
        ).add_to(folium_map)

    st_folium(folium_map, height=520, width=None)


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
        {"lat": selected_office["lat"], "lon": selected_office["lon"]},
        15,
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
        LONDON_CENTER,
        11,
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