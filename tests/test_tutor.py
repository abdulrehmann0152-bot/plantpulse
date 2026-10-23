import math, os, sys
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import tutor as t, monitor as m, heat_exchanger as hx, pump_pipe as pp
from core.templates import TEMPLATES

HXP = TEMPLATES["Sugar mill juice heater (example)"]["params"]
PUMPP = TEMPLATES["Cooling-water pump loop (example)"]["params"]

def test_concepts_are_well_formed():
    ids = [c["id"] for c in t.CONCEPTS]
    assert len(ids) == len(set(ids)) >= 10
    for c in t.CONCEPTS:
        assert c["formula"] and c["summary"] and c["plant"] and len(c["mistakes"]) >= 2
        assert 0 <= c["check"]["answer"] < len(c["check"]["options"]) and len(set(c["check"]["options"])) == len(c["check"]["options"])
    assert {c["topic"] for c in t.CONCEPTS} == {"Heat exchangers", "Fluid flow and pumps"}

def test_topic_filter():
    assert len(t.concepts_for("All")) == len(t.CONCEPTS)
    assert all(c["topic"] == "Heat exchangers" for c in t.concepts_for("Heat exchangers"))

def _opt(cid):
    c = next(x for x in t.CONCEPTS if x["id"] == cid)["check"]
    return c["options"][c["answer"]]

def test_quick_check_answers_match_the_engine():
    assert hx.heat_duty(2, 4180, 20, 50) / 1000 == pytest.approx(float(_opt("heat_duty").split()[0]))
    assert (1 - 900 / 1200) * 100 == 25  # sanity for the U-loss wording used in practice problems
    assert hx.fouling_resistance(800, 1000) == pytest.approx(float(_opt("fouling").split()[0]))
    assert hx.lmtd(100, 60, 20, 50, "counter") > hx.lmtd(100, 60, 20, 50, "parallel") and _opt("lmtd") == "Counter-flow"
    assert pp.reynolds(998, 1, 0.05, 1e-3) == pytest.approx(49900) and _opt("reynolds") == "50,000"
    assert 10 + 6 * 4 == 34 and _opt("system_curve") == "34 m"
    assert 1000 * 9.81 * 0.05 * 20 / 1000 == pytest.approx(float(_opt("pump_power").split()[0]), rel=0.01)
    assert 2 ** 2 == 4 and _opt("friction") == "4 times larger"
    # effectiveness rises less than proportionally with UA
    e1 = m.effectiveness("counter", 1.0, 0.8); e2 = m.effectiveness("counter", 2.0, 0.8)
    assert e1 < e2 < 2 * e1 and _opt("ntu").startswith("It increases")

@pytest.mark.parametrize("kind", list(t.PROBLEM_TYPES))
@pytest.mark.parametrize("seed", range(1, 26))
def test_problems_are_valid_and_self_consistent(kind, seed):
    p = t.make_problem(kind, seed)
    assert p["prompt"] and p["steps"] and p["answers"]
    for a in p["answers"]:
        assert a["value"] > 0 and math.isfinite(a["value"])
        ok, err = t.check_answer(p, a["key"], a["value"])
        assert ok and err == 0
        assert not t.check_answer(p, a["key"], a["value"] * 1.25)[0]
        assert not t.check_answer(p, a["key"], a["value"] * 0.75)[0]

def test_problems_are_deterministic_and_varied():
    assert t.make_problem("hx_u", 3) == t.make_problem("hx_u", 3)
    assert len({t.make_problem("hx_u", s)["prompt"] for s in range(1, 11)}) > 5

def test_unknown_problem_type():
    with pytest.raises(ValueError):
        t.make_problem("nope", 1)

def test_practice_answers_match_engine_functions():
    p = t.make_problem("hx_lmtd", 2)
    assert p["answers"][0]["value"] > p["answers"][1]["value"]            # counter > parallel
    p = t.make_problem("pump_power", 4)
    assert p["answers"][1]["value"] > p["answers"][0]["value"]            # shaft > hydraulic
    p = t.make_problem("pipe_dp", 5)
    re, f, dp = (a["value"] for a in p["answers"])
    assert re > 4000 and 0.01 < f < 0.06 and dp > 0

def test_explain_hx_gradual_fouling():
    text = " ".join(t.explain_hx(m.analyze_hx(m.demo_hx(HXP), HXP), HXP))
    assert "gradually" in text and "25%" in text and "digital twin" in text.lower()

def test_explain_hx_sudden_step_is_called_out():
    d = m.demo_hx(HXP, scenario="clean", days=40, noise=0)
    d.loc[25:, "t_cold_out_c"] -= 6.0                      # sudden drop in outlet temperature
    text = " ".join(t.explain_hx(m.analyze_hx(d, HXP), HXP))
    assert "within a few readings" in text and "gradually" not in text

def test_explain_hx_clean_exchanger():
    text = " ".join(t.explain_hx(m.analyze_hx(m.demo_hx(HXP, scenario="clean"), HXP), HXP))
    assert "no sign of fouling" in text and "within limits" in text

@pytest.mark.parametrize("scenario,word", [("healthy", "No fault"), ("throttled", "partly closed valve"), ("worn", "impeller")])
def test_explain_pump_matches_scenario(scenario, word):
    assert word in " ".join(t.explain_pump(m.analyze_pump(m.demo_pump(PUMPP, scenario), PUMPP), PUMPP))

def test_explain_with_too_little_data():
    d = m.demo_pump(PUMPP, days=5).head(2)
    assert "Not enough" in t.explain_pump(m.analyze_pump(d, PUMPP), PUMPP)[0]


@pytest.mark.parametrize("seed", range(1, 9))
def test_gradual_fouling_is_never_called_sudden(seed):
    text = " ".join(t.explain_hx(m.analyze_hx(m.demo_hx(HXP, seed=seed), HXP), HXP))
    assert "gradually" in text and "within a few readings" not in text
