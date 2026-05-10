import streamlit as st
import duckdb
import pandas as pd
import pydeck as pdk

st.set_page_config(page_title="Workspace Gym Finder", layout="wide")

st.title("🏋️ Workspace Office Gym Finder")
st.markdown("Find the closest PureGym and The Gym Group locations within 10 minutes walk of each office.")

# Connect to database
def get_data():
    con = duckdb.connect("gym_locator.db")
    offices = con.execute("SELECT * FROM offices").df()
    
    # Try to load gyms, handle case where tables might be missing
    try:
        pure_gyms = con.execute("SELECT * FROM puregym_gyms").df()
    except:
        pure_gyms = pd.DataFrame()
        
    try:
        gymgroup_gyms = con.execute("SELECT * FROM gymgroup_gyms").df()
    except:
        gymgroup_gyms = pd.DataFrame()
        
    con.close()
    return offices, pure_gyms, gymgroup_gyms

offices, pure_gyms, gymgroup_gyms = get_data()

# Sidebar - Selection
st.sidebar.header("Navigation")
selected_office_name = st.sidebar.selectbox("Select an Office", offices['office_name'].tolist())

# Get selected office data
selected_office = offices[offices['office_name'] == selected_office_name].iloc[0]

# Filter gyms for this office
office_pure_gyms = pure_gyms[pure_gyms['Office'] == selected_office_name].copy() if not pure_gyms.empty else pd.DataFrame()
office_gymgroup_gyms = gymgroup_gyms[gymgroup_gyms['Office'] == selected_office_name].copy() if not gymgroup_gyms.empty else pd.DataFrame()

# Combine all gyms for mapping
if not office_pure_gyms.empty:
    office_pure_gyms['type'] = 'PureGym'
    office_pure_gyms['color'] = [[0, 0, 255, 160]] * len(office_pure_gyms)
    
if not office_gymgroup_gyms.empty:
    office_gymgroup_gyms['type'] = 'The Gym Group'
    office_gymgroup_gyms['color'] = [[255, 0, 0, 160]] * len(office_gymgroup_gyms)

all_gyms = pd.concat([office_pure_gyms, office_gymgroup_gyms])


# Layout
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader(f"Results for {selected_office_name}")
    st.write(f"**Postcode:** {selected_office['postcode']}")
    
    st.markdown("### 🏟️ Gyms Nearby")
    if all_gyms.empty:
        st.warning("No gyms found for this office in the database.")
    else:
        # Display as a nice table
        display_df = all_gyms[['Name', 'Address', 'Duration', 'Distance', 'type']].rename(columns={
            'Duration': 'Walk Time',
            'Distance': 'Dist (m)',
            'type': 'Brand'
        })
        st.dataframe(display_df, use_container_width=True)

with col2:
    # Map Visualization
    st.subheader("Map View")
    
    # Define layers
    office_data = offices[offices['office_name'] == selected_office_name].copy()
    office_data['type'] = 'Office'
    office_data['Name'] = office_data['office_name']
    office_data['Duration'] = 'N/A'
    office_data['Distance'] = 0

    office_layer = pdk.Layer(
        "ScatterplotLayer",
        data=office_data,
        get_position=["lon", "lat"],
        get_color=[255, 255, 0, 200], # Yellow for office
        get_radius=30,
        pickable=True,
    )
    
    gym_layer = pdk.Layer(
        "ScatterplotLayer",
        data=all_gyms,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius=20,
        pickable=True,
    )

    # Combined Tooltip
    view_state = pdk.ViewState(
        latitude=selected_office['lat'],
        longitude=selected_office['lon'],
        zoom=15,
        pitch=0,
    )

    r = pdk.Deck(
        layers=[office_layer, gym_layer],
        initial_view_state=view_state,
        tooltip={
            "html": """
            <b>Name:</b> {Name}<br/>
            <b>Type:</b> {type}<br/>
            <b>Walk Time:</b> {Duration}<br/>
            <b>Distance:</b> {Distance}m
            """,
            "style": {"color": "white"}
        }
    )

    st.pydeck_chart(r)

st.sidebar.markdown("---")
st.sidebar.markdown("""
**Legend:**
- 🟡 **Yellow**: Selection Office
- 🔵 **Blue**: PureGym
- 🔴 **Red**: The Gym Group
""")
