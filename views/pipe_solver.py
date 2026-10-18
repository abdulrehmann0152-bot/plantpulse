import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from calc_engine import solver, pump_pipe as pp
from calc_engine.heat_exchanger import InputError
from core import animation, validation as val
from core.clipboard import show_copy_button
from core.form_state import FormState
from core.results_text import build_text
from core.unit_ui import unit_input as ui

fs = FormState("pp")
K, blank = fs.key, fs.blank
st.title("🚰 Problem Solver: Pipes and Pumps")
st.caption("Enter what the problem gives. PlantPulse shows the theory, every formula and assumption, and an animated flow diagram.")
fs.top_buttons()

with st.expander("Theory: pipe flow, friction and pump head (read this first)", expanded=False):
    st.markdown("**Reynolds number** tells whether the flow is laminar (Re below about 2,300), in transition, or turbulent (above about 4,000):")
    st.latex(r"Re=\dfrac{\rho\, v\, D}{\mu}")
    st.markdown("**Darcy-Weisbach** gives the friction loss in a straight pipe. The friction factor f is 64/Re for laminar flow and comes from the Moody chart (or the Swamee-Jain equation) for turbulent flow:")
    st.latex(r"h_f=f\,\dfrac{L}{D}\,\dfrac{v^2}{2g}\qquad \Delta P_f=\rho g h_f")
    st.markdown("**Fittings and valves** add minor losses. Textbooks give them either as a loss coefficient K, or as an equivalent length of straight pipe written as a multiple of the diameter (Le/D). Both can be used together:")
    st.latex(r"h_K=\Sigma K\,\dfrac{v^2}{2g}\qquad h_{Le}=f\,\dfrac{L_e}{D}\,\dfrac{v^2}{2g}")
    st.markdown("**Energy balance between two large tanks** (negligible velocity at both ends). The pump must lift the liquid, overcome any pressure difference, and pay for the losses:")
    st.latex(r"H=\Delta z+\dfrac{\Delta P}{\rho g}+h_f+h_K+h_{Le}\qquad P_{hyd}=\rho g Q H\qquad P_{shaft}=\dfrac{P_{hyd}}{\eta}")
    st.markdown("When the flow is unknown, friction depends on velocity and velocity depends on friction, so the equation is solved by iteration.")

mode = st.radio("What do you want to find?", ["Head, pressure drop and pump power for a given flow", "The flow for a given available head"], key=K("pp_mode"),
                help="Choose the first when the flow is known and you need the pump head and power. Choose the second when a head is available (a tank above the outlet, or a given pump head) and you need the flow it can drive.")
by_flow = mode.startswith("Head")
REQ = "required"

st.caption("Type each number as your problem gives it, then pick its unit.")
st.subheader("1. Fluid")
fluid = st.radio("Fluid", ["Water", "Other liquid (enter density and viscosity)"], horizontal=True, key=K("pp_fluid"))
temp = rho = mu = None
if fluid == "Water":
    temp = ui("Water temperature", "temp", 20.0, K("pp_temp"), optional=blank, placeholder=REQ,
              help="Water density and viscosity are looked up from this temperature (0 to 100 °C).")
    if temp is not None:
        try:
            rho, mu = pp.water_properties(temp)
        except InputError as e:
            st.error(f"{e} (Check the unit you selected.)"); st.stop()
        st.caption(f"Water at {temp:g} °C: density {rho:.1f} kg/m³, viscosity {mu * 1000:.3f} mPa·s (cP).")
else:
    c1, c2 = st.columns(2)
    rho = ui("Density", "density", 870.0, K("pp_rho"), min_value=0.0, container=c1, optional=blank, placeholder=REQ,
             help="Mass per unit volume of the liquid. If the problem gives a specific gravity, multiply it by 1000 kg/m³.")
    mu_in = ui("Viscosity", "viscosity", 10.0, K("pp_mu"), min_value=0.0, container=c2, optional=blank, placeholder=REQ,
               help="Dynamic viscosity. 1 mPa·s equals 1 cP; water at 20 °C is about 1 cP. Oils are often given in cP or in Pa·s.")
    mu = None if mu_in is None else mu_in / 1000.0

st.subheader("2. Pipe")
c1, c2 = st.columns(2)
d_mm = ui("Inside diameter", "diameter", 100.0, K("pp_d"), min_value=0.0, container=c1, optional=blank, placeholder=REQ,
          help="The inside diameter of the pipe, not the nominal size. Use the actual inside diameter from the pipe schedule if the problem gives a nominal size and a schedule.")
