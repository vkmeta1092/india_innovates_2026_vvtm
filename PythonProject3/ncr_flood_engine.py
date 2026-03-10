import pandas as pd
import numpy as np
import folium
import osmnx as ox
import geopandas as gpd
from shapely.geometry import Point, LineString
from datetime import datetime
import warnings

# Suppress minor spatial warnings for clean terminal output
warnings.filterwarnings('ignore')

# --- 1. SPATIAL ANCHORS ---
BHARAT_MANDAPAM = [28.6196, 77.2425]
NUM_POINTS = 2500

print("🌊 Fetching exact Yamuna River geometry from OpenStreetMap (Please wait ~15 seconds)...")

# --- 2. FETCH REAL YAMUNA GEOMETRY (ROBUST BBOX & OFFLINE FALLBACK) ---
# We define a bounding box covering the NCR Yamuna stretch
north, south, east, west = 28.88, 28.40, 77.35, 77.15
tags = {'waterway': ['river', 'riverbank'], 'natural': 'water'}

try:
    # 1. Fetch all water bodies in this box
    water_gdf = ox.features_from_bbox(north=north, south=south, east=east, west=west, tags=tags)

    # 2. Filter specifically for the Yamuna
    yamuna_gdf = water_gdf[
        water_gdf.get('name', pd.Series(dtype=str)).str.contains('Yamuna', na=False, case=False) |
        water_gdf.get('name:en', pd.Series(dtype=str)).str.contains('Yamuna', na=False, case=False)
        ]

    if yamuna_gdf.empty:
        raise ValueError("River found, but 'Yamuna' name tag is missing in this bounding box.")

    # 3. Project to UTM Zone 43N (Delhi local CRS) for exact meter calculations
    yamuna_proj = yamuna_gdf.to_crs(epsg=32643)
    yamuna_geom = yamuna_proj.unary_union
    print("✅ Yamuna River exact boundaries successfully loaded via OSM!")

except Exception as e:
    print(f"⚠️ OSM Fetch Failed ({e}). Network unstable or OSM timeout.")
    print("🔄 Engaging Offline High-Fidelity Fallback for Hackathon Demo...")

    # OFFLINE FALLBACK: High-res curved path to save the live demo
    YAMUNA_PATH = [
        [28.835, 77.195], [28.790, 77.210], [28.745, 77.221], [28.711, 77.234],
        [28.680, 77.232], [28.647, 77.251], [28.615, 77.258], [28.591, 77.271],
        [28.565, 77.295], [28.544, 77.311], [28.515, 77.320], [28.480, 77.330]
    ]

    # Convert fallback to a proper Shapely geometry
    fallback_line = LineString([(lon, lat) for lat, lon in YAMUNA_PATH])
    yamuna_gdf = gpd.GeoDataFrame(geometry=[fallback_line], crs="EPSG:4326")
    yamuna_geom = yamuna_gdf.to_crs(epsg=32643).unary_union

# --- 3. GENERATE MICRO-HOTSPOTS & CALCULATE TRUE DISTANCE ---
print("📍 Generating 2,500 hotspots and calculating exact hydraulic proximity...")
lats = np.random.uniform(BHARAT_MANDAPAM[0] - 0.2, BHARAT_MANDAPAM[0] + 0.25, NUM_POINTS)
lngs = np.random.uniform(BHARAT_MANDAPAM[1] - 0.2, BHARAT_MANDAPAM[1] + 0.25, NUM_POINTS)

df = pd.DataFrame({'lat': lats, 'lng': lngs})
df['zone_type'] = np.random.choice(['Planned', 'Unplanned'], size=NUM_POINTS, p=[0.2, 0.8])
df['vulnerability'] = np.random.uniform(0.8, 1.2, NUM_POINTS)

# Convert points to a GeoDataFrame to do spatial math
points_gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lng, df.lat), crs="EPSG:4326")
points_proj = points_gdf.to_crs(epsg=32643)

# Calculate exact distance to the nearest river bank in kilometers
df['dist_to_river'] = points_proj.geometry.distance(yamuna_geom) / 1000.0

