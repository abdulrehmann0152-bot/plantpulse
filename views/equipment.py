from datetime import date, timedelta

import streamlit as st
from core import db
from core.equipment_export import TYPE_NAMES, equipment_csv, maintenance_csv, to_bytes
from core.equipment_tools import next_tag
from core.templates import FLOW_LABELS, HX_DEFAULT, MATERIALS, PUMP_DEFAULT, TEMPLATES
from core.unit_ui import unit_input as ui

user = st.session_state["user"]
ss = st.session_state
st.title("🗂️ My Equipment")
st.caption("Register your heat exchangers and pumps once. They are saved in the PlantPulse database, so a page refresh does not lose them. Trends and alerts use these records.")
if user["id"] is None:
    st.info("You are using PlantPulse as a guest. Create an account to save equipment.")
    st.stop()

if "eq_flash" in ss:
    st.success(ss.pop("eq_flash"))

items = db.list_equipment(user["id"])
notes = {e["id"]: db.list_maintenance(user["id"], e["id"]) for e in items}
tags = [e["tag"] for e in items]


def summary(e):
    p = e["params"]
    if e["eq_type"] == "heat_exchanger":
        return f"A = {p['area_m2']:g} m², clean U = {p['u_clean']:g} W/m²K, {FLOW_LABELS[p['flow']]}"
    return f"D = {p['d_mm']:g} mm, L = {p['length_m']:g} m, static head = {p['static_m']:g} m, η = {p['eta_pct']:g}%"


# ---------------------------------------------------------------- callbacks
def _start_clone(eid):
    ss["eq_clone"] = eid
    ss.pop("eq_confirm_del", None)


def _cancel_clone():
    ss.pop("eq_clone", None)


def _ask_delete(eid):
    ss["eq_confirm_del"] = eid


def _cancel_delete():
    ss.pop("eq_confirm_del", None)


def _do_delete(eid, tag):
    db.delete_equipment(user["id"], eid)
    ss.pop("eq_confirm_del", None)
    if ss.get("eq_clone") == eid:
        ss.pop("eq_clone", None)
    ss["eq_flash"] = f"Deleted {tag}, with its readings and maintenance notes."


def _del_note(nid):
    db.delete_maintenance(user["id"], nid)


# ---------------------------------------------------------------- export
if items:
    c1, c2, _ = st.columns([2, 2, 3])
    c1.download_button("Export equipment list (CSV)", to_bytes(equipment_csv(items, notes)), file_name=f"PlantPulse_equipment_{date.today():%Y%m%d}.csv",
                       mime="text/csv", key="eq_export", icon="📥", help="One row per piece of equipment, with its data and its latest maintenance note. Opens in Excel.")
    all_notes = db.list_all_maintenance(user["id"])
    c2.download_button("Export maintenance history (CSV)", to_bytes(maintenance_csv(all_notes)), file_name=f"PlantPulse_maintenance_{date.today():%Y%m%d}.csv",
                       mime="text/csv", key="eq_export_notes", icon="📥", disabled=not all_notes, help="Every maintenance note of every piece of equipment.")

# ---------------------------------------------------------------- the list
if items:
    st.subheader(f"Registered equipment ({len(items)})")
    for e in items:
        eid, n_notes = e["id"], notes[e["id"]]
        with st.container(border=True):
            st.markdown(f"**{e['tag']}**  ·  {TYPE_NAMES[e['eq_type']]}  ·  {e['location'] or 'no location'}")
            st.caption(f"{summary(e)}  ·  added {e['created_at'][:10]}  ·  {len(n_notes)} maintenance note(s)")
            b1, b2, _ = st.columns([1, 1, 5])
            b1.button("Clone", key=f"eq_clone_{eid}", icon="📋", on_click=_start_clone, args=(eid,),
                      help="Open the form below with this equipment's data, ready for a new tag, to add an identical unit quickly.")
            b2.button("Delete", key=f"eq_delete_{eid}", icon="🗑️", on_click=_ask_delete, args=(eid,))
            if ss.get("eq_confirm_del") == eid:
                st.warning(f"Delete {e['tag']}? Its readings and maintenance notes are deleted too. This cannot be undone.")
                y, n, _ = st.columns([2, 1, 4])
                y.button("Yes, delete permanently", key=f"eq_yes_{eid}", type="primary", on_click=_do_delete, args=(eid, e["tag"]))
                n.button("Cancel", key=f"eq_no_{eid}", on_click=_cancel_delete)
            with st.expander(f"Maintenance history ({len(n_notes)})"):
                for note in n_notes:
                    t1, t2 = st.columns([9, 1])
                    t1.markdown(f"**{note['note_date']}**")
                    t1.text(note["note"])
                    t2.button("🗑️", key=f"eq_dn_{note['id']}", on_click=_del_note, args=(note["id"],), help="Delete this note")
                if not n_notes:
                    st.caption("No notes yet. Add the first one below, for example: Cleaned tubes, or Replaced the mechanical seal.")
                with st.form(f"eq_note_form_{eid}", clear_on_submit=True):
                    nd = st.date_input("Date", value=date.today(), min_value=date(1990, 1, 1), max_value=date.today() + timedelta(days=366),
                                       format="DD/MM/YYYY", key=f"eq_nd_{eid}")
                    nt = st.text_area("Note", max_chars=db.MAX_NOTE, key=f"eq_nt_{eid}", placeholder="e.g. Cleaned tubes, replaced gasket")
                    if st.form_submit_button("Add note", key=f"eq_na_{eid}"):
                        try:
                            db.add_maintenance(user["id"], eid, nd, nt)
                            ss["eq_flash"] = f"Note added to {e['tag']}."
                            st.rerun()
                        except db.DBError as err:
                            st.error(str(err))
