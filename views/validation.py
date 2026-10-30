from datetime import date

import pandas as pd
import streamlit as st
from core import db, validation as val
import zlib

from core.validation_report import build_certificate, build_validation_pdf

user = st.session_state["user"]
st.title("✅ Validation Log")
st.caption("Record each problem you test: the textbook answer, the PlantPulse answer and the difference. This is your validation evidence for the supervisor.")
if user["id"] is None:
    st.info("Log out and create an account to keep a validation log. Guests cannot save entries.")
    st.stop()

if "flash_vl" in st.session_state:
    st.success(st.session_state.pop("flash_vl"))


def _use(value):
    st.session_state["vl_app"] = f"{value:.6g}"


with st.expander("Add a validation entry", expanded=True):
    last = st.session_state.get("last_solve")
    if last:
        st.markdown(f"**Shortcut:** use a result from your last solved problem ({last['title']}).")
        names = list(last["values"])
        pick = st.selectbox("Result", names, key="vl_pick")
        value, unit = last["values"][pick]
        st.button(f"Use {pick} = {value:.6g} {unit} as the PlantPulse answer", key="vl_use", on_click=_use, args=(value,))
    with st.form("vl_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        source = c1.text_input("Source (book, edition, page or problem number)", key="vl_source", placeholder="e.g. Cengel, Example 11-2, p. 640")
        module = c2.selectbox("Module", val.MODULES, key="vl_module")
        problem = st.text_input("Problem (short description)", key="vl_problem", placeholder="e.g. Counter-flow oil cooler, find LMTD")
        c3, c4, c5, c6 = st.columns(4)
        quantity = c3.text_input("Quantity compared", key="vl_quantity", placeholder="e.g. LMTD")
        unit_in = c4.text_input("Unit", key="vl_unit", placeholder="e.g. K")
        ref_txt = c5.text_input("Textbook answer", key="vl_ref")
        app_txt = c6.text_input("PlantPulse answer", key="vl_app")
        notes = st.text_input("Notes (optional: assumptions, rounding, F read from a chart, property values)", key="vl_notes")
        if st.form_submit_button("Save entry", key="vl_save"):
            try:
                ref, app = float(ref_txt.replace(",", "")), float(app_txt.replace(",", ""))
            except ValueError:
                st.error("Please type both answers as numbers, for example 99.67.")
            else:
                try:
                    db.add_validation(user["id"], source, module, problem, quantity, unit_in, ref, app, notes)
                    st.session_state["flash_vl"] = "Entry saved."
                    st.rerun()
                except db.DBError as e:
                    st.error(str(e))

entries = val.enrich(db.list_validation(user["id"]))
summary = val.summarize(entries)
st.subheader("Results")
if not entries:
    st.info("No entries yet. Solve a problem, then add the textbook answer and the PlantPulse answer above.")
    st.stop()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Entries", summary["n"])
m2.metric("Match (within 2%)", f"{summary['match']} of {summary['n']}")
m3.metric("Within 5%", f"{summary['match'] + summary['acceptable']} of {summary['n']}")
m4.metric("Mean absolute difference", f"{summary['mean_abs']:.2f} %" if summary["mean_abs"] is not None else "n/a")
if summary["check"]:
    st.warning(f"{summary['check']} entr{'y' if summary['check'] == 1 else 'ies'} differ by more than 5%. Check the units and the inputs first. If they are right, tell your mentor: it could be a bug.")
st.dataframe(pd.DataFrame([{"Date": e["created_at"][:10], "Source": e["source"], "Module": e["module"], "Quantity": e["quantity"], "Unit": e["unit"],
                            "Textbook": e["reference"], "PlantPulse": e["app_value"],
                            "Difference %": None if e["diff_pct"] == float("inf") else round(e["diff_pct"], 2) + 0.0, "Verdict": e["verdict"], "Notes": e["notes"]} for e in entries]),
             hide_index=True, width="stretch")
st.caption("Match: within 2%. Acceptable: within 5%. Check: above 5%. Differences of 1-2% usually come from rounding and property values.")

c1, c2 = st.columns(2)
c1.download_button("Download CSV", val.to_csv(entries), file_name=f"PlantPulse_validation_{date.today():%Y%m%d}.csv", mime="text/csv", key="vl_csv")
try:
    c2.download_button("Download PDF validation note", build_validation_pdf(entries, summary, user), mime="application/pdf", key="vl_pdf",
                       file_name=f"PlantPulse_validation_note_{date.today():%Y%m%d}.pdf")
except Exception as e:  # never let the export break the page
    c2.error(f"The PDF could not be created: {e}")

with st.expander("Validation certificate (a PDF to hand to your supervisor)"):
    st.caption("Lists each comparison with its source, the textbook answer, the PlantPulse answer and the percentage difference, with space for signatures. "
               "Entries outside the 5% tolerance are left out unless you add them.")
    labels = {e["id"]: f"{e['created_at'][:10]}  |  {e['quantity']}  |  {e['source']}  |  {val.fmt_diff(e['diff_pct'])}%  |  {e['verdict']}" for e in entries}
    within = [e["id"] for e in entries if e["verdict"] != "Check"]
    sig = zlib.crc32("_".join(str(e["id"]) for e in entries).encode()) & 0xFFFF              # a new set of entries starts with a fresh default selection
    chosen = st.multiselect("Entries to include", list(labels), default=within, format_func=labels.get, key=f"vl_cert_pick_{sig}")
    project = st.text_input("Project or course (optional)", key="vl_cert_project", placeholder="e.g. Heat and Mass Transfer, semester project")
    outside = [e for e in entries if e["id"] in chosen and e["verdict"] == "Check"]
    if outside:
        st.warning(f"{len(outside)} selected entr{'y is' if len(outside) == 1 else 'ies are'} outside the 5% tolerance. The certificate marks them as outside tolerance; it does not confirm them.")
    left_out = len(entries) - len(within)
    if left_out and len(chosen) == len(within):
        st.caption(f"{left_out} entr{'y' if left_out == 1 else 'ies'} outside the tolerance {'is' if left_out == 1 else 'are'} not selected.")
    picked = [e for e in entries if e["id"] in chosen]
    try:
        st.download_button("Generate Validation Certificate (PDF)", build_certificate(picked, user, project), mime="application/pdf", key="vl_cert", icon="📄",
                           disabled=not picked, file_name=f"PlantPulse_validation_certificate_{date.today():%Y%m%d}.pdf")
    except Exception as e:  # never let the certificate break the page
        st.error(f"The certificate could not be created: {e}")

with st.expander("Remove an entry"):
    labels = {f"{e['created_at'][:10]}: {e['quantity']} ({e['source']})": e["id"] for e in entries}
    pick = st.selectbox("Entry", list(labels), key="vl_del_pick")
    if st.button("Delete selected entry", key="vl_del"):
        db.delete_validation(user["id"], labels[pick])
        st.session_state["flash_vl"] = "Entry deleted."
        st.rerun()
