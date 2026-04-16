"""
risk_engine.py  —  Scenario-based seismic risk assessment
==========================================================
Self-contained: no OpenQuake installation needed.

Pipeline
--------
1. HAZARD  : Boore-Atkinson 2008 GMPE  →  PGA (g) at each building site
2. FRAGILITY: Lognormal curves (GEM/HAZUS-calibrated) per structural archetype
3. RISK    : P(DS≥ds | PGA) per building  →  damage states & loss ratios
"""

import numpy as np
from scipy.stats import norm
from scipy.special import ndtr   # fast normal CDF
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import json, os

# ─────────────────────────────────────────────────────────────────────────────
#  1. BUILDING CLASS → STRUCTURAL ARCHETYPE MAPPING
# ─────────────────────────────────────────────────────────────────────────────
# Your 24 BEiT classes mapped to archetype keys used in fragility library
CLASS_TO_ARCHETYPE = {
    # Adobe / Dressed Rubble Masonry
    "AD_H1":              "MUR_ADO_LWAL_DNO_H1",   # Adobe, 1-storey
    "AD_H2":              "MUR_ADO_LWAL_DNO_H2",   # Adobe, 2-storey
    # Masonary Rubble
    "MR_H1 flat roof":    "MUR_LWAL_DNO_H1",
    "MR_H1 gable roof":   "MUR_LWAL_DNO_H1",
    "MR_H2 flat roof":    "MUR_LWAL_DNO_H2",
    "MR_H2 gable roof":   "MUR_LWAL_DNO_H2",
    "MR_H3":              "MUR_LWAL_DNO_H3",
    # Metal / Light Steel
    "Metal_H1":           "W_WWD_LWAL_DNO_H1",
    # Non-building
    "Non_Building":       "NON_BLDG",
    # RCC (Reinforced Concrete)
    "RCC_H1 flat roof":   "CR_LFINF_DUL_H1",
    "RCC_H1 gable roof":  "CR_LFINF_DUL_H1",
    "RCC_H2 flat roof":   "CR_LFINF_DUL_H2",
    "RCC_H2 gable roof":  "CR_LFINF_DUL_H2",
    "RCC_H3 flat roof":   "CR_LFINF_DUL_H3",
    "RCC_H3 gable roof":  "CR_LFINF_DUL_H3",
    "RCC_H4 flat roof":   "CR_LFINF_DUL_H4",
    "RCC_H4 gaqble roof": "CR_LFINF_DUL_H4",
    "RCC_H5":             "CR_LFINF_DUL_H5",
    "RCC_H6":             "CR_LFINF_DUL_H6",
    # RCC on soft storey / open ground
    "RCC_OS_H1":          "CR_LFINF_DUL_H2_SOS",
    "RCC_OS_H2":          "CR_LFINF_DUL_H2_SOS",
    "RCC_OS_H3":          "CR_LFINF_DUL_H3_SOS",
    "RCC_OS_H4":          "CR_LFINF_DUL_H4_SOS",
    # Timber
    "Timber":             "W_WWD_LWAL_DNO_H1",
}

