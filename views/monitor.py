from datetime import date

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from core import db, report, units
from calc_engine import monitor as mon
from calc_engine.heat_exchanger import InputError

NAVY, TEAL, RED, AMB, GRN = "#0B2545", "#13A89E", "#D64550", "#F5A623", "#2E9E5B"
user = st.session_state["user"]
st.title("📈 Monitor & Digital Twin")
st.caption("Upload readings, compare them with the twin, and get alerts before performance is lost.")
if user["id"] is None:
    st.info("Guests cannot save readings. Log out and create an account to use the monitor.")
    st.stop()
items = db.list_equipment(user["id"])
if not items:
    st.info("Add equipment first, then come back to upload readings.")
    st.page_link("views/equipment.py", label="Go to My Equipment", icon="🗂️")
    st.stop()

NAMES = {"heat_exchanger": "Heat exchanger", "pump": "Pump & pipeline"}
by_label = {f"{e['tag']} ({NAMES[e['eq_type']]})": e for e in items}
eq = by_label[st.selectbox("Equipment", list(by_label), key="mon_eq")]
kind, params, eid = eq["eq_type"], eq["params"], eq["id"]

if "flash" in st.session_state:
    getattr(st, st.session_state["flash"][0])(st.session_state.pop("flash")[1])


def flash(level, msg):
    st.session_state["flash"] = (level, msg)
    st.rerun()


logs = db.list_logs(user["id"], eid)
with st.expander("Add readings: upload a CSV or load demo data", expanded=not logs):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Upload a CSV file**")
        st.download_button("Download CSV template", mon.template_csv(kind), file_name=f"{kind}_template.csv",
                           mime="text/csv", key=f"mon_tpl_{kind}")
        with st.expander("My file uses other units"):
            st.caption("The template uses °C, kg/s, kJ/kg·K, m³/h and m. If your plant log uses other units, pick them here and PlantPulse converts on import.")
            cats = ({"temp": "Temperatures", "mass_flow": "Mass flows", "cp": "Specific heats"} if kind == "heat_exchanger"
                    else {"vol_flow": "Flow", "head": "Head", "temp": "Water temperature"})
            chosen = {cat: st.selectbox(label, units.unit_names(cat), key=f"mon_u_{cat}_{kind}") for cat, label in cats.items()}
        up = st.file_uploader("Choose a CSV file", type=["csv"], key=f"mon_file_{eid}")
        if up is not None and st.button("Import this file", key="mon_import"):
            try:
                df, dropped = mon.parse_csv(up, kind)
                df = mon.convert_units(df, kind, chosen)
                n = db.add_logs_bulk(user["id"], eid, mon.rows_for_db(df))
                flash("success", f"Imported {n} new reading(s). Skipped {len(df) - n} already stored"
                                 + (f" and {dropped} invalid row(s)." if dropped else "."))
            except InputError as e:
                st.error(str(e))
    with c2:
        st.markdown("**Or try demo data** (synthetic, generated from the physical model)")
        scn_map = ({"Fouling builds up over 60 days": "fouling", "Clean exchanger (healthy)": "clean"} if kind == "heat_exchanger"
                   else {"Healthy pump": "healthy", "Valve throttled / line blocked": "throttled", "Worn pump": "worn"})
        scn = st.selectbox("Scenario", list(scn_map), key="mon_scn")
        if st.button("Load demo data", key="mon_demo"):
            df = (mon.demo_hx(params, scenario=scn_map[scn]) if kind == "heat_exchanger"
                  else mon.demo_pump(params, scenario=scn_map[scn]))
            n = db.add_logs_bulk(user["id"], eid, mon.rows_for_db(df, demo=True))
            flash("success", f"Loaded {n} demo reading(s).")
        if logs and st.button("Delete all readings for this equipment", key="mon_delete"):
            flash("success", f"Deleted {db.delete_logs(user['id'], eid)} reading(s).")

if not logs:
    st.info("No readings yet. Upload a CSV or load demo data above.")
    st.stop()

df = mon.df_from_logs(logs, kind)
res = mon.analyze_hx(df, params) if kind == "heat_exchanger" else mon.analyze_pump(df, params)
status, text = mon.hx_status(res) if kind == "heat_exchanger" else mon.pump_status(res)
alerts = mon.alerts_hx(res) if kind == "heat_exchanger" else mon.alerts_pump(res)
good = res[res["error"] == ""]
{"ok": st.success, "warning": st.warning, "critical": st.error, "nodata": st.info}[status](
    f"**{ {'ok': 'HEALTHY', 'warning': 'WATCH', 'critical': 'ACTION NEEDED', 'nodata': 'NO DATA'}[status] }:** {text}")
has_demo = mon.has_demo_rows(df)
if has_demo:
    st.info("This equipment includes synthetic demo readings (generated from the physical model, not plant measurements).")
st.caption(f"{len(res)} readings from {res['timestamp'].min():%d %b %Y} to {res['timestamp'].max():%d %b %Y}"
           + (f" ({len(res) - len(good)} skipped)" if len(good) < len(res) else ""))
if good.empty:
    st.dataframe(res, hide_index=True, width="stretch")
    st.stop()
last = good.iloc[-1]


def line_chart(series, ytitle, hlines=(), band=None):
    fig = go.Figure()
    for name, col, color, dash in series:
        fig.add_scatter(x=good["timestamp"], y=good[col], name=name, line=dict(color=color, width=3, dash=dash))
    for y, color, label in hlines:
        fig.add_hline(y=y, line=dict(color=color, dash="dash"), annotation_text=label, annotation_position="top left")
    fig.update_layout(yaxis_title=ytitle, template="plotly_white", legend=dict(orientation="h", y=1.12), margin=dict(t=30))
    st.plotly_chart(fig, width="stretch")


