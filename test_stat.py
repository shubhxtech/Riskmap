import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '/Users/shubhsahu/Desktop/Risk/RiskMap/src')
from risk_engine import damage_state_probs

# Let's take site wh1zh8zx
pga = pd.read_csv('/Users/shubhsahu/Desktop/Risk/RiskMap/pga_actual.csv', low_memory=False, comment='#')
site = 'wh1zh8zx'
pgas = pga[pga['custom_site_id'] == site]['gmv_PGA'].values

mean_pga = np.mean(pgas)

# We use archetype MUR_LWAL_DNO_H1
arch = 'MUR_LWAL_DNO_H1'

# 1. PDS calculated from the mean PGA (What user likely did in Excel)
dp_from_mean_pga = damage_state_probs(float(mean_pga), arch)

# 2. Mean of PDS calculated per sample (What Python does)
ds_samples = {'None':[], 'DS1':[], 'DS2':[], 'DS3':[], 'DS4':[]}
for v in pgas:
    dp = damage_state_probs(float(v), arch)
    for k in dp:
        ds_samples[k].append(dp[k])

mean_ds_probs = {k: np.mean(ds_samples[k]) for k in ds_samples}

print(f"Mean PGA: {mean_pga:.4f}")
print("--- PDS for Mean PGA (Excel naive approach) vs Mean of PDS (Rigorous Monte Carlo) ---")
for k in ["None", "DS1", "DS2", "DS3", "DS4"]:
    print(f"{k}: Excel style $f(E[x])$ = {dp_from_mean_pga[k]:.5f} | System style $E[f(x)]$ = {mean_ds_probs[k]:.5f}")
