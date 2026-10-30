import streamlit as st
from calc_engine import tutor, monitor as mon
from core import db

user = st.session_state["user"]
st.title("🎓 Study Tutor")
st.caption("Learn heat exchangers and pumps with the same calculations the app uses. Works offline: every answer comes from "
           "PlantPulse's calculation engine and a hand-written concept library (no AI model, no internet).")
tab1, tab2, tab3 = st.tabs(["Concept library", "Practice lab", "Explain my result"])

with tab1:
    topic = st.radio("Topic", ["All", "Heat exchangers", "Fluid flow and pumps"], horizontal=True, key="tut_topic")
    for c in tutor.concepts_for(topic):
        with st.expander(c["title"]):
            st.write(c["summary"])
            st.latex(c["formula"])
            st.markdown(f"**In the plant:** {c['plant']}")
            st.markdown("**Common mistakes**")
            for m in c["mistakes"]:
                st.write(f"- {m}")
            st.markdown("**Quick check**")
            chk = c["check"]
            pick = st.radio(chk["q"], chk["options"], index=None, key=f"chk_radio_{c['id']}")
            if st.button("Check answer", key=f"chk_btn_{c['id']}"):
                if pick is None:
                    st.warning("Choose an answer first.")
                elif chk["options"].index(pick) == chk["answer"]:
                    st.success(f"Correct. {chk['why']}")
                else:
                    st.error(f"Not quite. {chk['why']}")

with tab2:
    st.write("Random numerical problems with an answer key from the real engine. Type your answers, then check them.")
    labels = list(tutor.PROBLEM_TYPES.values())
    chosen = st.selectbox("Problem type", labels, key="pr_kind")
    kind = next(k for k, v in tutor.PROBLEM_TYPES.items() if v == chosen)
    seed = st.session_state.setdefault("pr_seed", 1)
    if st.button("New problem", key="pr_new"):
        st.session_state["pr_seed"] = seed + 1
        st.rerun()
    prob = tutor.make_problem(kind, seed)
    st.markdown(f"**Problem {seed}.** {prob['prompt']}")
    typed = {a["key"]: st.text_input(f"{a['label']} ({a['unit']})", key=f"pr_{kind}_{seed}_{a['key']}", placeholder="Type your answer")
             for a in prob["answers"]}
    if st.button("Check my answers", key="pr_check"):
        for a in prob["answers"]:
            raw = typed[a["key"]].strip().replace(",", "")
            try:
                ok, err = tutor.check_answer(prob, a["key"], float(raw))
            except ValueError:
                st.warning(f"{a['label']}: please type a number.")
                continue
            (st.success if ok else st.error)(f"{a['label']}: " + ("correct." if ok else f"not quite (about {err * 100:.0f}% away). Try again or open the worked solution."))
    with st.expander("Show worked solution"):
        for s in prob["steps"]:
            st.write(f"- {s}")
        st.caption("Answers are accepted within " + ", ".join(f"{a['label']} ±{a['tol'] * 100:.0f}%" for a in prob["answers"]) + ".")

with tab3:
    if user["id"] is None:
        st.info("Log in with an account to get explanations of your own equipment readings.")
    else:
        items = [e for e in db.list_equipment(user["id"])]
        if not items:
            st.info("Add equipment and load readings first (My Equipment, then Monitor).")
        else:
            names = {f"{e['tag']} ({'Heat exchanger' if e['eq_type'] == 'heat_exchanger' else 'Pump & pipeline'})": e for e in items}
            eq = names[st.selectbox("Equipment", list(names), key="tut_eq")]
            logs = db.list_logs(user["id"], eq["id"])
            if not logs:
                st.info("No readings for this equipment yet. Open Monitor to upload a CSV or load demo data.")
            else:
                df = mon.df_from_logs(logs, eq["eq_type"])
                if eq["eq_type"] == "heat_exchanger":
                    cfg = db.get_alert_settings(user["id"], eq["id"])
                    lines = tutor.explain_hx(mon.analyze_hx(df, eq["params"]), eq["params"], cfg["u_warn_pct"], cfg["u_crit_pct"])
                else:
                    lines = tutor.explain_pump(mon.analyze_pump(df, eq["params"]), eq["params"])
                if mon.has_demo_rows(df):
                    st.info("These readings include synthetic demo data.")
                for line in lines:
                    st.markdown(line)
                st.caption("Rule-based explanation of your readings. It describes what the numbers show; confirm causes by inspection.")