# ─────────────────────────────────────────────────────────────────────────────
#  2. FRAGILITY LIBRARY  (lognormal parameters per archetype)
#
#  Format: archetype → {DS1..DS4: (median_PGA_g, beta)}
#  DS1=Slight, DS2=Moderate, DS3=Extensive, DS4=Complete/Collapse
#
#  Sources:
#   • RC frames  — Martins & Silva 2020 (GEM global model), Table A2
#   • Masonry    — HAZUS-MH MR3, Table 5.9-B (URM, low-code)
#   • Adobe      — Sumerente et al 2020 (Frontiers Built Env)
#   • Timber     — HAZUS-MH MR3 W1A low-code
#   • Steel      — HAZUS-MH MR3 S4 low-code
#   • RC open-storey — Chaulagain et al 2015 (Nepal RC soft-storey)
# ─────────────────────────────────────────────────────────────────────────────
FRAGILITY_LIB = {

    # ── Masonry ──────────────────────────────────────────────────────────
    "MUR_LWAL_DNO_H1": {
        "DS1": (-0.911962642, 0.562491152),
        "DS2": (-0.122671306, 0.562491149),
        "DS3": (0.244340625, 0.562491149),
        "DS4": (0.475321695, 0.562491150),
    },
    "MUR_LWAL_DNO_H2": {
        "DS1": (-1.14523825, 0.640541373),
        "DS2": (-0.195063817, 0.640541374),
        "DS3": (0.246757011, 0.640541374),
        "DS4": (0.524819493, 0.640541374),
    },
    "MUR_LWAL_DNO_H3": {
        "DS1": (-0.997431738, 0.620121965),
        "DS2": (-0.149794943, 0.620121965),
        "DS3": (0.261344033, 0.620121965),
        "DS4": (0.522761753, 0.620121965),
    },

    # ── Adobe Masonry ────────────────────────────────────────────────────
    "MUR_ADO_LWAL_DNO_H1": {
        "DS1": (-1.391966295, 0.583567900),
        "DS2": (-0.476747385, 0.583567955),
        "DS3": (-0.085830535, 0.583567955),
        "DS4": (0.155673662, 0.583567955),
    },
    "MUR_ADO_LWAL_DNO_H2": {
        "DS1": (-1.373471577, 0.616118189),
        "DS2": (-0.442437526, 0.616118185),
        "DS3": (-0.013589126, 0.616118185),
        "DS4": (0.255716470, 0.616118185),
    },

    # ── Reinforced Concrete ──────────────────────────────────────────────
    "CR_LFINF_DUL_H1": {
        "DS1": (-0.87468608, 0.425436474),
        "DS2": (-0.301963334, 0.425387123),
        "DS3": (-0.052527248, 0.425387137),
        "DS4": (0.102190225, 0.425387201),
    },
    "CR_LFINF_DUL_H2": {
        "DS1": (-1.059004334, 0.675242443),
        "DS2": (0.292452209, 0.675242443),
        "DS3": (0.780034443, 0.675242443),
        "DS4": (1.072491258, 0.675242443),
    },
    "CR_LFINF_DUL_H3": {
        "DS1": (-0.940573418, 0.651291225),
        "DS2": (0.264215968, 0.651291225),
        "DS3": (0.723776922, 0.651291225),
        "DS4": (1.001847867, 0.651291225),
    },
    "CR_LFINF_DUL_H4": {
        "DS1": (-1.633714273, 0.554505247),
        "DS2": (-0.392197844, 0.554495710),
        "DS3": (0.114065380, 0.554495710),
        "DS4": (0.424016783, 0.554495710),
    },
    "CR_LFINF_DUL_H5": {
        "DS1": (-1.480628673, 0.579459665),
        "DS2": (-0.338988655, 0.579459737),
        "DS3": (0.157748777, 0.579459737),
        "DS4": (0.465801289, 0.579459737),
    },
    "CR_LFINF_DUL_H6": {
        "DS1": (-1.283064485, 0.570498605),
        "DS2": (-0.255782702, 0.570498623),
        "DS3": (0.225368906, 0.570498623),
        "DS4": (0.528702724, 0.570498622),
    },

    # ── RC Soft Storey ───────────────────────────────────────────────────
    "CR_LFINF_DUL_H2_SOS": {
        "DS1": (-1.238300799, 0.665461304),
        "DS2": (-0.141006715, 0.665461304),
        "DS3": (0.315083295, 0.665461304),
        "DS4": (0.595333806, 0.665461304),
    },
    "CR_LFINF_DUL_H3_SOS": {
        "DS1": (-1.132783934, 0.653567396),
        "DS2": (-0.134873191, 0.653567396),
        "DS3": (0.294080513, 0.653567396),
        "DS4": (0.559427234, 0.653567396),
    },
    "CR_LFINF_DUL_H4_SOS": {
        "DS1": (-1.870615607, 0.537026630),
        "DS2": (-0.849105436, 0.536711006),
        "DS3": (-0.377744984, 0.536711000),
        "DS4": (-0.081595127, 0.536711000),
    },

    # ── Wood / Timber ────────────────────────────────────────────────────
    "W_WWD_LWAL_DNO_H1": {
        "DS1": (-1.272244384, 0.553822894),
        "DS2": (-0.386797794, 0.553823200),
        "DS3": (-0.015491804, 0.553823200),
        "DS4": (0.213055871, 0.553823200),
    },

    "NON_BLDG": {
        "DS1": (99.0, 0.01),
        "DS2": (99.0, 0.01),
        "DS3": (99.0, 0.01),
        "DS4": (99.0, 0.01),
    },
}

