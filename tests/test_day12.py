import math, os, re, sys
import pytest
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import solver as sv, pump_pipe as pp
from calc_engine.heat_exchanger import InputError

ROOT = os.path.dirname(os.path.dirname(__file__))
RHO, MU = 998.2, 1.002e-3
CURVE = [(0.0, 30.0), (200.0, 25.0), (300.0, 17.0)]

# ====================================================================== vapour pressure and NPSH
@pytest.mark.parametrize("t,table", [(20, 2.339), (40, 7.384), (60, 19.946), (80, 47.416), (100, 101.325)])
def test_water_vapour_pressure_agrees_with_steam_tables(t, table):
    assert pp.water_vapor_pressure_kpa(t) == pytest.approx(table, rel=0.01)

def test_water_vapour_pressure_range():
    for bad in (0.5, 120):
        with pytest.raises(InputError):
            pp.water_vapor_pressure_kpa(bad)

def test_npsh_matches_a_hand_calculation():
    pv = pp.water_vapor_pressure_kpa(20)
    r = sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, pv, RHO, 4.0)
    hand = (101.325 - pv) * 1000 / (RHO * 9.81) + 3.0 - 0.5                       # head of pressure above vapour pressure + static - friction
    assert r["npsha"] == pytest.approx(hand) and r["npsha"] == pytest.approx(12.609, abs=0.01)
    assert r["status"] == "ok" and r["needed"] == 4.5 and r["excess"] == pytest.approx(hand - 4.0)
    assert any("NPSH available" in s["title"] for s in r["steps"]) and all(s["title"] and s["formula"] and s["working"] for s in r["steps"])

def test_gauge_and_absolute_pressures_give_the_same_answer():
    a = sv.npsh_check(50.0, "gauge", 101.325, 2.0, 0.3, 2.34, RHO, 3.0)
    b = sv.npsh_check(151.325, "absolute", 101.325, 2.0, 0.3, 2.34, RHO, 3.0)
    assert a["npsha"] == pytest.approx(b["npsha"]) and a["p_abs_kpa"] == pytest.approx(151.325)
    assert len(a["steps"]) == 3 and len(b["steps"]) == 2                             # the conversion step only appears for gauge pressure

def test_each_term_moves_npsh_by_the_right_amount():
    base = sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, 2.34, RHO, 3.0)["npsha"]
    assert sv.npsh_check(0.0, "gauge", 101.325, -3.0, 0.5, 2.34, RHO, 3.0)["npsha"] == pytest.approx(base - 6.0)      # a suction lift of 3 m instead of 3 m of head
    assert sv.npsh_check(0.0, "gauge", 101.325, 3.0, 1.5, 2.34, RHO, 3.0)["npsha"] == pytest.approx(base - 1.0)       # 1 m more friction
    assert sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, 47.4, RHO, 3.0)["npsha"] < base                              # hotter water, higher vapour pressure
    assert sv.npsh_check(100.0, "gauge", 101.325, 3.0, 0.5, 2.34, RHO, 3.0)["npsha"] == pytest.approx(base + 100e3 / (RHO * 9.81))   # a pressurised vessel
    assert sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, 2.34, 800.0, 3.0)["npsha"] > base                           # a lighter liquid gives more head per kPa

def test_cavitation_warning_thresholds_with_the_half_metre_margin():
    n = sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, 2.34, RHO, 1.0)["npsha"]
    at_limit = sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, 2.34, RHO, n - 0.5)
    assert at_limit["status"] == "ok"                                                  # exactly NPSHr + 0.5 m is still acceptable
    assert sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, 2.34, RHO, n - 0.499)["status"] == "risk"
    assert sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, 2.34, RHO, n + 0.1)["status"] == "cavitation"
    assert sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, 2.34, RHO, n - 0.8, margin_m=1.0)["status"] == "risk"          # a bigger margin is honoured

def test_boiling_at_the_suction_and_bad_inputs():
    r = sv.npsh_check(5.0, "absolute", 101.325, 0.5, 1.0, 20.0, RHO, 1.0)
    assert r["npsha"] < 0 and r["status"] == "cavitation" and any("boil" in w for w in r["warnings"])
    for bad in (dict(basis="atm"), dict(p_vessel_kpa=-150.0), dict(p_vapor_kpa=-1.0), dict(npshr_m=-1.0), dict(margin_m=-0.1), dict(hf_suction_m=-1.0), dict(rho=0.0), dict(p_atm_kpa=0.0)):
        a = dict(p_vessel_kpa=0.0, basis="gauge", p_atm_kpa=101.325, level_m=3.0, hf_suction_m=0.5, p_vapor_kpa=2.34, rho=RHO, npshr_m=3.0); a.update(bad)
        with pytest.raises(InputError):
            sv.npsh_check(**a)

