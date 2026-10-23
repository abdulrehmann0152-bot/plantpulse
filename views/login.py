import streamlit as st
from core import db

st.title("🌡️ PlantPulse")
st.subheader("Learn it in class. Monitor it in the plant.")


def _remember(user, keep):
    """If the user asked to stay signed in, create a server-side token; app.py writes it to the browser cookie."""
    if keep:
        token = db.create_session(user["id"])
        st.session_state["session_token"] = token
        st.session_state["set_cookie"] = token


tab_in, tab_up, tab_guest = st.tabs(["Log in", "Create account", "Try as guest"])

with tab_in:
    with st.form("login_form"):
        email = st.text_input("Email", key="login_email")
        pw = st.text_input("Password", type="password", key="login_pw")
        keep_in = st.checkbox("Keep me signed in on this browser (not on a shared computer)", key="keep_in",
                              help="Stores a random sign-in code in a cookie so a page refresh does not log you out. It holds no password. Log out to remove it.")
        if st.form_submit_button("Log in", key="do_login"):
            user = db.authenticate(email, pw)
            if user:
                st.session_state["user"] = user
                _remember(user, keep_in)
                st.rerun()
            else:
                st.error("Email or password is incorrect.")

with tab_up:
    with st.form("register_form"):
        name = st.text_input("Full name", key="reg_name")
        email2 = st.text_input("Email", key="reg_email")
        role = st.radio("I am a", ["Student", "Plant engineer"], horizontal=True, key="reg_role")
        pw2 = st.text_input("Password (at least 6 characters)", type="password", key="reg_pw")
        keep_up = st.checkbox("Keep me signed in on this browser (not on a shared computer)", key="keep_up")
        if st.form_submit_button("Create account", key="do_register"):
            try:
                st.session_state["user"] = db.create_user(
                    name, email2, pw2, "student" if role == "Student" else "engineer")
                _remember(st.session_state["user"], keep_up)
                st.rerun()
            except db.DBError as e:
                st.error(str(e))

with tab_guest:
    st.write("Use every calculator without an account. Guests cannot save equipment.")
    if st.button("Continue as guest", key="do_guest"):
        st.session_state["user"] = {"id": None, "name": "Guest", "email": None, "role": "student"}
        st.rerun()
