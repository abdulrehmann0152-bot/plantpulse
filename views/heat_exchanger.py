import streamlit as st
import plotly.graph_objects as go
from calc_engine import heat_exchanger as hx
from core.unit_ui import unit_input as ui

NAVY, BLUE, RED = "#0B2545", "#2F6DA8", "#D64550"
st.title("🌡️ Heat Exchanger")
st.caption("Performance calculator: duty, LMTD, U value and fouling.")

FLOWS = {"Counter-flow": "counter", "Parallel flow": "parallel",
         "1 shell pass / 2 tube passes": "shell_1_2"}

with st.sidebar:
    st.header("Inputs")
    st.caption("Type each number as your problem gives it, then pick its unit.")
    flow_label = st.selectbox("Flow arrangement", list(FLOWS))
    st.subheader("Hot side")
    m_h = ui("Mass flow", "mass_flow", 1.5, "mh", min_value=0.0, step=0.1)
    cp_h = ui("Cp", "cp", 4.18, "cph", min_value=0.0, step=0.01)
    th_in = ui("Inlet temperature", "temp", 100.0, "thi")
    th_out = ui("Outlet temperature", "temp", 60.0, "tho")
    st.subheader("Cold side")
    m_c = ui("Mass flow", "mass_flow", 2.0, "mc", min_value=0.0, step=0.1)
    cp_c = ui("Cp", "cp", 4.18, "cpc", min_value=0.0, step=0.01)
    tc_in = ui("Inlet temperature", "temp", 20.0, "tci")
    tc_out = ui("Outlet temperature", "temp", 50.0, "tco")
    st.subheader("Exchanger")
    area = ui("Heat transfer area", "area", 10.0, "hx_area", min_value=0.0, step=0.5)
    know_clean = st.checkbox("I know the clean (design) U", key="hx_know")
    u_clean = ui("Clean U", "u_coeff", 800.0, "hx_uc", min_value=0.0, step=10.0) if know_clean else None

try:
    r = hx.analyze(m_h, cp_h * 1000, th_in, th_out, m_c, cp_c * 1000, tc_in, tc_out,
                   area, FLOWS[flow_label], u_clean)
except hx.InputError as e:
    st.error(f"Please check your readings: {e}")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Heat duty Q", f"{r['q_avg'] / 1000:,.1f} kW")
c2.metric("LMTD", f"{r['lmtd']:.2f} K")
c3.metric("Correction factor F", f"{r['f']:.3f}")
c4.metric("Overall U", f"{r['u']:,.1f} W/m².K")

if r["mismatch_pct"] > 5:
    st.warning(f"Heat balance mismatch is {r['mismatch_pct']:.1f}% between hot and cold side. "
               "Check flow, Cp or temperature readings (instrument error or heat loss).")
else:
    st.success(f"Heat balance is consistent (mismatch {r['mismatch_pct']:.1f}%).")

if r["rf"] is not None:
    d1, d2 = st.columns(2)
    d1.metric("Fouling resistance Rf", f"{r['rf']:.6f} m².K/W")
    d2.metric("U lost vs clean", f"{r['u_loss_pct']:.1f} %")
    if r["u_loss_pct"] > 25:
        st.error("U has dropped more than 25% from clean. Fouling is likely; plan cleaning.")
    elif r["u_loss_pct"] > 10:
        st.warning("U has dropped more than 10% from clean. Watch the trend.")

tab1, tab2 = st.tabs(["Temperature profile", "Step-by-step solution"])
with tab1:
    n = 21
    xs = [i / (n - 1) for i in range(n)]
    hot = [th_in - (th_in - th_out) * x for x in xs]
    if FLOWS[flow_label] == "parallel":
        cold = [tc_in + (tc_out - tc_in) * x for x in xs]
    else:
        cold = [tc_out - (tc_out - tc_in) * x for x in xs]
    fig = go.Figure()
    fig.add_scatter(x=xs, y=hot, name="Hot fluid", line=dict(color=RED, width=3))
    fig.add_scatter(x=xs, y=cold, name="Cold fluid", line=dict(color=BLUE, width=3))
    fig.update_layout(xaxis_title="Fraction of heat transferred (from the hot inlet end)",
                      yaxis_title="Temperature (°C)", template="plotly_white",
                      legend=dict(orientation="h", y=1.1), margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")
    st.caption("With constant Cp, both temperatures change linearly with heat transferred.")
with tab2:
    st.markdown("**1. Heat duty**")
    st.latex(r"Q = \dot m\,C_p\,\Delta T")
    st.write(f"Hot: {m_h} × {cp_h * 1000:,.0f} × {abs(th_in - th_out):g} = {r['q_hot'] / 1000:,.2f} kW")
    st.write(f"Cold: {m_c} × {cp_c * 1000:,.0f} × {abs(tc_out - tc_in):g} = {r['q_cold'] / 1000:,.2f} kW")
    st.markdown("**2. Log mean temperature difference**")
    st.latex(r"LMTD = \dfrac{\Delta T_1 - \Delta T_2}{\ln(\Delta T_1/\Delta T_2)}")
    st.write(f"LMTD = {r['lmtd']:.2f} K" + (f", F = {r['f']:.3f}" if r['f'] != 1 else ""))
    st.markdown("**3. Overall heat transfer coefficient**")
    st.latex(r"U = \dfrac{Q}{A\,F\,LMTD}")
    st.write(f"U = {r['q_avg']:,.0f} / ({area:g} × {r['f']:.3f} × {r['lmtd']:.2f}) = {r['u']:,.1f} W/m².K")
    if r["rf"] is not None:
        st.markdown("**4. Fouling resistance**")
        st.latex(r"R_f = \dfrac{1}{U_{fouled}} - \dfrac{1}{U_{clean}}")
        st.write(f"Rf = 1/{r['u']:,.1f} − 1/{u_clean:g} = {r['rf']:.6f} m².K/W")
