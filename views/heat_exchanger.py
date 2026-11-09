import streamlit as st
from calc_engine import heat_exchanger as hx
from calc_engine import hx_explain
from core import hx_plot, step_view
from core.unit_ui import unit_input as ui

st.title("🌡️ Heat Exchanger")
st.caption("Performance calculator: duty, LMTD, U value and fouling.")

FLOWS = {"Counter-flow": "counter", "Parallel flow": "parallel",
         "1 shell pass / 2 tube passes": "shell_1_2"}

with st.sidebar:
    st.header("Inputs")
    st.caption("Type each number as your problem gives it, then pick its unit. Hover the ? icons for ranges and meaning.")
    flow_label = st.selectbox("Flow arrangement", list(FLOWS), key="hx_flow",
                              help="Counter-flow: the fluids move in opposite directions (most effective, F = 1). Parallel flow: both move the same way (smaller LMTD, and the cold outlet can never be hotter than the hot outlet). "
                                   "1 shell pass / 2 tube passes: the common shell-and-tube layout; its LMTD is corrected by F, calculated from R and P. "
                                   "Some temperatures are impossible in some arrangements; the app tells you when a temperature cross occurs.")
    st.subheader("Hot side")
    m_h = ui("Mass flow", "mass_flow", 1.5, "mh", min_value=0.0, step=0.1,
             help="Mass flow rate of the hot stream. Must be greater than 0. Typical process streams are about 0.1 to 50 kg/s (1 kg/s = 3,600 kg/h).")
    cp_h = ui("Cp", "cp", 4.18, "cph", min_value=0.0, step=0.01,
              help="Specific heat of the hot stream at its mean temperature. Must be greater than 0. Water is about 4.18 kJ/kg·K, most oils 1.8 to 2.5, steam about 2.0, air about 1.0.")
    th_in = ui("Inlet temperature", "temp", 100.0, "thi",
               help="Temperature of the hot stream entering. Must be above its outlet and above absolute zero (−273.15 °C). It must also be above the cold outlet in counter-flow, or heat could not flow (temperature cross).")
    th_out = ui("Outlet temperature", "temp", 60.0, "tho",
                help="Temperature of the hot stream leaving. Must be below its inlet. It must stay above the cold inlet in counter-flow, and above the cold outlet in parallel flow.")
    st.subheader("Cold side")
    m_c = ui("Mass flow", "mass_flow", 2.0, "mc", min_value=0.0, step=0.1,
             help="Mass flow rate of the cold stream. Must be greater than 0. Typical process streams are about 0.1 to 50 kg/s (1 kg/s = 3,600 kg/h).")
    cp_c = ui("Cp", "cp", 4.18, "cpc", min_value=0.0, step=0.01,
              help="Specific heat of the cold stream at its mean temperature. Must be greater than 0. Water is about 4.18 kJ/kg·K, most oils 1.8 to 2.5, air about 1.0.")
    tc_in = ui("Inlet temperature", "temp", 20.0, "tci",
               help="Temperature of the cold stream entering. Must be below its outlet. It must also be below the hot outlet in counter-flow.")
    tc_out = ui("Outlet temperature", "temp", 50.0, "tco",
                help="Temperature of the cold stream leaving. Must be above its inlet. It must stay below the hot inlet in counter-flow, and below the hot outlet in parallel flow.")
    st.subheader("Exchanger")
    area = ui("Heat transfer area", "area", 10.0, "hx_area", min_value=0.0, step=0.5,
              help="Heat transfer surface area. Must be greater than 0. Typical shell-and-tube units are about 1 to 1,000 m². Use the same area basis (outside or inside surface) as your U value.")
    know_clean = st.checkbox("I know the clean (design) U", key="hx_know",
                             help="Tick this if you know the overall U of the exchanger when it is new and clean (from the datasheet). The app then estimates the fouling resistance and the loss of U.")
    u_clean = ui("Clean U", "u_coeff", 800.0, "hx_uc", min_value=0.0, step=10.0,
                 help="Overall U when clean. Must be greater than 0. Rough textbook ranges: water to water 800 to 1,500 W/m²·K, oil to water 100 to 400, gas to gas 10 to 50. Prefer your datasheet value.") if know_clean else None
    st.subheader("Checks")
    tol = st.number_input("Heat balance tolerance (%)", min_value=0.1, max_value=20.0, value=hx.HEAT_BALANCE_TOL_PCT, step=0.5, format="%g", key="hx_tol",
                          help="Largest accepted difference between the hot-side and cold-side heat duties, as a % of their average. 1% is strict and suits textbook or laboratory data. "
                               "Field instruments are often only accurate to about 2 to 5%, so raise it for plant data. Above the tolerance the app shows a red error.")

