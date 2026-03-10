from flask import Flask, request, jsonify
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from math import radians, cos, sin, asin, sqrt
import pandas as pd
import numpy as np
import folium
import geopandas as gpd
from shapely.geometry import LineString, Polygon
import warnings

warnings.filterwarnings('ignore')

app = Flask(__name__)

# --- 1. REAL & DUMMY NDRF UNIT ROSTER ---
BHARAT_MANDAPAM = [28.6196, 77.2425]
NUM_POINTS = 2500
RELIEF_CAMPS = [
    {"name": "NDRF Unit 8 (CWG Village)", "lat": 28.612, "lng": 77.275, "type": "Real"},
    {"name": "Geeta Colony Relief Center", "lat": 28.650, "lng": 77.265, "type": "Real"},
    {"name": "Okhla Phase 1 Response Hub", "lat": 28.525, "lng": 77.285, "type": "Dummy"},
    {"name": "Mayur Vihar Ext. Shelter", "lat": 28.600, "lng": 77.295, "type": "Dummy"}
]

DELHI_BOUNDARY = [
    [28.88, 77.10], [28.85, 77.35], [28.50, 77.40], [28.40, 77.20], [28.45, 77.05], [28.88, 77.10]
]


def haversine(lat1, lon1, lat2, lon2):
    R = 6372.8
    dLat, dLon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dLat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dLon / 2) ** 2
    return 2 * R * asin(sqrt(a))