# ====================================================================== Hydraulic Institute viscosity correction
@pytest.mark.parametrize("nu,h,q,n,published", [(87, 37.3, 817, 1495, 2.51), (191, 37.3, 818, 1496, 3.72), (1160, 58.5, 1296, 1783, 7.59),
                                                (864, 22.5, 277, 1895, 10.84), (1877, 41, 59, 2875, 26.69)])
def test_parameter_b_reproduces_published_test_pump_values(nu, h, q, n, published):
    assert sv.hi_parameter_b(nu, h, q, n) == pytest.approx(published, abs=0.01)         # AFT paper, table of viscous test pumps

def test_correction_factors_match_the_published_behaviour():
    assert 1 - sv.hi_factors(3)["cq"] < 0.03                                              # "less than three percent when B equals three"
    assert 1 - sv.hi_factors(7)["cq"] == pytest.approx(0.10, abs=0.02)                    # "about ten percent when B equals seven"
    assert sv.hi_factors(26.69)["ceta"] < 0.2                                             # efficiency factor below 0.2 at B = 26.7
    assert sv.hi_factors(3)["cq"] == pytest.approx(0.9841, abs=1e-4) and sv.hi_factors(7)["ceta"] == pytest.approx(0.6652, abs=1e-4)

def test_factor_limits_and_trends():
    for b in (0.2, 0.99, 1.0):
        f = sv.hi_factors(b)
        assert (f["cq"], f["ch"], f["ceta"], f["applies"]) == (1.0, 1.0, 1.0, False)
    bs = [1.5, 3, 7, 12, 20, 30, 39.9]
    cq, ce = [sv.hi_factors(b)["cq"] for b in bs], [sv.hi_factors(b)["ceta"] for b in bs]
    assert cq == sorted(cq, reverse=True) and ce == sorted(ce, reverse=True) and all(0 < x < 1 for x in cq + ce)
    f0, f1, f12 = sv.hi_factors(10, 0.0), sv.hi_factors(10, 1.0), sv.hi_factors(10, 1.2)
    assert f0["ch"] == 1.0 and f1["ch"] == pytest.approx(f1["cq"]) and f12["ch"] < f1["ch"] < f0["ch"]      # shut-off head unchanged; head factor falls with flow
    for b in (40, 55):
        with pytest.raises(InputError, match="below 40"):
            sv.hi_factors(b)
    for bad in ((0, 30, 100, 1450), (10, 0, 100, 1450), (10, 30, 0, 1450), (10, 30, 100, 0)):
        with pytest.raises(InputError):
            sv.hi_parameter_b(*bad)

def _pump(nu=230.0, rho=870.0, n=2900.0, stages=1, system=None, q_bep=250.0, eta=75.0):
    return sv.pump_viscosity(CURVE, q_bep, eta, n, stages, nu, rho, system)

def test_water_like_liquid_needs_no_correction():
    r = _pump(nu=1.0, rho=998.0)
    assert r["applies"] is False and r["b"] < 1 and r["cq"] == r["ceta"] == 1.0
    assert r["visc_curve"] == r["water_curve"] and r["eta_bep_visc_pct"] == pytest.approx(75.0) and any("No correction" in s["title"] for s in r["steps"])

def test_best_efficiency_point_is_corrected_with_the_published_factors():
    r = _pump()
    f = sv.hi_factors(r["b"])
    assert r["applies"] and 1 < r["b"] < 40 and r["cq"] == pytest.approx(f["cq"]) and r["ceta"] == pytest.approx(f["ceta"])
    h_w = r["h_bep_total"]
    a, b, c = pp.fit_pump_curve(CURVE)
    assert h_w == pytest.approx(a + b * 250 + c * 250 ** 2)
    assert r["q_bep_visc"] == pytest.approx(f["cq"] * 250) and r["h_bep_visc"] == pytest.approx(f["cq"] * h_w) and r["eta_bep_visc_pct"] == pytest.approx(f["ceta"] * 75)
    assert r["p_bep_visc_kw"] == pytest.approx(870 * 9.81 * (r["q_bep_visc"] / 3600) * r["h_bep_visc"] / (r["eta_bep_visc_pct"] / 100) / 1000)
    assert r["eta_bep_visc_pct"] < 75 and r["q_bep_visc"] < 250 and r["h_bep_visc"] < h_w
    assert [round(t["ratio"], 1) for t in r["table"]] == [0.6, 0.8, 1.0, 1.2] and r["table"][2]["ch"] == pytest.approx(f["cq"])

