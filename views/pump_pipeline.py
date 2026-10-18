import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from calc_engine import pump_pipe as pp
from calc_engine.heat_exchanger import InputError
from core.unit_ui import unit_input as ui

NAVY, TEAL, RED, AMB = "#0B2545", "#13A89E", "#D64550", "#F5A623"
st.title("💧 Pump & Pipeline")
st.caption("System curve vs pump curve, operating point, power and energy cost. Water service.")

ROUGH = {"Commercial steel (0.045 mm)": 0.045, "Cast iron (0.26 mm)": 0.26,
         "Galvanised iron (0.15 mm)": 0.15, "PVC / drawn tubing (0.0015 mm)": 0.0015}

with st.sidebar:
    st.header("Inputs")
    st.caption("Type each number as your problem gives it, then pick its unit.")
    st.subheader("Fluid: water")
    temp = ui("Temperature", "temp", 30.0, "p_t", step=1.0)
    st.subheader("Pipeline")
    d_mm = ui("Inside diameter", "diameter", 200.0, "p_d", min_value=0.0, step=10.0)
    length = ui("Pipe length", "length", 200.0, "p_l", min_value=0.0, step=10.0)
    mat = st.selectbox("Pipe material", list(ROUGH), key="p_m")
    sum_k = st.number_input("Fittings and valves, ΣK (-)", 0.0, 500.0, 8.0, 0.5, key="p_k")
    static = ui("Static head", "head", 10.0, "p_s", min_value=0.0, step=0.5)
    st.subheader("Pump curve (3 datasheet points)")
    pts = []
    for i, (q0, h0) in enumerate([(0, 30), (200, 25), (300, 17)]):
        qi = ui(f"Flow {i + 1}", "vol_flow", float(q0), f"p_q{i}", min_value=0.0, step=10.0)
        hi = ui(f"Head {i + 1}", "head", float(h0), f"p_h{i}", min_value=0.0, step=0.5)
        pts.append((qi / 3600.0, hi))
    st.subheader("Energy")
    eta = st.number_input("Overall pump efficiency (%)", 5.0, 95.0, 70.0, 1.0, key="p_eta") / 100
    tariff = st.number_input("Electricity cost (Rs/kWh), edit to your tariff", 0.0, 500.0, 50.0, 1.0, key="p_tar")
    hours = st.number_input("Running hours per day", 0.0, 24.0, 24.0, 1.0, key="p_hr")

d, rough = d_mm / 1000.0, ROUGH[mat] / 1000.0
try:
    rho, mu = pp.water_properties(temp)
    coeffs = pp.fit_pump_curve(pts)
    q_max = max(p[0] for p in pts) * 1.5
    args = (static, d, length, rough)
    op = pp.operating_point(coeffs, *args, sum_k, rho, mu, q_max)
    p_shaft = pp.shaft_power(op["hyd_w"], eta)
except InputError as e:
    st.error(f"Please check your inputs: {e}")
    st.stop()

kwh_day = p_shaft / 1000 * hours
c1, c2, c3, c4 = st.columns(4)
c1.metric("Operating flow", f"{op['q'] * 3600:,.1f} m³/h")
c2.metric("Operating head", f"{op['h']:.2f} m")
c3.metric("Velocity", f"{op['v']:.2f} m/s")
c4.metric("Reynolds number", f"{op['re']:,.0f}", pp.flow_regime(op["re"]), delta_color="off")
c5, c6, c7, c8 = st.columns(4)
c5.metric("Friction factor f", f"{op['f']:.4f}")
c6.metric("Hydraulic power", f"{op['hyd_w'] / 1000:.2f} kW")
c7.metric("Shaft power", f"{p_shaft / 1000:.2f} kW")
c8.metric("Energy cost per day", f"Rs {kwh_day * tariff:,.0f}", f"{kwh_day:,.0f} kWh/day", delta_color="off")
if coeffs[1] + 2 * coeffs[2] * op["q"] >= 0:
    st.warning("The fitted pump curve is rising at the operating point. Check the three datasheet points.")
if op["v"] > 3:
    st.warning("Velocity above 3 m/s is high for water lines. Check the diameter or flow.")
if 2300 <= op["re"] < 4000:
    st.warning("Flow is in the transition zone, so the friction factor is uncertain.")

tab1, tab2, tab3, tab4 = st.tabs(["Curves", "Step-by-step solution", "What-if: throttle valve", "Check my readings"])

