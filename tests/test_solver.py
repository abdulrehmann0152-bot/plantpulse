import os, sys
import xml.etree.ElementTree as ET
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import solver as sv, heat_exchanger as hx
from calc_engine.heat_exchanger import InputError
from core.diagrams import schematic_svg

# The three numericals supplied by the student, with answers worked by hand / verified independently.

def test_problem_1_lmtd_with_f_correction():
    r = sv.solve_hx("shell_1_2", 180, 120, 30, 70)
    assert r["lmtd_counter"] == pytest.approx(20 / 0.2006707, rel=1e-4)        # 99.666 K
    assert r["R"] == pytest.approx(1.5) and r["P"] == pytest.approx(40 / 150)
    assert r["f_computed"] == pytest.approx(0.9583, abs=5e-4)
    assert r["lmtd_eff"] == pytest.approx(r["f_computed"] * r["lmtd_counter"]) and r["lmtd_eff"] == pytest.approx(95.505, abs=0.01)
    assert r["q_kw"] is None and r["area"] is None                              # temperature-only problem

def test_problem_2a_counter_vs_parallel_and_area():
    r = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=500)
    assert r["lmtd_counter"] == pytest.approx(88.498, abs=0.001)
    assert r["lmtd_parallel"] == pytest.approx(140 / 2.0794415, rel=1e-4)       # 67.326 K
    assert r["area"] == pytest.approx(1.2e6 / (500 * 88.498), rel=1e-4)         # 27.12 m2

def test_problem_2b_duty_flow_and_u_with_given_f():
    r = sv.solve_hx("shell_1_2", 95, 60, 25, 45, m_hot=12, cp_hot=3.6, cp_cold=4.18, area=80, f_given=0.92)
    assert r["q_kw"] == pytest.approx(12 * 3.6 * 35)                            # 1512 kW
    assert r["m_cold"] == pytest.approx(1512 / (4.18 * 20), rel=1e-6)           # 18.09 kg/s
    assert r["lmtd_counter"] == pytest.approx(42.055, abs=0.001)
    assert r["f_used"] == 0.92 and r["lmtd_eff"] == pytest.approx(0.92 * 42.055, abs=0.002)   # 38.69 K
    assert r["u"] == pytest.approx(1512e3 / (80 * 0.92 * 42.055), rel=1e-4)     # 488.5 W/m2K
    assert any("differs" in w for w in r["warnings"])                           # computed F is 0.9296, not 0.92

def test_cross_check_with_the_calculator_page_engine():
    r = sv.solve_hx("shell_1_2", 100, 60, 20, 50, m_hot=1.5, cp_hot=4.18, m_cold=2.0, cp_cold=4.18, area=10)
    h = hx.analyze(1.5, 4180, 100, 60, 2.0, 4180, 20, 50, 10, "shell_1_2")
    assert r["u"] == pytest.approx(h["u"], rel=1e-9) and r["f_used"] == pytest.approx(h["f"])

def test_every_step_has_title_formula_and_working():
    r = sv.solve_hx("shell_1_2", 95, 60, 25, 45, m_hot=12, cp_hot=3.6, cp_cold=4.18, area=80)
    assert len(r["steps"]) >= 7
    assert all(s["title"] and s["formula"] and s["working"] for s in r["steps"])
    assert len(r["assumptions"]) >= 6 and any("F" in a for a in r["assumptions"])

def test_parallel_flow_with_temperature_cross():
    r = sv.solve_hx("counter", 100, 60, 20, 70)           # fine in counter-flow
    assert r["lmtd_parallel"] is None and any("parallel" in w for w in r["warnings"])
    with pytest.raises(InputError):
        sv.solve_hx("parallel", 100, 60, 20, 70)

def test_solves_for_hot_flow_and_for_area_vs_u():
    r = sv.solve_hx("counter", 100, 60, 20, 50, m_cold=2, cp_cold=4.18, cp_hot=4.18, u=800)
    assert r["m_hot"] == pytest.approx(1.5) and r["area"] == pytest.approx(250.8e3 / (800 * r["lmtd_counter"]))
    both = sv.solve_hx("counter", 100, 60, 20, 50, m_cold=2, cp_cold=4.18, area=10, u=800)
    assert any("Both area and U" in w for w in both["warnings"])

def test_heat_balance_mismatch_warning():
    ok = sv.solve_hx("counter", 100, 60, 20, 50, 1.5, 4.18, 2.0, 4.18)
    bad = sv.solve_hx("counter", 100, 60, 20, 50, 1.5, 4.18, 2.5, 4.18)
    assert not ok["warnings"] and ok["mismatch_pct"] == pytest.approx(0, abs=1e-9)
    assert any("heat balance" in w for w in bad["warnings"])

def test_low_f_warning():
    r = sv.solve_hx("shell_1_2", 100, 55, 20, 66)            # F is about 0.56
    assert r["f_computed"] < 0.75 and any("0.75" in w for w in r["warnings"])
    assert not any("0.75" in w for w in sv.solve_hx("shell_1_2", 180, 120, 30, 70)["warnings"])

def test_invalid_inputs_are_rejected_politely():
    for bad in (dict(m_hot=-1), dict(f_given=1.2), dict(area=0.0)):
        with pytest.raises(InputError):
            sv.solve_hx("counter", 100, 60, 20, 50, **bad)
    with pytest.raises(InputError):
        sv.solve_hx("counter", 60, 100, 20, 50)             # hot fluid heating up
    with pytest.raises(InputError, match="one shell"):
        sv.solve_hx("shell_1_2", 100, 60, 20, 95)           # fine in counter-flow, impossible with one shell pass
    with pytest.raises(InputError):
        sv.solve_hx("plate", 100, 60, 20, 50)

@pytest.mark.parametrize("arr", list(sv.ARRANGEMENTS))
def test_schematics_are_valid_svg_with_the_temperatures(arr):
    svg = schematic_svg(arr, 180, 120, 30, 70)
    ET.fromstring(svg)
    assert svg.startswith("<svg") and all(t in svg for t in ("180", "120", "30", "70"))