flow_key = FLOWS[flow_label]
try:
    r = hx.analyze(m_h, cp_h * 1000, th_in, th_out, m_c, cp_c * 1000, tc_in, tc_out, area, flow_key, u_clean, balance_tol_pct=tol)
except hx.InputError as e:
    st.error(f"Please check your readings: {e}")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Heat duty Q", f"{r['q_avg'] / 1000:,.1f} kW", help="The average of the hot-side and cold-side duties.")
c2.metric("LMTD", f"{r['lmtd']:.2f} K", help="Log mean temperature difference of the chosen arrangement (counter-flow value for a multi-pass exchanger, before the F correction).")
c3.metric("Correction factor F", f"{r['f']:.3f}", help="1 for pure counter-flow and parallel flow. For one shell pass and two tube passes it is calculated from R and P with the analytical equation.")
c4.metric("Overall U", f"{r['u']:,.1f} W/m²K", help="U = Q / (A × F × LMTD), using the average of the hot-side and cold-side duties.")
if flow_key == "shell_1_2":
    st.caption(f"R = {r['r_ratio']:.3f} and P = {r['p_ratio']:.3f}. F is calculated from them with the analytical (Underwood / Bowman) equation, not read from a chart.")

bal = r["balance"]
if bal["ok"]:
    st.success(bal["message"])
else:
    st.error("⚠️ " + bal["message"])
    u_hot, u_cold = r["q_hot"] / (area * r["f"] * r["lmtd"]), r["q_cold"] / (area * r["f"] * r["lmtd"])
    st.caption(f"The overall U shown uses the average duty. Using only the hot-side duty it would be {u_hot:,.1f} W/m²K, and only the cold-side duty {u_cold:,.1f} W/m²K.")
for w in r["approach_warnings"]:
    st.warning(w)
if r["f_warning"]:
    st.warning(r["f_warning"])

if r["rf"] is not None:
    d1, d2 = st.columns(2)
    d1.metric("Fouling resistance Rf", f"{r['rf']:.6f} m²K/W")
    d2.metric("U lost vs clean", f"{r['u_loss_pct']:.1f} %")
    if r["u_loss_pct"] > 25:
        st.error("U has dropped more than 25% from clean. Fouling is likely; plan cleaning.")
    elif r["u_loss_pct"] > 10:
        st.warning("U has dropped more than 10% from clean. Watch the trend.")

tab1, tab2 = st.tabs(["Temperature profile", "Step-by-step solution"])
with tab1:
    profile = hx.temperature_profile(flow_key, th_in, th_out, tc_in, tc_out)
    st.plotly_chart(hx_plot.profile_figure(profile), width="stretch")
    st.caption("The horizontal axis is the fraction of the heat duty transferred, not the length. With constant Cp both temperatures are straight lines against heat transferred; "
               "against length they would curve (unless both streams have the same heat capacity rate).")
with tab2:
    step_view.show_steps(hx_explain.page_steps(m_h, cp_h, th_in, th_out, m_c, cp_c, tc_in, tc_out, area, flow_key, u_clean, r, tol))