def test_corrected_curve_keeps_the_shutoff_head_and_lies_below_the_water_curve():
    r = _pump()
    qw, hw = r["water_curve"]; qv, hv = r["visc_curve"]
    assert qw[0] == qv[0] == 0 and hw[0] == hv[0] and len(qw) == len(qv) == 25 and qw[-1] == pytest.approx(1.2 * 250)
    assert all(v <= w + 1e-9 for v, w in zip(hv[1:], hw[1:])) and all(a < b for a, b in zip(qv[1:], qw[1:]))

def test_more_stages_lower_the_head_per_stage_and_so_b():
    one, four = _pump(stages=1), _pump(stages=4)
    assert four["b"] == pytest.approx(one["b"] * 4 ** -0.0625)                            # B scales with (head per stage)^(1/16)
    assert four["h_bep_total"] == one["h_bep_total"]

def test_operating_points_sit_on_both_curves_and_viscosity_lowers_them():
    sysfn = lambda q: sv.system_head_curve(q, 150, 300, 870.0, 0.230 * 0.87e-3 * 1000 / 1000, 0.045, 5, 8)
    r = _pump(system=sysfn)
    wo, vo = r["water_op"], r["visc_op"]
    a, b, c = pp.fit_pump_curve(CURVE)
    assert wo["h"] == pytest.approx(a + b * wo["q"] + c * wo["q"] ** 2, abs=1e-6) and wo["h"] == pytest.approx(sysfn(wo["q"]), abs=1e-4)
    qv, hv = r["visc_curve"]
    interp = lambda x: next(hv[i] + (hv[i + 1] - hv[i]) * (x - qv[i]) / (qv[i + 1] - qv[i]) for i in range(len(qv) - 1) if qv[i] <= x <= qv[i + 1])
    assert vo["h"] == pytest.approx(interp(vo["q"]), abs=1e-6) and vo["h"] == pytest.approx(sysfn(vo["q"]), abs=1e-3)
    assert vo["q"] < wo["q"] and vo["h"] < wo["h"]

def test_a_system_that_cannot_meet_the_corrected_curve_is_reported():
    r = _pump(system=lambda q: 18.0 + 0.5 * (q - 290.0))    # crosses the water curve near 290 m3/h, but the corrected curve ends at about 283 m3/h still above it
    assert r["water_op"] is not None and r["water_op"]["q"] == pytest.approx(290, abs=1)
    assert r["visc_op"] is None and any("does not meet the system curve inside the range" in w for w in r["warnings"])
    r2 = _pump(system=lambda q: 40.0)                       # above the shut-off head: no operating point at all
    assert r2["water_op"] is None and r2["visc_op"] is None and any("water pump curve does not meet" in w for w in r2["warnings"])

def test_pump_viscosity_validation_and_limits():
    for bad in (dict(eta=0), dict(eta=150), dict(stages=0), dict(stages=1.5), dict(nu=4500.0)):
        with pytest.raises(InputError):
            _pump(**bad)
    with pytest.raises(InputError, match="below 40"):
        sv.pump_viscosity([(0, 30), (15, 29), (30, 26)], 20.0, 60.0, 500.0, 1, 2000.0, 900.0)     # a small slow pump with a very viscous liquid
    with pytest.raises(InputError):
        sv.pump_viscosity([(0, 30), (200, 25), (200, 17)], 250.0, 75.0, 1450.0, 1, 100.0, 900.0)   # two points at the same flow
    high_ns = sv.pump_viscosity([(0, 20), (1000, 15), (1500, 8)], 1200.0, 80.0, 3500.0, 1, 30.0, 900.0)
    assert any("specific speed" in w for w in high_ns["warnings"])

def test_system_head_curve_agrees_with_the_solver():
    for q in (20.0, 56.55, 120.0):
        r = sv.solve_pipe(q, 100, 200, RHO, MU, 0.045, 8, 10, 25, None, 15)
        assert sv.system_head_curve(q, 100, 200, RHO, MU, 0.045, 8, 10, 25, 15) == pytest.approx(r["head_m"])
    assert sv.system_head_curve(0.0, 100, 200, RHO, MU, 0.045, 8, 10, 0) == 10.0

