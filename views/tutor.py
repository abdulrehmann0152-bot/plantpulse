import streamlit as st
from calc_engine import glossary, tutor, monitor as mon
from core import db

user = st.session_state["user"]
st.title("🎓 Study Tutor")
st.caption("Learn heat exchangers and pumps with the same calculations the app uses. Works offline: every answer comes from "
           "PlantPulse's calculation engine and a hand-written concept library (no AI model, no internet).")
tab1, tab2, tab3 = st.tabs(["Concept library", "Practice Lab", "Explain my result"])

with tab1:
    view = st.radio("Show", ["Concepts", "Glossary"], horizontal=True, key="tut_view")
    if view == "Concepts":
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
    else:
        st.write(f"{len(glossary.GLOSSARY)} terms used in PlantPulse, each with a definition, its formula and unit, and where you meet it in the app.")
        g1, g2 = st.columns([2, 3])
        query = g1.text_input("Search the glossary", key="gl_search", placeholder="e.g. LMTD, cavitation, friction",
                              help="Searches the term names, their other names (for example 'cp' or 'npsha') and the definitions.")
        category = g2.radio("Category", ["All"] + glossary.CATEGORIES, horizontal=True, key="gl_cat")
        found = glossary.search(query, category)
        if not found:
            st.info("No term matches. Try a shorter word, or choose All.")
        else:
            st.caption(f"{len(found)} term(s)")
        for term in found:
            with st.expander(term["term"], expanded=bool(query.strip()) and len(found) <= 3):
                st.write(term["definition"])
                if term["formula"]:
                    st.latex(term["formula"])
                meta = ([f"**Unit:** {term['unit']}"] if term["unit"] else []) + ([f"**In PlantPulse:** {term['in_app']}"] if term["in_app"] else [])
                if meta:
                    st.markdown("  \n".join(meta))
                if term["see_also"]:
                    st.caption("See also: " + ", ".join(glossary.term_names(term["see_also"])))

with tab2:
    ss = st.session_state
    st.write("Random numerical problems with an answer key from the real engine. Type your answers, ask for a hint if you are stuck, then check them or open the solution.")
    labels = ["Random (any type)"] + list(tutor.PROBLEM_TYPES.values())
    chosen = st.selectbox("Problem type", labels, key="pr_kind")
    kind = "random" if chosen == labels[0] else next(k for k, v in tutor.PROBLEM_TYPES.items() if v == chosen)
    seed = ss.setdefault("pr_seed", 1)
    if st.button("New problem", key="pr_new"):
        ss["pr_seed"] = seed + 1
        st.rerun()
    prob = tutor.make_problem(kind, seed)
    pid = f"{prob['kind']}_{seed}"
    st.markdown(f"**Problem {seed}** · {prob['title']}")
    st.markdown(prob["prompt"])
    typed = {a["key"]: st.text_input(f"{a['label']} ({a['unit']})", key=f"pr_{prob['kind']}_{seed}_{a['key']}", placeholder="Type your answer")
             for a in prob["answers"]}

    hint_key, sol_key = f"pr_hint_{pid}", f"pr_sol_{pid}"
    shown, total = ss.get(hint_key, 0), len(prob["hints"])

    def _more_hint():
        ss[hint_key] = min(ss.get(hint_key, 0) + 1, total)

    def _toggle_solution():
        ss[sol_key] = not ss.get(sol_key, False)

    b1, b2, b3, _ = st.columns([1.2, 1.3, 1.3, 3])
    check = b1.button("Check my answers", key="pr_check")
    b2.button(f"Show hint ({shown}/{total})", key="pr_hint", on_click=_more_hint, disabled=shown >= total, icon="💡",
              help="Each click shows one more hint, from a nudge towards the method to an intermediate value. It never gives the final answer.")
    b3.button("Hide solution" if ss.get(sol_key) else "Show solution", key="pr_solution", on_click=_toggle_solution, icon="✅",
              help="Shows the worked solution and the answers.")
    if check:
        for a in prob["answers"]:
            raw = typed[a["key"]].strip().replace(",", "")
            try:
                ok, err = tutor.check_answer(prob, a["key"], float(raw))
            except ValueError:
                st.warning(f"{a['label']}: please type a number.")
                continue
            miss = "far from the correct value: check your units" if err > 5 else f"not quite (about {err * 100:.0f}% away). Try again, ask for a hint, or open the solution."
            (st.success if ok else st.error)(f"{a['label']}: " + ("correct." if ok else miss))
    for i in range(shown):
        st.info(f"**Hint {i + 1}.** {prob['hints'][i]}")
    if shown >= total:
        st.caption("That was the last hint. Open the solution if you are still stuck.")
    if ss.get(sol_key):
        st.markdown("**Worked solution**")
        for step in prob["steps"]:
            st.write(f"- {step}")
        st.markdown("**Answers**")
        for a in prob["answers"]:
            st.write(f"- {a['label']}: **{a['value']:.4g} {a['unit']}**".replace(" -**", "**"))
        st.caption("Answers are accepted within " + ", ".join(f"{a['label']} ±{a['tol'] * 100:.0f}%" for a in prob["answers"]) + ".")
    if prob["terms"]:
        st.caption("Related glossary terms: " + ", ".join(glossary.term_names(prob["terms"])) + ". Open the Concept library and choose Glossary.")

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