# --- 2. DASHBOARD UI ---
dashboard_html = """
    <div style="position: fixed; top: 15px; left: 15px; width: 360px; max-height: 90vh; overflow-y: auto;
                background: rgba(10, 10, 15, 0.98); color: #ffffff; z-index: 999999 !important; 
                padding: 20px; border-radius: 12px; font-family: 'Segoe UI', sans-serif;
                border: 1px solid #444; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">

        <div style="font-size: 24px; font-weight: bold; color: #00ffcc; margin-bottom: 2px;" id="liveClock">00:00:00</div>
        <div style="font-size: 10px; color: #888; letter-spacing: 1px; margin-bottom: 15px;">URBAN FLOODING & HYDROLOGY ENGINE</div>

        <div style="background: linear-gradient(90deg, #111, #222); padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 1px solid #00ffcc; text-align: center;">
            <div style="font-size: 10px; color: #00ffcc; text-transform: uppercase;">Zonal Readiness (Structural + Maint)</div>
            <div style="font-size: 32px; font-weight: bold;" id="avgReadiness">100%</div>
        </div>

        <div style="background: #1a1a1a; padding: 12px; border-radius: 8px; margin-bottom: 10px; border: 1px solid #333;">
            <label style="font-size: 12px; font-weight: bold; display: block; margin-bottom: 5px;">🌧️ RAINFALL: <span id="rainDisp" style="color:#00ffcc">10mm</span></label>
            <input type="range" min="0" max="150" value="10" id="rainSlider" style="width: 100%; cursor: pointer;">
        </div>

        <div style="background: #1a1a1a; padding: 12px; border-radius: 8px; margin-bottom: 10px; border: 1px solid #333;">
            <div style="display: flex; justify-content: space-between; align-items: center;"><label style="font-size: 12px; font-weight: bold;">🌊 YAMUNA OVERFLOW</label><input type="checkbox" id="toggleRiver" onchange="updateSim()"></div>
            <label style="font-size: 11px; color: #00aaff; margin-top: 5px; display: block;">River Stage: <span id="riverDisp">204.0m</span></label>
            <input type="range" min="203" max="209" value="204" step="0.1" id="riverSlider" style="width: 100%; cursor: pointer;">
        </div>

        <div style="background: #1a1a1a; padding: 12px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #333;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;"><label style="font-size: 12px; font-weight: bold;">⚠️ MAINTENANCE</label><input type="checkbox" id="toggleMaint" onchange="updateSim()"></div>
            <select id="trashStatus" style="width:100%; background:#000; color:#ffaa00; padding:8px; border-radius: 4px; font-size: 11px;" onchange="updateSim()">
                <option value="1">TRASH RACKS: CLEAR</option><option value="2.5">TRASH RACKS: BLOCKED</option>
            </select>
            <input type="range" min="1" max="4" value="1" step="0.5" id="siltSlider" style="width: 100%; margin-top:10px; cursor: pointer;">
        </div>

        <button onclick="sendEmergencyDispatch()" id="dispatchBtn" style="width: 100%; padding: 14px; background: #8f00ff; color: white; font-weight: bold; border: none; border-radius: 8px; cursor: pointer; display: none; margin-bottom:10px;">🚨 DISPATCH NDRF</button>
        <button onclick="exportToKepler()" id="keplerBtn" style="width: 100%; padding: 14px; background: #00ffcc; color: #000; font-weight: bold; border: none; border-radius: 8px; cursor: pointer;">📥 EXPORT FOR KEPLER.GL</button>
    </div>

    <script>
        setInterval(() => { document.getElementById('liveClock').innerText = new Date().toLocaleTimeString(); }, 1000);
        window.allDataQueue = []; window.violetQueue = [];

        function updateSim() {
            const rain = parseInt(document.getElementById('rainSlider').value);
            const river = parseFloat(document.getElementById('riverSlider').value);
            const silt = parseFloat(document.getElementById('siltSlider').value);
            const trash = parseFloat(document.getElementById('trashStatus').value);
            const enableRiver = document.getElementById('toggleRiver').checked;
            const enableMaint = document.getElementById('toggleMaint').checked;

            document.getElementById('rainDisp').innerText = rain + "mm";
            document.getElementById('riverDisp').innerText = enableRiver ? river.toFixed(1) + "m" : "Disabled";

            let maintFactor = enableMaint ? (silt * trash) : 1.0;
            const nodes = document.querySelectorAll('.node');
            const currentAll = []; const currentViolet = [];
            let totalReadiness = 0;

            nodes.forEach(node => {
                const vulnerability = parseInt(node.classList[2].split('-')[1]) / 100;
                const dist = parseInt(node.classList[3].split('-')[1]) / 10; 
                const baseCapacity = parseInt(node.classList[4].split('-')[1]);
                const effectiveCapacity = baseCapacity / maintFactor;
                const readinessScore = (effectiveCapacity / baseCapacity) * 100;
                totalReadiness += readinessScore;

                const riverSurcharge = (enableRiver && river > 205.3) ? ((river - 205.3) * 45) / (dist + 0.1) : 0;
                const runoff = rain * vulnerability;
                const floodLoad = Math.max(0, (runoff - effectiveCapacity) + riverSurcharge);

                if (floodLoad > 80) { node.setAttribute('fill', '#df00ff'); node.setAttribute('fill-opacity', '1'); }
                else if (floodLoad > 40) { node.setAttribute('fill', '#ff0000'); node.setAttribute('fill-opacity', '1'); }
                else if (floodLoad > 10) { node.setAttribute('fill', '#ffcc00'); node.setAttribute('fill-opacity', '1'); }
                else { node.setAttribute('fill', '#00ff00'); node.setAttribute('fill-opacity', '0.7'); }

                const dataTag = node.className.baseVal.split('data-')[1];
                if(dataTag) {
                    const parts = dataTag.split('_');
                    const nodeData = { 
                        lat: parseFloat(parts[0]), lng: parseFloat(parts[1]), 
                        load: floodLoad.toFixed(2), readiness: readinessScore.toFixed(0),
                        digipin: "DL-" + parts[0].toString().substring(3,5) + parts[1].toString().substring(3,5)
                    };
                    currentAll.push(nodeData);
                    if (floodLoad > 80) currentViolet.push(nodeData);
                }
            });

            let avgR = totalReadiness / nodes.length;
            document.getElementById('avgReadiness').innerText = Math.round(avgR) + "%";
            document.getElementById('avgReadiness').style.color = avgR < 40 ? "#ff0000" : (avgR < 75 ? "#ffaa00" : "#00ffcc");

            window.allDataQueue = currentAll; window.violetQueue = currentViolet;
            const dBtn = document.getElementById('dispatchBtn');
            if (currentViolet.length > 0) { dBtn.style.display = 'block'; dBtn.innerHTML = "🚨 DISPATCH NDRF (" + currentViolet.length + " ZONES)"; }
            else { dBtn.style.display = 'none'; }
        }

        function exportToKepler() { fetch('/export_kepler', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({nodes: window.allDataQueue}) }).then(() => { document.getElementById('keplerBtn').innerText = "✅ FILE SAVED"; }); }
        function sendEmergencyDispatch() { fetch('/trigger_dispatch', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({nodes: window.violetQueue, score: document.getElementById('avgReadiness').innerText}) }).then(() => { document.getElementById('dispatchBtn').innerText = "✅ DISPATCHED"; }); }

        document.getElementById('rainSlider').oninput = updateSim;
        document.getElementById('riverSlider').oninput = updateSim;
        document.getElementById('siltSlider').oninput = updateSim;
        setTimeout(updateSim, 1000);
    </script>
"""

# --- 3. MAP ENGINE ---
m = folium.Map(location=BHARAT_MANDAPAM, zoom_start=11, tiles=None)
folium.TileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satellite').add_to(m)

# 🏛️ Bharat Mandapam (Octagon)
folium.RegularPolygonMarker(location=BHARAT_MANDAPAM, number_of_sides=8, radius=15, color='#FFD700', fill=True,
                            fill_opacity=0.8).add_to(m)

