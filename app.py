import streamlit as st
from core import db

st.set_page_config(page_title="PlantPulse", page_icon="🌡️", layout="wide")
db.init_db()

if "user" not in st.session_state:
    st.navigation([st.Page("views/login.py", title="Log in", icon="🔐")]).run()
else:
    user = st.session_state["user"]
    pages = [
        st.Page("views/home.py", title="Home", icon="🏠", default=True),
        st.Page("views/heat_exchanger.py", title="Heat Exchanger", icon="🌡️"),
        st.Page("views/pump_pipeline.py", title="Pump & Pipeline", icon="💧"),
        st.Page("views/solver.py", title="Heat Exchanger Solver", icon="🧮"),
        st.Page("views/pipe_solver.py", title="Pipe and Pump Solver", icon="🚰"),
        st.Page("views/tutor.py", title="Study Tutor", icon="🎓"),
        st.Page("views/monitor.py", title="Monitor", icon="📈"),
        st.Page("views/validation.py", title="Validation Log", icon="✅"),
        st.Page("views/equipment.py", title="My Equipment", icon="🗂️"),
    ]
    nav = st.navigation(pages)
    with st.sidebar:
        st.caption(f"Signed in as **{user['name']}** ({user['role']})")
        if st.button("Log out", key="logout"):
            del st.session_state["user"]
            st.rerun()
    nav.run()