# Loss ratios per damage state (central values, from HAZUS / GEM)
LOSS_RATIO = {
    "None": 0.00,
    "DS1":  0.05,   # Slight:    ~5%  replacement cost
    "DS2":  0.20,   # Moderate: ~20%
    "DS3":  0.50,   # Extensive: ~50%
    "DS4":  1.00,   # Complete: 100%
}

# ─────────────────────────────────────────────────────────────────────────────
#  3. HAZARD — Boore-Atkinson 2008 GMPE
# ─────────────────────────────────────────────────────────────────────────────
def boore_atkinson_2008_pga(
    Mw: float,
    Rjb: float,          # Joyner-Boore distance (km)
    depth: float = 10.0, # hypocentral depth (km) — used for Rjb floor
    Vs30: float = 400.0, # time-avg shear-wave velocity top 30 m (m/s)
    fault_type: str = "unspecified",  # "normal", "reverse", "unspecified"
) -> Tuple[float, float]:
    """
    BA08: Boore & Atkinson 2008 NGA GMPE for PGA.
    Returns (median_PGA_g, sigma_ln) — both in natural-log space.

    Coefficients from Table 1 of Boore & Atkinson (2008),
    Earthquake Spectra 24(1):99-138.
    """
    # Fault-type flags
    U = 1 if fault_type == "unspecified" else 0
    SS = 1 if fault_type == "strike-slip" else 0
    NS = 1 if fault_type == "normal" else 0
    RS = 1 if fault_type == "reverse" else 0

    # PGA coefficients (T=0, i.e. "pga" row in BA08 Table 1)
    e1  =  -0.66050
    e2  =  -0.51429
    e3  =  -0.84407
    e4  =  -0.56996
    e5  =   0.43291
    e6  =  -0.05311
    e7  =   0.00000
    Mh  =   6.75
    c1  =  -0.66220
    c2  =   0.12000
    c3  =  -0.01151
    Mref=   4.50
    Rref=   1.00
    blin= -0.36020
    b1  =  -0.64010
    b2  =  -0.14380
    V1  = 180.0
    V2  = 300.0
    Vref= 760.0
    sigma_T = 0.600   # total sigma (ln units), Table 8 BA08

    # ── 1. Source term ───────────────────────────────────────────────────
    if Mw <= Mh:
        FM = (e1*U + e2*SS + e3*NS + e4*RS
              + e5*(Mw - Mh)
              + e6*(Mw - Mh)**2)
    else:
        FM = (e1*U + e2*SS + e3*NS + e4*RS
              + e7*(Mw - Mh))

    # ── 2. Path term ─────────────────────────────────────────────────────
    R = np.sqrt(Rjb**2 + depth**2)   # effective distance
    FD = (c1 + c2*(Mw - Mref)) * np.log(R / Rref) + c3*(R - Rref)

    # ── 3. Site amplification term ────────────────────────────────────────
    # Linear component
    if Vs30 <= V1:
        ln_Flin = blin * np.log(V1 / Vref)
    elif Vs30 <= V2:
        ln_Flin = blin * np.log(Vs30 / Vref)
    else:
        ln_Flin = blin * np.log(min(Vs30, Vref) / Vref)

    # Nonlinear component (bnl)
    pga_ref_ln = FM + FD  # ln PGA on reference rock (Vs30=760)
    pga_ref = np.exp(pga_ref_ln)   # in g (BA08 uses g as output unit)
    bnl= 0
    dx = np.log(V2 / V1)
    if Vs30 <= V1:
        bnl = b1

    elif Vs30 <= V2:
        bnl =  (b1 - b2) * np.log(Vs30 / V2) / np.log(V1 / V2) + b2

    elif Vs30 <= Vref:
        bnl = b2 * np.log(Vs30 / Vref) / np.log(V2 / Vref)

    else:
        bnl = 0.0

    # Nonlinear amplification (BA08 Eq. 5)
    # constants
    a1 = 0.03
    a2 = 0.09
    pga_low = 0.06
    dy = bnl * np.log(a2 / pga_low)
    # compute c and d
    # x = np.log(a2 / a1)
    # y = bnl * np.log(a2 / pga_low)

    c = (3*dy - bnl*dx) / (dx**2)
    d = (-2*dy + bnl*dx) / (dx**3)

    # nonlinear term
    if pga_ref <= a1:
        ln_Fnl = bnl * np.log(pga_low / 0.1)

    elif pga_ref <= a2:
        ln_ratio = np.log(pga_ref / a1)
        ln_Fnl = (bnl * np.log(pga_low / 0.1)
                + c * (ln_ratio**2)
                + d * (ln_ratio**3))

    else:
        ln_Fnl = bnl * np.log(pga_ref / 0.1)

    FS = ln_Flin + ln_Fnl

    # ── 4. Total ln(PGA) ─────────────────────────────────────────────────
    ln_pga = FM + FD + FS
    median_pga = np.exp(ln_pga)   # g

    return float(median_pga), float(sigma_T)