# ====================================================================== the page
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d12.db"))

def _page():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.button(key="do_guest").click().run()
    return at.switch_page("views/pipe_solver.py").run()

def _n(text):
    return float(re.search(r"-?[\d,]*\.?\d+", text).group(0).replace(",", ""))

def _m(at):
    return {m.label: _n(m.value) for m in at.metric}

def _other_liquid(at, mu_cp=200.0, rho=870.0):
    at.radio(key="pp_fluid").set_value("Other liquid (enter density and viscosity)").run()
    at.number_input(key="pp_rho").set_value(rho); at.number_input(key="pp_mu").set_value(mu_cp)
    return at.run()

def test_the_new_sections_are_off_by_default_and_hidden_in_the_flow_mode():
    at = _page()
    heads = [h.value for h in at.subheader]
    assert any("4. NPSH" in h for h in heads) and any("5. Pump curve" in h for h in heads)
    assert not at.checkbox(key="pp_npsh").value and not any(m.label.startswith("NPSH") for m in at.metric)
    assert any("no viscosity correction is needed" in c.value for c in at.caption)         # water: nothing to correct
    at.radio(key="pp_mode").set_value("The flow for a given available head").run()
    assert not any(c.key in ("pp_npsh", "pp_hi") for c in at.checkbox)

def test_npsh_section_default_example_is_safe():
    at = _page()
    at.checkbox(key="pp_npsh").check().run()
    assert not at.exception
    expected = sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, pp.water_vapor_pressure_kpa(20), RHO, 4.0)
    m = _m(at)
    assert m["NPSH available"] == pytest.approx(expected["npsha"], abs=0.01) and m["NPSH required"] == 4.0 and m["NPSHa minus NPSHr"] == pytest.approx(expected["excess"], abs=0.01)
    assert any("No cavitation risk" in s.value for s in at.success) and not any("Cavitation Risk!" in e.value for e in at.error)
    assert any("Antoine" in c.value for c in at.caption)                                    # the vapour pressure came from the temperature
    assert any("NPSH calculation" in h.value for h in at.subheader)

def test_cavitation_risk_message_and_its_three_wordings():
    at = _page()
    at.checkbox(key="pp_npsh").check().run()
    npsha = _m(at)["NPSH available"]
    at.number_input(key="pp_npshr").set_value(npsha - 0.3).run()                             # above NPSHr but inside the 0.5 m margin
    err = [e.value for e in at.error if "Cavitation Risk!" in e.value]
    assert err and err[0].startswith("Cavitation Risk!") and "inside the safety margin" in err[0] and not any("No cavitation risk" in s.value for s in at.success)
    at.number_input(key="pp_npshr").set_value(npsha + 1.0).run()
    assert any("below NPSHr" in e.value for e in at.error)
    at.number_input(key="pp_npshr").set_value(npsha - 0.6).run()                             # comfortably above NPSHr + margin
    assert any("No cavitation risk" in s.value for s in at.success) and not any("Cavitation Risk!" in e.value for e in at.error)
    at.number_input(key="pp_npshr").set_value(npsha - 0.6).run()
    at.number_input(key="pp_mrg").set_value(1.0).run()                                       # a bigger margin turns it into a warning
    assert any("Cavitation Risk!" in e.value for e in at.error)
    assert "Cavitation Risk!" in "\n".join(c.value for c in at.code)                         # and the warning is in the copy-text

def test_npsh_gauge_absolute_lift_and_units():
    at = _page()
    at.checkbox(key="pp_npsh").check().run()
    base = _m(at)["NPSH available"]
    assert not at.number_input(key="pp_patm").disabled
    at.radio(key="pp_psb").set_value("Absolute pressure"); at.number_input(key="pp_ps").set_value(101.325); at.run()
    assert at.number_input(key="pp_patm").disabled and _m(at)["NPSH available"] == pytest.approx(base, abs=1e-6)
    at.selectbox(key="pp_ps_u").select("bar"); at.number_input(key="pp_ps").set_value(1.01325); at.run()
    assert _m(at)["NPSH available"] == pytest.approx(base, abs=1e-6)                         # 1.01325 bar abs is the same pressure
    at.number_input(key="pp_zl").set_value(-3.0).run()                                       # a suction lift
    assert _m(at)["NPSH available"] == pytest.approx(base - 6.0, abs=1e-3)
    at.radio(key="pp_psb").set_value("Absolute pressure"); at.selectbox(key="pp_ps_u").select("kPa"); at.number_input(key="pp_ps").set_value(0.0).run()
    assert not at.exception and any("above zero" in e.value for e in at.error)                # 0 absolute is impossible: a polite message, not a crash

