import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from calc_engine import solver
from calc_engine.heat_exchanger import InputError
from core import animation, validation as val
from core.clipboard import show_copy_button
from core.form_state import FormState
from core.results_text import build_text
from core.unit_ui import unit_input as ui

RED, BLUE = "#D64550", "#2F6DA8"
fs = FormState("sv")
K, blank = fs.key, fs.blank
st.title("🧮 Problem Solver: Heat Exchangers")
st.caption("Enter what the problem gives. PlantPulse finds everything it can and shows the theory, the assumptions and every formula step by step.")
fs.top_buttons()

with st.expander("Theory: the LMTD method (read this first)", expanded=False):
    st.markdown("""
**When to use it.** Use the LMTD method when all four terminal temperatures are known (hot in/out, cold in/out). The heat duty is then
`Q = U · A · F · LMTD`, so you can find U, the required area A, or check a flow.

**The temperature difference changes along the exchanger**, so the correct average is the *log mean*:
""")
    st.latex(r"LMTD=\dfrac{\Delta T_1-\Delta T_2}{\ln(\Delta T_1/\Delta T_2)}")
    st.markdown("""
- **Counter-flow:** ΔT₁ = T(hot in) − T(cold out), ΔT₂ = T(hot out) − T(cold in). It gives the largest LMTD, so it needs the least area.
- **Parallel flow:** ΔT₁ = T(hot in) − T(cold in), ΔT₂ = T(hot out) − T(cold out). The cold outlet can never exceed the hot outlet.
- **Multi-pass shell-and-tube:** part of the flow is parallel, so the counter-flow LMTD is multiplied by a correction factor **F** (F ≤ 1):
""")
    st.latex(r"R=\dfrac{T_{h,in}-T_{h,out}}{T_{c,out}-T_{c,in}},\qquad P=\dfrac{T_{c,out}-T_{c,in}}{T_{h,in}-T_{c,in}},\qquad \Delta T_{lm,corr}=F\cdot LMTD_{counter}")
    st.markdown("""
F depends only on R, P and the number of passes. Designers try to keep **F above about 0.75**; a lower value means the arrangement is a poor match.

**Heat balance.** With no heat loss, the hot fluid gives what the cold fluid takes:
""")
    st.latex(r"Q=\dot m_h C_{p,h}(T_{h,in}-T_{h,out})=\dot m_c C_{p,c}(T_{c,out}-T_{c,in})")
    st.markdown("**Exchanger type and F.** Choose 1-1 (pure counter-flow or parallel flow, F = 1), 1-2 (one shell pass, two tube passes) or 2-4 (two shell passes, four tube passes). "
                "For 1-2 and 2-4, PlantPulse calculates F from R and P with the standard analytical equations; a 2-4 exchanger is treated as two identical 1-2 shells in series. "
                "More shell passes bring F closer to 1. If your problem reads F from a chart, type that value in the F box and it will be used instead.")
    st.markdown("**Wall-viscosity correction (Sieder-Tate).** Viscosity changes between the bulk of the fluid and the wall, which changes the film coefficient h of that fluid:")
    st.latex(r"\phi=\left(\dfrac{\mu_{bulk}}{\mu_{wall}}\right)^{0.14}\qquad h_{corrected}=\phi\,h")
    st.markdown("The factor belongs to one fluid's film, not to U as a whole. If that film controls the overall resistance, U is multiplied by φ. "
                "If it is only a fraction x of the total resistance, then U_corr = U / (x/φ + 1 − x). PlantPulse applies the correction to a U you give, to find the required area.")
    st.markdown("**Shell side or tube side.** Which fluid is on which side does not change the LMTD, the correction factor or the duty. It decides which fluid's viscosity data you use "
                "and how the exchanger is drawn. **Tube geometry:** the area of the tubes is the outside surface, A = N·π·Dₒ·L, so a required area can be turned into a number of tubes "
                "(or a tube length), and a given tube bundle can be turned into an area.")
    st.markdown("**Equipment types.** Shell-and-tube, double-pipe and plate exchangers all use these same equations. What changes between types is the flow arrangement (and so F) and the value of U, which you supply.")

st.subheader("1. Exchanger type and sides")
arr = st.selectbox("Exchanger type", list(solver.ARRANGEMENTS), format_func=solver.ARRANGEMENTS.get, key=K("sv_arr"),
                   help="1-1 means one shell pass and one tube pass: pure counter-flow or parallel flow (F = 1). 1-2 is one shell pass with two tube passes. "
                        "2-4 is two shell passes with four tube passes (two 1-2 shells in series). For 1-2 and 2-4 PlantPulse calculates the LMTD correction factor F "
                        "automatically from R and P.")
