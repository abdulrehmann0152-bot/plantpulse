import json, os, re, sys
import pytest
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import solver as sv
from calc_engine.heat_exchanger import InputError
from core import clipboard, validation as val
from core.results_text import build_text

ROOT = os.path.dirname(os.path.dirname(__file__))
RHO, MU = 998.2, 1.002e-3

# ------------------------------------------------------------------ equivalent length (Le/D) in the engine
def test_equivalent_length_adds_f_leD_velocity_head():
    base = sv.solve_pipe(56.55, 100, 200, RHO, MU, 0.045, 8, 10, 0, 70)
    r = sv.solve_pipe(56.55, 100, 200, RHO, MU, 0.045, 8, 10, 0, 70, equiv_len_d=30)
    assert base["hle"] == 0 and r["hle"] == pytest.approx(r["f"] * 30 * r["v"] ** 2 / (2 * 9.81))
    assert r["head_m"] == pytest.approx(base["head_m"] + r["hle"]) and r["dp_friction_kpa"] == pytest.approx(base["dp_friction_kpa"])   # straight-pipe friction is unchanged
    assert r["shaft_kw"] > base["shaft_kw"] and any("equivalent length" in s["title"] for s in r["steps"])
    assert any(s["title"].startswith("Total head") and "h_{Le}" in s["formula"] for s in r["steps"])

def test_equivalent_length_works_with_and_without_k():
    only_le = sv.solve_pipe(56.55, 100, 200, RHO, MU, 0.045, 0, 0, 0, None, 40)
    assert only_le["hk"] == 0 and only_le["head_m"] == pytest.approx(only_le["hf"] + only_le["hle"])
    both = sv.solve_pipe(56.55, 100, 200, RHO, MU, 0.045, 5, 0, 0, None, 40)
    assert both["head_m"] == pytest.approx(both["hf"] + both["hk"] + both["hle"]) and both["head_m"] > only_le["head_m"]

@pytest.mark.parametrize("args", [(56.55, 100, 200, RHO, MU, 0.045, 8, 30), (2.0, 50, 30, 870, 0.2, 0.045, 2, 60), (300, 150, 500, 870, 0.01, 0.15, 12, 100)])
def test_flow_from_head_round_trips_with_equivalent_length(args):
    r = sv.solve_pipe(*args[:7], 0, 0, None, args[7])
    f = sv.flow_from_head(r["hf"] + r["hk"] + r["hle"], *args[1:7], args[7])
    assert f["q_m3h"] == pytest.approx(args[0], rel=1e-6) and f["hle"] == pytest.approx(r["hle"], rel=1e-6)
    assert any("h_{Le}" in s["formula"] for s in f["steps"])

def test_more_equivalent_length_means_less_flow_and_negative_is_rejected():
    qs = [sv.flow_from_head(5, 100, 200, RHO, MU, 0.045, 8, led)["q_m3h"] for led in (0, 20, 50, 100)]
    assert qs == sorted(qs, reverse=True) and len(set(qs)) == 4
    with pytest.raises(InputError):
        sv.solve_pipe(56.55, 100, 200, RHO, MU, 0.045, equiv_len_d=-1)
    with pytest.raises(InputError):
        sv.flow_from_head(5, 100, 200, RHO, MU, 0.045, equiv_len_d=-1)

def test_old_calls_without_equivalent_length_are_unchanged():
    r = sv.solve_pipe(56.55, 100, 200, RHO, MU, 0.045, 8, 10, 0, 70)
    assert r["head_m"] == pytest.approx(19.245, abs=1e-3) and r["hle"] == 0

def test_fittings_loss_appears_in_the_validation_values():
    v = val.pipe_values(sv.solve_pipe(56.55, 100, 200, RHO, MU, 0.045, 8, 10, 0, 70, 30))
    assert v["Fittings head loss"][0] == pytest.approx(1.631 + 0.114, abs=0.01)
    assert "Fittings head loss" not in val.pipe_values(sv.solve_pipe(56.55, 100, 200, RHO, MU, 0.045))

