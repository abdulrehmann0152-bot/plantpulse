from datetime import date, timedelta

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from core import chart_notes, db, importer, report, units
from calc_engine import monitor as mon
from calc_engine.heat_exchanger import InputError

NAVY, BLUE, RED, AMB, GRN = "#0B2545", "#2F6DA8", "#D64550", "#F5A623", "#2E7D4F"
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
cfg = db.get_alert_settings(user["id"], eid)
warn, crit = cfg["u_warn_pct"], cfg["u_crit_pct"]
data_notes = db.list_maintenance(user["id"], eid)

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
        n1, n2 = st.columns([1, 2])
        note_date = n1.date_input("Date of the note", value=date.today(), min_value=date(1990, 1, 1), max_value=date.today() + timedelta(days=366),
                                  format="DD/MM/YYYY", key=f"mon_nd_{eid}",
                                  help="The date the note is about, for example the day the tubes were cleaned. It is marked on the trend charts.")
        note_txt = n2.text_input("Note for this dataset (optional)", max_chars=200, key=f"mon_nt_{eid}", placeholder="e.g. After chemical cleaning",
                                 help="Tags this dataset with a note. It is saved in the equipment's maintenance history, drawn on the charts, and printed in the PDF report.")
        if up is not None and st.button("Import this file", key="mon_import"):
            try:
                df, dropped = mon.parse_csv(up, kind)
                df = mon.convert_units(df, kind, chosen)
                n, msg = importer.save_import(user["id"], eid, df, note_date, note_txt)
                flash("success", msg + f" Skipped {len(df) - n} already stored" + (f" and {dropped} invalid row(s)." if dropped else "."))
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

if kind == "heat_exchanger":
    def _reset_alerts():
        db.reset_alert_settings(user["id"], eid)
        st.session_state[f"mon_warn_{eid}"], st.session_state[f"mon_crit_{eid}"] = db.DEFAULT_U_WARN, db.DEFAULT_U_CRIT

    with st.expander(f"Alert settings: warn at {warn:g}% loss of U, alarm at {crit:g}% loss" + ("" if cfg["custom"] else " (default)")):
        st.caption("The warning level turns the status amber (WATCH); the alarm level turns it red (ACTION NEEDED). Set them for this exchanger. They also move the lines on the U chart and the alerts in the report.")
        with st.form(f"mon_alert_form_{eid}"):
            a1, a2 = st.columns(2)
            w_in = a1.number_input("Warn me at (% loss of U)", min_value=0.1, max_value=94.9, value=float(warn), step=1.0, key=f"mon_warn_{eid}",
                                   help="The loss of U below its clean value at which you want a warning. U loss = (1 - U now / U clean) x 100. For example 10 means U has fallen to 90% of clean.")
            c_in = a2.number_input("Alarm me at (% loss of U)", min_value=0.2, max_value=95.0, value=float(crit), step=1.0, key=f"mon_crit_{eid}",
                                   help="The loss at which you want an alarm. It must be higher than the warning level. For example 25 means U has fallen to 75% of clean.")
            if st.form_submit_button("Save alert settings", key=f"mon_alert_save_{eid}"):
                try:
                    db.set_alert_settings(user["id"], eid, w_in, c_in)
                    flash("success", f"Alert settings saved: warn at {w_in:g}% and alarm at {c_in:g}% loss of U.")
                except db.DBError as err:
                    st.error(str(err))
        st.button(f"Reset to the defaults ({db.DEFAULT_U_WARN:g}% and {db.DEFAULT_U_CRIT:g}%)", key=f"mon_alert_reset_{eid}", on_click=_reset_alerts, disabled=not cfg["custom"])

if not logs:
    st.info("No readings yet. Upload a CSV or load demo data above.")
    st.stop()

df = mon.df_from_logs(logs, kind)
res = mon.analyze_hx(df, params) if kind == "heat_exchanger" else mon.analyze_pump(df, params)
status, text = mon.hx_status(res, warn, crit) if kind == "heat_exchanger" else mon.pump_status(res)
alerts = mon.alerts_hx(res, warn, crit) if kind == "heat_exchanger" else mon.alerts_pump(res)
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


events = chart_notes.event_markers(data_notes, good["timestamp"].min(), good["timestamp"].max())