def test_npsh_for_another_liquid_needs_its_vapour_pressure():
    at = _other_liquid(_page(), mu_cp=5.0, rho=800.0)
    at.checkbox(key="pp_npsh").check().run()
    assert not at.exception and any(c.placeholder == "required" for c in at.number_input if c.key == "pp_pv")
    at.number_input(key="pp_pv").set_value(40.0).run()
    exp = sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, 40.0, 800.0, 4.0)["npsha"]
    assert _m(at)["NPSH available"] == pytest.approx(exp, abs=0.01)

def test_pump_viscosity_section_end_to_end():
    at = _other_liquid(_page(), mu_cp=200.0)
    assert any(c.key == "pp_hi" for c in at.checkbox)
    at.checkbox(key="pp_hi").check().run()
    at.number_input(key="pp_rpm").set_value(2900.0).run()
    nu = 200.0 / 870.0 * 1000
    ref = sv.pump_viscosity(CURVE, 250.0, 75.0, 2900.0, 1, nu, 870.0)
    m = _m(at)
    assert not at.exception and m["Viscosity parameter B"] == pytest.approx(ref["b"], abs=0.01) and m["Flow factor C_Q"] == pytest.approx(ref["cq"], abs=1e-4)
    assert m["Efficiency factor C_η"] == pytest.approx(ref["ceta"], abs=1e-4) and m["BEP efficiency, viscous"] == pytest.approx(ref["eta_bep_visc_pct"], abs=0.05)
    assert m["BEP flow, viscous"] == pytest.approx(ref["q_bep_visc"], abs=0.05) and any("Viscosity correction of the pump curve" in h.value for h in at.subheader)
    assert len(at.dataframe) >= 1 and "Kinematic viscosity" in "\n".join(c.value for c in at.code)

def test_small_effect_is_explained_and_the_ten_centipoise_hint_is_honest():
    at = _other_liquid(_page(), mu_cp=10.0)
    at.checkbox(key="pp_hi").check().run()
    assert not at.exception and any("under the usual 10 cP" in i.value for i in at.info)
    big_pump = _other_liquid(_page(), mu_cp=2.0)
    big_pump.checkbox(key="pp_hi").check().run()
    big_pump.number_input(key="pp_rpm").set_value(2900.0).run()
    assert any("not above 1" in i.value for i in big_pump.info)                           # about 2.3 cSt in this pump: B is about 0.5, so nothing to correct

def test_out_of_range_viscosity_is_refused_politely():
    at = _other_liquid(_page(), mu_cp=1740.0)                                               # about 2000 cSt
    at.checkbox(key="pp_hi").check().run()
    at.number_input(key="pp_rpm").set_value(500.0).run()
    at.number_input(key="pp_qbep").set_value(20.0).run()
    assert not at.exception and any("could not be applied" in e.value and "below 40" in e.value for e in at.error)
    assert not any(m.label == "Viscosity parameter B" for m in at.metric)

def test_new_inputs_have_tooltips_and_reset_turns_the_sections_off():
    at = _other_liquid(_page())
    at.checkbox(key="pp_npsh").check().run()
    at.checkbox(key="pp_hi").check().run()
    for key, word in (("pp_ps", "gauge"), ("pp_zl", "suction lift"), ("pp_hfs", "suction"), ("pp_pv", "vapour"), ("pp_npshr", "data sheet"), ("pp_mrg", "margin"),
                      ("pp_patm", "gauge"), ("pp_rpm", "speed"), ("pp_etab", "efficiency"), ("pp_qbep", "best efficiency"), ("pp_stg", "stage")):
        assert word in (at.number_input(key=key).help or "").lower(), key
    assert "absolute" in at.radio(key="pp_psb").help.lower() and at.checkbox(key="pp_npsh").help and at.checkbox(key="pp_hi").help
    at.button(key="pp_reset").click().run()
    assert not at.exception and not at.checkbox(key="pp_npsh__1").value and len(at.metric) == 0
    assert not any(c.key.startswith("pp_hi") for c in at.checkbox)                          # a reset returns to Water, where there is no viscosity section

def test_values_can_be_copied_into_the_validation_log():
    at = _page()
    at.checkbox(key="pp_npsh").check().run()
    assert "NPSH available" in at.session_state["last_solve"]["values"] and at.session_state["last_solve"]["values"]["NPSH available"][1] == "m"