# ------------------------------------------------------------------ results text and clipboard button
def test_results_text_has_every_section():
    t = build_text("Heat Exchanger Solver", ["Arrangement: Counter-flow"], [("Hot fluid inlet", 180.0, "°C"), ("F given", 0.92, "")],
                   [("LMTD, counter-flow", "99.67 K")], ["Check the units."])
    lines = t.splitlines()
    assert lines[0] == "PlantPulse - Heat Exchanger Solver" and "Arrangement: Counter-flow" in lines
    assert "  Hot fluid inlet: 180 °C" in lines and "  F given: 0.92" in lines and "  LMTD, counter-flow: 99.67 K" in lines and "  - Check the units." in lines
    assert "Given" in lines and "Results" in lines and "Notes" in lines and "Calculated with PlantPulse" in lines[-1]
    assert "Notes" not in build_text("T", [], [], [("a", "1")])

@pytest.mark.parametrize("text", ["plain", "line one\nline two", 'quotes " and \' and \\ backslash', "</script><script>alert(1)</script>", "unicode: °C m² ΣK η ≥", "tab\there"])
def test_clipboard_payload_survives_any_text(text):
    html = clipboard.copy_button_html(text)
    payload = re.search(r"var T=(.*?),b=document", html, re.S).group(1)
    assert json.loads(payload) == text
    assert html.count("</script>") == 1                                    # only our own closing tag: the text cannot break out of the script

def test_clipboard_button_has_a_fallback_and_a_label():
    html = clipboard.copy_button_html("x", "Copy results to clipboard")
    assert "Copy results to clipboard" in html and "navigator.clipboard.writeText" in html and "execCommand('copy')" in html and "Copied!" in html

# ------------------------------------------------------------------ the pages
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d10.db"))

def _page(page):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.button(key="do_guest").click().run()
    return at.switch_page(page).run()

def _n(text):
    return float(re.search(r"-?[\d,]*\.?\d+", text).group(0).replace(",", ""))

def _m(at):
    return {m.label: _n(m.value) for m in at.metric}

def _has_answers(at):
    return any(h.value == "Answers" for h in at.subheader) and len(at.metric) > 0

def test_hx_reset_clears_inputs_and_hides_answers_until_calculate():
    at = _page("views/solver.py")
    assert _has_answers(at)                                                  # the worked example shows first
    at.number_input(key="sv_mh").set_value(5.0); at.number_input(key="sv_a").set_value(10.0)
    at.button(key="sv_reset").click().run()
    assert not at.exception and not _has_answers(at) and len(at.metric) == 0
    for key in ("sv_thi__1", "sv_tho__1", "sv_tci__1", "sv_tco__1", "sv_mh__1", "sv_a__1"):
        assert at.number_input(key=key).value is None
    assert any("click **Calculate**" in i.value or "click Calculate" in i.value for i in at.info)
    at.number_input(key="sv_thi__1").set_value(180.0); at.number_input(key="sv_tho__1").set_value(120.0)
    at.number_input(key="sv_tci__1").set_value(30.0); at.number_input(key="sv_tco__1").set_value(70.0)
    at.run()
    assert not _has_answers(at)                                              # typing alone does not bring the answers back
    at.button(key="sv_calc").click().run()
    assert _has_answers(at) and _m(at)["LMTD, counter-flow"] == pytest.approx(99.67, abs=0.01)
    at.number_input(key="sv_tco__1").set_value(60.0).run()                   # after the first Calculate the answers follow the inputs
    assert _m(at)["LMTD, counter-flow"] == pytest.approx(sv.solve_hx("counter", 180, 120, 30, 60)["lmtd_counter"], abs=0.01)

def test_hx_calculate_with_missing_temperatures_asks_politely():
    at = _page("views/solver.py")
    at.button(key="sv_reset").click().run()
    at.button(key="sv_calc").click().run()
    assert not at.exception and any("all four temperatures" in w.value for w in at.warning) and len(at.metric) == 0

