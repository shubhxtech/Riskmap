import pandas as pd

df = pd.read_csv('/Users/shubhsahu/Desktop/Risk/RiskMap/latlongid.csv')
print("Columns:", list(df.columns))

has_custom_id = "custom_site_id" in df.columns
print("Has custom_site_id:", has_custom_id)
if has_custom_id:
    for idx, r in df.head().iterrows():
        print(f"Row {idx} custom_site_id value: '{r['custom_site_id']}'")
        
pga = pd.read_csv('/Users/shubhsahu/Desktop/Risk/RiskMap/pga_actual.csv', low_memory=False, comment='#')
print("PGA Unique IDs (first 5):", set(list(pga['custom_site_id'].unique())[:5]))

matched = 0
for idx, r in df.iterrows():
    if str(r['custom_site_id']) in set(pga['custom_site_id']):
        matched += 1
print(f"Matched {matched} out of {len(df)} buildings")
