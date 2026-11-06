SNAPSHOT_ID = "eprel_wm_2026-11-02"
RAW_FILE = "data/raw/eprel_export_2026-11-02/washingmachines2019_EN.csv"

# our field name -> exact header in the EPREL export (checked 6 Nov 2026)
COLUMN_MAP = {
    "eprel_id":                          "Registration identifier",
    "brand":                             "Brand or trademark",
    "model_identifier":                  "Model identifier",
    "supplier_name":                     "Supplier name",
    "gtin":                              "GTIN identifier",
    "first_placement_date":              "Date of first placing on the market",
    "end_placement_date":                "Date of end of placement on the market",
    "rated_capacity_kg":                 "Rated capacity (Kg)",
    "energy_class":                      "Energy Efficiency Class",
    "eei":                               "Energy efficiency Index (EEI)",
    "energy_kwh_per_cycle_eco4060":      "Energy consumption (per cycle, eco 40-60 programme) (kWh)",
    "energy_kwh_per_100_cycles_eco4060": "Weighted energy consumption (per 100 cycles, eco 40-60 programme) (kWh)",
    "water_l_per_cycle_eco4060":         "Water consumption (per cycle, eco 40-60 programme) (litres)",
    "duration_min_rated":                "Programme duration (Rated capacity) (minutes)",
    "noise_db_spin":                     "Airborne acoustical noise emissions (spinning phase) (dB)",
    "commercial_guarantee_months":       "Duration of the commercial guarantee offered by the supplier (months)",
    "supplier_information_url":          "Weblink to the supplier’s website",
    "installation_type":                 "Type",
}

FIGURE_FIELDS = ["eprel_id", "rated_capacity_kg", "energy_kwh_per_100_cycles_eco4060",
                 "water_l_per_cycle_eco4060", "energy_class"]

PLAUSIBLE = {
    "rated_capacity_kg":                 (1, 20),
    "energy_kwh_per_100_cycles_eco4060": (10, 200),
    "water_l_per_cycle_eco4060":         (10, 120),
    "noise_db_spin":                     (30, 100),
    "duration_min_rated":                (30, 480),
}
DB_PATH = "outputs/monitor.sqlite"
