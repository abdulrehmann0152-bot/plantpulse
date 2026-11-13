import math, os, re, sys
import xml.etree.ElementTree as ET
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import solver as sv, pump_pipe as pp
from calc_engine.heat_exchanger import InputError
from core import animation as an

RHO, MU = 998.2, 1.002e-3          # water at 20 C

def _colebrook(re, d, e):
    f = 0.02
    for _ in range(100):
        f = (-2 * math.log10(e / (3.7 * d) + 2.51 / (re * math.sqrt(f)))) ** -2
    return f

def test_hand_calculation_water_100mm_2_ms():
    q = 2.0 * math.pi * 0.1 ** 2 / 4 * 3600                       # 56.55 m3/h gives v = 2 m/s
    r = sv.solve_pipe(q, 100, 200, RHO, MU, 0.045, 0, 0, 0)
    assert r["v"] == pytest.approx(2.0) and r["re"] == pytest.approx(RHO * 2 * 0.1 / MU, rel=1e-9) and r["re"] == pytest.approx(199243, rel=1e-4)
    assert r["f"] == pytest.approx(_colebrook(r["re"], 0.1, 0.045e-3), rel=0.02)
    assert r["dp_friction_kpa"] * 1000 == pytest.approx(r["f"] * (200 / 0.1) * RHO * 2 ** 2 / 2, rel=1e-9)   # g cancels

def test_total_head_and_power_follow_the_formulas():
    r = sv.solve_pipe(100, 100, 200, RHO, MU, 0.045, 8, 10, 50, 70)
    v = 100 / 3600 / (math.pi * 0.1 ** 2 / 4)
    assert r["head_m"] == pytest.approx(10 + 50e3 / (RHO * 9.81) + r["hf"] + 8 * v * v / (2 * 9.81))
    assert r["hyd_kw"] == pytest.approx(RHO * 9.81 * (100 / 3600) * r["head_m"] / 1000)
    assert r["shaft_kw"] == pytest.approx(r["hyd_kw"] / 0.70)

def test_agrees_with_the_pump_page_engine():
    r = sv.solve_pipe(80, 100, 150, RHO, MU, 0.045, 0)
    p = pp.pipe_losses(80 / 3600, 0.1, 150, 0.045e-3, 0.0, RHO, MU, method="swamee_jain")      # the same explicit formula: exact agreement
    assert r["dp_friction_kpa"] * 1000 == pytest.approx(p["dp"], rel=1e-9) and r["f"] == pytest.approx(p["f"])
    c = pp.pipe_losses(80 / 3600, 0.1, 150, 0.045e-3, 0.0, RHO, MU)                             # the Pump page default, Colebrook-White: a different, more rigorous method
    assert r["f"] == pytest.approx(c["f"], rel=0.02) and r["dp_friction_kpa"] * 1000 == pytest.approx(c["dp"], rel=0.02)

def test_laminar_flow_uses_64_over_re():
    r = sv.solve_pipe(1.0, 50, 30, 870, 0.2, 0.045, 0)
    assert r["re"] < 2300 and r["f"] == pytest.approx(64 / r["re"])

def test_gravity_case_needs_no_pump():
    r = sv.solve_pipe(50, 100, 100, RHO, MU, 0.045, 5, -30)
    assert r["head_m"] < 0 and r["hyd_kw"] is None and any("gravity" in w for w in r["warnings"])

@pytest.mark.parametrize("args", [(56.5, 100, 200, RHO, MU, 0.045, 8), (300, 150, 500, 870, 0.01, 0.15, 12), (2.0, 50, 30, 870, 0.2, 0.045, 2), (1500, 400, 1000, RHO, MU, 0.26, 4)])
def test_flow_from_head_round_trips(args):
    r = sv.solve_pipe(*args, static_head_m=0.0)
    f = sv.flow_from_head(r["hf"] + r["hk"], *args[1:])
    assert f["q_m3h"] == pytest.approx(args[0], rel=1e-6)
    assert f["hf"] + f["hk"] == pytest.approx(r["hf"] + r["hk"], rel=1e-6)

