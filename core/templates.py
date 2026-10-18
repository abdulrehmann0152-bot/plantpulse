"""Starting values for the Add Equipment form. Example values only: replace with real plant data."""
MATERIALS = ["Commercial steel (0.045 mm)", "Cast iron (0.26 mm)",
             "Galvanised iron (0.15 mm)", "PVC / drawn tubing (0.0015 mm)"]
FLOW_LABELS = {"counter": "Counter-flow", "parallel": "Parallel flow", "shell_1_2": "1 shell pass / 2 tube passes"}

HX_DEFAULT = {"area_m2": 10.0, "u_clean": 800.0, "flow": "counter"}
PUMP_DEFAULT = {"d_mm": 200.0, "length_m": 200.0, "material": MATERIALS[0], "sum_k": 8.0,
                "static_m": 10.0, "curve": [[0.0, 30.0], [200.0, 25.0], [300.0, 17.0]], "eta_pct": 70.0}

TEMPLATES = {
    "Blank (enter your own values)": {"eq_type": "heat_exchanger", "tag": "", "location": "", "params": HX_DEFAULT},
    "Sugar mill juice heater (example)": {"eq_type": "heat_exchanger", "tag": "JH-01",
        "location": "Juice heating station",
        "params": {"area_m2": 150.0, "u_clean": 1200.0, "flow": "shell_1_2"}},
    "Cooling-water pump loop (example)": {"eq_type": "pump", "tag": "CWP-01",
        "location": "Cooling tower circuit", "params": PUMP_DEFAULT},
}
