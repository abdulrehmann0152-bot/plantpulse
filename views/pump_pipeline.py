import pandas as pd
import streamlit as st
from calc_engine import pump_explain, pump_pipe as pp, solver as sv
from calc_engine.heat_exchanger import InputError
from core import pump_plot, step_view
from core.unit_ui import unit_input as ui

st.title("💧 Pump & Pipeline")
st.caption("System curve vs pump curve, operating point, power and energy cost. Water service. Hover the ? icons for ranges and meaning.")

ROUGH = pp.ROUGHNESS_MM

with st.sidebar:
    st.header("Inputs")
    st.caption("Type each number as your problem gives it, then pick its unit.")
    st.subheader("Fluid: water")
    temp = ui("Temperature", "temp", 30.0, "p_t", step=1.0,
              help="Temperature of the water, from 0 to 100 °C (liquid water at atmospheric pressure). It sets the density and the viscosity: cold water is much more viscous, which matters most for laminar flow.")
    st.subheader("Pipeline")
    d_mm = ui("Inside diameter", "diameter", 200.0, "p_d", min_value=0.0, step=10.0,
              help="Inside (not nominal) diameter of the pipe. Must be greater than 0. Typical process and water lines are about 25 to 600 mm. A diameter typed in the wrong unit is the commonest mistake: 200 mm is 0.2 m.")
    length = ui("Pipe length", "length", 200.0, "p_l", min_value=0.0, step=10.0,
                help="Total straight pipe length from suction to discharge. Must be greater than 0. Do not count fittings here: add them below as ΣK or as an equivalent length.")
    mat = st.selectbox("Pipe material", list(ROUGH), key="p_m",
                       help="Sets the absolute roughness of the pipe wall (shown in brackets). Typical values: commercial steel 0.045 mm, galvanised iron 0.15 mm, cast iron 0.26 mm, drawn tubing or PVC 0.0015 mm. Old, corroded pipe is rougher than new.")
    minor = st.radio("Fittings and valves are given as", ["Sum of K values", "Equivalent length (Le/D)"], key="p_minor",
                     help="Two ways to account for elbows, tees, valves, entrances and exits. Sum of K values: each fitting has a loss coefficient K and the losses add. "
                          "Equivalent length: each fitting is replaced by a length of straight pipe, written as a multiple of the diameter (Le/D). Use only one.")
    if minor == "Sum of K values":
        sum_k = st.number_input("Fittings and valves, ΣK (-)", 0.0, 500.0, 8.0, 0.5, key="p_k",
                                help="Sum of the loss coefficients of all fittings (0 to 500). Typical order of magnitude: sharp pipe entrance 0.5, pipe exit 1.0, 90° elbow 0.3 to 0.9, fully open gate valve about 0.2, fully open globe valve 6 to 10. Cannot be negative.")
        le_d = 0.0
    else:
        le_d = st.number_input("Equivalent length of the fittings, Le/D (-)", 0.0, 5000.0, 30.0, 5.0, key="p_led",
                               help="Total equivalent length of all fittings as a multiple of the pipe diameter. For example a 90° elbow is roughly 30 diameters. Cannot be negative. It is added to the pipe length when the friction is calculated.")
        sum_k = 0.0
    static = ui("Static head", "head", 10.0, "p_s", min_value=0.0, step=0.5,
                help="Height the pump must lift the water: discharge liquid level minus suction liquid level (plus any pressure difference between the two ends, expressed as head). It does not change with flow. Cannot be negative on this page; 0 is allowed (a closed loop).")
    st.subheader("Pump curve (3 datasheet points)")
    st.caption("Heads must be above zero and normally fall as the flow rises. The first point is usually the shut-off point (flow 0).")
    pts = []
    for i, (q0, h0) in enumerate([(0, 30), (200, 25), (300, 17)]):
        qi = ui(f"Flow {i + 1}", "vol_flow", float(q0), f"p_q{i}", min_value=0.0, step=10.0,
                help="Flow at this point of the manufacturer's pump curve. Cannot be negative; 0 is allowed for the shut-off point. The three flows must all be different.")
        hi = ui(f"Head {i + 1}", "head", float(h0), f"p_h{i}", min_value=0.0, step=0.5,
                help="Head the pump produces at this flow. Must be greater than 0. A normal centrifugal pump curve falls as flow rises, with the highest head at zero flow.")
        pts.append((qi / 3600.0, hi))
    st.subheader("Energy")
    eta = st.number_input("Pump efficiency (%)", 0.0, 100.0, 70.0, 1.0, key="p_eta",
                          help="Hydraulic power divided by shaft power at the operating flow. Must be above 0% and below 100%. Typical centrifugal pumps: 50 to 85%. It is assumed constant here, but a real pump's efficiency changes with flow.") / 100
    eta_m = st.number_input("Motor efficiency (%)", 0.0, 100.0, 100.0, 1.0, key="p_etam",
                            help="Electrical power drawn = shaft power divided by motor efficiency. Typical industrial motors: 90 to 96%. The default of 100% means motor losses are NOT included in the energy cost, so enter your motor's value for a realistic cost.") / 100
    tariff = st.number_input("Electricity cost (Rs/kWh), edit to your tariff", 0.0, 500.0, 50.0, 1.0, key="p_tar",
                             help="Price of electricity in Rs per kWh. Cannot be negative. Check your latest bill or tariff schedule.")
    hours = st.number_input("Running hours per day", 0.0, 24.0, 24.0, 1.0, key="p_hr",
                            help="Hours the pump runs each day, from 0 to 24. The energy cost per day is proportional to it.")
    st.subheader("NPSH check (optional)")
    npsh_on = st.checkbox("Check NPSH available against NPSH required", key="p_npsh",
                          help="Tick this if you know the suction conditions. The app then compares the NPSH available with the NPSH the pump needs, to warn about cavitation. The vapour pressure is calculated from the water temperature above.")
    if npsh_on:
        basis_label = st.radio("Pressure on the liquid surface is given as", ["Gauge pressure", "Absolute pressure"], key="p_psb",
                               help="Gauge pressure is measured relative to the atmosphere (an open tank is 0). Absolute pressure is measured from a vacuum. NPSH needs the absolute value, so a gauge value is converted.")
        basis = "gauge" if basis_label.startswith("Gauge") else "absolute"
        p_vessel = ui("Pressure on the liquid surface", "pressure", 0.0, "p_ps", step=10.0,
                      help="Pressure acting on the free surface of the suction tank. For an open tank use 0 as gauge pressure (or 101.325 kPa absolute).")
        p_atm = ui("Atmospheric pressure", "pressure", 101.325, "p_patm", min_value=0.0, step=1.0, disabled=basis == "absolute",
                   help="Local atmospheric pressure, about 101.325 kPa at sea level (lower at altitude). Used only to convert a gauge pressure to absolute.")
        level = ui("Liquid level above the pump", "head", 3.0, "p_zl", step=0.5,
                   help="Height of the liquid surface above the pump centreline. Enter a negative number for a suction lift (tank below the pump).")
        hfs = ui("Friction loss in the suction line", "head", 0.5, "p_hfs", min_value=0.0, step=0.1,
                 help="Head lost to friction and fittings between the tank and the pump suction. Cannot be negative. Measure or calculate it for the suction pipe only.")
        npshr = ui("NPSH required by the pump", "head", 4.0, "p_npshr", min_value=0.0, step=0.5,
                   help="NPSH required (NPSHr) from the pump datasheet at the operating flow. It rises with flow, so read it at your operating point. Cannot be negative.")
        margin = st.number_input("Safety margin (m)", 0.0, 10.0, 0.5, 0.1, key="p_mrg",
                                 help="Extra NPSH you want above NPSHr, in metres. 0.5 m is a common minimum; many specifications ask for more.")