def mark_notes(fig):
    """Draw each note of this equipment as a dotted vertical line with its first words."""
    for ev in events:
        x = ev["date"].isoformat()
        fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, xref="x", yref="paper", line=dict(color="#6B7280", width=1, dash="dot"))
        fig.add_annotation(x=x, y=1, xref="x", yref="paper", text=ev["text"], showarrow=False, textangle=-90, xanchor="left", yanchor="top",
                           font=dict(size=10, color="#6B7280"))


def line_chart(series, ytitle, hlines=(), band=None):
    fig = go.Figure()
    for name, col, color, dash in series:
        fig.add_scatter(x=good["timestamp"], y=good[col], name=name, line=dict(color=color, width=3, dash=dash))
    for y, color, label in hlines:
        fig.add_hline(y=y, line=dict(color=color, dash="dash"), annotation_text=label, annotation_position="top left")
    mark_notes(fig)
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
        line_chart([("Observed U", "u", BLUE, None)], "Overall U (W/m²K)",
                   [(u_clean, GRN, "Clean U"), (u_clean * (1 - warn / 100), AMB, f"{warn:g}% loss (watch)"), (u_clean * (1 - crit / 100), RED, f"{crit:g}% loss (act)")])
        line_chart([("Fouling resistance Rf", "rf", NAVY, None)], "Rf (m²K/W)")
    with t2:
        st.write("The twin predicts the outlet temperatures of the **clean** exchanger at the same flows and inlets.")
        fig = go.Figure()
        fig.add_scatter(x=df["timestamp"], y=df["t_cold_out_c"], name="Observed cold outlet", line=dict(color=RED, width=3))
        fig.add_scatter(x=good["timestamp"], y=good["tc_out_expected"], name="Twin (clean) cold outlet",
                        line=dict(color=GRN, width=3, dash="dash"))
        mark_notes(fig)
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
        line_chart([("Measured head", "head_m", RED, None), ("Expected on pump curve", "h_pump_expected", BLUE, "dash"),
                    ("Expected on system curve", "h_sys_expected", NAVY, "dot")], "Head (m)")
        line_chart([("Measured flow", "flow_m3_h", BLUE, None)], "Flow (m³/h)")
    with t2:
        line_chart([("Vs pump curve (%)", "pump_dev_pct", BLUE, None), ("Vs system curve (%)", "sys_dev_pct", NAVY, None)],
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


with st.expander(f"Data notes ({len(data_notes)})"):
    st.caption("Notes about this equipment's data, for example 'After chemical cleaning'. They are marked on the charts, printed in the PDF report and kept in My Equipment under Maintenance history.")
    for n_ in data_notes[:10]:
        st.markdown(f"**{n_['note_date']}**")
        st.text(n_["note"])
    with st.form(f"mon_dn_form_{eid}", clear_on_submit=True):
        dn_date = st.date_input("Date", value=date.today(), min_value=date(1990, 1, 1), max_value=date.today() + timedelta(days=366), format="DD/MM/YYYY", key=f"mon_dn_date_{eid}")
        dn_text = st.text_area("Note", max_chars=db.MAX_NOTE, key=f"mon_dn_text_{eid}", placeholder="e.g. After chemical cleaning")
        if st.form_submit_button("Add note", key=f"mon_dn_add_{eid}"):
            try:
                db.add_maintenance(user["id"], eid, dn_date, dn_text)
                flash("success", "Note added.")
            except db.DBError as err:
                st.error(str(err))

st.divider()
st.subheader("📄 PDF report")
st.caption("A two-page summary for your supervisor or plant head: status, charts, alerts, actions and method.")
note = st.text_input("Data source note (optional, printed on the report)", key="mon_note",
                     placeholder="e.g. Daily log sheets, Unit 2, shift A")
try:
    first_day, last_day = good["timestamp"].min().date().isoformat(), good["timestamp"].max().date().isoformat()
    report_events = sorted((n_ for n_ in data_notes if first_day <= n_["note_date"] <= last_day), key=lambda n_: n_["note_date"])
    pdf_bytes = report.build_report(kind, eq, res, alerts, status, text, user, note, has_demo, thresholds=(warn, crit), events=report_events)
    st.download_button("Download PDF report", pdf_bytes, mime="application/pdf", key="mon_pdf",
                       file_name=f"PlantPulse_{eq['tag']}_{date.today():%Y%m%d}.pdf")
except Exception as e:  # never let a report problem break the monitor page
    st.error(f"The PDF report could not be created: {e}")