# 🗺️ Operational Boundary
folium.Polygon(locations=DELHI_BOUNDARY, color='#ffcc00', weight=3, fill=True, fill_opacity=0.05,
               dash_array='5, 10').add_to(m)

# 🌊 Yamuna Marker
YAMUNA_PATH = [[28.835, 77.195], [28.790, 77.210], [28.615, 77.258], [28.480, 77.330]]
yamuna_gdf = gpd.GeoDataFrame(geometry=[LineString([(lon, lat) for lat, lon in YAMUNA_PATH])], crs="EPSG:4326")
folium.GeoJson(yamuna_gdf, style_function=lambda x: {'color': '#00d4ff', 'weight': 8, 'opacity': 0.8}).add_to(m)

# Nodes
lats = np.random.uniform(BHARAT_MANDAPAM[0] - 0.2, BHARAT_MANDAPAM[0] + 0.25, NUM_POINTS)
lngs = np.random.uniform(BHARAT_MANDAPAM[1] - 0.2, BHARAT_MANDAPAM[1] + 0.25, NUM_POINTS)
df = pd.DataFrame({'lat': lats, 'lng': lngs, 'zone_type': np.random.choice(['Planned', 'Unplanned'], NUM_POINTS),
                   'vulnerability': np.random.uniform(0.8, 1.2, NUM_POINTS)})
df['base_capacity'] = np.where(df['zone_type'] == 'Planned', 60, 25)
points_gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lng, df.lat), crs="EPSG:4326")
df['dist_to_river'] = points_gdf.to_crs(epsg=32643).geometry.distance(
    yamuna_gdf.to_crs(epsg=32643).unary_union) / 1000.0

for idx, row in df.head(450).iterrows():
    tag = f"{row['lat']}_{row['lng']}_SYNC"
    folium.CircleMarker(location=[row['lat'], row['lng']], radius=6, color='white', weight=1, fill=True,
                        fill_color='#00ff00', fill_opacity=0.9,
                        className=f"node {row['zone_type']} v-{int(row['vulnerability'] * 100)} d-{min(int(row['dist_to_river'] * 10), 999)} c-{row['base_capacity']} data-{tag}").add_to(
        m)

m.get_root().html.add_child(folium.Element(dashboard_html))


@app.route('/')
def index(): return m.get_root().render()


@app.route('/export_kepler', methods=['POST'])
def export_kepler():
    data = request.json['nodes']
    df_exp = pd.DataFrame(data)
    gpd.GeoDataFrame(df_exp, geometry=gpd.points_from_xy(df_exp.lng, df_exp.lat), crs="EPSG:4326").to_file(
        "mcd_kepler_export.geojson", driver="GeoJSON")
    return jsonify({"status": "success"})


@app.route('/trigger_dispatch', methods=['POST'])
def trigger_dispatch():
    nodes = request.json['nodes']
    score = request.json['score']
    sorted_nodes = sorted(nodes, key=lambda x: float(x['load']), reverse=True)[:3]

    alert_msg = f"🚨 *CRITICAL MCD DEPLOYMENT ALERT*\n\nAvg Zonal Readiness: *{score}*\n\n*Top Hit Hotspots:*\n"
    email_body = f"<h2>MCD Readiness: {score}</h2><ul>"

    for i, node in enumerate(sorted_nodes):
        nearest_camp = min(RELIEF_CAMPS, key=lambda c: haversine(node['lat'], node['lng'], c['lat'], c['lng']))
        dist = haversine(node['lat'], node['lng'], nearest_camp['lat'], nearest_camp['lng'])
        nature = f"({nearest_camp['type']} Camp)"

        # Telegram & Email construction
        block = (f"{i + 1}. DigiPIN: `{node['digipin']}` (Load: {node['load']})\n"
                 f"   📍 Coords: `{node['lat']:.5f}, {node['lng']:.5f}`\n"
                 f"   🚁 NDRF Unit: {nearest_camp['name']} {nature} ({dist:.1f}km away)\n\n")
        alert_msg += block
        email_body += f"<li>DigiPIN {node['digipin']} - {nature}</li>"

    requests.post("https://api.telegram.org/bot8686433144:AAF2x7pxOHgxndgo45q9aE42ocPc3gzTdSQ/sendMessage",
                  json={"chat_id": "7938650094", "text": alert_msg, "parse_mode": "Markdown"})

    # Send Email
    try:
        sender, app_pass, receiver = "vk.meta.1092@gmail.com", "mlbi pwqh fcnj abgn", "vishnujohri11@gmail.com"
        msg = MIMEMultipart()
        msg['Subject'] = f"CRITICAL: MCD DEPLOYMENT ({score} Readiness)"
        msg.attach(MIMEText(email_body, 'html'))
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender, app_pass)
            server.send_message(msg, from_addr=sender, to_addrs=receiver)
    except:
        pass

    return jsonify({"status": "success"})


if __name__ == '__main__': app.run(port=5000)