d, rough = d_mm / 1000.0, ROUGH[mat] / 1000.0
try:
    rho, mu = pp.water_properties(temp)
    pp.check_positive("Pipe length", length, " m")
    pp.check_non_negative("Equivalent length of the fittings Le/D", le_d)
    length_eff = length + le_d * d                       # equivalent length is added to the straight pipe: f (L + Le) / D
    curve_warnings = pp.check_pump_points(pts)
    coeffs = pp.fit_pump_curve(pts)
    pp.check_efficiency(eta)
    pp.check_motor_efficiency(eta_m)
    data_q_max = max(p[0] for p in pts)
    q_max = data_q_max * 1.5
    args = (static, d, length_eff, rough)
    op = pp.operating_point(coeffs, *args, sum_k, rho, mu, q_max, data_q_max)
    p_shaft = pp.shaft_power(op["hyd_w"], eta)
    npsh = None
    if npsh_on:
        pv = pp.water_vapor_pressure_kpa(temp)
        npsh = {"result": sv.npsh_check(p_vessel, basis, p_atm, level, hfs, pv, rho, npshr, margin, g=pp.G), "pv": pv, "level": level, "hfs": hfs, "npshr": npshr, "margin": margin}
except InputError as e:
    st.error(f"Please check your inputs: {e}")
    st.stop()