def test_hx_load_example_and_repeated_resets():
    at = _page("views/solver.py")
    at.button(key="sv_reset").click().run()
    at.button(key="sv_reset").click().run()
    assert not _has_answers(at) and at.number_input(key="sv_thi__2").value is None
    at.button(key="sv_example").click().run()
    assert not at.exception and _has_answers(at) and at.number_input(key="sv_thi__3").value == 180.0
    assert _m(at)["LMTD, counter-flow"] == pytest.approx(99.67, abs=0.01)

def test_hx_entering_a_duty_locks_the_flows_and_vice_versa():
    at = _page("views/solver.py")
    assert not at.number_input(key="sv_mh").disabled and not at.number_input(key="sv_q").disabled
    at.number_input(key="sv_q").set_value(1200.0).run()
    assert at.number_input(key="sv_mh").disabled and at.number_input(key="sv_mc").disabled and at.selectbox(key="sv_mh_u").disabled
    assert not at.number_input(key="sv_q").disabled and not at.number_input(key="sv_cph").disabled
    assert any("flow boxes are locked" in i.value for i in at.info)
    at.number_input(key="sv_q").set_value(None).run()
    assert not at.number_input(key="sv_mh").disabled and not at.number_input(key="sv_mc").disabled
    at.number_input(key="sv_mh").set_value(5.0).run()
    assert at.number_input(key="sv_q").disabled and at.selectbox(key="sv_q_u").disabled and any("duty box is locked" in i.value for i in at.info)
    at.number_input(key="sv_mh").set_value(None).run()
    assert not at.number_input(key="sv_q").disabled

def test_hx_duty_wins_over_stale_flows_and_still_finds_an_unknown_flow():
    at = _page("views/solver.py")
    at.number_input(key="sv_mh").set_value(12.0); at.number_input(key="sv_cph").set_value(3.6)
    at.number_input(key="sv_q").set_value(1200.0); at.number_input(key="sv_cpc").set_value(4.18)
    at.run()
    m = _m(at)
    assert not at.exception and m["Heat duty Q"] == pytest.approx(1200.0) and m["Cold flow (found)"] == pytest.approx(1200 / (4.18 * 40), rel=1e-3)

def test_tooltips_explain_the_complex_inputs():
    hx = _page("views/solver.py")
    helps = {k: hx.number_input(key=k).help for k in ("sv_f", "sv_u", "sv_q", "sv_a", "sv_mh", "sv_cph", "sv_thi")}
    assert all(helps.values())
    assert "correction factor" in helps["sv_f"] and "R and P" in helps["sv_f"] and "chart" in helps["sv_f"]
    assert "heat transfer coefficient" in helps["sv_u"] and "Q = U·A·F·LMTD" in helps["sv_u"]
    assert "locks" in helps["sv_q"] and "Cp" in helps["sv_q"] and hx.selectbox(key="sv_arr").help
    pipe = _page("views/pipe_solver.py")
    for key in ("pp_k", "pp_d", "pp_l", "pp_q", "pp_static", "pp_dp", "pp_eta"):
        assert pipe.number_input(key=key).help, key
    pipe.radio(key="pp_minor").set_value("Equivalent length (Le/D)").run()
    led_help = pipe.number_input(key="pp_led").help
    assert "equivalent length" in led_help.lower() and "How to find it" in led_help
    assert pipe.radio(key="pp_minor").help and pipe.selectbox(key="pp_mat").help and pipe.radio(key="pp_mode").help
    pipe.radio(key="pp_minor").set_value("Sum of K values").run()
    assert "loss coefficients" in pipe.number_input(key="pp_k").help

def test_pipe_answers_wait_for_calculate_after_reset():
    at = _page("views/pipe_solver.py")
    at.button(key="pp_reset").click().run()
    at.number_input(key="pp_temp__1").set_value(20.0); at.number_input(key="pp_d__1").set_value(100.0)
    at.number_input(key="pp_l__1").set_value(200.0); at.number_input(key="pp_q__1").set_value(56.55)
    at.run()
    assert not _has_answers(at) and any("click **Calculate**" in i.value for i in at.info)
    at.button(key="pp_calc").click().run()
    assert _has_answers(at)