length = ui("Pipe length", "length", 200.0, K("pp_l"), min_value=0.0, container=c2, optional=blank, placeholder=REQ,
            help="The straight length of pipe. Fittings go in the boxes below, not here.")
minor = st.radio("Minor losses (fittings and valves) are given as", ["Sum of K values", "Equivalent length (Le/D)"], horizontal=True, key=K("pp_minor"),
                 help="Textbooks give the losses of elbows, valves and tees in one of two ways: a loss coefficient K for each fitting, or an equivalent length of straight pipe written as a "
                      "multiple of the diameter (Le/D). Pick the way your problem gives them; only that method is used.")
by_k = minor.startswith("Sum")
sum_k = led = 0.0
if by_k:
    sum_k = st.number_input("Fittings and valves, ΣK (-)", min_value=0.0, max_value=1000.0, value=None if blank else 8.0, placeholder="0", key=K("pp_k"),
                            help="The sum of the loss coefficients K of all elbows, valves, tees, entrances and exits. Each adds K·v²/2g of head loss. "
                                 "Take K from the table in your textbook, and use 0 if the problem ignores minor losses.") or 0.0
else:
    led = st.number_input("Equivalent length of the fittings, Le/D (-)", min_value=0.0, max_value=100000.0, value=None if blank else 0.0, placeholder="0", key=K("pp_led"),
                          help="Equivalent length: each fitting or valve is treated as a length of straight pipe that gives the same friction loss, written as a multiple of the pipe diameter (Le/D). "
                               "How to find it: look up the Le/D of every elbow, valve and tee in the table in your textbook, then add them up. "
                               "It adds f·(Le/D)·v²/2g of head loss.") or 0.0
mat = st.selectbox("Pipe material (roughness)", list(pp.ROUGHNESS_MM) + ["Custom (enter roughness)"], key=K("pp_mat"),
                   help="The absolute roughness ε of the pipe wall, used to find the friction factor in turbulent flow. Pick the material, or choose Custom if the problem gives ε.")
rough = (ui("Roughness ε", "roughness", 0.045, K("pp_rough"), min_value=0.0, optional=blank, placeholder=REQ, help="Absolute roughness of the pipe wall, as given in the problem.")
         if mat.startswith("Custom") else pp.ROUGHNESS_MM[mat])

st.subheader("3. Flow and heads")
q = v_in = static = dp = eta = head = None
if by_flow:
    c1, c2 = st.columns(2)
    given_kind = c1.radio("The problem gives", ["Flow rate", "Velocity"], horizontal=True, key=K("pp_given"))
    if given_kind == "Flow rate":
        q = ui("Flow", "vol_flow", 56.5, K("pp_q"), min_value=0.0, container=c1, optional=blank, placeholder=REQ, help="The volumetric flow rate through the pipe.")
    else:
        v_in = ui("Velocity", "velocity", 2.0, K("pp_vel"), min_value=0.0, container=c1, optional=blank, placeholder=REQ,
                  help="The average velocity in the pipe. PlantPulse converts it to a flow with Q = v × A.")
        if v_in is not None and d_mm:
            q = v_in * math.pi * (d_mm / 1000.0) ** 2 / 4 * 3600
            c1.caption(f"Flow = v × A = {q:.3f} m³/h")
    static = ui("Static head Δz", "head", 10.0, K("pp_static"), container=c1, optional=blank, placeholder="0",
                help="The height the liquid is lifted: the discharge level minus the suction level. Negative if the liquid flows downhill.") or 0.0
    dp = ui("Pressure difference between ends", "pressure", 0.0, K("pp_dp"), container=c2, optional=blank, placeholder="0",
            help="The pressure at the discharge end minus the pressure at the suction end (for example a pressurised vessel). Use 0 if both ends are open to the atmosphere.") or 0.0
    eta = c2.number_input("Pump efficiency (%)", min_value=1.0, max_value=100.0, value=None, placeholder="optional", key=K("pp_eta"),
                          help="Overall pump efficiency from the problem or the pump curve. Needed only if you want the shaft power; without it you get the hydraulic power.")
