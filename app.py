import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import json

# Set up wide-screen layout
st.set_page_config(layout="wide")
st.title("California Daily PM2.5 Smoke Dashboard (2006-2020)")

# --- 1. DATA LOADING FUNCTION ---
@st.cache_data
def load_dashboard_data():
    # Read spatial elements
    gdf = gpd.read_file("ca_grid_10km.geojson")
    gdf['ID'] = gdf['ID'].astype(int).astype(str).str.strip()
    
    # Optional Speed Optimization: simplifies shapes for faster web loading
    gdf['geometry'] = gdf['geometry'].simplify(tolerance=0.001, preserve_topology=True)
    geojson_dict = json.loads(gdf.to_json())
    
    # --- UPDATED: LOAD CHUNKS AND CONCATENATE ---
    df_part1 = pd.read_parquet("ca_smoke_pm25_part1.parquet")
    df_part2 = pd.read_parquet("ca_smoke_pm25_part2.parquet")
    df = pd.concat([df_part1, df_part2], ignore_index=True)
    
    df['grid_id_10km'] = df['grid_id_10km'].astype(int).astype(str).str.strip()
    
    # Mathematical Unix Epoch date fixer
    raw_nanoseconds = df['date'].astype('int64') % 86400000000000
    df['date'] = pd.to_datetime(raw_nanoseconds.astype(str), format='%Y%m%d', errors='coerce')
    df = df.dropna(subset=['date'])
    df['year'] = df['date'].dt.year
    
    return gdf, df, geojson_dict

grid_gdf, pm25_df, geojson_dict = load_dashboard_data()

# --- 2. LAYOUT COLUMNS SETUP ---
col_left, col_right = st.columns([2, 1])

# --- 3. LEFT PANEL: AUTO-ANIMATED CHOROPLETH MAP ---
with col_left:
    st.subheader("Interactive Temporal Map Visualization")
    st.write("Use the Play controller below the map to automatically animate the historical trends across years.")
    
    # Pre-aggregate data by year and cell block for smooth animation rendering
    map_aggregated = pm25_df.groupby(['year', 'grid_id_10km'])['smokePM_pred'].mean().reset_index()
    map_aggregated = map_aggregated.sort_values(by='year')
    
    if map_aggregated.empty:
        st.error("The analytical database returned zero operational rows.")
    else:
        # Pull global scale bounds so color matching stays consistent across frames
        min_val = float(map_aggregated['smokePM_pred'].min())
        max_val = float(map_aggregated['smokePM_pred'].max())

        # Render complete choropleth with built-in temporal playback 
        fig_map = px.choropleth_map(
            map_aggregated,
            geojson=geojson_dict,
            locations="grid_id_10km",
            featureidkey="properties.ID", 
            color="smokePM_pred",
            animation_frame="year",  # THIS ACTIVATES THE PLAY/PAUSE CONTROLLERS!
            color_continuous_scale="YlOrRd",
            range_color=[min_val, max_val],
            hover_name="grid_id_10km",
            hover_data={"smokePM_pred": ":.2f", "year": False},
            zoom=5,
            center={"lat": 36.7783, "lon": -119.4179},
            height=700,  # <-- ADD THIS LINE HERE TO INCREASE THE SIZE
        )
        
       # Style polygons to maximize layout coverage and eliminate white boundary lines
        fig_map.update_traces(marker=dict(line_width=0, opacity=0.8))
        fig_map.update_layout(
            margin={"r":0,"t":0,"l":0,"b":0}, 
            map_style="carto-positron"
        )
        
        # FIX: Slower frame duration + smooth easing transition stops the legend from flashing/jittering
        fig_map.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 1200
        fig_map.layout.updatemenus[0].buttons[0].args[1]["transition"] = {"duration": 300, "easing": "cubic-in-out"}
        
        map_selection = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun")

# --- 4. RIGHT PANEL: TIME-SERIES TIMELINE ---
with col_right:
    st.subheader("Pixel Analysis Panel")
    st.write("Click on any grid block to graph its unique continuous daily trajectory.")
    
    # Establish a default fallback block from the dataset
    default_grid_id = str(map_aggregated['grid_id_10km'].iloc[0])
    selected_grid_id = default_grid_id
    
    # Extract structural selection hooks directly out of the clicked map component
    if map_selection and "selection" in map_selection and "points" in map_selection["selection"]:
        points = map_selection["selection"]["points"]
        if len(points) > 0:
            selected_grid_id = str(points[0].get("location", default_grid_id))
            
    st.info(f"Showing Data for Grid Cell ID: **{selected_grid_id}**")
    
    # Filter down and arrange chronological sequence
    pixel_timeline = pm25_df[pm25_df['grid_id_10km'] == selected_grid_id].sort_values('date')
    
    fig_timeline = px.line(
        pixel_timeline,
        x='date',
        y='smokePM_pred',
        title=f"Daily Smoke PM2.5 Predictions (2006 - 2020)",
        labels={'date': 'Timeline', 'smokePM_pred': 'PM2.5 (ug/m3)'}
    )
    fig_timeline.update_traces(line=dict(color='#e74c3c', width=1))
    fig_timeline.update_layout(xaxis_rangeslider_visible=True)
    
    st.plotly_chart(fig_timeline, use_container_width=True)