def compute_site_pga(
    source_lat: float, source_lon: float,
    site_lats: np.ndarray, site_lons: np.ndarray,
    Mw: float, depth: float, Vs30: float,
    fault_type: str = "unspecified",
    n_samples: int = 1000,
) -> np.ndarray:
    """
    For each site, compute Rjb and then sample PGA from BA08 distribution.
    Returns array of shape (n_sites, n_samples) — PGA in g.
    """
    # Haversine distance (km)
    R_earth = 6371.0
    dlat = np.radians(site_lats - source_lat)
    dlon = np.radians(site_lons - source_lon)
    a = (np.sin(dlat/2)**2
         + np.cos(np.radians(source_lat))
         * np.cos(np.radians(site_lats))
         * np.sin(dlon/2)**2)
    Rjb = R_earth * 2 * np.arcsin(np.sqrt(a))   # surface distance
    Rjb = np.maximum(Rjb, 1.0)                   # floor 1 km

    n_sites = len(site_lats)
    pga_samples = np.zeros((n_sites, n_samples))

    rng = np.random.default_rng(42)
    eps = rng.standard_normal((n_sites, n_samples))  # aleatory variability

    for i in range(n_sites):
        mu, sigma = boore_atkinson_2008_pga(Mw, float(Rjb[i]), depth, Vs30, fault_type)
        ln_pga_samples = np.log(mu) + sigma * eps[i]
        pga_samples[i] = np.exp(ln_pga_samples)

    return pga_samples   # shape (n_sites, n_samples)


# ─────────────────────────────────────────────────────────────────────────────
#  4. FRAGILITY — P(DS ≥ ds | PGA)
# ─────────────────────────────────────────────────────────────────────────────
def fragility_prob(pga: float, ln_median: float, beta: float) -> float:
    """P(DS ≥ ds | PGA) for lognormal fragility curve."""
    if ln_median >= 90.0:
        return 0.0
    return float(ndtr((np.log(pga) - ln_median) / beta))


def damage_state_probs(pga: float, archetype: str) -> Dict[str, float]:
    """
    Returns dict of P(DS = ds | PGA) for each damage state
    including "None" (no damage).
    """
    params = FRAGILITY_LIB.get(archetype, FRAGILITY_LIB["CR_LFINF_DUL_H1"])

    p_ds1 = fragility_prob(pga, *params["DS1"])
    p_ds2 = fragility_prob(pga, *params["DS2"])
    p_ds3 = fragility_prob(pga, *params["DS3"])
    p_ds4 = fragility_prob(pga, *params["DS4"])

    # P(DS = ds) = P(DS≥ds) - P(DS≥ds+1)
    p_none = max(0.0, 1.0 - p_ds1)
    p1 = max(0.0, p_ds1 - p_ds2)
    p2 = max(0.0, p_ds2 - p_ds3)
    p3 = max(0.0, p_ds3 - p_ds4)
    p4 = max(0.0, p_ds4)

    return {"None": p_none, "DS1": p1, "DS2": p2, "DS3": p3, "DS4": p4}


def expected_loss_ratio(pga: float, archetype: str) -> float:
    """E[LR | PGA] = Σ P(DS=ds) × LR(ds)"""
    probs = damage_state_probs(pga, archetype)
    return sum(LOSS_RATIO[ds] * p for ds, p in probs.items())


# ─────────────────────────────────────────────────────────────────────────────
#  5. SCENARIO RISK CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ScenarioParams:
    Mw:         float = 6.5
    depth_km:   float = 10.0
    source_lat: float = 31.70
    source_lon: float = 76.93
    Vs30:       float = 400.0     # m/s  (400 = stiff soil, 760 = rock)
    fault_type: str   = "unspecified"
    n_samples:  int   = 500