else:
    head = ui("Available head to overcome friction and fittings", "head", 5.0, K("pp_head"), min_value=0.0, optional=blank, placeholder=REQ,
              help="The head that drives the flow: for example the height of a supply tank above the outlet, or a given pump head, after subtracting any static lift.")

npsh_on = pump_on = False
ps = patm = level = hfs = pv = npshr = margin = rpm = stages = qbep = etab = None
basis = "gauge"
curve_pts = []
if by_flow:
    st.subheader("4. NPSH (Net Positive Suction Head), optional")
    npsh_on = st.checkbox("Check NPSH available against NPSH required", key=K("pp_npsh"),
                          help="NPSH tells you whether the pump will cavitate. NPSH available is the pressure head above the liquid's vapour pressure at the pump suction; "
                               "it must exceed the NPSH the pump needs.")
    if npsh_on:
        n1, n2 = st.columns(2)
        ps = ui("Suction vessel pressure", "pressure", 0.0, K("pp_ps"), container=n1, optional=blank, placeholder=REQ,
                help="The pressure on the liquid surface in the suction vessel. For a tank open to the atmosphere this is 0 as a gauge pressure. Choose below whether your number is gauge or absolute.")
        basis_txt = n1.radio("The vessel pressure is", ["Gauge pressure", "Absolute pressure"], horizontal=True, key=K("pp_psb"),
                             help="NPSH needs ABSOLUTE pressure. A gauge pressure is converted by adding the atmospheric pressure. Mixing the two up is the most common NPSH mistake.")
        basis = "gauge" if basis_txt.startswith("Gauge") else "absolute"
        patm = ui("Atmospheric pressure", "pressure", 101.325, K("pp_patm"), min_value=0.0, container=n1, optional=blank, placeholder="101.325",
                  disabled=basis == "absolute", help="Used only to convert a gauge reading to absolute. Sea level is 101.325 kPa; it is lower at altitude.")
        level = ui("Liquid level above the pump", "head", 3.0, K("pp_zl"), container=n2, optional=blank, placeholder=REQ,
                   help="The height of the liquid surface above the pump centreline. Enter a negative number if the liquid is below the pump (a suction lift).")
        hfs = ui("Suction line friction losses", "head", 0.5, K("pp_hfs"), min_value=0.0, container=n2, optional=blank, placeholder="0",
                 help="The head lost to friction and fittings in the SUCTION line only (from the vessel to the pump inlet), in metres of liquid.")
        n3, n4 = st.columns(2)
        pv = ui("Vapor pressure of the liquid (absolute)", "pressure", None, K("pp_pv"), optional=True, min_value=0.0, container=n3,
                placeholder="empty = from temperature" if fluid == "Water" else REQ,
                help="The absolute vapour pressure of the liquid at the pumping temperature, from a table or the problem. For water you can leave it empty: it is calculated from the water temperature.")
        npshr = ui("NPSH required (NPSHr)", "head", 4.0, K("pp_npshr"), min_value=0.0, container=n4, optional=blank, placeholder=REQ,
                   help="The NPSH the pump needs at this flow, from the pump data sheet or curve (metres of liquid, tested on water).")
        margin = ui("Safety margin", "head", 0.5, K("pp_mrg"), min_value=0.0, container=n4, optional=blank, placeholder="0.5",
                    help="Extra NPSH you want above NPSHr. The warning appears when NPSHa is below NPSHr plus this margin. 0.5 m is a common minimum.")
        if pv is None and fluid == "Water" and temp is not None:
            try:
                pv = pp.water_vapor_pressure_kpa(temp)
                n3.caption(f"Water at {temp:g} °C: {pv:.3f} kPa absolute (Antoine equation).")
            except InputError as e:
                n3.error(str(e))

    st.subheader("5. Pump curve and viscosity correction, optional")
    if fluid == "Water":
        st.caption("Water: pumps are rated on water, so no viscosity correction is needed. Choose 'Other liquid' above for a viscous liquid. For the pump's operating point on water use the Pump & Pipeline page.")
    else:
        pump_on = st.checkbox("Correct a pump curve for the viscosity (Hydraulic Institute method)", key=K("pp_hi"),
                              help="Pumps are rated on water. A viscous liquid lowers the flow, the head and above all the efficiency. Above roughly 10 cP the effect is usually worth checking; "
                                   "the method itself decides from the parameter B, which also depends on the pump size, head and speed.")
        if pump_on:
            st.caption("Enter the pump's WATER performance from its data sheet.")
            h1, h2 = st.columns(2)
            rpm = h1.number_input("Pump speed (rpm)", min_value=1.0, value=None if blank else 1450.0, placeholder=REQ, key=K("pp_rpm"),
                                  help="The rotational speed of the pump, for example 1450 or 2900 rpm.")
            etab = h2.number_input("Efficiency at the BEP, on water (%)", min_value=1.0, max_value=100.0, value=None if blank else 75.0, placeholder=REQ, key=K("pp_etab"),
                                   help="The best efficiency point (BEP) is where the pump is most efficient on water. Read its efficiency from the pump curve.")
            qbep = ui("BEP flow, on water", "vol_flow", 250.0, K("pp_qbep"), min_value=0.0, container=h1, optional=blank, placeholder=REQ,
                      help="The flow at the best efficiency point on the water curve. The BEP head is read from the curve you enter below.")
            stages = h2.number_input("Number of stages", min_value=1, step=1, value=None if blank else 1, placeholder="1", key=K("pp_stg"),
                                     help="Number of impellers in series. The method uses the head per stage; use 1 for a single-stage pump.") or 1
            st.caption("Water pump curve: three points (total head)")
            for i, (q0, h0) in enumerate([(0, 30), (200, 25), (300, 17)]):
                a1, a2 = st.columns(2)
                curve_pts.append((ui(f"Flow {i + 1}", "vol_flow", float(q0), K(f"pp_pq{i}"), min_value=0.0, container=a1, optional=blank, placeholder=REQ),
                                  ui(f"Head {i + 1}", "head", float(h0), K(f"pp_ph{i}"), min_value=0.0, container=a2, optional=blank, placeholder=REQ)))