def test_pipe_reset_calculate_and_missing_data():
    at = _page("views/pipe_solver.py")
    assert _has_answers(at)
    at.button(key="pp_reset").click().run()
    assert not at.exception and not _has_answers(at)
    for key in ("pp_temp__1", "pp_d__1", "pp_l__1", "pp_q__1", "pp_k__1", "pp_static__1"):
        assert at.number_input(key=key).value is None, key
    at.button(key="pp_calc").click().run()
    assert any("Still needed" in w.value and "diameter" in w.value and "flow or velocity" in w.value for w in at.warning)
    at.number_input(key="pp_temp__1").set_value(20.0); at.number_input(key="pp_d__1").set_value(100.0)
    at.number_input(key="pp_l__1").set_value(200.0); at.number_input(key="pp_q__1").set_value(56.55)
    at.run()
    assert not at.exception and _has_answers(at)               # Calculate was already clicked, so the answers follow the data once it is complete
    r = sv.solve_pipe(56.55, 100, 200, RHO, MU, 0.045)            # blank fittings, static head and efficiency mean zero
    assert _m(at)["Total head required"] == pytest.approx(r["head_m"], abs=2e-3) and "Shaft power" not in _m(at)
    at.button(key="pp_example").click().run()
    assert _has_answers(at) and at.number_input(key="pp_d__2").value == 100.0

def test_pipe_page_toggle_switches_between_k_values_and_equivalent_length():
    at = _page("views/pipe_solver.py")
    k_head = _m(at)["Total head required"]
    assert k_head == pytest.approx(sv.solve_pipe(56.5, 100, 200, RHO, MU, 0.045, 8, 10)["head_m"], abs=2e-3)
    assert not any(n.key == "pp_led" for n in at.number_input)                     # the Le/D box is hidden while ΣK is selected
    at.radio(key="pp_minor").set_value("Equivalent length (Le/D)").run()
    assert not any(n.key == "pp_k" for n in at.number_input)                       # and ΣK is hidden while Le/D is selected
    at.number_input(key="pp_led").set_value(30.0).run()
    r = sv.solve_pipe(56.5, 100, 200, RHO, MU, 0.045, 0, 10, 0, None, 30)           # only Le/D is used: ΣK is not added
    assert not at.exception and _m(at)["Total head required"] == pytest.approx(r["head_m"], abs=2e-3)
    assert "Equivalent length of the fittings" in " ".join(n.label for n in at.number_input)
    at.radio(key="pp_mode").set_value("The flow for a given available head").run()
    assert not at.exception and "Fittings head loss" in _m(at)
    at.radio(key="pp_minor").set_value("Sum of K values").run()
    assert not at.exception

def test_copy_text_box_holds_the_results():
    at = _page("views/solver.py")
    at.selectbox(key="sv_arr").select("shell_1_2").run()
    for key, v in dict(sv_thi=95.0, sv_tho=60.0, sv_tci=25.0, sv_tco=45.0, sv_mh=12.0, sv_cph=3.6, sv_cpc=4.18, sv_a=80.0, sv_f=0.92).items():
        at.number_input(key=key).set_value(v)
    at.run()
    assert not at.exception and any("Show results as text" in e.label for e in at.expander)
    text = "\n".join(c.value for c in at.code)
    assert text.startswith("PlantPulse - Heat Exchanger Solver") and "1 shell pass / 2 tube passes" in text
    assert "Heat duty Q: 1,512.0 kW" in text and "Overall U: 488.5 W/m²K" in text and "Hot flow: 12 kg/s" in text and "F given: 0.92" in text and "Area: 80 m²" in text
    pipe = _page("views/pipe_solver.py")
    ptext = "\n".join(c.value for c in pipe.code)
    assert ptext.startswith("PlantPulse - Pipe and Pump Solver") and "Total head required" in ptext and "Pipe inside diameter: 100 mm" in ptext and "ΣK: 8" in ptext

def test_no_copy_text_or_answers_while_hidden():
    at = _page("views/solver.py")
    at.button(key="sv_reset").click().run()
    assert len(at.code) == 0 and len(at.expander) >= 1                          # only the theory expander remains