side = st.radio("Which fluid is in the tubes?", ["Cold fluid in the tubes, hot fluid in the shell", "Hot fluid in the tubes, cold fluid in the shell"], key=K("sv_side"),
                help="This does not change the LMTD, F or the duty. It changes the diagram, which fluid your viscosity data belongs to, and how the area is read "
                     "(the tube area is the outside surface of the tubes).")
hot_in_tubes = side.startswith("Hot")

st.subheader("2. Terminal temperatures (required)")
st.caption("Type each number as your problem gives it, then pick its unit.")
c1, c2 = st.columns(2)


def temp(label, default, key, box, tip):
    return ui(label, "temp", default, K(key), container=box, optional=blank, placeholder="required", help=tip)


th_in = temp("Hot fluid inlet", 180.0, "sv_thi", c1, "Temperature of the hot stream entering the exchanger.")
th_out = temp("Hot fluid outlet", 120.0, "sv_tho", c1, "Temperature of the hot stream leaving the exchanger. It must be below the hot inlet.")
tc_in = temp("Cold fluid inlet", 30.0, "sv_tci", c2, "Temperature of the cold stream entering the exchanger.")
tc_out = temp("Cold fluid outlet", 70.0, "sv_tco", c2, "Temperature of the cold stream leaving the exchanger. It must be above the cold inlet.")

st.subheader("3. Optional data (leave empty when unknown)")
st.caption("Leave exactly what you want to find empty. For example, leave the cold flow empty to find it from the heat balance, or leave the area empty to find the required area.")
ss = st.session_state
lock_flows = bool(ss.get(K("sv_q")))                                           # a duty is entered: flows would conflict with it
lock_q = (not lock_flows) and bool(ss.get(K("sv_mh")) or ss.get(K("sv_mc")))   # a flow is entered: a duty would conflict with it
o1, o2, o3 = st.columns(3)
opt = lambda label, cat, key, box, tip, locked=False: ui(label, cat, None, K(key), optional=True, min_value=0.0, container=box, help=tip, disabled=locked)
m_hot = opt("Hot flow", "mass_flow", "sv_mh", o1, "Mass flow rate of the hot stream. With its Cp it gives the heat duty, Q = m·Cp·ΔT. Locked while a duty Q is entered.", lock_flows)
cp_hot = opt("Hot Cp", "cp", "sv_cph", o1, "Specific heat of the hot stream (water is about 4.18 kJ/kg·K). Use the value the problem or your textbook table gives. Needed to find an unknown hot flow.")
m_cold = opt("Cold flow", "mass_flow", "sv_mc", o2, "Mass flow rate of the cold stream. Leave empty to find it from the heat balance. Locked while a duty Q is entered.", lock_flows)
cp_cold = opt("Cold Cp", "cp", "sv_cpc", o2, "Specific heat of the cold stream (water is about 4.18 kJ/kg·K). Needed to find an unknown cold flow.")
q_kw = opt("Duty Q given", "power", "sv_q", o3, "The heat transferred per unit time (for example 1.2 MW), when the problem states it. Entering it locks the flow boxes, because the duty already fixes them; "
           "you can still find an unknown flow by entering its Cp. Clear it to enter flows instead.", lock_q)
f_given = o3.number_input("F given in the problem", min_value=0.0, value=None, placeholder="empty = calculate", key=K("sv_f"),
                          help="The LMTD correction factor for multi-pass exchangers (F is 1 for pure counter-flow). Some problems give it, or tell you to read it from a chart using R and P. "
                               "Leave it empty (recommended) and PlantPulse calculates it automatically from R and P for the 1-2 and 2-4 types.")
a1, a2 = st.columns(2)
area = opt("Area A", "area", "sv_a", a1, "The heat transfer surface area of the exchanger. Leave it empty to find the required area (enter U and the heat data).")
u = opt("Overall U", "u_coeff", "sv_u", a2, "The overall heat transfer coefficient: how much heat passes through each square metre of surface per degree of temperature difference. "
        "Take it from the problem, or leave it empty to calculate it from Q = U·A·F·LMTD. If you enter U, leave the area empty to find the required area.")
if lock_flows:
    st.info("The flow boxes are locked because you entered a duty Q. Clear the duty to enter flows instead.")
elif lock_q:
    st.info("The duty box is locked because you entered a flow. Clear the flows to enter a duty instead.")
if lock_flows:
    m_hot = m_cold = None
if lock_q:
    q_kw = None