fs.calculate_button()
needed = [("diameter", d_mm), ("length", length)] + ([("water temperature", temp)] if fluid == "Water" else [("density", rho), ("viscosity", mu)])
needed += [("roughness", rough)] + ([("flow or velocity", q)] if by_flow else [("available head", head)])
if npsh_on:
    needed += [("suction vessel pressure", ps), ("liquid level above the pump", level), ("vapor pressure", pv), ("NPSH required", npshr)]
    needed += [("atmospheric pressure", patm)] if basis == "gauge" else []
if pump_on:
    needed += [("pump speed", rpm), ("BEP efficiency", etab), ("BEP flow", qbep)]
    needed += [(f"curve point {i + 1}", None if None in pt else 0) for i, pt in enumerate(curve_pts)]
missing = [name for name, v in needed if v is None]
if not fs.done:
    st.info("Fill in the data above and click **Calculate** to see the solution.")
    st.stop()
if missing:
    st.warning("Still needed: " + ", ".join(missing) + ".")
    st.stop()
try:
    if by_flow:
        r = solver.solve_pipe(q, d_mm, length, rho, mu, rough, sum_k, static, dp, eta or None, led)
    else:
        r = solver.flow_from_head(head, d_mm, length, rho, mu, rough, sum_k, led)
except InputError as e:
    st.error(f"Please check the data: {e}")
    st.stop()

npsh = pump = None
npsh_err = pump_err = None
if npsh_on:
    try:
        npsh = solver.npsh_check(ps, basis, patm or 101.325, level, hfs or 0.0, pv, rho, npshr, 0.5 if margin is None else margin)
    except InputError as e:
        npsh_err = str(e)
if pump_on:
    nu_cst = mu / rho * 1e6
    try:
        pump = solver.pump_viscosity(curve_pts, qbep, etab, rpm, stages, nu_cst, rho,
                                     lambda qq: solver.system_head_curve(qq, d_mm, length, rho, mu, rough, sum_k, static, dp, led))
    except InputError as e:
        pump_err = str(e)

values = val.pipe_values(r)
if npsh:
    values["NPSH available"] = (npsh["npsha"], "m")
if pump:
    values.update({"Viscosity parameter B": (pump["b"], "-"), "Flow factor C_Q": (pump["cq"], "-"), "Efficiency factor C_eta": (pump["ceta"], "-")})
st.session_state["last_solve"] = {"title": "Pipe and Pump Solver", "values": values}
st.divider()
st.header("Solution")
for w in r["warnings"]:
    st.warning(w)