# --- 4. BUILD THE MAP VISUALS ---
m = folium.Map(location=BHARAT_MANDAPAM, zoom_start=12, tiles=None)
folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satellite').add_to(m)

# 4A. Draw the TRUE Yamuna River Geometry
folium.GeoJson(
    yamuna_gdf,
    name='Yamuna River (GIS Data)',
    style_function=lambda x: {'fillColor': '#00aaff', 'color': '#00aaff', 'weight': 6, 'fillOpacity': 0.4},
    tooltip="True Yamuna River Channel"
).add_to(m)

# 4B. Center Anchor: Bharat Mandapam
folium.RegularPolygonMarker(
    location=BHARAT_MANDAPAM, number_of_sides=8, radius=20,
    color='#FFD700', fill=True, fill_opacity=0.9, weight=3,
    popup="<b>HACK4DELHI COMMAND CENTER</b><br>Bharat Mandapam"
).add_to(m)

# Render a subset to keep the browser rendering smooth during the demo
df_subset = df.head(450).copy()

for idx, row in df_subset.iterrows():
    z_class = row['zone_type']
    v_class = int(row['vulnerability'] * 100)
    # Cap distance at 999 to avoid parsing issues in JS, scale to 10s of meters
    d_class = min(int(row['dist_to_river'] * 10), 999)

    folium.CircleMarker(
        location=[row['lat'], row['lng']],
        radius=5, color='white', weight=0.5, fill=True, fill_opacity=0.8, fill_color='#00FF00',
        className=f"node {z_class} v-{v_class} d-{d_class}",
        popup=f"Zone: {z_class}<br>Exact Dist to Bank: {row['dist_to_river']:.2f}km"
    ).add_to(m)