st.subheader("4. Wall-viscosity correction (optional)")
st.caption("Applies the Sieder-Tate factor to a given U, to find the required area. Fill both viscosities, or neither.")
v1, v2 = st.columns(2)
mu_bulk = ui("Bulk viscosity", "viscosity", None, K("sv_mub"), optional=True, min_value=0.0, container=v1,
             help="Viscosity of the fluid at its bulk (average) temperature, as given in the problem. 1 cP equals 1 mPa·s.")
mu_wall = ui("Wall viscosity", "viscosity", None, K("sv_muw"), optional=True, min_value=0.0, container=v2,
             help="Viscosity of the same fluid at the tube wall temperature. The factor is (bulk / wall)^0.14, so a hotter wall (lower viscosity) gives a factor above 1 for a heated fluid.")
visc_side = st.radio("These viscosities belong to the", ["Tube-side fluid", "Shell-side fluid"], horizontal=True, key=K("sv_vside"),
                     help="Pick the fluid whose bulk and wall viscosities you entered. It is only used to label the solution.")
film = st.number_input("Share of the total resistance due to that fluid's film (%)", min_value=1.0, max_value=100.0, value=None,
                       placeholder="empty = 100 (that film controls)", key=K("sv_film"),
                       help="φ strictly corrects one fluid's film coefficient. If that film is all of the resistance (or the problem applies φ to U directly), leave this empty. "
                            "If it is only part, enter the percentage of 1/U that this film represents.")
tube_fluid = "hot" if hot_in_tubes else "cold"
shell_fluid = "cold" if hot_in_tubes else "hot"
visc_label = f"the tube-side fluid ({tube_fluid})" if visc_side.startswith("Tube") else f"the shell-side fluid ({shell_fluid})"

st.subheader("5. Tube geometry (optional)")
st.caption("Turns an area into tubes. The area and U refer to the OUTSIDE surface of the tubes.")
g1, g2, g3 = st.columns(3)
tube_od = ui("Tube outside diameter", "diameter", None, K("sv_od"), optional=True, min_value=0.0, container=g1,
             help="The OUTSIDE diameter of one tube (for example 1 in, or 25.4 mm). Not the inside diameter.")
tube_len = ui("Tube length", "length", None, K("sv_tl"), optional=True, min_value=0.0, container=g2,
              help="The length of one tube (for example 4 m or 12 ft). With the outside diameter, the required area becomes a number of tubes.")
n_tubes = g3.number_input("Number of tubes", min_value=1, step=1, value=None, placeholder="empty = unknown", key=K("sv_nt"),
                          help="The number of tubes in the bundle. With the outside diameter and length it gives the installed area; with only the diameter it gives the tube length needed.")

fs.calculate_button()
required = [th_in, th_out, tc_in, tc_out]
if not fs.done:
    st.info("Fill in the data above and click **Calculate** to see the solution.")
    st.stop()
if any(v is None for v in required):
    st.warning("Enter all four temperatures first.")
    st.stop()
try:
    r = solver.solve_hx(arr, th_in, th_out, tc_in, tc_out, m_hot or None, cp_hot or None, m_cold or None, cp_cold or None,
                        q_kw or None, area or None, u or None, f_given or None, hot_side="tube" if hot_in_tubes else "shell",
                        mu_bulk=mu_bulk or None, mu_wall=mu_wall or None, visc_label=visc_label, film_share_pct=film or 100.0,
                        tube_od_mm=tube_od or None, tube_length_m=tube_len or None, n_tubes=n_tubes or None)
except InputError as e:
    st.error(f"Please check the data: {e}")
    st.stop()

st.session_state["last_solve"] = {"title": "Heat Exchanger Solver", "values": val.hx_values(r)}
st.divider()
st.header("Solution")
for w in r["warnings"]:
    st.warning(w)

cards = [("LMTD, counter-flow", f"{r['lmtd_counter']:.2f} K")]
if r["lmtd_parallel"] is not None:
    cards.append(("LMTD, parallel flow", f"{r['lmtd_parallel']:.2f} K"))
if r["R"] is not None:
    cards += [("R", f"{r['R']:.4f}"), ("P", f"{r['P']:.4f}")]
if arr.startswith("shell") or f_given:
    cards += [("Correction factor F" + (" (given)" if f_given else ""), f"{r['f_used']:.4f}"), ("Corrected LMTD", f"{r['lmtd_eff']:.2f} K")]
if r["q_kw"] is not None:
    cards.append(("Heat duty Q", f"{r['q_kw']:,.1f} kW"))
if r["m_cold"] and not m_cold:
    cards.append(("Cold flow (found)", f"{r['m_cold']:.3f} kg/s"))