p_elec = p_shaft / eta_m
kwh_day = p_elec / 1000 * hours

c1, c2, c3, c4 = st.columns(4)
c1.metric("Operating flow", f"{pump_explain.fmt_flow(op['q'] * 3600)} m³/h", help="The flow at which the pump curve crosses the system curve.")
c2.metric("Operating head", f"{op['h']:.2f} m", help="The head the pump produces at the operating flow. It equals the head the pipeline needs: static head plus friction and fittings losses.")
c3.metric("Velocity", f"{op['v']:.2f} m/s", help="Mean velocity in the pipe, Q / A. Typical design range for water lines is 1 to 3 m/s.")
c4.metric("Reynolds number", f"{op['re']:,.0f}", pump_explain.REGIME_TEXT[op["regime"]], delta_color="off",
          help="Re = ρ v D / μ. Below 2,300 the flow is laminar, from 2,300 to 4,000 transitional (uncertain), above 4,000 turbulent.")
c5, c6, c7, c8 = st.columns(4)
c5.metric("Friction factor f", f"{op['f']:.4f}", help="Darcy friction factor: 64/Re when laminar, Colebrook-White when turbulent, a blend in between.")
c6.metric("Hydraulic power", f"{pump_explain.fmt_power(op['hyd_w'] / 1000) if op['hyd_w'] < 10 else format(op['hyd_w'] / 1000, '.2f')} kW", help="P = ρ g Q H: the useful power delivered to the water.")
c7.metric("Shaft power", f"{pump_explain.fmt_power(p_shaft / 1000) if p_shaft < 10 else format(p_shaft / 1000, '.2f')} kW", help="Hydraulic power divided by the pump efficiency: the power the motor must deliver to the pump shaft.")
c8.metric("Energy cost per day", f"Rs {kwh_day * tariff:,.0f}", f"{kwh_day:,.0f} kWh/day", delta_color="off",
          help="Electrical power (shaft power ÷ motor efficiency) × running hours × tariff. With a motor efficiency of 100% the motor losses are not included.")
if eta_m >= 0.999:
    st.caption("The energy cost uses the shaft power because the motor efficiency is 100%. Enter your motor's efficiency for the electricity actually drawn.")

for w in curve_warnings:
    st.warning(w)
if coeffs[1] + 2 * coeffs[2] * op["q"] >= 0:
    st.warning("The fitted pump curve is rising at the operating point. Check the three datasheet points.")
if op["extrapolated"]:
    st.warning(f"The operating point ({op['q'] * 3600:,.1f} m³/h) is beyond your last pump curve point ({data_q_max * 3600:g} m³/h). "
               "There the curve is an extrapolation of the fitted polynomial, not manufacturer data, so treat the flow, head and power as indicative only.")
if op["v"] > 3:
    st.warning("Velocity above 3 m/s is high for water lines. Check the diameter or flow.")
if 2300 <= op["re"] < 4000:
    st.warning("Flow is in the transition zone, so the friction factor is uncertain.")
note = pp.efficiency_note(eta)
if note:
    st.info(note)