with tab1:
    qs = [i * q_max / 60 for i in range(61)]
    pump_h = [pp.pump_head(coeffs, q) for q in qs]
    sys_h = [pp.system_head(q, *args, sum_k, rho, mu) for q in qs]
    fig = go.Figure()
    fig.add_scatter(x=[q * 3600 for q in qs], y=pump_h, name="Pump curve", line=dict(color=TEAL, width=3))
    fig.add_scatter(x=[q * 3600 for q in qs], y=sys_h, name="System curve", line=dict(color=NAVY, width=3))
    fig.add_scatter(x=[op["q"] * 3600], y=[op["h"]], name="Operating point", mode="markers",
                    marker=dict(color=RED, size=14, line=dict(color="white", width=2)))
    fig.update_layout(xaxis_title="Flow (m³/h)", yaxis_title="Head (m)", template="plotly_white",
                      legend=dict(orientation="h", y=1.1), margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")
    st.caption("The pump runs where its curve crosses the system curve.")

with tab2:
    st.markdown("**1. Pump curve fit (from your 3 points)**")
    st.latex(r"H_{pump} = a + bQ + cQ^2")
    st.write(f"a = {coeffs[0]:.2f},  b = {coeffs[1]:.1f},  c = {coeffs[2]:.1f}  (Q in m³/s, H in m)")
    st.markdown("**2. Reynolds number and friction factor**")
    st.latex(r"Re = \dfrac{\rho v D}{\mu}")
    st.write(f"ρ = {rho:.1f} kg/m³, μ = {mu * 1000:.3f} mPa·s, v = {op['v']:.2f} m/s → Re = {op['re']:,.0f} ({pp.flow_regime(op['re'])})")
    st.latex(r"f = \dfrac{0.25}{\left[\log_{10}\left(\dfrac{\varepsilon}{3.7D} + \dfrac{5.74}{Re^{0.9}}\right)\right]^2}\quad\text{(Swamee-Jain)}")
    st.write(f"f = {op['f']:.4f}")
    st.markdown("**3. System curve**")
    st.latex(r"H_{sys} = H_{static} + \left(f\dfrac{L}{D} + \Sigma K\right)\dfrac{v^2}{2g}")
    st.write(f"Friction and fittings head = ({op['f']:.4f} × {length:g}/{d:.3f} + {sum_k:g}) × {op['v']:.2f}² / (2 × 9.81) = {op['head']:.2f} m")
    st.write(f"H_sys = {static:g} + {op['head']:.2f} = {static + op['head']:.2f} m  (equals pump head {op['h']:.2f} m at the operating point)")
    st.markdown("**4. Power**")
    st.latex(r"P_{hyd} = \rho g Q H \qquad P_{shaft} = P_{hyd}/\eta")
    st.write(f"P_hyd = {rho:.1f} × 9.81 × {op['q']:.4f} × {op['h']:.2f} = {op['hyd_w'] / 1000:.2f} kW → P_shaft = {p_shaft / 1000:.2f} kW at η = {eta * 100:.0f}%")

with tab3:
    st.write("A partly closed valve adds resistance (extra K). See how flow, head and power change.")
    extra = st.slider("Extra resistance added by valve, ΔK", 0, 100, 20, key="p_xk")
    try:
        op2 = pp.operating_point(coeffs, *args, sum_k + extra, rho, mu, q_max)
        ps2 = pp.shaft_power(op2["hyd_w"], eta)
        df = pd.DataFrame({"Baseline": [op["q"] * 3600, op["h"], p_shaft / 1000, kwh_day * tariff],
                           "With valve": [op2["q"] * 3600, op2["h"], ps2 / 1000, ps2 / 1000 * hours * tariff]},
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
    q_m = ui("Measured flow", "vol_flow", round(op["q"] * 3600 * 0.9, 0), "p_qm", min_value=0.0, step=5.0, container=m1)
    h_m = ui("Measured head", "head", round(pp.pump_head(coeffs, op["q"] * 0.9), 1), "p_hm", min_value=0.0, step=0.5, container=m2)
    if q_m <= 0 or h_m <= 0:
        st.warning("Enter a measured flow and head above zero.")
        st.stop()
    dg = pp.diagnose(q_m / 3600, h_m, coeffs, *args, sum_k, rho, mu)
    box = {"healthy": st.success, "check_data": st.warning}.get(dg["status"], st.error)
    box(dg["message"])
    st.dataframe(pd.DataFrame({"Expected on pump curve (m)": [dg["h_pump"]], "Expected on system curve (m)": [dg["h_sys"]],
                               "Measured (m)": [h_m], "Deviation from pump curve": [f"{dg['pump_dev'] * 100:+.1f}%"],
                               "Deviation from system curve": [f"{dg['sys_dev'] * 100:+.1f}%"]}).round(2),
                 hide_index=True, width="stretch")
    st.caption("Rule of thumb: ±5% is treated as normal. This is a screening aid, not a replacement for inspection.")
