import math, os, re, sys
import pytest
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import glossary as g, heat_exchanger as hx, tutor

ROOT = os.path.dirname(os.path.dirname(__file__))
TYPES = list(tutor.PROBLEM_TYPES)

# ====================================================================== glossary: content
def test_the_five_requested_terms_are_there_and_first_in_their_own_search():
    for name in ("LMTD", "Fouling factor", "NPSH", "Darcy-Weisbach equation", "Overall heat transfer coefficient"):
        found = g.search(name)
        assert found and found[0]["term"].lower().startswith(name.lower()), name

def test_glossary_entries_are_complete_and_cross_references_resolve():
    ids = [t["id"] for t in g.GLOSSARY]
    assert len(ids) == len(set(ids)) >= 30 and {t["category"] for t in g.GLOSSARY} == set(g.CATEGORIES)
    for t in g.GLOSSARY:
        assert t["term"] and len(t["definition"]) >= 60 and t["in_app"], t["id"]
        assert t["id"] not in t["see_also"] and all(g.get_term(i) for i in t["see_also"]), t["id"]
        f = t["formula"]
        assert f.count("{") == f.count("}") and f.count(r"\left") == f.count(r"\right"), t["id"]
        assert t["definition"].rstrip().endswith("."), t["id"]
    assert g.get_term("nope") is None and g.term_names(["lmtd", "nope", "npsh"]) == [g.get_term("lmtd")["term"], g.get_term("npsh")["term"]]

def test_key_definitions_state_the_right_facts():
    d = {t["id"]: t for t in g.GLOSSARY}
    assert r"\ln" in d["lmtd"]["formula"] and "logarithmic mean" in d["lmtd"]["definition"]
    assert "U_{fouled}" in d["fouling_factor"]["formula"] and "U_{clean}" in d["fouling_factor"]["formula"] and d["fouling_factor"]["unit"] == "m²·K/W"
    assert "U\\,A" in d["overall_u"]["formula"] and d["overall_u"]["unit"] == "W/m²·K"
    assert r"\dfrac{L}{D}" in d["darcy_weisbach"]["formula"] and "square of the velocity" in d["darcy_weisbach"]["definition"]
    assert "P_v" in d["npsh"]["formula"] and "NPSHa" in d["npsh"]["definition"] and "NPSHr" in d["npsh"]["definition"] and "cavitates" in d["npsh"]["definition"]
    assert "2,300" in d["reynolds"]["definition"] and "4,000" in d["reynolds"]["definition"]
    assert "4.18" in d["specific_heat"]["definition"] and "1 cP = 1 mPa·s" in d["viscosity"]["definition"]
    assert "0.14" in d["sieder_tate"]["formula"] and "16.5" in d["hi_viscosity"]["formula"] and "P_{abs}=P_{gauge}+P_{atm}" in d["absolute_pressure"]["formula"]

# ====================================================================== glossary: search
def test_search_ranks_exact_then_prefix_then_contains_then_definition():
    assert g.search("lmtd")[0]["id"] == "lmtd" and g.search("LMTD")[0]["id"] == "lmtd" and g.search("  lmtd  ")[0]["id"] == "lmtd"
    assert g.search("npsha")[0]["id"] == "npsh" and g.search("cp")[0]["id"] == "specific_heat" and g.search("co-current")[0]["id"] == "parallel_flow"
    ranked = [t["id"] for t in g.search("foul")]
    assert ranked[0] == "fouling_factor" and "digital_twin" in ranked                       # the second only mentions fouling in its definition
    assert "npsh" in [t["id"] for t in g.search("cavitate")]

