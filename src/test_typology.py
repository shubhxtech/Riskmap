import os
import json
import numpy as np
import sys
sys.path.insert(0, '/Users/shubhsahu/Desktop/Risk/RiskMap/src')
from risk_engine import register_custom_typology, BuildingRecord, FRAGILITY_LIB, CLASS_TO_ARCHETYPE

# 1. Register a custom typology
name = "TEST_ARCH"
ds_params = {
    "DS1": (0.1, 0.5),
    "DS2": (0.3, 0.5),
    "DS3": (0.5, 0.5),
    "DS4": (0.7, 0.5)
}
register_custom_typology(name, ds_params, 0.4, 5.0)

# 2. Verify it's in the maps
print(f"FRAGILITY_LIB has {name}: {name in FRAGILITY_LIB}")
print(f"CLASS_TO_ARCHETYPE has {name}: {name in CLASS_TO_ARCHETYPE}")

# 3. Create a building with this typology
b = BuildingRecord(id=1, lat=23.0, lon=77.0, beit_class=name)
print(f"Building archetype: {b.archetype}")

# 4. Check if persistence file exists and has the data
if os.path.exists("custom_typologies.json"):
    with open("custom_typologies.json", "r") as f:
        data = json.load(f)
        print(f"Persistence data for {name}: {data.get(name)}")

