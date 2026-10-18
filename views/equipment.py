import pandas as pd
import streamlit as st
from core import db
from core.unit_ui import unit_input as ui
from core.templates import TEMPLATES, MATERIALS, FLOW_LABELS

user = st.session_state["user"]
st.title("🗂️ My Equipment")
st.caption("Register your heat exchangers and pumps once. Trends and alerts will use these records.")
if user["id"] is None:
    st.info("You are using PlantPulse as a guest. Create an account to save equipment.")
    st.stop()


def summary(e):
    p = e["params"]
    if e["eq_type"] == "heat_exchanger":
        return f"A = {p['area_m2']:g} m², clean U = {p['u_clean']:g} W/m²K, {FLOW_LABELS[p['flow']]}"
    return f"D = {p['d_mm']:g} mm, L = {p['length_m']:g} m, static head = {p['static_m']:g} m, η = {p['eta_pct']:g}%"


items = db.list_equipment(user["id"])
if items:
    st.dataframe(pd.DataFrame([{"Tag": e["tag"], "Type": "Heat exchanger" if e["eq_type"] == "heat_exchanger" else "Pump & pipeline",
                                "Location": e["location"], "Key data": summary(e), "Added": e["created_at"][:10]} for e in items]),
                 hide_index=True, width="stretch")
else:
    st.info("No equipment yet. Add your first one below. The examples are only starting values.")

st.subheader("Add equipment")
tmpl_name = st.selectbox("Start from", list(TEMPLATES), key="eq_tmpl")
t = TEMPLATES[tmpl_name]
kind = st.radio("Equipment type", ["Heat exchanger", "Pump & pipeline"], horizontal=True,
                index=0 if t["eq_type"] == "heat_exchanger" else 1, key=f"eq_kind_{tmpl_name}")
is_hx = kind == "Heat exchanger"
pd_ = t["params"] if (t["eq_type"] == "heat_exchanger") == is_hx else None
if pd_ is None:
    from core.templates import HX_DEFAULT, PUMP_DEFAULT
    pd_ = HX_DEFAULT if is_hx else PUMP_DEFAULT
k = f"{tmpl_name}_{kind}"
with st.form("add_equipment"):
    c1, c2 = st.columns(2)
    tag = c1.text_input("Equipment tag", t["tag"], key=f"eq_tag_{k}")
    loc = c2.text_input("Location / service", t["location"], key=f"eq_loc_{k}")
    st.caption("Type each number as it appears on the datasheet, then pick its unit. Values are stored in SI units.")
    if is_hx:
        a, b, c = st.columns(3)
        area = ui("Heat transfer area", "area", float(pd_["area_m2"]), f"eq_a_{k}", min_value=0.0, container=a, show_si=False)
        uc = ui("Clean U", "u_coeff", float(pd_["u_clean"]), f"eq_u_{k}", min_value=0.0, container=b, show_si=False)
        flow = c.selectbox("Flow arrangement", list(FLOW_LABELS), format_func=FLOW_LABELS.get,
                           index=list(FLOW_LABELS).index(pd_["flow"]), key=f"eq_f_{k}")
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
        params = {"d_mm": dm, "length_m": ln, "material": mat, "sum_k": sk,
                  "static_m": st_h, "curve": curve, "eta_pct": eta}
        positive = [dm, ln]
    if st.form_submit_button("Save equipment", key="eq_save"):
        if any(v <= 0 for v in positive):
            st.error("Area, U, diameter and length must be greater than zero.")
            st.stop()
        try:
            db.add_equipment(user["id"], "heat_exchanger" if is_hx else "pump", tag, loc, params)
            st.rerun()
        except db.DBError as e:
            st.error(str(e))

if items:
    st.subheader("Remove equipment")
    labels = {f"{e['tag']} ({e['location'] or 'no location'})": e["id"] for e in items}
    pick = st.selectbox("Choose equipment", list(labels), key="eq_del_pick")
    if st.button("Delete selected equipment", key="eq_del"):
        db.delete_equipment(user["id"], labels[pick])
        st.rerun()