else:
    st.info("No equipment yet. Add your first one below. The examples are only starting values.")

# ---------------------------------------------------------------- add (or clone) equipment
st.subheader("Add equipment")
clone = next((e for e in items if e["id"] == ss.get("eq_clone")), None)
if ss.get("eq_clone") and clone is None:
    ss.pop("eq_clone", None)
if clone:
    suggestion = next_tag(clone["tag"], tags)
    st.info(f"Cloning **{clone['tag']}**: its data is copied into the form. Type a new tag (for example **{suggestion}**) and save. "
            "Its readings and maintenance notes are not copied.")
    st.button("Cancel clone", key="eq_clone_cancel", on_click=_cancel_clone)
    t = {"eq_type": clone["eq_type"], "tag": "", "location": clone["location"], "params": clone["params"]}
    tmpl_name = f"clone{clone['id']}"
else:
    suggestion = ""
    tmpl_name = st.selectbox("Start from", list(TEMPLATES), key="eq_tmpl")
    t = TEMPLATES[tmpl_name]
kind = st.radio("Equipment type", ["Heat exchanger", "Pump & pipeline"], horizontal=True, disabled=clone is not None,
                index=0 if t["eq_type"] == "heat_exchanger" else 1, key=f"eq_kind_{tmpl_name}")
is_hx = kind == "Heat exchanger"
pd_ = t["params"] if (t["eq_type"] == "heat_exchanger") == is_hx else (HX_DEFAULT if is_hx else PUMP_DEFAULT)
k = f"{tmpl_name}_{kind}"
with st.form("add_equipment"):
    c1, c2 = st.columns(2)
    tag = c1.text_input("Equipment tag", t["tag"], key=f"eq_tag_{k}", placeholder=f"e.g. {suggestion}" if suggestion else "e.g. JH-01")
    loc = c2.text_input("Location / service", t["location"], key=f"eq_loc_{k}")
    st.caption("Type each number as it appears on the datasheet, then pick its unit. Values are stored in SI units.")
    if is_hx:
        a, b, c = st.columns(3)
        area = ui("Heat transfer area", "area", float(pd_["area_m2"]), f"eq_a_{k}", min_value=0.0, container=a, show_si=False)
        uc = ui("Clean U", "u_coeff", float(pd_["u_clean"]), f"eq_u_{k}", min_value=0.0, container=b, show_si=False)
        flow = c.selectbox("Flow arrangement", list(FLOW_LABELS), format_func=FLOW_LABELS.get, index=list(FLOW_LABELS).index(pd_["flow"]), key=f"eq_f_{k}")
        params = {"area_m2": area, "u_clean": uc, "flow": flow}
        positive = [area, uc]
    else:
        a, b, c, d = st.columns(4)
        dm = ui("Diameter", "diameter", float(pd_["d_mm"]), f"eq_d_{k}", min_value=0.0, container=a, show_si=False)
        ln = ui("Length", "length", float(pd_["length_m"]), f"eq_l_{k}", min_value=0.0, container=b, show_si=False)
        mat = c.selectbox("Material", MATERIALS, index=MATERIALS.index(pd_["material"]), key=f"eq_m_{k}")
        sk = d.number_input("Fittings ΣK", 0.0, value=float(pd_["sum_k"]), key=f"eq_k_{k}")
        a, b = st.columns(2)
        st_h = ui("Static head", "head", float(pd_["static_m"]), f"eq_s_{k}", min_value=0.0, container=a, show_si=False)
        eta = b.number_input("Overall efficiency (%)", 5.0, 95.0, float(pd_["eta_pct"]), key=f"eq_e_{k}")
        st.caption("Pump curve: three datasheet points")
        curve = []
        for i, (q0, h0) in enumerate(pd_["curve"]):
            x, y = st.columns(2)
            curve.append([ui(f"Flow {i + 1}", "vol_flow", float(q0), f"eq_q{i}_{k}", min_value=0.0, container=x, show_si=False),
                          ui(f"Head {i + 1}", "head", float(h0), f"eq_h{i}_{k}", min_value=0.0, container=y, show_si=False)])
        params = {"d_mm": dm, "length_m": ln, "material": mat, "sum_k": sk, "static_m": st_h, "curve": curve, "eta_pct": eta}
        positive = [dm, ln]
    st.markdown("**Maintenance history** (optional): a first dated note")
    n1, n2 = st.columns([1, 3])
    n_date = n1.date_input("Date", value=date.today(), min_value=date(1990, 1, 1), max_value=date.today() + timedelta(days=366), format="DD/MM/YYYY", key=f"eq_d0_{k}")
    n_text = n2.text_area("Note", max_chars=db.MAX_NOTE, key=f"eq_n0_{k}", placeholder="e.g. Installed and commissioned, or Cleaned tubes")
    submitted = st.form_submit_button("Save equipment", key="eq_save")

if submitted:
    if any(v <= 0 for v in positive):
        st.error("Area, U, diameter and length must be greater than zero.")
    else:
        try:
            new_id = db.add_equipment(user["id"], "heat_exchanger" if is_hx else "pump", tag, loc, params)
        except db.DBError as err:
            st.error(str(err))
        else:
            msg = f"Saved {tag.strip()}."
            if n_text.strip():
                try:
                    db.add_maintenance(user["id"], new_id, n_date, n_text)
                    msg += " The maintenance note was added."
                except db.DBError as err:
                    msg += f" The equipment is saved, but the note was not: {err}"
            ss.pop("eq_clone", None)
            ss["eq_flash"] = msg
            st.rerun()
