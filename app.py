import streamlit as st
import csv
import math
import requests
import time
import os
import pandas as pd
import folium
from streamlit_folium import st_folium
import base64

# Page Config
st.set_page_config(page_title="Utah Aggregate Estimator", layout="wide")

# Constants
AVG_SPEED_MPH = 35 
LOAD_TIME_MIN = 15   
UNLOAD_TIME_MIN = 8 
EFFICIENCY_FACTOR = 0.90 

# Load data without caching so CSV updates are immediate
def load_data():
    pits = []
    pit_file = 'data/pits_utah.csv'
    if os.path.exists(pit_file):
        with open(pit_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    row['Price_Per_Ton'] = float(row['Price_Per_Ton'])
                    row['Latitude'] = float(row['Latitude'])
                    row['Longitude'] = float(row['Longitude'])
                    pits.append(row)
                except ValueError:
                    continue

    trucks = []
    truck_file = 'data/trucks.csv'
    if os.path.exists(truck_file):
        with open(truck_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    row['Hourly_Rate'] = float(row['Hourly_Rate'])
                    row['Capacity_Tons'] = float(row['Capacity_Tons'])
                    trucks.append(row)
                except ValueError:
                    continue
                    
    return pits, trucks

@st.cache_data(show_spinner=False)
def geocode_address(address):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": "GravelEstimatorApp/1.0"}
    try:
        resp = requests.get(url, params=params, headers=headers)
        if resp.status_code == 200 and resp.json():
            data = resp.json()[0]
            return float(data['lat']), float(data['lon']), data['display_name']
    except Exception:
        pass
    return None, None, None

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 3958.8 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@st.cache_data(show_spinner=False)
def get_real_route(lat1, lon1, lat2, lon2):
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
    try:
        time.sleep(0.5)
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data['code'] == 'Ok':
                route = data['routes'][0]
                dist_miles = route['distance'] / 1609.34
                duration_hr = (route['duration'] / 3600.0) * 1.10 # 10% truck penalty
                return dist_miles, duration_hr
    except Exception:
        pass
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    return dist, dist / 35.0

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

try:
    bg_img = get_base64_of_bin_file("background.jpg")
    bg_url = f"data:image/jpeg;base64,{bg_img}"
except:
    bg_url = "https://images.unsplash.com/photo-1518002171953-a080ee817e1f?q=80&w=2000&auto=format&fit=crop"

# UI Starts Here
st.markdown(f"""
<style>
    /* Background Image with a dark overlay so text stays readable */
    .stApp {{
        background-image: linear-gradient(rgba(17, 24, 39, 0.85), rgba(17, 24, 39, 0.92)), url("{bg_url}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}
    
    /* Make the sidebar slightly translucent but distinct */
    [data-testid="stSidebar"] {{
        background-color: rgba(31, 41, 55, 0.85);
    }}

    /* Strong, Professional Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=Oswald:wght@800&display=swap');
    html, body, [class*="css"]  {{
        font-family: 'Inter', sans-serif;
    }}
    /* Center the headers */
    .centered-header {{
        text-align: center !important;
        display: block;
        width: 100%;
        font-family: 'Oswald', sans-serif;
        font-weight: 900;
        font-size: 3.5rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #f9fafb;
        margin-bottom: 0.5rem;
        margin-top: 1rem;
        line-height: 1.2;
    }}
    .centered-sub {{
        text-align: center !important;
        display: block;
        width: 100%;
        font-size: 1.1rem;
        font-weight: 500;
        color: #9ca3af;
        margin-bottom: 2rem;
    }}
    
    /* Mobile adjustments */
    @media (max-width: 768px) {{
        .centered-header {{
            font-size: 2.2rem;
            letter-spacing: 0px;
        }}
        .centered-sub {{
            font-size: 1rem;
        }}
    }}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='centered-header'>Utah Aggregate Estimator</h1>", unsafe_allow_html=True)
st.markdown("<div class='centered-sub'>Calculate the most cost-effective aggregate delivery options using live routing.</div>", unsafe_allow_html=True)

pits, trucks = load_data()

if not pits or not trucks:
    st.error("Data files not found. Please ensure data/pits_utah.csv and data/trucks.csv exist.")
    st.stop()

# State for the map
if "map_center" not in st.session_state:
    st.session_state.map_center = [40.6, -111.9] # Approx SL Valley
if "job_site_marker" not in st.session_state:
    st.session_state.job_site_marker = None
if "job_address_name" not in st.session_state:
    st.session_state.job_address_name = ""
if "map_expanded" not in st.session_state:
    st.session_state.map_expanded = True
if "collapse_sidebar" not in st.session_state:
    st.session_state.collapse_sidebar = False

# Sidebar for inputs
with st.sidebar:
    st.header("1. Find Job Site")
    st.write("Type an address OR click directly on the map.")
    
    # Address Search
    address = st.text_area("Search Address", value="", placeholder="e.g., 5600 W 8600 S, West Jordan")
    if st.button("Search on Map", width='stretch'):
        if address:
            with st.spinner("Finding location..."):
                lat, lon, display_name = geocode_address(address)
                if lat:
                    st.session_state.map_center = [lat, lon]
                    st.session_state.job_site_marker = [lat, lon]
                    st.session_state.job_address_name = display_name
                    st.rerun()
                else:
                    st.error("Could not find that address.")
        else:
            st.warning("Please enter an address.")
            
    st.divider()
            
    st.header("2. Job Details")
    tons = st.number_input("Tons Needed", min_value=1, value=None, placeholder="e.g., 800", step=10)
    
    truck_options = ["Best Option (Compare Both)", "Side Dump", "10-Wheeler"]
    truck_choice = st.selectbox("Truck Type", truck_options)
    
    # Get unique materials
    materials = sorted(list(set([p['Material'] for p in pits])))
    material_choices = st.multiselect("Filter by Material", materials, placeholder="Select materials (leave empty for all)")
    
    st.divider()
    calc_button = st.button("Calculate Best Price", type="primary", use_container_width=True)

# Main Area Map
with st.expander("📍 **Select Job Site Location (Map)**", expanded=st.session_state.map_expanded):
    # Current Status
    if st.session_state.job_address_name:
        st.info(f"**Selected Site:** {st.session_state.job_address_name}")
    elif st.session_state.job_site_marker:
        lat, lon = st.session_state.job_site_marker
        st.info(f"**Selected Site:** Custom Coordinates ({lat:.5f}, {lon:.5f})")
    
    m = folium.Map(location=st.session_state.map_center, zoom_start=11)
    
    # Add existing pits as markers
    for p in pits:
        folium.CircleMarker(
            location=[p['Latitude'], p['Longitude']],
            radius=5,
            popup=p['Pit Name'],
            color="#f97316",
            fill=True,
            fill_color="#f97316"
        ).add_to(m)
    
    # Add Job Site Marker
    if st.session_state.job_site_marker:
        folium.Marker(
            st.session_state.job_site_marker, 
            tooltip="Job Site", 
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(m)
    
    # Render Map
    map_data = st_folium(m, height=400, width='stretch', returned_objects=["last_clicked"])
    
    # Handle Map Clicks
    if map_data and map_data.get("last_clicked"):
        click_lat = map_data["last_clicked"]["lat"]
        click_lon = map_data["last_clicked"]["lng"]
        new_marker = [click_lat, click_lon]
        
        if st.session_state.job_site_marker != new_marker:
            st.session_state.job_site_marker = new_marker
            st.session_state.job_address_name = "" # Clear previous address name since it's a raw click
            st.session_state.map_expanded = True
            st.rerun()

# --- Calculate Logic ---
if calc_button:
    st.session_state.do_calc = True
    st.session_state.map_expanded = False
    st.session_state.collapse_sidebar = True
    st.rerun()

import streamlit.components.v1 as components
if st.session_state.get('collapse_sidebar', False):
    components.html(
        """
        <script>
            var elements = window.parent.document.querySelectorAll('button[kind="header"]');
            var btn = Array.from(elements).find(el => el.getAttribute('data-testid') === 'baseButton-header' || el.querySelector('svg'));
            if (btn) { btn.click(); }
        </script>
        """,
        height=0,
        width=0
    )
    st.session_state.collapse_sidebar = False

if st.session_state.get('do_calc', False):
    if not st.session_state.job_site_marker:
        st.warning("Please click on the map or search for an address to set the job site.")
        st.session_state.do_calc = False
        st.stop()
    if not tons:
        st.warning("Please enter the total tons needed in the sidebar.")
        st.session_state.do_calc = False
        st.stop()
        
    lat, lon = st.session_state.job_site_marker
    
    # Filter trucks
    selected_trucks = trucks
    if truck_choice == "Side Dump":
        selected_trucks = [t for t in trucks if "Side Dump" in t['Type']]
    elif truck_choice == "10-Wheeler":
        selected_trucks = [t for t in trucks if "10-Wheeler" in t['Type']]
        
    # Filter pits
    filtered_pits = pits
    if material_choices:
        filtered_pits = [p for p in pits if p['Material'] in material_choices]
        
    if not filtered_pits:
        st.warning("No pits found for the selected materials.")
        st.stop()

    load_unload_hr = (LOAD_TIME_MIN + UNLOAD_TIME_MIN) / 60
    
    results = []
    
    st.markdown("---")
    st.subheader(f"📊 Best Options for {tons} Tons")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_pits = len(filtered_pits)
    for i, pit in enumerate(filtered_pits):
        status_text.text(f"Routing to {pit['Pit Name']} ({i+1}/{total_pits})...")
        dist, one_way_time_hr = get_real_route(lat, lon, pit['Latitude'], pit['Longitude'])
        
        travel_time_hr = one_way_time_hr * 2
        raw_cycle_hr = travel_time_hr + load_unload_hr
        cycle_time_hr = raw_cycle_hr / EFFICIENCY_FACTOR
        
        for truck in selected_trucks:
            # 1. Total trips required (always rounds UP to the nearest whole trip)
            trips = math.ceil(tons / truck['Capacity_Tons'])
            
            # 2. Max trips a truck can do in an 8-hour shift
            max_trips_per_day = math.floor(8.0 / cycle_time_hr)
            if max_trips_per_day < 1:
                max_trips_per_day = 1 # If one trip takes more than 8 hours, it's a 1-trip day
            
            # 3. How many full 8-hour truck shifts, plus the leftover trips
            full_shifts = trips // max_trips_per_day
            leftover_trips = trips % max_trips_per_day
            
            # 4. Round up hours to the nearest half-hour per shift
            def round_half_hr(hrs):
                return math.ceil(hrs * 2) / 2.0
                
            full_shift_hrs = round_half_hr(max_trips_per_day * cycle_time_hr)
            leftover_hrs = round_half_hr(leftover_trips * cycle_time_hr) if leftover_trips > 0 else 0.0
            
            # 5. Calculate total billed trucking hours
            total_billed_hrs = (full_shifts * full_shift_hrs) + leftover_hrs
            
            # 6. Calculate total costs
            total_trucking_cost = total_billed_hrs * truck['Hourly_Rate']
            material_cost = pit['Price_Per_Ton'] * tons
            total_cost = material_cost + total_trucking_cost
            
            results.append({
                'Pit': pit['Pit Name'],
                'Material': pit['Material'],
                'Truck': truck['Type'],
                'Dist (mi)': round(dist, 1),
                'Cycle (min)': int(cycle_time_hr * 60),
                'Base $/Ton': f"${pit['Price_Per_Ton']:.2f}",
                'Del $/Ton': total_cost / tons, # Keep as float for sorting
                'Total Cost': total_cost
            })
            
        progress_bar.progress((i + 1) / total_pits)
        
    status_text.empty()
    progress_bar.empty()
    
    # Sort and format
    df = pd.DataFrame(results)
    df = df.sort_values('Del $/Ton').head(10).reset_index(drop=True)
    
    # Format currency columns for display
    df['Del $/Ton'] = df['Del $/Ton'].apply(lambda x: f"${x:.2f}")
    df['Total Cost'] = df['Total Cost'].apply(lambda x: f"${x:,.2f}")
    
    # Adjust index to start at 1
    df.index = df.index + 1
    
    st.markdown(f"*Assumptions: {LOAD_TIME_MIN}m load, {UNLOAD_TIME_MIN}m unload, {int(EFFICIENCY_FACTOR*100)}% efficiency, 10% truck speed penalty.*")
    
    # Display interactive dataframe
    st.dataframe(df, width='stretch')
    
    # Highlight the absolute best option
    if not df.empty:
        best = df.iloc[0]
        st.success(f"**Best Value:** {best['Pit']} using a {best['Truck']} for **{best['Del $/Ton']}** delivered.")
