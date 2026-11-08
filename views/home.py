import streamlit as st
from core import branding, db

user = st.session_state["user"]
branding.brand_header()
role = "Student" if user["role"] == "student" else "Plant engineer"
st.write(f"Welcome, **{user['name']}** ({role}). {branding.DESCRIPTION} Pick a module to start.")
n = len(db.list_equipment(user["id"])) if user["id"] else None
modules = [
    ("views/heat_exchanger.py", "Heat Exchanger", "🌡️", "Duty, LMTD, F, U value and fouling for given readings."),
    ("views/pump_pipeline.py", "Pump & Pipeline", "💧", "Pump curve vs system curve, operating point, power, energy cost."),
    ("views/solver.py", "HX Solver", "🧮", "Exchanger numericals: theory, every step, animated flow."),
    ("views/pipe_solver.py", "Pipe Solver", "🚰", "Pipe and pump numericals: theory, every step, animated flow."),
    ("views/tutor.py", "Study Tutor", "🎓", "Concepts, practice problems and explanations of your results."),
    ("views/monitor.py", "Monitor", "📈", "Upload readings, compare with the twin, trends, alerts, PDF report."),
    ("views/validation.py", "Validation Log", "✅", "Record textbook vs PlantPulse answers and export the evidence."),
    ("views/equipment.py", "My Equipment", "🗂️", "Log in to save equipment." if n is None else f"{n} saved item(s)."),
]
for title, row in (("Calculate and solve", 0), ("Learn, monitor and record", 4)):
    st.subheader(title)
    for col, (path, label, icon, caption) in zip(st.columns(4), modules[row:row + 4]):
        with col, st.container(border=True):
            st.page_link(path, label=label, icon=icon)
            st.caption(caption)
if user["role"] == "student":
    st.info("Tip: open the Step-by-step section on any page to see every formula with your numbers.")
else:
    st.info("Coming next: more exchanger types and the conversational AI tutor.")