def alert_table():
    if not alerts:
        st.success("No alerts. All readings are within limits.")
        return
    a = pd.DataFrame(alerts).rename(columns={"first_seen": "First seen", "severity": "Severity", "rule": "Rule", "detail": "Details"})
    st.dataframe(a, hide_index=True, width="stretch")


if kind == "heat_exchanger":
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Latest U", f"{last['u']:,.0f} W/m²K", f"{-last['u_loss_pct']:.1f}% vs clean", delta_color="inverse")
    m2.metric("Fouling resistance Rf", f"{last['rf']:.6f} m²K/W")
    m3.metric("Duty (observed)", f"{last['q_kw']:,.0f} kW")
    m4.metric("Duty lost vs clean twin", f"{last['q_expected_kw'] - last['q_kw']:,.0f} kW", f"{last['shortfall_pct']:.1f}%", delta_color="off")
    t1, t2, t3, t4 = st.tabs(["U and fouling trend", "Twin: expected vs observed", "Alerts and actions", "Data"])
    with t1:
        u_clean = params["u_clean"]
        line_chart([("Observed U", "u", TEAL, None)], "Overall U (W/m²K)",
                   [(u_clean, GRN, "Clean U"), (u_clean * 0.9, AMB, "10% loss (watch)"), (u_clean * 0.75, RED, "25% loss (act)")])
        line_chart([("Fouling resistance Rf", "rf", NAVY, None)], "Rf (m²K/W)")
    with t2:
        st.write("The twin predicts the outlet temperatures of the **clean** exchanger at the same flows and inlets.")
        fig = go.Figure()
        fig.add_scatter(x=df["timestamp"], y=df["t_cold_out_c"], name="Observed cold outlet", line=dict(color=RED, width=3))
        fig.add_scatter(x=good["timestamp"], y=good["tc_out_expected"], name="Twin (clean) cold outlet",
                        line=dict(color=GRN, width=3, dash="dash"))
        fig.update_layout(yaxis_title="Cold outlet temperature (°C)", template="plotly_white",
                          legend=dict(orientation="h", y=1.12), margin=dict(t=30))
        st.plotly_chart(fig, width="stretch")
        line_chart([("Duty shortfall vs clean (%)", "shortfall_pct", RED, None)], "Shortfall (%)")
    with t3:
        alert_table()
        if status in ("warning", "critical"):
            st.markdown("**Suggested actions**")
            st.write(f"- Plan cleaning or inspection. The twin says the clean exchanger would deliver about "
                     f"**{last['q_expected_kw'] - last['q_kw']:,.0f} kW more** at today's flows and inlet temperatures.")
            st.write("- Check the trend of Rf: a steady rise points to fouling; a sudden jump points to a flow or instrument change.")
            st.write("- Use the Heat Exchanger calculator to test how a different flow or temperature would change U and duty.")
    with t4:
        st.dataframe(res.round({c: 3 for c in res.select_dtypes("number").columns}), hide_index=True, width="stretch")
else:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Latest flow", f"{last['flow_m3_h']:,.0f} m³/h")
    m2.metric("Latest head", f"{last['head_m']:.1f} m")
    m3.metric("Deviation from pump curve", f"{last['pump_dev_pct']:+.1f}%")
    m4.metric("Deviation from system curve", f"{last['sys_dev_pct']:+.1f}%")
    t1, t2, t3, t4 = st.tabs(["Head vs expected", "Deviation from twin", "Alerts and actions", "Data"])
    with t1:
        line_chart([("Measured head", "head_m", RED, None), ("Expected on pump curve", "h_pump_expected", TEAL, "dash"),
                    ("Expected on system curve", "h_sys_expected", NAVY, "dot")], "Head (m)")
        line_chart([("Measured flow", "flow_m3_h", TEAL, None)], "Flow (m³/h)")
    with t2:
        line_chart([("Vs pump curve (%)", "pump_dev_pct", TEAL, None), ("Vs system curve (%)", "sys_dev_pct", NAVY, None)],
                   "Deviation (%)", [(5, AMB, "+5%"), (-5, AMB, "-5%")])
        st.caption("Within ±5% is treated as normal. Pump wear shows as a negative deviation from the pump curve; "
                   "extra line resistance shows as a positive deviation from the system curve.")
    with t3:
        alert_table()
        advice = {"pump_degraded": ["Check impeller and wear rings for wear or damage.", "Check pump speed and suction conditions (strainer, NPSH).",
                                    "Compare with the datasheet curve after maintenance."],
                  "system_resistance": ["Check that discharge and suction valves are fully open as intended.", "Check strainers, filters and scaling in the line.",
                                        "Use the What-if tab on the Pump page to see the effect of valve position."]}
        if last["status"] in advice:
            st.markdown("**Possible causes to check**")
            for line in advice[last["status"]]:
                st.write(f"- {line}")
    with t4:
        st.dataframe(res.round({c: 3 for c in res.select_dtypes("number").columns}), hide_index=True, width="stretch")


st.divider()
st.subheader("📄 PDF report")
st.caption("A two-page summary for your supervisor or plant head: status, charts, alerts, actions and method.")
note = st.text_input("Data source note (optional, printed on the report)", key="mon_note",
                     placeholder="e.g. Daily log sheets, Unit 2, shift A")
try:
    pdf_bytes = report.build_report(kind, eq, res, alerts, status, text, user, note, has_demo)
    st.download_button("Download PDF report", pdf_bytes, mime="application/pdf", key="mon_pdf",
                       file_name=f"PlantPulse_{eq['tag']}_{date.today():%Y%m%d}.pdf")
except Exception as e:  # never let a report problem break the monitor page
    st.error(f"The PDF report could not be created: {e}")
