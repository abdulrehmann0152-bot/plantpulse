import streamlit as st
from core import db

user = st.session_state["user"]
st.title("👤 Account")
if user["id"] is None:
    st.info("You are using PlantPulse as a guest. Nothing is stored for guests. Create an account to save equipment, readings and notes.")
    st.stop()

info = db.storage_info()
st.write(f"**{user['name']}**  ·  {user['email']}  ·  {user['role']}")
st.caption(f"Your data is kept in: {info['kind']}.")

st.subheader("What is stored about you")
st.markdown("- Your name, email and role, and a scrambled (hashed) version of your password. The password itself is never stored.\n"
            "- The equipment, readings, maintenance notes, alert settings and validation entries you create.\n"
            "- If you tick *Keep me signed in*, a random sign-in code (only its hash is stored) for up to 14 days.")
st.caption("Use synthetic or teaching data. Please do not enter confidential plant data. The project team can technically read the database, as with any app.")

st.subheader("Delete my account")
st.warning("This permanently deletes your account and everything above. It cannot be undone. Use My Equipment's export buttons first if you want a copy.")
pw = st.text_input("Type your password to confirm", type="password", key="acc_pw")
sure = st.checkbox("I understand that this cannot be undone", key="acc_sure")
if st.button("Delete my account and all my data", key="acc_delete", type="primary", disabled=not sure):
    try:
        db.delete_account(user["id"], pw)
    except db.DBError as err:
        st.error(str(err))
    else:
        db.delete_session(st.session_state.pop("session_token", None))
        del st.session_state["user"]
        st.session_state["clear_cookie"] = True
        st.session_state["account_deleted"] = True
        st.rerun()