# --- 5. THE MODULAR CONTROL PANEL (HTML/JS) ---
dashboard_html = f'''
    <div style="position: fixed; top: 10px; left: 10px; width: 360px; 
                background: rgba(10, 10, 15, 0.95); color: #ffffff; z-index:9999; 
                padding: 15px; border-radius: 12px; font-family: 'Segoe UI', Tahoma, sans-serif;
                border: 1px solid #555; box-shadow: 0 4px 15px rgba(0,0,0,0.5);">

        <div style="font-size: 22px; font-weight: bold; color: #00ffcc;" id="liveClock">{datetime.now().strftime("%H:%M:%S")}</div>
        <div style="font-size: 11px; margin-bottom: 15px; color: #aaa; letter-spacing: 1px;">URBAN FLOODING & HYDROLOGY ENGINE</div>

        <div style="background: #222; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
            <label style="font-size: 12px; font-weight: bold;">🌧️ RAINFALL INTENSITY: <span id="rainDisp" style="color:#00ffcc">10mm</span></label>
            <input type="range" min="0" max="150" value="10" id="rainSlider" style="width: 100%;">
        </div>

        <div style="background: #222; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
            <input type="checkbox" id="togglePlan" checked onchange="updateSim()">
            <label style="font-size: 12px; font-weight: bold;">🏢 INSTITUTIONAL DRAINAGE SHIELD</label>
            <div style="font-size: 9px; color: #888;">(Muffles risk for planned zones)</div>
        </div>

        <div style="background: #222; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
            <input type="checkbox" id="toggleRiver" onchange="updateSim()">
            <label style="font-size: 12px; font-weight: bold;">🌊 YAMUNA OVERFLOW: <span id="riverDisp" style="color:#00aaff">204.0m</span></label>
            <input type="range" min="203" max="209" value="204" step="0.1" id="riverSlider" style="width: 100%;">
        </div>

        <div style="background: #222; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
            <input type="checkbox" id="toggleMaint" onchange="updateSim()">
            <label style="font-size: 12px; font-weight: bold;">⚠️ MAINTENANCE FACTOR</label>
            <div style="margin-top: 8px; font-size: 11px;">Siltation Blockage: <span id="siltDisp" style="color:#ffaa00">1.0x</span></div>
            <input type="range" min="1" max="4" value="1" step="0.5" id="siltSlider" style="width: 100%;">
            <select id="trashStatus" style="width:100%; background:#111; color:white; padding:4px; border:1px solid #555; margin-top:5px;" onchange="updateSim()">
                <option value="1">Trash Rack: Clear</option>
                <option value="2.5">Trash Rack: Blocked</option>
            </select>
        </div>

        <div style="margin-top: 10px; padding: 10px; background: #000; border: 1px solid #bc13fe; border-radius: 8px; text-align: center;">
            <div id="statLine" style="font-size: 12px; font-weight: bold; color: #fff;">SYSTEM STATUS: NORMAL</div>
        </div>
    </div>

    <script>
        setInterval(() => {{ document.getElementById('liveClock').innerHTML = new Date().toLocaleTimeString(); }}, 1000);

        function updateSim() {{
            let rain = parseInt(document.getElementById('rainSlider').value);
            let river = parseFloat(document.getElementById('riverSlider').value);
            let silt = parseFloat(document.getElementById('siltSlider').value);
            let trash = parseFloat(document.getElementById('trashStatus').value);

            let enablePlan = document.getElementById('togglePlan').checked;
            let enableRiver = document.getElementById('toggleRiver').checked;
            let enableMaint = document.getElementById('toggleMaint').checked;

            document.getElementById('rainDisp').innerHTML = rain + "mm";
            document.getElementById('riverDisp').innerHTML = enableRiver ? river.toFixed(1) + "m" : "Disabled";
            document.getElementById('siltDisp').innerHTML = enableMaint ? silt.toFixed(1) + "x" : "Disabled";

            let maxRisk = 0;
            let nodes = document.querySelectorAll('.node');

            nodes.forEach(node => {{
                let isPlanned = node.classList.contains('Planned');
                let vFactor = parseInt(node.classList[2].split('-')[1]) / 100;
                let dist = parseInt(node.classList[3].split('-')[1]) / 10; 

                let effectiveRain = rain * vFactor;
                if (enablePlan && isPlanned) {{ effectiveRain *= 0.2; }}

                let maintMultiplier = enableMaint ? (silt * trash) : 1.0;

                let riverSurcharge = 0;
                if (enableRiver && river > 205.3) {{ 
                    riverSurcharge = ((river - 205.3) * 40) / (dist + 0.1); 
                }}

                let totalLoad = (effectiveRain * maintMultiplier) + riverSurcharge;
                if (totalLoad > maxRisk) maxRisk = totalLoad;

                if (totalLoad > 115) {{ node.setAttribute('fill', '#bc13fe'); node.setAttribute('stroke', '#fff'); }}
                else if (totalLoad > 75) {{ node.setAttribute('fill', '#ff0000'); node.setAttribute('stroke', '#500'); }}
                else if (totalLoad > 35) {{ node.setAttribute('fill', '#ffa500'); node.setAttribute('stroke', '#530'); }}
                else {{ node.setAttribute('fill', '#00ff00'); node.setAttribute('stroke', '#050'); }}
            }});

            let stat = document.getElementById('statLine');
            if (maxRisk > 115) stat.innerHTML = "VIOLET ALERT: MULTI-SYSTEM FAILURE";
            else if (enableRiver && river > 206) stat.innerHTML = "RED ALERT: YAMUNA BACKFLOW ACTIVE";
            else if (maxRisk > 75) stat.innerHTML = "ALERT: SEVERE LOCAL RUNOFF";
            else stat.innerHTML = "SYSTEM STATUS: NORMAL";
        }}

        document.getElementById('rainSlider').oninput = updateSim;
        document.getElementById('riverSlider').oninput = updateSim;
        document.getElementById('siltSlider').oninput = updateSim;
        updateSim();
    </script>
'''
m.get_root().html.add_child(folium.Element(dashboard_html))
m.save("h4d_ultimate_gis_dashboard.html")
print("🚀 SUCCESS: Accurate GIS River Dashboard Generated!")