if r["m_hot"] and not m_hot:
    cards.append(("Hot flow (found)", f"{r['m_hot']:.3f} kg/s"))
if r["area_required"]:
    cards.append(("Required area A", f"{r['area_required']:,.2f} m²"))
if r["area_from_tubes"]:
    cards.append(("Area of the tubes", f"{r['area_from_tubes']:,.2f} m²"))
if r["n_tubes_needed"]:
    cards.append(("Tubes needed", f"{r['n_tubes_needed']} (exact {r['n_tubes_exact']:.2f})"))
if r["tube_length_found"]:
    cards.append(("Tube length needed", f"{r['tube_length_found']:.3f} m"))
if r.get("over_surface_pct") is not None:
    cards.append(("Installed vs required area", f"{r['over_surface_pct']:+.1f} %"))
if r["phi"]:
    cards.append(("Viscosity factor φ", f"{r['phi']:.4f}"))
if r["u_corrected"]:
    cards.append(("Corrected U", f"{r['u_corrected']:,.1f} W/m²K"))
if r["u"] and not u:
    cards.append(("Overall U", f"{r['u']:,.1f} W/m²K"))

given = [("Hot fluid inlet", th_in, "°C"), ("Hot fluid outlet", th_out, "°C"), ("Cold fluid inlet", tc_in, "°C"), ("Cold fluid outlet", tc_out, "°C")]
for label, value, unit in (("Hot flow", m_hot, "kg/s"), ("Hot Cp", cp_hot, "kJ/kg·K"), ("Cold flow", m_cold, "kg/s"), ("Cold Cp", cp_cold, "kJ/kg·K"),
                           ("Duty Q", q_kw, "kW"), ("F given", f_given, ""), ("Area", area, "m²"), ("Overall U", u, "W/m²·K")):
    if value:
        given.append((label, value, unit))
for label, value, unit in (("Bulk viscosity", mu_bulk, "mPa·s"), ("Wall viscosity", mu_wall, "mPa·s"), ("Film share of resistance", film, "%"),
                           ("Tube outside diameter", tube_od, "mm"), ("Tube length", tube_len, "m"), ("Number of tubes", n_tubes, "")):
    if value:
        given.append((label, value, unit))
text = build_text("Heat Exchanger Solver", [f"Exchanger type: {solver.ARRANGEMENTS[arr]}", f"Tubes carry the {tube_fluid} fluid; the shell carries the {shell_fluid} fluid"], given, cards, r["warnings"])

head_col, copy_col = st.columns([3, 2])
head_col.subheader("Answers")
with copy_col:
    show_copy_button(text)
for i in range(0, len(cards), 4):
    cols = st.columns(4)
    for col, (label, value) in zip(cols, cards[i:i + 4]):
        col.metric(label, value)
with st.expander("Show results as text (copy icon at the top right of the box)"):
    st.code(text, language=None)

st.subheader("Step-by-step solution")
for n, s in enumerate(r["steps"], 1):
    st.markdown(f"**Step {n}. {s['title']}**")
    st.latex(s["formula"])
    st.write(s["working"])

st.subheader("Assumptions used")
for a in r["assumptions"]:
    st.write(f"- {a}")

st.subheader("How the fluids flow")
animation.show(animation.animated_hx_html(arr, th_in, th_out, tc_in, tc_out, hot_in_tubes), animation.HX_HEIGHT)
xs = [i / 20 for i in range(21)]
hot = [th_in - (th_in - th_out) * x for x in xs]
cold = ([tc_in + (tc_out - tc_in) * x for x in xs] if arr == "parallel" else [tc_out - (tc_out - tc_in) * x for x in xs])
fig = go.Figure()
fig.add_scatter(x=xs, y=hot, name="Hot fluid", line=dict(color=RED, width=3))
fig.add_scatter(x=xs, y=cold, name="Cold fluid", line=dict(color=BLUE, width=3))
fig.update_layout(xaxis_title="Fraction of heat transferred (from the hot inlet end)", yaxis_title="Temperature (°C)",
                  template="plotly_white", legend=dict(orientation="h", y=1.12), margin=dict(t=30))
st.plotly_chart(fig, width="stretch")
if arr.startswith("shell"):
    st.caption("In a multi-pass exchanger the cold stream makes two passes, so the real profile bends; the straight lines show the overall counter-flow equivalent used with the F factor.")
if r["lmtd_parallel"] is not None:
    st.dataframe(pd.DataFrame({"Arrangement": ["Counter-flow", "Parallel flow"], "LMTD (K)": [r["lmtd_counter"], r["lmtd_parallel"]]}).round(3),
                 hide_index=True, width="stretch")
