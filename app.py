import streamlit as st
import csv
import math
import requests
import time
import os
import pandas as pd

# Page Config
st.set_page_config(page_title="Utah Gravel Estimator", page_icon="🪨", layout="wide")

# Constants
AVG_SPEED_MPH = 35 
LOAD_TIME_MIN = 15   
UNLOAD_TIME_MIN = 8 
EFFICIENCY_FACTOR = 0.90 

@st.cache_data
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

# UI Starts Here
st.title("🪨 Utah Gravel Estimator")
st.markdown("Calculate the most cost-effective aggregate delivery options using live routing.")

pits, trucks = load_data()

if not pits or not trucks:
    st.error("Data files not found. Please ensure data/pits_utah.csv and data/trucks.csv exist.")
    st.stop()

# Sidebar for inputs
with st.sidebar:
    st.header("Job Details")
    address = st.text_area("Project Address", value="2805 W 13800 S Bluffdale UT")
    tons = st.number_input("Tons Needed", min_value=1, value=800, step=10)
    
    truck_options = ["Best Option (Compare Both)", "Side Dump", "10-Wheeler"]
    truck_choice = st.selectbox("Truck Type", truck_options)
    
    # Get unique materials
    materials = sorted(list(set([p['Material'] for p in pits])))
    materials.insert(0, "All Materials")
    material_choice = st.selectbox("Filter by Material", materials)
    
    calc_button = st.button("Calculate Best Price", type="primary")

if calc_button:
    if not address:
        st.warning("Please enter a project address.")
        st.stop()
        
    with st.spinner("Finding location..."):
        lat, lon, display_name = geocode_address(address)
        
    if not lat:
        st.error("Could not find that address. Try adding 'Utah' or a ZIP code.")
        st.stop()
        
    st.success(f"📍 **Location Found:** {display_name}")
    
    # Filter trucks
    selected_trucks = trucks
    if truck_choice == "Side Dump":
        selected_trucks = [t for t in trucks if "Side Dump" in t['Type']]
    elif truck_choice == "10-Wheeler":
        selected_trucks = [t for t in trucks if "10-Wheeler" in t['Type']]
        
    # Filter pits
    filtered_pits = pits
    if material_choice != "All Materials":
        filtered_pits = [p for p in pits if p['Material'] == material_choice]
        
    if not filtered_pits:
        st.warning(f"No pits found offering '{material_choice}'.")
        st.stop()

    load_unload_hr = (LOAD_TIME_MIN + UNLOAD_TIME_MIN) / 60
    
    results = []
    
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
            trips = math.ceil(tons / truck['Capacity_Tons'])
            haul_cost_per_ton = (cycle_time_hr * truck['Hourly_Rate']) / truck['Capacity_Tons']
            total_trucking_cost = haul_cost_per_ton * tons
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
    
    st.subheader("🏆 Top 10 Options")
    st.markdown(f"*Assumptions: {LOAD_TIME_MIN}m load, {UNLOAD_TIME_MIN}m unload, {int(EFFICIENCY_FACTOR*100)}% efficiency, 10% truck speed penalty.*")
    
    # Display interactive dataframe
    st.dataframe(df, use_container_width=True)
    
    # Highlight the absolute best option
    if not df.empty:
        best = df.iloc[0]
        st.info(f"**Best Value:** {best['Pit']} using a {best['Truck']} for **{best['Del $/Ton']}** delivered.")