@dataclass
class BuildingRecord:
    id:             int
    lat:            float
    lon:            float
    beit_class:     str
    archetype:      str = field(init=False)

    def __post_init__(self):
        self.archetype = CLASS_TO_ARCHETYPE.get(self.beit_class, "RC_H1")


@dataclass
class BuildingResult:
    id:          int
    beit_class:  str
    archetype:   str
    lat:         float
    lon:         float
    pga_median:  float        # g
    pga_84pct:   float        # g (84th percentile across aleatory samples)
    ds_probs:    Dict[str, float]
    mean_ds:     str          # most-likely damage state
    loss_ratio:  float        # expected loss ratio 0–1


def run_scenario(
    buildings: List[BuildingRecord],
    params: ScenarioParams,
) -> Tuple[List[BuildingResult], pd.DataFrame]:
    """
    Full scenario risk calculation.
    Returns list of BuildingResult and a summary DataFrame.
    """
    if not buildings:
        return [], pd.DataFrame()

    lats = np.array([b.lat for b in buildings])
    lons = np.array([b.lon for b in buildings])

    # PGA samples: shape (n_sites, n_samples)
    pga_samples = compute_site_pga(
        params.source_lat, params.source_lon,
        lats, lons,
        params.Mw, params.depth_km, params.Vs30,
        params.fault_type, params.n_samples,
    )

    results = []
    for i, bldg in enumerate(buildings):
        samples_i   = pga_samples[i]
        pga_med     = float(np.median(samples_i))
        pga_84      = float(np.percentile(samples_i, 84))

        # Compute mean damage probabilities across aleatory samples
        ds_probs_acc = {k: 0.0 for k in ["None","DS1","DS2","DS3","DS4"]}
        lr_acc = 0.0
        for pga_val in samples_i:
            dp = damage_state_probs(float(pga_val), bldg.archetype)
            for k in dp:
                ds_probs_acc[k] += dp[k]
            lr_acc += expected_loss_ratio(float(pga_val), bldg.archetype)

        ds_probs = {k: v / params.n_samples for k, v in ds_probs_acc.items()}
        lr       = lr_acc / params.n_samples
        mean_ds  = max(ds_probs, key=ds_probs.get)

        results.append(BuildingResult(
            id          = bldg.id,
            beit_class  = bldg.beit_class,
            archetype   = bldg.archetype,
            lat         = bldg.lat,
            lon         = bldg.lon,
            pga_median  = pga_med,
            pga_84pct   = pga_84,
            ds_probs    = ds_probs,
            mean_ds     = mean_ds,
            loss_ratio  = lr,
        ))

    # Summary DataFrame
    rows = []
    for r in results:
        rows.append({
            "ID":           r.id,
            "BEiT Class":   r.beit_class,
            "Archetype":    r.archetype,
            "Lat":          round(r.lat, 6),
            "Lon":          round(r.lon, 6),
            "PGA median(g)": round(r.pga_median, 4),
            "PGA 84%(g)":   round(r.pga_84pct,  4),
            "P(None)":      round(r.ds_probs["None"], 3),
            "P(DS1)":       round(r.ds_probs["DS1"],  3),
            "P(DS2)":       round(r.ds_probs["DS2"],  3),
            "P(DS3)":       round(r.ds_probs["DS3"],  3),
            "P(DS4)":       round(r.ds_probs["DS4"],  3),
            "Mean DS":      r.mean_ds,
            "Loss Ratio":   round(r.loss_ratio, 3),
        })

    df = pd.DataFrame(rows)
    return results, df


def portfolio_summary(results: List[BuildingResult]) -> Dict:
    """Aggregate statistics across the portfolio."""
    if not results:
        return {}
    n = len(results)
    ds_counts = {ds: sum(1 for r in results if r.mean_ds == ds)
                 for ds in ["None","DS1","DS2","DS3","DS4"]}
    avg_lr   = np.mean([r.loss_ratio for r in results])
    total_lr = np.sum([r.loss_ratio for r in results])

    return {
        "n_buildings":    n,
        "ds_counts":      ds_counts,
        "ds_pct":         {k: round(100*v/n,1) for k,v in ds_counts.items()},
        "avg_loss_ratio": round(float(avg_lr), 3),
        "total_loss_units": round(float(total_lr), 2),
        "pga_mean_g":     round(float(np.mean([r.pga_median for r in results])), 4),
    }