def test_search_filters_by_category_and_lists_a_to_z_without_a_query():
    allt = g.search("")
    assert len(allt) == len(g.GLOSSARY) and [t["term"].lower() for t in allt] == sorted(t["term"].lower() for t in g.GLOSSARY)
    assert g.search("", "General")[0]["id"] == "digital_twin" and len(g.search("", "General")) == 1
    assert {t["category"] for t in g.search("", "Heat exchangers")} == {"Heat exchangers"} and len(g.search("", "All")) == len(allt)
    assert g.search("pressure", "General") == [] and g.search("zzzz") == [] and g.search(None)[0]["term"].lower() == allt[0]["term"].lower()

# ====================================================================== practice problems: hints, terms, random
@pytest.mark.parametrize("kind", TYPES)
@pytest.mark.parametrize("seed", range(1, 31))
def test_every_problem_has_three_progressive_hints_that_do_not_give_the_answer(kind, seed):
    p = tutor.make_problem(kind, seed)
    assert len(p["hints"]) == 3 and all(isinstance(h, str) and len(h) > 25 for h in p["hints"]) and len(set(p["hints"])) == 3
    assert p["terms"] and all(g.get_term(i) for i in p["terms"])
    final = f"{p['answers'][-1]['value']:.4g}"
    if len(final.replace(".", "")) >= 4:
        assert final not in " ".join(p["hints"])                                            # no hint states the final answer

def test_the_first_hint_points_to_the_method_and_the_last_gives_a_value():
    for kind in TYPES:
        p = tutor.make_problem(kind, 4)
        assert not re.search(r"\d+\.\d{2,}", p["hints"][0]) and re.search(r"\d", p["hints"][2])

def test_random_mode_is_deterministic_and_covers_every_type():
    assert tutor.make_problem("random", 7) == tutor.make_problem("random", 7)
    assert {tutor.make_problem("random", s)["kind"] for s in range(1, 80)} == set(TYPES) and "random" not in tutor.PROBLEM_TYPES
    p = tutor.make_problem("random", 3)
    assert p["kind"] in TYPES and p == tutor.make_problem(p["kind"], 3)

def test_existing_problems_are_unchanged_by_the_new_types():
    p = tutor.make_problem("hx_lmtd", 2)
    assert [round(a["value"], 2) for a in p["answers"]] == [62.47, 56.39] and tutor.make_problem("foul_rf", 2)["answers"][1]["value"] == pytest.approx(20.0)

# ---- the new types, recomputed from their own prompt text with plain arithmetic
@pytest.mark.parametrize("seed", range(1, 26))
def test_counter_flow_lmtd_problem_uses_the_requested_wording_and_the_right_answer(seed):
    p = tutor.make_problem("hx_lmtd_counter", seed)
    m = re.search(r"counter-flow exchanger with Hot In: (\d+) °C, Hot Out: (\d+) °C, Cold In: (\d+) °C, Cold Out: (\d+) °C", p["prompt"].replace("**", ""))
    assert p["prompt"].startswith("Calculate the LMTD for a counter-flow exchanger with") and m
    thi, tho, tci, tco = map(float, m.groups())
    d1, d2 = thi - tco, tho - tci
    assert d1 > 0 and d2 > 0 and p["answers"][0]["value"] == pytest.approx((d1 - d2) / math.log(d1 / d2), rel=1e-12)
    assert len(p["answers"]) == 1 and f"{d1:g}" in p["hints"][2] and f"{d2:g}" in p["hints"][2]

def test_the_example_in_the_brief_has_the_expected_answer():
    assert hx.lmtd(150, 90, 25, 65, "counter") == pytest.approx(20 / math.log(85 / 65)) and hx.lmtd(150, 90, 25, 65, "counter") == pytest.approx(74.55, abs=0.01)

