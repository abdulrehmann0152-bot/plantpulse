"""Reset / example / calculate state for a solver page.

Reset works by changing the keys of every widget on the page (key -> key__1, key__2 ...), so Streamlit
treats them as brand-new, empty widgets. Version 0 keeps the plain keys.
"""
import streamlit as st


class FormState:
    def __init__(self, prefix):
        self.prefix = prefix
        ss = st.session_state
        ss.setdefault(self._k("ver"), 0)
        ss.setdefault(self._k("blank"), False)     # True after Reset: inputs start empty
        ss.setdefault(self._k("done"), True)       # False after Reset: answers hidden until Calculate

    def _k(self, name):
        return f"{self.prefix}__{name}"

    @property
    def ver(self):
        return st.session_state[self._k("ver")]

    @property
    def blank(self):
        return st.session_state[self._k("blank")]

    @property
    def done(self):
        return st.session_state[self._k("done")]

    def key(self, name):
        """Widget key for the current form version."""
        return name if self.ver == 0 else f"{name}__{self.ver}"

    def _reset(self):
        ss = st.session_state
        ss[self._k("ver")] += 1
        ss[self._k("blank")] = True
        ss[self._k("done")] = False

    def _example(self):
        ss = st.session_state
        ss[self._k("ver")] += 1
        ss[self._k("blank")] = False
        ss[self._k("done")] = True

    def _calculate(self):
        st.session_state[self._k("done")] = True

    def top_buttons(self):
        c1, c2, _ = st.columns([1, 1, 4])
        c1.button("Reset form", key=f"{self.prefix}_reset", on_click=self._reset, icon="🧹",
                  help="Clears every input and hides the answers until you click Calculate again.")
        c2.button("Load example", key=f"{self.prefix}_example", on_click=self._example, icon="📘",
                  help="Fills the form with a worked example and shows its solution.")

    def calculate_button(self):
        st.button("Calculate", key=f"{self.prefix}_calc", type="primary", on_click=self._calculate,
                  help="Solve the problem with the data above. After the first calculation the answers update as you edit.")
