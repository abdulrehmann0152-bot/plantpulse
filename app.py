import streamlit as st
from core import branding, clock, db, session_cookie

st.set_page_config(page_title="PlantPulse", page_icon="🌡️", layout="wide")
clock.apply_timezone()
branding.apply()
try:
    db.init_db()
except db.DBError as err:                                           # for example the hosted database is unreachable
    st.error(str(err))
    st.stop()

if "user" not in st.session_state:                                  # a page refresh starts a new session: sign in again from the cookie, if there is one
    cookie_token = session_cookie.read_token()
    restored = db.user_from_session(cookie_token) if cookie_token else None
    if restored:
        st.session_state["user"] = restored
        st.session_state["session_token"] = cookie_token

if "user" not in st.session_state:
    if st.session_state.pop("clear_cookie", False):
        session_cookie.clear_cookie()
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
        st.Page("views/account.py", title="Account", icon="👤"),
    ]
    nav = st.navigation(pages)
    with st.sidebar:
        st.caption(f"Signed in as **{user['name']}** ({user['role']})")
        storage = db.storage_info()
        st.caption(f"Storage: {storage['kind']}" + (" (temporary)" if storage["temporary"] else ""))
        if st.button("Log out", key="logout"):
            db.delete_session(st.session_state.pop("session_token", None))
            del st.session_state["user"]
            st.session_state["clear_cookie"] = True
            st.rerun()
        new_token = st.session_state.pop("set_cookie", None)
        if new_token:
            session_cookie.write_cookie(new_token)
    nav.run()