if npsh:
    r = npsh["result"]
    if r["status"] == "ok":
        st.success(f"No cavitation risk: NPSH available {r['npsha']:.2f} m is above NPSH required {npsh['npshr']:g} m plus the {npsh['margin']:g} m margin.")
    elif r["status"] == "risk":
        st.error(f"Cavitation Risk! NPSH available {r['npsha']:.2f} m is above NPSH required {npsh['npshr']:g} m but inside the {npsh['margin']:g} m safety margin.")
    else:
        st.error(f"Cavitation Risk! NPSH available {r['npsha']:.2f} m is below NPSH required {npsh['npshr']:g} m: the pump will cavitate.")

tab1, tab2, tab3, tab4 = st.tabs(["Curves", "Step-by-step solution", "What-if: throttle valve", "Check my readings"])

with tab1:
    fig = pump_plot.operating_figure(coeffs, lambda q: pp.system_head(q, *args, sum_k, rho, mu), pts, op, static, data_q_max, q_max)
    st.plotly_chart(fig, width="stretch")
    st.caption("The pump runs where its curve crosses the system curve.")

with tab2:
    step_view.show_steps(pump_explain.build_steps(dict(
        temp=temp, rho=rho, mu=mu, d=d, length=length, rough=rough, sum_k=sum_k, le_d=le_d, static=static, pts=pts, coeffs=coeffs, op=op, q_data_max=data_q_max,
        eta=eta, eta_motor=eta_m, hours=hours, tariff=tariff, p_shaft_w=p_shaft, npsh=npsh)))

with tab3:
    st.write("A partly closed valve adds resistance (extra K). See how flow, head and power change.")
    extra = st.slider("Extra resistance added by valve, ΔK", 0, 100, 20, key="p_xk")
    try:
        op2 = pp.operating_point(coeffs, *args, sum_k + extra, rho, mu, q_max, data_q_max)
        ps2 = pp.shaft_power(op2["hyd_w"], eta)
        df = pd.DataFrame({"Baseline": [op["q"] * 3600, op["h"], p_shaft / 1000, kwh_day * tariff],
                           "With valve": [op2["q"] * 3600, op2["h"], ps2 / 1000, ps2 / eta_m / 1000 * hours * tariff]},
                          index=["Flow (m³/h)", "Head (m)", "Shaft power (kW)", "Energy cost (Rs/day)"]).round(2)
        st.dataframe(df, width="stretch")
        drop = (1 - op2["q"] / op["q"]) * 100
        st.info(f"Flow falls by {drop:.1f}% while shaft power changes by {(ps2 / p_shaft - 1) * 100:+.1f}%. "
                "Throttling cuts flow but saves little power; the extra head is lost across the valve. (Efficiency assumed constant.)")
    except InputError as e:
        st.error(f"This valve setting cannot be solved: {e}")

with tab4:
    st.write("Enter a reading from the plant. The twin compares it with the pump and system curves above.")
    m1, m2 = st.columns(2)
    q_m = ui("Measured flow", "vol_flow", round(op["q"] * 3600 * 0.9, 0), "p_qm", min_value=0.0, step=5.0, container=m1,
             help="Flow measured in the plant. Must be greater than 0.")
    h_m = ui("Measured head", "head", round(pp.pump_head(coeffs, op["q"] * 0.9), 1), "p_hm", min_value=0.0, step=0.5, container=m2,
             help="Pump head measured in the plant (discharge minus suction pressure, as head). Must be greater than 0.")
    try:
        dg = pp.diagnose(q_m / 3600, h_m, coeffs, *args, sum_k, rho, mu)
    except InputError as e:
        st.error(f"Please check the reading: {e}")
        st.stop()
    box = {"healthy": st.success, "check_data": st.warning}.get(dg["status"], st.error)
    box(dg["message"])
    st.dataframe(pd.DataFrame({"Expected on pump curve (m)": [dg["h_pump"]], "Expected on system curve (m)": [dg["h_sys"]],
                               "Measured (m)": [h_m], "Deviation from pump curve": [f"{dg['pump_dev'] * 100:+.1f}%"],
                               "Deviation from system curve": [f"{dg['sys_dev'] * 100:+.1f}%"]}).round(2),
                 hide_index=True, width="stretch")
    st.caption("Rule of thumb: ±5% is treated as normal. This is a screening aid, not a replacement for inspection.")