cards = [("Velocity", f"{r['v']:.3f} m/s"), ("Reynolds number", f"{r['re']:,.0f}"), ("Friction factor f", f"{r['f']:.5f}")]
fit_loss = r["hk"] + r["hle"]
if by_flow:
    cards += [("Friction pressure drop", f"{r['dp_friction_kpa']:.2f} kPa"), ("Friction head loss", f"{r['hf']:.3f} m"), ("Total head required", f"{r['head_m']:.3f} m")]
    if r["hyd_kw"] is not None:
        cards.append(("Hydraulic power", f"{r['hyd_kw']:.3f} kW"))
    if r["shaft_kw"] is not None:
        cards.append(("Shaft power", f"{r['shaft_kw']:.3f} kW"))
else:
    cards = [("Flow found", f"{r['q_m3h']:.2f} m³/h")] + cards + [("Friction head loss", f"{r['hf']:.3f} m"), ("Fittings head loss", f"{fit_loss:.3f} m")]

if npsh:
    cards += [("NPSH available", f"{npsh['npsha']:.2f} m"), ("NPSH required", f"{npsh['npshr']:g} m"), ("NPSHa minus NPSHr", f"{npsh['excess']:+.2f} m")]
if pump:
    cards += [("Viscosity parameter B", f"{pump['b']:.2f}"), ("Flow factor C_Q", f"{pump['cq']:.4f}"), ("Efficiency factor C_η", f"{pump['ceta']:.4f}"),
              ("BEP flow, viscous", f"{pump['q_bep_visc']:.1f} m³/h"), ("BEP head, viscous", f"{pump['h_bep_visc']:.2f} m"),
              ("BEP efficiency, viscous", f"{pump['eta_bep_visc_pct']:.1f} %")]
    if pump["visc_op"]:
        cards += [("Operating flow, corrected curve", f"{pump['visc_op']['q']:.1f} m³/h"), ("Operating head, corrected curve", f"{pump['visc_op']['h']:.2f} m")]
given = [("Pipe inside diameter", d_mm, "mm"), ("Pipe length", length, "m"), ("Roughness", rough, "mm"), ("Density", rho, "kg/m³"), ("Viscosity", mu * 1000, "mPa·s")]
for label, value, unit in (("ΣK", sum_k, ""), ("Le/D", led, "")):
    if value:
        given.append((label, value, unit))
if npsh:
    given += [("Suction vessel pressure (" + basis + ")", ps, "kPa"), ("Liquid level above the pump", level, "m"), ("Suction friction loss", hfs or 0.0, "m"),
              ("Vapor pressure", pv, "kPa"), ("NPSH required", npshr, "m"), ("Safety margin", 0.5 if margin is None else margin, "m")]
if pump:
    given += [("Pump speed", rpm, "rpm"), ("BEP flow (water)", qbep, "m³/h"), ("BEP efficiency (water)", etab, "%"), ("Stages", stages, ""), ("Kinematic viscosity", mu / rho * 1e6, "cSt")]
if by_flow:
    given.append(("Flow", q, "m³/h"))
    for label, value, unit in (("Static head", static, "m"), ("Pressure difference", dp, "kPa"), ("Pump efficiency", eta, "%")):
        if value:
            given.append((label, value, unit))
else:
    given.append(("Available head", head, "m"))
extra_warn = (list(pump["warnings"]) if pump else []) + (list(npsh["warnings"]) if npsh else []) + ([f"NPSH: {npsh_err}"] if npsh_err else []) + ([f"Viscosity correction: {pump_err}"] if pump_err else [])
if npsh and npsh["status"] != "ok":
    extra_warn.insert(0, f"Cavitation Risk! NPSHa = {npsh['npsha']:.2f} m is below NPSHr + margin = {npsh['needed']:g} m.")
text = build_text("Pipe and Pump Solver", [mode, minor], given, cards, r["warnings"] + extra_warn)

head_col, copy_col = st.columns([3, 2])
head_col.subheader("Answers")
with copy_col:
    show_copy_button(text)
for i in range(0, len(cards), 4):
    for col, (label, value) in zip(st.columns(4), cards[i:i + 4]):
        col.metric(label, value)
with st.expander("Show results as text (copy icon at the top right of the box)"):
    st.code(text, language=None)

if npsh_err:
    st.error(f"NPSH could not be calculated: {npsh_err}")
