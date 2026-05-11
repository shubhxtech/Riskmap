import pandas as pd
import numpy as np

# Load everything
bld_df = pd.read_csv('/Users/shubhsahu/Desktop/Risk/RiskMap/latlongid.csv')
pga_df = pd.read_csv('/Users/shubhsahu/Desktop/Risk/RiskMap/pga_actual.csv', low_memory=False, comment='#')

# Missing sites
sites_in_bld = set(bld_df['custom_site_id'].dropna().astype(str))
sites_in_pga = set(pga_df['custom_site_id'].dropna().astype(str))
missing = sites_in_bld - sites_in_pga

print(f"Total Buildings: {len(bld_df)}")
print(f"Unique Sites in PGA data: {len(sites_in_pga)}")
print(f"Missing sites (appended as 0.001g): {len(missing)}")

if missing:
    print(f"First few missing: {list(missing)[:5]}")

avg_excel = pga_df['gmv_PGA'].mean()
print(f"\nExcel Average calculation of the CSV: {avg_excel:.4f}")

# Simulate how Risk Engine builds the internal list:
means = []
grouped = pga_df.groupby('custom_site_id')['gmv_PGA'].apply(list).to_dict()

for _, r in bld_df.iterrows():
    sid = str(r['custom_site_id'])
    v = grouped.get(sid, [])
    if not v:
        v = [0.001]
    means.append(np.mean(v))

print(f"RiskMap Risk Engine 'Mean PGA' Output: {np.mean(means):.4f}")

