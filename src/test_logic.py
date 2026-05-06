import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '/Users/shubhsahu/Desktop/Risk/RiskMap/src')
from risk_engine import BuildingRecord, run_actual_pga

# 1. Create a dummy test scenario matching the logic
df_exposure = pd.DataFrame({
    'id': [1, 2],
    'lat': [31.5, 31.6],
    'lon': [77.5, 77.6],
    'classification': ['RCC_H1', 'MUR'],
    'custom_site_id': ['site_A', 'site_B']
})

df_pga = pd.DataFrame({
    'custom_site_id': ['site_A', 'site_A', 'site_B', 'site_B', 'site_B'],
    'gmv_PGA': [0.1, 0.3, 0.5, 0.5, 0.5] # Site A has variation, Site B has none
})

# 2. Build records
buildings = []
for _, r in df_exposure.iterrows():
    b = BuildingRecord(id=int(r['id']), lat=float(r['lat']), lon=float(r['lon']), beit_class=str(r['classification']))
    b.custom_site_id = str(r['custom_site_id'])
    buildings.append(b)

# 3. Process
results, out_df = run_actual_pga(buildings, df_pga)

print("--- VERIFICATION ---")
for r in results:
    match = df_pga[df_pga['custom_site_id'] == r.custom_site_id]
    expected_mean = match['gmv_PGA'].mean()
    expected_sigma = match['gmv_PGA'].std(ddof=0)
    print(f"Building {r.id} (Lat: {r.lat}, Lon: {r.lon}, Site: {r.custom_site_id})")
    print(f"  Mapped correctly? {r.pga_mean == expected_mean}")
    print(f"  sigma tracked? {r.pga_sigma == expected_sigma} (Calculated: {r.pga_sigma:.4f})")
    print()