@pytest.mark.parametrize("seed", range(1, 26))
def test_darcy_problem_answer_matches_the_equation(seed):
    p = tutor.make_problem("darcy_head", seed)
    m = re.search(r"at \*\*([\d.]+) m/s\*\* through a pipe of \*\*(\d+) mm\*\* inside diameter and \*\*(\d+) m\*\* length. The Darcy friction factor is \*\*([\d.]+)\*\*", p["prompt"])
    v, d_mm, length, f = map(float, m.groups())
    hf = f * (length / (d_mm / 1000)) * v * v / (2 * 9.81)
    assert p["answers"][0]["value"] == pytest.approx(hf, rel=1e-12) and p["answers"][1]["value"] == pytest.approx(1000 * 9.81 * hf / 1000, rel=1e-12)
    assert "h_f = f (L/D) v²/2g" in " ".join(p["steps"]) and "Darcy-Weisbach" in p["hints"][0]

@pytest.mark.parametrize("seed", range(1, 61))
def test_npsh_problem_matches_hand_arithmetic_and_the_verdict_is_right(seed):
    p = tutor.make_problem("npsh", seed); text = p["prompt"].replace("**", "")
    t, rho, pv = map(float, re.search(r"Water at (\d+) °C \(ρ = ([\d.]+) kg/m³, vapor pressure = ([\d.]+) kPa absolute\)", text).groups())
    level_abs, side = re.search(r"The liquid level is ([\d.]+) m (above|below) the pump", text).groups()
    level = float(level_abs) * (1 if side == "above" else -1)
    hf, npshr = float(re.search(r"suction line is ([\d.]+) m", text).group(1)), float(re.search(r"NPSHr = ([\d.]+) m", text).group(1))
    npsha = (101.325 - pv) * 1000 / (rho * 9.81) + level - hf
    assert npsha > 0 and p["answers"][0]["value"] == pytest.approx(npsha, rel=1e-9) and p["answers"][1]["value"] == pytest.approx(npsha / npshr, rel=1e-9)
    verdict = p["steps"][-1]
    if npsha >= npshr + 0.5:
        assert "no cavitation risk" in verdict and "Cavitation Risk" not in verdict
    elif npsha >= npshr:
        assert "inside the 0.5 m safety margin" in verdict and "Cavitation Risk!" in verdict
    else:
        assert "will cavitate" in verdict and "Cavitation Risk!" in verdict
    assert f"{(101.325 - pv) * 1000 / (rho * 9.81):.2f}" in p["hints"][2]

def test_the_npsh_problems_include_every_kind_of_outcome():
    verdicts = {tutor.make_problem("npsh", s)["steps"][-1].split(". ", 1)[1] for s in range(1, 120)}
    assert any("no cavitation risk" in v for v in verdicts) and any("inside the 0.5 m" in v for v in verdicts) and any("will cavitate" in v for v in verdicts)

# ====================================================================== the page
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d15.db"))

def _tutor():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.button(key="do_guest").click().run()
    return at.switch_page("views/tutor.py").run()

def _infos(at):
    return [i.value for i in at.info if i.value.startswith("**Hint")]

def _md(at):
    return [m.value for m in at.markdown]

def test_tabs_and_defaults():
    at = _tutor()
    assert not at.exception and [t.label for t in at.tabs] == ["Concept library", "Practice Lab", "Explain my result"]
    labels = at.selectbox(key="pr_kind").options
    assert labels[0] == "Random (any type)" and len(labels) == 1 + len(TYPES) and "Heat exchanger: LMTD (counter-flow only)" in labels
    assert at.button(key="pr_hint").label == "Show hint (0/3)" and at.button(key="pr_solution").label == "Show solution"

def test_hints_arrive_one_at_a_time_and_a_new_problem_starts_fresh():
    at = _tutor(); prob = tutor.make_problem("random", 1)
    for n in (1, 2, 3):
        at.button(key="pr_hint").click().run()
        assert not at.exception and at.button(key="pr_hint").label == f"Show hint ({n}/3)" and len(_infos(at)) == n
        assert _infos(at)[n - 1] == f"**Hint {n}.** {prob['hints'][n - 1]}"
    assert at.button(key="pr_hint").disabled and any("last hint" in c.value for c in at.caption)
    at.button(key="pr_new").click().run()
    assert _infos(at) == [] and at.button(key="pr_hint").label == "Show hint (0/3)" and not at.button(key="pr_hint").disabled

