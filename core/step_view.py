"""Show a worked solution step by step: governing equation, variables, substitution, intermediate calculation and result.

A step is a dict with 'title' and 'formula', and normally 'variables' and 'calc' (see calc_engine.hx_explain). A step that has no 'calc'
(an older kind of step) is shown with its one-line 'working' instead, so nothing is lost. All text comes from the engine, never from a user.
"""
import streamlit as st


def show_steps(steps):
    for n, s in enumerate(steps, 1):
        with st.container(border=True):
            st.markdown(f"**Step {n}. {s['title']}**")
            st.markdown("**Governing equation**")
            st.latex(s["formula"])
            if s.get("variables"):
                st.markdown("**Where**")
                if all(len(v) == 3 for v in s["variables"]):                         # symbol, meaning and unit: a small table
                    rows = ["| Symbol | Meaning | Unit |", "|:--|:--|:--|"] + [f"| ${sym}$ | {meaning} | {unit} |" for sym, meaning, unit in s["variables"]]
                    st.markdown("\n".join(rows))
                else:
                    st.markdown("\n".join(f"- ${sym}$: {meaning}" for sym, meaning in s["variables"]))
            if s.get("calc"):
                for c in s["calc"]:
                    lines = [f"**{c['label']}**", f"- Substitution: `{c['substitution']}`"]
                    if c.get("intermediate"):
                        lines.append(f"- Intermediate: `{c['intermediate']}`")
                    lines.append(f"- **Result: {c['result']}**")
                    st.markdown("\n".join(lines))
            else:
                st.markdown("**Calculation**")
                st.write(s["working"])
            if s.get("interpretation"):
                st.markdown(f"**Interpretation:** {s['interpretation']}")