def test_more_head_gives_more_flow():
    qs = [sv.flow_from_head(h, 100, 200, RHO, MU, 0.045, 8)["q_m3h"] for h in (1, 2, 5, 10, 20)]
    assert qs == sorted(qs) and len(set(qs)) == 5

def test_warnings_for_high_velocity_and_transition():
    assert any("3 m/s" in w for w in sv.solve_pipe(200, 80, 50, RHO, MU, 0.045)["warnings"])
    r = sv.solve_pipe(4.9, 50, 30, 870, 0.01, 0.045)                       # Re is about 3,000
    assert 2300 <= r["re"] < 4000 and any("transition" in w for w in r["warnings"])

def test_steps_and_assumptions_are_complete():
    for r in (sv.solve_pipe(100, 100, 200, RHO, MU, 0.045, 8, 10, 0, 70), sv.flow_from_head(5, 100, 200, RHO, MU, 0.045, 8)):
        assert len(r["steps"]) >= 5 and all(s["title"] and s["formula"] and s["working"] for s in r["steps"])
        assert len(r["assumptions"]) >= 6

def test_bad_inputs_are_rejected():
    for bad in (dict(q_m3h=0), dict(q_m3h=-5), dict(d_mm=0), dict(length_m=-1), dict(rho=0), dict(mu_pas=0), dict(rough_mm=-0.1), dict(sum_k=-1), dict(eta_pct=0), dict(eta_pct=120)):
        a = dict(q_m3h=100, d_mm=100, length_m=200, rho=RHO, mu_pas=MU, rough_mm=0.045); a.update(bad)
        with pytest.raises(InputError):
            sv.solve_pipe(**a)
    for h in (0, -2):
        with pytest.raises(InputError):
            sv.flow_from_head(h, 100, 200, RHO, MU, 0.045)

# ------------------------------------------------------------------ animated diagrams
def _svg(html):
    return ET.fromstring(re.search(r"<svg.*</svg>", html, re.S).group(0))

@pytest.mark.parametrize("arr", ["counter", "parallel", "shell_1_2"])
def test_hx_animation_is_valid_labelled_and_animated(arr):
    h = an.animated_hx_html(arr, 180, 120, 30, 70)
    _svg(h)
    assert h.count("<animateMotion") >= 20 and "pauseAnimations" in h and 'id="pp"' in h and 'id="sp"' in h
    for label in ("Hot in 180 °C", "Hot out 120 °C", "Cold in 30 °C", "Cold out 70 °C", "Shell (hot fluid)", "Tube sheet", "Shell inlet nozzle", "Shell outlet nozzle", "Channel head"):
        assert label in h
    assert ("Return head" in h and "Baffle" in h) == (arr == "shell_1_2")

def test_hx_animation_cold_flows_in_the_right_direction():
    assert 'path="M760,160 L40,160"' in an.animated_hx_html("counter", 180, 120, 30, 70)       # cold enters on the right
    assert 'path="M40,160 L760,160"' in an.animated_hx_html("parallel", 180, 120, 30, 70)      # cold enters on the left
    assert 'path="M230,40 L230,115' in an.animated_hx_html("counter", 180, 120, 30, 70)         # hot enters at the top-left nozzle

def test_pipe_animation_labels_and_pump():
    h = an.animated_pipe_html(180, 2.4, 100, 200, 8, 10, 19.8, 9.6, 126000)
    _svg(h)
    for label in ("Pump", "Suction tank", "Discharge tank", "Valves and fittings (ΣK = 8)", "Static head 10 m", "D = 100 mm, L = 200 m", "shaft power = 9.60 kW"):
        assert label in h
    assert 'calcMode="discrete"' in h and "animateTransform" in h                                   # pressure colour change and spinning impeller
    g = an.animated_pipe_html(50, 1.0, 100, 100, 5, 4, has_pump=False, static_label="Available head")
    assert "Available head 4 m" in g and ">Pump<" not in g and "animateTransform" not in g

def test_faster_flow_moves_the_dots_faster():
    def dur(v):
        return float(re.search(r'<animateMotion data-dur="([\d.]+)"', an.animated_pipe_html(100, v, 100, 100, 5, 4)).group(1))
    assert dur(0.5) > dur(2.0) > dur(4.0)