def test_solution_button_shows_hides_and_matches_the_engine():
    at = _tutor(); prob = tutor.make_problem("random", 1)
    assert "**Worked solution**" not in _md(at)
    at.button(key="pr_solution").click().run()
    md = _md(at)
    assert "**Worked solution**" in md and "**Answers**" in md and at.button(key="pr_solution").label == "Hide solution"
    for step in prob["steps"]:
        assert f"- {step}" in md
    for a in prob["answers"]:
        assert any(m.startswith(f"- {a['label']}: **{a['value']:.4g}") for m in md)
    at.button(key="pr_solution").click().run()
    assert "**Worked solution**" not in _md(at) and at.button(key="pr_solution").label == "Show solution"

def test_the_users_example_format_appears_and_wrong_units_are_called_out():
    at = _tutor()
    at.selectbox(key="pr_kind").select("Heat exchanger: LMTD (counter-flow only)").run()
    prob = tutor.make_problem("hx_lmtd_counter", 1)
    assert prob["prompt"] in _md(at)
    key = "pr_hx_lmtd_counter_1_lmtd"
    at.text_input(key=key).input(str(prob["answers"][0]["value"] * 1000)); at.button(key="pr_check").click().run()
    assert any("far from the correct value: check your units" in e.value for e in at.error)
    at.text_input(key=key).input(f"{prob['answers'][0]['value']:.2f}"); at.button(key="pr_check").click().run()
    assert any("correct." in s.value for s in at.success)

@pytest.mark.parametrize("label", ["Random (any type)"] + list(tutor.PROBLEM_TYPES.values()))
def test_every_problem_type_has_working_hint_and_solution_buttons(label):
    at = _tutor()
    at.selectbox(key="pr_kind").select(label).run()
    assert not at.exception
    at.button(key="pr_hint").click().run(); at.button(key="pr_solution").click().run()
    assert not at.exception and len(_infos(at)) == 1 and "**Worked solution**" in _md(at)
    assert any("Related glossary terms:" in c.value for c in at.caption)

def test_concepts_view_is_unchanged_by_default_and_the_glossary_is_one_click_away():
    at = _tutor()
    assert at.radio(key="tut_view").value == "Concepts" and any("Heat duty" in e.label for e in at.expander) and not any(e.label.startswith("LMTD") for e in at.expander)
    at.radio(key="tut_view").set_value("Glossary").run()
    labels = [e.label for e in at.expander]
    assert not at.exception and len(labels) == len(g.GLOSSARY) and labels[0] == g.search("")[0]["term"]
    for name in ("LMTD", "Fouling factor", "NPSH", "Darcy-Weisbach equation", "Overall heat transfer coefficient"):
        assert any(label.startswith(name) for label in labels), name

def test_glossary_search_category_and_empty_result():
    at = _tutor(); at.radio(key="tut_view").set_value("Glossary").run()
    at.text_input(key="gl_search").input("npsh").run()
    labels = [e.label for e in at.expander]
    assert labels[0].startswith("NPSH") and len(labels) < len(g.GLOSSARY) and any("term(s)" in c.value for c in at.caption)
    at.text_input(key="gl_search").input("lmtd").run()
    assert [e.label for e in at.expander][0].startswith("LMTD") and any(r"\ln" in l.value for l in at.latex)       # an open result shows its formula
    assert any("Heat Exchanger Solver" in m for m in _md(at)) and any(c.value.startswith("See also:") for c in at.caption)
    at.text_input(key="gl_search").input("").run()
    at.radio(key="gl_cat").set_value("General").run()
    assert [e.label for e in at.expander] == ["Digital twin"]
    at.radio(key="gl_cat").set_value("All").run()
    at.text_input(key="gl_search").input("zzzzz").run()
    assert not at.exception and any("No term matches" in i.value for i in at.info) and len(at.expander) == 0
