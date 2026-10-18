import streamlit as st
from core import db

st.title("🌡️ PlantPulse")
st.subheader("Learn it in class. Monitor it in the plant.")
tab_in, tab_up, tab_guest = st.tabs(["Log in", "Create account", "Try as guest"])

with tab_in:
    with st.form("login_form"):
        email = st.text_input("Email", key="login_email")
        pw = st.text_input("Password", type="password", key="login_pw")
        if st.form_submit_button("Log in", key="do_login"):
            user = db.authenticate(email, pw)
            if user:
                st.session_state["user"] = user
                st.rerun()
            else:
                st.error("Email or password is incorrect.")

with tab_up:
    with st.form("register_form"):
        name = st.text_input("Full name", key="reg_name")
        email2 = st.text_input("Email", key="reg_email")
        role = st.radio("I am a", ["Student", "Plant engineer"], horizontal=True, key="reg_role")
        pw2 = st.text_input("Password (at least 6 characters)", type="password", key="reg_pw")
        if st.form_submit_button("Create account", key="do_register"):
            try:
                st.session_state["user"] = db.create_user(
                    name, email2, pw2, "student" if role == "Student" else "engineer")
                st.rerun()
            except db.DBError as e:
                st.error(str(e))

with tab_guest:
    st.write("Use every calculator without an account. Guests cannot save equipment.")
    if st.button("Continue as guest", key="do_guest"):
        st.session_state["user"] = {"id": None, "name": "Guest", "email": None, "role": "student"}
        st.rerun()