if npsh:
    if npsh["status"] == "ok":
        st.success(f"No cavitation risk: NPSHa = {npsh['npsha']:.2f} m is at least NPSHr + safety margin = {npsh['needed']:g} m.")
    else:
        where = "below NPSHr" if npsh["status"] == "cavitation" else "above NPSHr but inside the safety margin"
        st.error(f"Cavitation Risk! NPSHa = {npsh['npsha']:.2f} m is {where} (NPSHr + margin = {npsh['needed']:g} m). "
                 "Raise the liquid level or the suction pressure, shorten or enlarge the suction line, lower the liquid temperature, or choose a pump with a lower NPSHr.")
    for w in npsh["warnings"]:
        st.warning(w)
if pump_err:
    st.error(f"The viscosity correction could not be applied: {pump_err}")
if pump:
    if not pump["applies"]:
        st.info(f"The viscosity parameter B = {pump['b']:.2f} is not above 1, so the effect of viscosity is negligible for this pump and no correction is applied.")
    elif mu * 1000 <= 10:
        st.info(f"The viscosity is {mu * 1000:g} cP (under the usual 10 cP rule of thumb), but B = {pump['b']:.2f} is above 1, so the standard still applies a small correction.")
    for w in pump["warnings"]:
        st.warning(w)

st.subheader("Step-by-step solution")
for n, s in enumerate(r["steps"], 1):
    st.markdown(f"**Step {n}. {s['title']}**")
    st.latex(s["formula"])
    st.write(s["working"])
if npsh:
    st.subheader("NPSH calculation")
    for n, s in enumerate(npsh["steps"], 1):
        st.markdown(f"**Step {n}. {s['title']}**")
        st.latex(s["formula"])
        st.write(s["working"])
if pump:
    st.subheader("Viscosity correction of the pump curve")
    st.caption(pump["note"])
    for n, s in enumerate(pump["steps"], 1):
        st.markdown(f"**Step {n}. {s['title']}**")
        st.latex(s["formula"])
        st.write(s["working"])
    st.dataframe(pd.DataFrame([{"Q / Q_BEP": t["ratio"], "Flow, water (m³/h)": t["q_water"], "Head, water (m)": t["h_water"], "Head factor C_H": t["ch"],
                                "Flow, viscous (m³/h)": t["q_visc"], "Head, viscous (m)": t["h_visc"]} for t in pump["table"]]).round(3), hide_index=True, width="stretch")
    fig = go.Figure()
    fig.add_scatter(x=pump["water_curve"][0], y=pump["water_curve"][1], name="Pump curve on water", line=dict(color="#13A89E", width=3))
    fig.add_scatter(x=pump["visc_curve"][0], y=pump["visc_curve"][1], name="Corrected for viscosity", line=dict(color="#D64550", width=3, dash="dash"))
    q_sys = [i * max(pump["water_curve"][0]) * 1.15 / 40 for i in range(41)]
    fig.add_scatter(x=q_sys, y=[solver.system_head_curve(x, d_mm, length, rho, mu, rough, sum_k, static, dp, led) for x in q_sys], name="System curve (this liquid)", line=dict(color="#0B2545", width=3))
    for key, label, color in (("water_op", "Operating point, water curve", "#13A89E"), ("visc_op", "Operating point, corrected curve", "#D64550")):
        if pump[key]:
            fig.add_scatter(x=[pump[key]["q"]], y=[pump[key]["h"]], mode="markers", name=label, marker=dict(color=color, size=12, line=dict(color="white", width=2)))
    fig.update_layout(xaxis_title="Flow (m³/h)", yaxis_title="Head (m)", template="plotly_white", legend=dict(orientation="h", y=1.15), margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")
    st.caption("The corrected curve stops at 1.2 times the BEP flow, the limit of the method. Efficiency is corrected at the BEP only, because a single BEP efficiency is entered.")
st.subheader("Assumptions used")
for a in r["assumptions"]:
    st.write(f"- {a}")

st.subheader("How the fluid flows")
if by_flow:
    html = animation.animated_pipe_html(q, r["v"], d_mm, length, sum_k, static, r["head_m"], r["shaft_kw"], r["re"], has_pump=True, equiv_len_d=led)
else:
    html = animation.animated_pipe_html(r["q_m3h"], r["v"], d_mm, length, sum_k, head, None, None, r["re"], has_pump=False, static_label="Available head", equiv_len_d=led)
animation.show(html, animation.PIPE_HEIGHT)
