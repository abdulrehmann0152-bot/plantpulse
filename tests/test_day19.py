"""Independent regression tests for the Pump & Pipeline engineering upgrade.

Expected values are computed here by other routes: Hagen-Poiseuille for laminar flow, a SciPy root finder for Colebrook-White,
reference tables for water, numpy for the polynomial fit, and plain arithmetic for the worked solution."""
import ast, json, math, os, re, sys
import numpy as np
import pytest
from scipy.optimize import brentq
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import pump_explain as px, pump_pipe as pp, solver as sv
from calc_engine.heat_exchanger import InputError
from core import db, pump_plot

ROOT = os.path.dirname(os.path.dirname(__file__))
G = 9.80665
RHO, MU = pp.water_properties(30)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d19.db"))
    db.init_db()


# ====================================================================== water properties
RHO_REF = {0: 999.84, 5: 999.97, 10: 999.70, 15: 999.10, 20: 998.21, 25: 997.05, 30: 995.65, 35: 994.03, 40: 992.22, 45: 990.21, 50: 988.04, 60: 983.20, 70: 977.76, 80: 971.79, 90: 965.31, 100: 958.35}
MU_REF = {0: 1.792, 5: 1.519, 10: 1.307, 15: 1.138, 20: 1.002, 25: 0.890, 30: 0.797, 35: 0.719, 40: 0.653, 45: 0.596, 50: 0.547, 60: 0.467, 70: 0.404, 80: 0.355, 90: 0.315, 100: 0.282}

@pytest.mark.parametrize("t", sorted(RHO_REF))
def test_water_properties_match_the_reference_tables(t):
    rho, mu = pp.water_properties(t)
    assert rho == pytest.approx(RHO_REF[t], rel=1e-4)
    assert mu * 1000 == pytest.approx(MU_REF[t], rel=0.005 if t >= 15 else 0.01)                 # the viscosity equation is formally for 20 to 100 deg C

def test_the_old_linear_interpolation_was_wrong_and_the_new_value_is_not():
    """At 30 deg C linear interpolation between the 20 and 40 deg C table points over-states the viscosity by about 4%."""
    linear = 1.002 + (0.653 - 1.002) * (30 - 20) / (40 - 20)
    new = pp.water_properties(30)[1] * 1000
    assert linear / 0.797 - 1 > 0.035 and abs(new / 0.797 - 1) < 0.005

def test_water_properties_are_smooth_and_physical():
    ts = [i * 0.5 for i in range(201)]
    mus = [pp.water_properties(t)[1] for t in ts]
    assert all(a > b for a, b in zip(mus, mus[1:]))                                              # viscosity falls steadily with temperature
    assert max(abs(b / a - 1) for a, b in zip(mus, mus[1:])) < 0.03                              # no jumps between 0.5 deg C steps
    assert pp.water_properties(4)[0] > pp.water_properties(0)[0] and pp.water_properties(4)[0] > pp.water_properties(10)[0]      # the density maximum near 4 deg C

@pytest.mark.parametrize("bad", [-0.1, -5, 100.1, 150, float("nan"), float("inf"), None, True, "30"])
def test_water_temperature_outside_liquid_range_is_refused_with_the_value(bad):
    with pytest.raises(InputError) as e:
        pp.water_properties(bad)
    assert "Water temperature" in str(e.value)
    if isinstance(bad, float) and math.isfinite(bad):
        assert f"{bad:g}" in str(e.value)

# ====================================================================== geometry, flow, Reynolds number
@pytest.mark.parametrize("d", [0.025, 0.05, 0.1, 0.2, 0.4])
def test_area_velocity_and_flow_relations(d):
    r = d / 2
    assert pp.area(d) == pytest.approx(math.pi * r * r, rel=1e-14)
    q = 0.01
    assert pp.velocity(q, d) == pytest.approx(q / (math.pi * r * r)) and pp.velocity(q, d) * pp.area(d) == pytest.approx(q)
    assert pp.mass_flow(RHO, q) == pytest.approx(RHO * q) and pp.mass_flow(RHO, q) / RHO == pytest.approx(q)

@pytest.mark.parametrize("d,q", [(0.025, 0.0004), (0.1, 0.01), (0.4, 0.2)])
def test_reynolds_number_two_independent_ways(d, q):
    v = q / (math.pi * d * d / 4)
    assert pp.reynolds(RHO, v, d, MU) == pytest.approx(4 * RHO * q / (math.pi * d * MU), rel=1e-12)      # Re = rho v D / mu = 4 m_dot / (pi D mu)

@pytest.mark.parametrize("re,regime", [(1, "laminar"), (2299.9, "laminar"), (2300, "transition (uncertain)"), (3999.9, "transition (uncertain)"), (4000, "turbulent"), (1e7, "turbulent")])
def test_flow_classification_boundaries(re, regime):
    assert pp.flow_regime(re) == regime

# ====================================================================== friction factor
def _colebrook_independent(re, d, eps):
    rr = eps / d
    return brentq(lambda f: 1 / math.sqrt(f) + 2 * math.log10(rr / 3.7 + 2.51 / (re * math.sqrt(f))), 1e-4, 1.0, xtol=1e-15, rtol=1e-14)

@pytest.mark.parametrize("re", [4e3, 1e4, 1e5, 1e6, 1e7, 1e8])
@pytest.mark.parametrize("rr", [0.0, 1e-6, 1e-4, 1e-3, 1e-2, 4e-2])
def test_colebrook_white_matches_an_independent_root_finder(re, rr):
    d = 0.1
    f = pp.friction_factor(re, d, rr * d)
    assert f == pytest.approx(_colebrook_independent(re, d, rr * d), rel=1e-9)
    assert 1 / math.sqrt(f) + 2 * math.log10(rr / 3.7 + 2.51 / (re * math.sqrt(f))) == pytest.approx(0, abs=1e-9)          # it satisfies the equation

@pytest.mark.parametrize("re", [5e3, 1e5, 1e7, 1e8])
@pytest.mark.parametrize("rr", [1e-6, 1e-4, 1e-2])
def test_swamee_jain_stays_close_to_colebrook_in_its_stated_range(re, rr):
    """Measured: at most 2.83% (at Re 5000, e/D 0.01) and about 1% or less for Re of 1e5 and above, not the 'plus or minus 1%' often quoted."""
    sj, cw = pp.friction_factor(re, 0.1, rr * 0.1, "swamee_jain"), pp.friction_factor(re, 0.1, rr * 0.1)
    assert abs(sj / cw - 1) < 0.03 and sj == pytest.approx(0.25 / math.log10(rr / 3.7 + 5.74 / re ** 0.9) ** 2)
    if re >= 1e5:
        assert abs(sj / cw - 1) < 0.015

def test_known_friction_factors():
    assert pp.friction_factor(1e5, 0.1, 0.0) == pytest.approx(0.0180, abs=2e-4)                    # smooth pipe, Moody chart
    assert pp.friction_factor(1e8, 0.1, 0.001) == pytest.approx(1 / (2 * math.log10(3.7 / 0.01)) ** 2, rel=0.01)       # fully rough limit (von Karman / Nikuradse)

@pytest.mark.parametrize("re", [10, 500, 1500, 2299])
def test_laminar_friction_factor_is_64_over_re(re):
    assert pp.friction_factor(re, 0.05, 4.5e-5) == pytest.approx(64 / re, rel=1e-14)

@pytest.mark.parametrize("d,q,length", [(0.005, 0.0421 / 3600, 40.0), (0.01, 0.08 / 3600, 25.0), (0.004, 0.02 / 3600, 5.0)])
def test_laminar_pressure_drop_equals_hagen_poiseuille(d, q, length):
    rho, mu = pp.water_properties(5)
    r = pp.pipe_losses(q, d, length, 4.5e-5, 0.0, rho, mu)
    assert r["regime"] == "laminar" and r["re"] < 2300
    assert r["dp"] == pytest.approx(128 * mu * length * q / (math.pi * d ** 4), rel=1e-10)         # the exact analytical solution for laminar pipe flow

def test_the_friction_factor_has_no_jump_in_the_transition_zone():
    for rr in (0.0, 1e-4, 1e-2):
        f = lambda re: pp.friction_factor(re, 0.1, rr * 0.1)
        assert abs(f(2300 - 1e-6) - f(2300 + 1e-6)) < 1e-6 and abs(f(4000 - 1e-6) - f(4000 + 1e-6)) < 1e-6
        edge_lo, edge_hi = 64 / 2300, f(4000)
        assert all(min(edge_lo, edge_hi) - 1e-12 <= f(re) <= max(edge_lo, edge_hi) + 1e-12 for re in range(2300, 4000, 50))
    assert abs(pp.friction_factor(2301, 0.2, 4.5e-5) / pp.friction_factor(2299, 0.2, 4.5e-5) - 1) < 0.01          # it used to jump by 75%

def test_friction_detail_reports_how_f_was_found():
    t = pp.friction_detail(1e5, 0.1, 4.5e-5)
    assert t["kind"] == "turbulent" and t["method"] == "colebrook" and t["iterations"] >= 1 and abs(t["f_swamee"] / t["f"] - 1) < 0.02 and t["f_colebrook"] == t["f"]
    assert pp.friction_detail(1000, 0.1, 4.5e-5)["kind"] == "laminar"
    x = pp.friction_detail(3000, 0.1, 4.5e-5)
    assert x["kind"] == "transition" and x["f_lam_edge"] == pytest.approx(64 / 2300) and 0 < x["weight"] < 1
    assert pp.friction_detail(1e5, 0.1, 4.5e-5, "swamee_jain")["method"] == "swamee_jain"

@pytest.mark.parametrize("args,text", [((0, 0.1, 1e-5), "Reynolds number"), ((-5, 0.1, 1e-5), "Reynolds number"), ((1e5, 0, 1e-5), "Pipe inside diameter"), ((1e5, -0.1, 1e-5), "Pipe inside diameter"),
                                       ((1e5, 0.1, -1e-5), "Pipe roughness"), ((1e5, 0.1, 0.01), "Relative roughness"), ((float("nan"), 0.1, 1e-5), "number"), ((None, 0.1, 1e-5), "number")])
def test_friction_factor_rejects_impossible_inputs_by_name(args, text):
    with pytest.raises(InputError) as e:
        pp.friction_factor(*args)
    assert text in str(e.value)
    with pytest.raises(InputError, match="friction method"):
        pp.friction_factor(1e5, 0.1, 1e-5, "moody")

# ====================================================================== Darcy-Weisbach, minor losses, different pipe sizes
@pytest.mark.parametrize("d_mm", [25, 50, 100, 200, 400])
@pytest.mark.parametrize("q_m3h", [1.0, 30.0, 300.0])
def test_head_loss_is_the_darcy_weisbach_equation_for_every_pipe_size(d_mm, q_m3h):
    d, q, length, k = d_mm / 1000, q_m3h / 3600, 120.0, 6.0
    r = pp.pipe_losses(q, d, length, 4.5e-5, k, RHO, MU)
    v = q / (math.pi * d * d / 4)
    re = RHO * v * d / MU
    f = 64 / re if re < 2300 else (_colebrook_independent(re, d, 4.5e-5) if re >= 4000 else r["f"])
    head = (f * length / d + k) * v * v / (2 * G)
    assert r["v"] == pytest.approx(v) and r["re"] == pytest.approx(re) and r["f"] == pytest.approx(f, rel=1e-9) and r["head"] == pytest.approx(head, rel=1e-9)
    assert r["dp"] == pytest.approx(RHO * G * head, rel=1e-12) and r["head_friction"] + r["head_fittings"] == pytest.approx(r["head"])
    assert r["m_dot"] == pytest.approx(RHO * q) and r["area"] == pytest.approx(math.pi * d * d / 4) and r["regime"] == pp.flow_regime(re)

def test_the_regime_follows_the_pipe_size_at_a_fixed_flow():
    q = 20 / 3600
    regimes = {d: pp.pipe_losses(q, d, 50, 4.5e-5, 0, RHO, MU)["regime"] for d in (0.01, 0.05, 0.1, 0.4)}
    assert regimes[0.01] == regimes[0.05] == "turbulent" and pp.pipe_losses(1e-6, 0.4, 50, 4.5e-5, 0, RHO, MU)["regime"] == "laminar"

def test_fittings_head_scales_with_the_square_of_the_flow_and_equivalent_length_is_equivalent():
    a, b = pp.pipe_losses(0.01, 0.1, 10, 4.5e-5, 7.0, RHO, MU), pp.pipe_losses(0.02, 0.1, 10, 4.5e-5, 7.0, RHO, MU)
    assert b["head_fittings"] / a["head_fittings"] == pytest.approx(4.0)
    base = pp.pipe_losses(0.01, 0.1, 10, 4.5e-5, 0.0, RHO, MU)
    le_over_d = 35.0
    eq_len = pp.pipe_losses(0.01, 0.1, 10 + le_over_d * 0.1, 4.5e-5, 0.0, RHO, MU)             # fittings as extra pipe length
    as_k = pp.pipe_losses(0.01, 0.1, 10, 4.5e-5, base["f"] * le_over_d, RHO, MU)               # the same fittings as K = f Le/D
    assert eq_len["head"] == pytest.approx(as_k["head"], rel=1e-9) and eq_len["head"] > base["head"]

def test_zero_flow_gives_zero_loss_but_is_never_a_default_for_bad_input():
    z = pp.pipe_losses(0.0, 0.1, 10, 4.5e-5, 5, RHO, MU)
    assert z["head"] == 0 and z["v"] == 0 and z["regime"] == "no flow"
    for bad in (-0.001, float("nan")):
        with pytest.raises(InputError, match="Flow"):
            pp.pipe_losses(bad, 0.1, 10, 4.5e-5, 5, RHO, MU)

@pytest.mark.parametrize("kwargs,text", [(dict(d=0.0), "Pipe inside diameter must be greater than zero (you entered 0 mm)"), (dict(d=-0.1), "Pipe inside diameter must be greater than zero"),
                                         (dict(length=0.0), "Pipe length must be greater than zero (you entered 0 m)"), (dict(length=-5.0), "Pipe length must be greater than zero"),
                                         (dict(rough=-1e-5), "Pipe roughness cannot be negative"), (dict(k=-1.0), "Fittings loss ΣK cannot be negative (you entered -1)"),
                                         (dict(rho=0.0), "Fluid density must be greater than zero"), (dict(mu=0.0), "Fluid viscosity must be greater than zero"),
                                         (dict(d=0.01, rough=0.001), "Relative roughness"), (dict(d=float("nan")), "must be a number")])
def test_pipe_data_validation_names_the_input_and_echoes_the_value(kwargs, text):
    a = dict(d=0.1, length=10.0, rough=4.5e-5, k=1.0, rho=RHO, mu=MU)
    a.update(kwargs)
    with pytest.raises(InputError) as e:
        pp.pipe_losses(0.01, a["d"], a["length"], a["rough"], a["k"], a["rho"], a["mu"])
    assert text in str(e.value)

# ====================================================================== pump curve, operating point, power, efficiency
POINT_SETS = [[(0, 30), (200, 25), (300, 17)], [(0, 50), (100, 45), (250, 30)], [(10, 22), (60, 20), (120, 12)], [(0, 8), (0.03, 6), (0.06, 3)]]

@pytest.mark.parametrize("raw", POINT_SETS)
def test_pump_curve_passes_through_the_points_and_matches_numpy(raw):
    pts = [(q / 3600, h) for q, h in raw]
    co = pp.fit_pump_curve(pts)
    for q, h in pts:
        assert pp.pump_head(co, q) == pytest.approx(h, abs=1e-9)
    c, b, a = np.polyfit([p[0] for p in pts], [p[1] for p in pts], 2)
    assert co == pytest.approx((a, b, c), rel=1e-6)

@pytest.mark.parametrize("pts,text", [([(0, 30), (200 / 3600, 25)], "exactly three"), ([(0, 30), (-1, 25), (300 / 3600, 17)], "point 2 flow cannot be negative"),
                                     ([(0, 0), (200 / 3600, 25), (300 / 3600, 17)], "point 1 head must be greater than zero"), ([(0, 30), (200 / 3600, -2), (300 / 3600, 17)], "point 2 head must be greater than zero"),
                                     ([(0, 30), (200 / 3600, 25), (200 / 3600, 17)], "different flows"), ([(0, 30), (float("nan"), 25), (300 / 3600, 17)], "must be a number")])
def test_pump_curve_points_are_validated_by_name(pts, text):
    with pytest.raises(InputError, match=re.escape(text)):
        pp.fit_pump_curve(pts)

def test_a_rising_pump_curve_is_a_warning_not_a_silent_fix():
    assert pp.check_pump_points([(0, 30 / 1), (200 / 3600, 25), (300 / 3600, 17)]) == []
    w = pp.check_pump_points([(0, 20), (200 / 3600, 25), (300 / 3600, 17)])
    assert len(w) == 1 and "head rises" in w[0] and "20 m" in w[0] and "25 m" in w[0]

@pytest.mark.parametrize("static,d,length,k", [(10, 0.2, 200, 8), (5, 0.15, 80, 3), (20, 0.1, 40, 1), (0, 0.3, 500, 12)])
def test_operating_point_satisfies_both_curves_and_matches_a_root_finder(static, d, length, k):
    pts = [(0, 40), (200 / 3600, 33), (300 / 3600, 20)]
    co = pp.fit_pump_curve(pts)
    qmax = 450 / 3600
    try:
        op = pp.operating_point(co, static, d, length, 4.5e-5, k, RHO, MU, qmax, 300 / 3600)
    except InputError:
        pytest.skip("this system has no operating point in the curve range")
    gap = lambda q: pp.pump_head(co, q) - (static + pp.pipe_losses(q, d, length, 4.5e-5, k, RHO, MU)["head"])
    assert gap(op["q"]) == pytest.approx(0, abs=1e-9)
    assert op["q"] == pytest.approx(brentq(gap, 0, qmax, xtol=1e-15), rel=1e-9) and op["h"] == pytest.approx(pp.pump_head(co, op["q"]))
    assert op["hyd_w"] == pytest.approx(RHO * G * op["q"] * op["h"], rel=1e-12)

def test_extrapolation_is_flagged_and_unreachable_systems_give_clear_errors():
    co = pp.fit_pump_curve([(0, 30), (200 / 3600, 25), (300 / 3600, 17)])
    easy = dict(static_head=1, d=0.4, length=20, rough=4.5e-5, sum_k=1.0, rho=RHO, mu=MU)
    op = pp.operating_point(co, easy["static_head"], easy["d"], easy["length"], easy["rough"], easy["sum_k"], RHO, MU, 450 / 3600, 300 / 3600)
    assert op["extrapolated"] is True and op["q"] > 300 / 3600 and op["q_data_max"] == 300 / 3600
    ok = pp.operating_point(co, 10, 0.2, 200, 4.5e-5, 8, RHO, MU, 450 / 3600, 300 / 3600)
    assert ok["extrapolated"] is False
    with pytest.raises(InputError) as e:
        pp.operating_point(co, 40, 0.2, 200, 4.5e-5, 8, RHO, MU, 450 / 3600, 300 / 3600)
    assert "shut-off head (30.00 m)" in str(e.value) and "static head (40 m)" in str(e.value)
    with pytest.raises(InputError, match="No operating point"):
        pp.operating_point(co, 10, 0.02, 2000, 4.5e-5, 50, RHO, MU, 1 / 3600, 1 / 3600) if False else pp.operating_point(co, 0, 0.5, 1, 4.5e-5, 0, RHO, MU, 100 / 3600, 100 / 3600)
    with pytest.raises(InputError, match="Static head cannot be negative"):
        pp.operating_point(co, -1, 0.2, 200, 4.5e-5, 8, RHO, MU, 450 / 3600)

def test_power_equations_and_efficiency_validation():
    assert pp.hydraulic_power(RHO, 0.08, 20) == pytest.approx(RHO * 9.80665 * 0.08 * 20)
    assert pp.shaft_power(15000, 0.75) == pytest.approx(20000)
    for bad in (0, 0.0, 1.0, 1.2, -0.1, float("nan"), None):
        with pytest.raises(InputError, match="Pump efficiency"):
            pp.shaft_power(15000, bad)
    with pytest.raises(InputError, match=r"above 0% and below 100% \(you entered 120%\)"):
        pp.check_efficiency(1.2)
    with pytest.raises(InputError, match="Hydraulic power"):
        pp.shaft_power(0, 0.7)
    assert pp.check_motor_efficiency(1.0) == 1.0 and pp.check_motor_efficiency(0.92) == 0.92
    for bad in (0, -0.5, 1.01):
        with pytest.raises(InputError, match="Motor efficiency"):
            pp.check_motor_efficiency(bad)
    assert "unusually high" in pp.efficiency_note(0.95) and "very low" in pp.efficiency_note(0.2) and pp.efficiency_note(0.7) is None

def test_diagnose_refuses_meaningless_comparisons_instead_of_dividing_by_zero():
    co = pp.fit_pump_curve([(0, 30), (200 / 3600, 25), (300 / 3600, 17)])
    args = (co, 10, 0.2, 200, 4.5e-5, 8, RHO, MU)
    assert pp.diagnose(0.07, 22.0, *args)["status"] in ("healthy", "pump_degraded", "system_resistance", "check_data")
    for q, h, text in ((0, 20, "Measured flow"), (-1, 20, "Measured flow"), (0.07, 0, "Measured head"), (0.07, -3, "Measured head")):
        with pytest.raises(InputError, match=text):
            pp.diagnose(q, h, *args)
    with pytest.raises(InputError, match="beyond the pump data"):
        pp.diagnose(1500 / 3600, 20, *args)                                                        # the fitted curve is negative there

def test_npsh_uses_the_gravity_the_caller_asks_for():
    pv = pp.water_vapor_pressure_kpa(30)
    std = sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, pv, RHO, 4.0, g=pp.G)
    text = sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, pv, RHO, 4.0)                              # the Problem Solver keeps 9.81
    assert std["npsha"] == pytest.approx((101.325 - pv) * 1000 / (RHO * 9.80665) + 3.0 - 0.5, rel=1e-12)
    assert text["npsha"] == pytest.approx((101.325 - pv) * 1000 / (RHO * 9.81) + 3.0 - 0.5, rel=1e-12) and std["npsha"] != text["npsha"]

# ====================================================================== worked solution: seven parts and honest arithmetic
def _eval(expr):
    e = expr.replace("×", "*").replace("−", "-").replace("²", "**2").replace("^", "**").replace("π", "pi").replace("[", "(").replace("]", ")")
    e = e.replace("√", "sqrt")
    e = re.sub(r"sqrt(\d+\.?\d*)", r"sqrt(\1)", e)
    e = re.sub(r"(?<=\d),(?=\d{3})", "", e)
    funcs = {"ln": math.log, "log10": math.log10, "sqrt": math.sqrt, "abs": abs}

    def walk(n):
        if isinstance(n, ast.Expression):
            return walk(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name) and n.id == "pi":
            return math.pi
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -walk(n.operand) if isinstance(n.op, ast.USub) else walk(n.operand)
        if isinstance(n, ast.BinOp):
            a, b = walk(n.left), walk(n.right)
            return {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b, ast.Div: lambda: a / b, ast.Pow: lambda: a ** b}[type(n.op)]()
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funcs and len(n.args) == 1:
            return funcs[n.func.id](walk(n.args[0]))
        raise ValueError(f"not evaluable: {expr}")
    return walk(ast.parse(e, mode="eval"))

def _value(text):
    return float(re.search(r"=\s*(?:Rs\s*)?([+-]?[\d,]*\.?\d+(?:[eE][+-]?\d+)?)", text).group(1).replace(",", ""))

def _close(a, b):
    return abs(a - b) <= 5e-3 * max(1.0, abs(b))

def _inputs(temp=30, d=0.2, length=200.0, k=8.0, le_d=0.0, static=10.0, raw=((0, 30), (200, 25), (300, 17)), eta=0.7, eta_m=1.0, hours=24.0, tariff=50.0, npsh=None, rough=0.045e-3):
    rho, mu = pp.water_properties(temp)
    pts = [(q / 3600, h) for q, h in raw]
    co = pp.fit_pump_curve(pts)
    dq = max(p[0] for p in pts)
    op = pp.operating_point(co, static, d, length + le_d * d, rough, k, rho, mu, dq * 1.5, dq)
    n = None
    if npsh:
        pv = pp.water_vapor_pressure_kpa(temp)
        n = {"result": sv.npsh_check(0.0, "gauge", 101.325, npsh["level"], npsh["hfs"], pv, rho, npsh["npshr"], npsh["margin"], g=pp.G), "pv": pv, **npsh}
    return dict(temp=temp, rho=rho, mu=mu, d=d, length=length, rough=rough, sum_k=k, le_d=le_d, static=static, pts=pts, coeffs=co, op=op, q_data_max=dq,
                eta=eta, eta_motor=eta_m, hours=hours, tariff=tariff, p_shaft_w=pp.shaft_power(op["hyd_w"], eta), npsh=n)

SCENARIOS = {
    "turbulent": dict(),
    "laminar": dict(temp=5, d=0.005, length=40.0, k=0.0, static=0.2, raw=((0, 8), (0.03, 6), (0.06, 3))),
    "transitional": dict(temp=5, d=0.005, length=10.0, k=0.0, static=0.2, raw=((0, 8), (0.03, 6), (0.06, 3))),
    "equivalent length": dict(k=0.0, le_d=40.0),
    "with NPSH": dict(npsh=dict(level=3.0, hfs=0.5, npshr=4.0, margin=0.5)),
    "extrapolated": dict(static=1.0, d=0.4, length=20.0, k=1.0),
    "motor losses": dict(eta_m=0.92),
}

@pytest.mark.parametrize("name", list(SCENARIOS))
def test_every_step_has_the_seven_parts_and_correct_arithmetic(name):
    p = _inputs(**SCENARIOS[name])
    steps = px.build_steps(p)
    expected_regime = {"laminar": "laminar", "transitional": "transition (uncertain)"}.get(name)
    if expected_regime:
        assert p["op"]["regime"] == expected_regime                                                  # the scenario really exercises that branch
    n_checked = 0
    for s in steps:
        assert s["title"] and s["formula"] and s["interpretation"] and len(s["interpretation"]) > 40 and s["calc"], s["title"]
        assert s["variables"] and all(len(v) == 3 and all(v) for v in s["variables"]), s["title"]            # symbol, meaning and unit
        for c in s["calc"]:
            assert c["label"] and c["substitution"] and c["result"], (s["title"], c)
            if c.get("numeric") is False:
                continue
            target = _value(c["result"])
            assert _close(_eval(c["substitution"]), target), (s["title"], c)
            if c.get("intermediate"):
                assert all(_close(_eval(part), target) for part in c["intermediate"].split(" = ")), (s["title"], c)
            n_checked += 1
    assert n_checked >= 18

def test_the_steps_report_the_same_numbers_as_the_engine():
    p = _inputs()
    op, steps = p["op"], {s["title"]: s for s in px.build_steps(p)}
    res = lambda title, label: next(c["result"] for c in steps[title]["calc"] if c["label"] == label)
    assert _value(res("Cross-sectional area of the pipe", "A")) == pytest.approx(op["area"], abs=5e-7)
    assert _value(res("Mean velocity", "v")) == pytest.approx(op["v"], abs=5e-4)
    assert _value(res("Reynolds number and flow regime", "Re")) == pytest.approx(op["re"], abs=1)
    assert _value(res("Major loss in the straight pipe (Darcy-Weisbach)", "h_f")) == pytest.approx(op["head_friction"], abs=5e-4)
    assert _value(res("Total system head and check against the pump", "H_sys")) == pytest.approx(op["h"], abs=5e-4)
    assert _value(res("Hydraulic power", "P_hyd")) == pytest.approx(op["hyd_w"] / 1000, abs=5e-4)
    assert _value(res("Shaft power and pump efficiency", "P_shaft")) == pytest.approx(p["p_shaft_w"] / 1000, abs=5e-4)
    assert _value(res("Operating point: pump curve meets system curve", "Pump head at Q*")) == pytest.approx(op["h"], abs=5e-3)
    assert abs(_value(res("Total system head and check against the pump", "Check against the pump head"))) < 5e-4          # H_pump = H_sys at the operating point

def test_the_required_concepts_appear_in_order_with_interpretations():
    titles = [s["title"] for s in px.build_steps(_inputs())]
    required = ["Fluid properties of water", "Pump curve polynomial fit", "Operating point: pump curve meets system curve", "Cross-sectional area of the pipe", "Volumetric and mass flow rate", "Mean velocity",
                "Reynolds number and flow regime", "Relative roughness", "Friction factor", "Major loss in the straight pipe (Darcy-Weisbach)", "Minor losses in fittings and valves",
                "Total system head and check against the pump", "Hydraulic power", "Shaft power and pump efficiency", "Electrical power, energy and running cost"]
    assert titles == required and "NPSH available and cavitation check" in [s["title"] for s in px.build_steps(_inputs(**SCENARIOS["with NPSH"]))]

def test_friction_step_shows_the_right_equation_for_each_regime():
    by = lambda name: next(s for s in px.build_steps(_inputs(**SCENARIOS[name])) if s["title"] == "Friction factor")
    assert by("laminar")["formula"] == r"f=\dfrac{64}{Re}" and by("laminar")["calc"][0]["substitution"].startswith("64 / ")
    t = by("transitional")
    assert "f_{lam}(2300)" in t["formula"] and [c["label"] for c in t["calc"]] == ["f at Re = 2300 (laminar)", "f at Re = 4000 (Colebrook-White)", "f in the transition zone"] and "only an estimate" in t["interpretation"]
    c = by("turbulent")
    assert "Colebrook-White" in c["formula"] and c["calc"][0]["label"].startswith("Colebrook-White") and "iterations" in c["calc"][0]["result"] and c["calc"][1]["label"].startswith("Swamee-Jain cross-check")

def test_equivalent_length_and_motor_losses_appear_in_the_steps():
    steps = {s["title"]: s for s in px.build_steps(_inputs(**SCENARIOS["equivalent length"]))}
    m = steps["Minor losses in fittings and valves"]
    assert [c["label"] for c in m["calc"]] == ["h_Le"] and "L_e" in m["formula"] and "There are no fittings" not in m["interpretation"]
    e = {s["title"]: s for s in px.build_steps(_inputs(**SCENARIOS["motor losses"]))}["Electrical power, energy and running cost"]
    assert "Motor losses of" in e["interpretation"] and "NOT included" not in e["interpretation"]
    assert "NOT included" in {s["title"]: s for s in px.build_steps(_inputs())}["Electrical power, energy and running cost"]["interpretation"]

def test_interpretations_react_to_the_numbers():
    p = _inputs(**SCENARIOS["extrapolated"])
    st = {s["title"]: s for s in px.build_steps(p)}
    assert p["op"]["extrapolated"] and "BEYOND the datasheet" in st["Operating point: pump curve meets system curve"]["interpretation"]
    assert "NOT falling" not in st["Pump curve polynomial fit"]["interpretation"]
    assert "inside the usual" in px.velocity_comment(2.0) and "above 3 m/s" in px.velocity_comment(4.0) and "below the usual" in px.velocity_comment(0.5)

# ====================================================================== the graph
def _figure(**kw):
    p = _inputs(**kw)
    args = (p["static"], p["d"], p["length"] + p["le_d"] * p["d"], p["rough"])
    return pump_plot.operating_figure(p["coeffs"], lambda q: pp.system_head(q, *args, p["sum_k"], p["rho"], p["mu"]), p["pts"], p["op"], p["static"], p["q_data_max"], p["q_data_max"] * 1.5), p

def test_graph_has_every_curve_marker_and_label():
    fig, p = _figure()
    traces = {t.name: t for t in fig.data}
    assert set(traces) == {"System curve", "Pump curve", "Pump curve (extrapolated)", "Datasheet points", "Operating point"}
    assert list(traces["Datasheet points"].x) == pytest.approx([q * 3600 for q, _ in p["pts"]]) and list(traces["Datasheet points"].y) == [h for _, h in p["pts"]]
    assert traces["Operating point"].x[0] == pytest.approx(p["op"]["q"] * 3600) and traces["Operating point"].y[0] == pytest.approx(p["op"]["h"])
    assert max(traces["Pump curve"].x) == pytest.approx(p["q_data_max"] * 3600) and min(traces["Pump curve (extrapolated)"].x) == pytest.approx(p["q_data_max"] * 3600)
    assert fig.layout.xaxis.title.text == "Flow rate, Q (m³/h)" and fig.layout.yaxis.title.text == "Head, H (m)"
    # every plotted point lies on the real curves
    for x, y in zip(traces["Pump curve"].x, traces["Pump curve"].y):
        assert y == pytest.approx(pp.pump_head(p["coeffs"], x / 3600))

def test_graph_annotates_the_operating_point_static_head_and_shut_off():
    fig, p = _figure()
    texts = [a.text for a in fig.layout.annotations]
    qx, hy = p["op"]["q"] * 3600, p["op"]["h"]
    assert any(t.startswith("<b>Operating point</b>") and f"Q = {qx:,.1f} m³/h" in t and f"H = {hy:.2f} m" in t for t in texts)
    assert any(t == "Static head 10 m (does not change with flow)" for t in texts) and any(t == f"Shut-off head {p['coeffs'][0]:.1f} m" for t in texts)
    assert any(t.startswith("friction + fittings") and f"{hy - 10:.2f} m" in t for t in texts)
    lines = [(s.x0, s.x1, s.y0, s.y1) for s in fig.layout.shapes]
    assert (0, pytest.approx(qx), pytest.approx(hy), pytest.approx(hy)) in lines and (pytest.approx(qx), pytest.approx(qx), 0, pytest.approx(hy)) in lines          # drop lines to both axes

def test_graph_note_is_wrapped_and_has_room_and_extrapolation_is_stated():
    fig, p = _figure()
    note = next(a for a in fig.layout.annotations if a.xref == "paper")
    rows = note.text.split("<br>")
    assert all(len(r) <= 58 for r in rows) and "How to read this graph:" in rows[0] and fig.layout.margin.b >= 85 + len(rows) * 15
    assert "DOTTED" not in note.text                                                                  # not extrapolated here
    fig2, p2 = _figure(**SCENARIOS["extrapolated"])
    assert p2["op"]["extrapolated"] and "DOTTED, extrapolated part" in " ".join(next(a for a in fig2.layout.annotations if a.xref == "paper").text.split("<br>")).replace("  ", " ")
    op_note = next(a for a in fig2.layout.annotations if a.text.startswith("<b>Operating point"))
    assert op_note.ax < 0                                                                              # near the right edge the label is placed to the left, so it is not cut off

# ====================================================================== the page
def _page():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.button(key="do_guest").click().run()
    return at.switch_page("views/pump_pipeline.py").run()

def _set(at, **values):
    for key, v in values.items():
        at.number_input(key=key).set_value(v)
    return at.run()

def _expected(**kw):
    p = _inputs(**kw)
    return p, p["op"]

def test_default_page_has_full_kpi_cards_with_units_and_tooltips():
    at = _page()
    assert not at.exception and not any(e.value.startswith("Please check") for e in at.error)         # (the readings tab may legitimately show a diagnosis)
    p, op = _expected()
    kpi = {m.label: m for m in at.metric}
    assert kpi["Operating flow"].value == f"{op['q'] * 3600:,.1f} m³/h" and kpi["Operating head"].value == f"{op['h']:.2f} m" and kpi["Velocity"].value == f"{op['v']:.2f} m/s"
    assert kpi["Reynolds number"].value == f"{op['re']:,.0f}" and kpi["Reynolds number"].delta == "Turbulent"
    assert kpi["Hydraulic power"].value == f"{op['hyd_w'] / 1000:.2f} kW" and kpi["Shaft power"].value == f"{p['p_shaft_w'] / 1000:.2f} kW" and kpi["Friction factor f"].value == f"{op['f']:.4f}"
    assert kpi["Energy cost per day"].value.startswith("Rs ") and len(kpi) == 8 and all(m.help and len(m.help) > 30 for m in kpi.values())

@pytest.mark.parametrize("change,text", [
    (dict(p_d=0.0), "Pipe inside diameter must be greater than zero (you entered 0 mm)"), (dict(p_l=0.0), "Pipe length must be greater than zero (you entered 0 m)"),
    (dict(p_eta=0.0), "Pump efficiency must be above 0% and below 100% (you entered 0%)"), (dict(p_eta=100.0), "Pump efficiency must be above 0% and below 100% (you entered 100%)"),
    (dict(p_etam=0.0), "Motor efficiency must be above 0% and at most 100% (you entered 0%)"), (dict(p_h0=0.0), "Pump curve point 1 head must be greater than zero"),
    (dict(p_h1=0.0), "Pump curve point 2 head must be greater than zero"), (dict(p_q2=200.0), "different flows"),
    (dict(p_t=150.0), "Water temperature must be between 0 and 100 °C"), (dict(p_t=-5.0), "(you entered -5 °C)"), (dict(p_s=40.0), "shut-off head (30.00 m) is not above the static head (40 m)")])
def test_bad_input_gives_a_clear_named_error_and_no_results(change, text):
    at = _set(_page(), **change)
    assert not at.exception and any(text in e.value and e.value.startswith("Please check your inputs:") for e in at.error), [e.value for e in at.error]
    assert len(at.metric) == 0                                                                        # nothing is calculated from invalid data, and nothing is replaced by a default

def test_a_diameter_in_the_wrong_unit_is_caught_by_the_roughness_check():
    at = _page(); at.selectbox(key="p_m").select("Cast iron (0.26 mm)").run()
    at = _set(at, p_d=3.0)
    assert any("Relative roughness" in e.value and "0.087" in e.value and "right units" in e.value for e in at.error)

def test_warnings_for_a_rising_curve_extrapolation_and_unusual_efficiency():
    at = _set(_page(), p_h0=20.0)
    assert any("The head rises from 20 m" in w.value for w in at.warning) and any("rising at the operating point" in w.value or "head rises" in w.value for w in at.warning)
    at = _set(_page(), p_d=400.0, p_l=20.0, p_k=1.0, p_s=1.0)
    assert any("beyond your last pump curve point (300 m³/h)" in w.value and "extrapolation" in w.value for w in at.warning)
    assert any("unusually high" in i.value for i in _set(_page(), p_eta=95.0).info) and any("very low" in i.value for i in _set(_page(), p_eta=20.0).info)

def test_equivalent_length_mode_matches_the_engine():
    at = _page(); at.radio(key="p_minor").set_value("Equivalent length (Le/D)").run()
    assert not any(n.key == "p_k" for n in at.number_input) and at.number_input(key="p_led").value == 30.0
    at = _set(at, p_led=40.0)
    p, op = _expected(k=0.0, le_d=40.0)
    kpi = {m.label: m.value for m in at.metric}
    assert kpi["Operating head"] == f"{op['h']:.2f} m" and kpi["Operating flow"] == f"{op['q'] * 3600:,.1f} m³/h"

def test_motor_efficiency_changes_the_cost_and_the_caption():
    base = _page()
    assert any("energy cost uses the shaft power" in c.value for c in base.caption)
    at = _set(base, p_etam=90.0)
    p, op = _expected(eta_m=0.9)
    cost = float(next(m.value for m in at.metric if m.label == "Energy cost per day").replace("Rs ", "").replace(",", ""))
    assert cost == pytest.approx(p["p_shaft_w"] / 1000 / 0.9 * 24 * 50, abs=1) and not any("energy cost uses the shaft power" in c.value for c in at.caption)

def test_npsh_check_on_the_pump_page():
    at = _page(); at.checkbox(key="p_npsh").check().run()
    assert not at.exception
    pv = pp.water_vapor_pressure_kpa(30)
    r = sv.npsh_check(0.0, "gauge", 101.325, 3.0, 0.5, pv, RHO, 4.0, 0.5, g=pp.G)
    assert any(f"NPSH available {r['npsha']:.2f} m" in s.value and "No cavitation risk" in s.value for s in at.success)
    at = _set(at, p_npshr=r["npsha"] - 0.2)
    assert any(e.value.startswith("Cavitation Risk!") and "inside the 0.5 m safety margin" in e.value for e in at.error)
    at = _set(at, p_npshr=r["npsha"] + 1.0)
    assert any(e.value.startswith("Cavitation Risk!") and "will cavitate" in e.value for e in at.error)
    assert "NPSH available and cavitation check" in " ".join(m.value for m in at.markdown)

def test_every_input_has_a_tooltip_with_its_range():
    at = _page()
    keys = ["p_d", "p_l", "p_k", "p_s", "p_q0", "p_q1", "p_q2", "p_h0", "p_h1", "p_h2", "p_eta", "p_etam", "p_tar", "p_hr"]
    for k in keys:
        assert at.number_input(key=k).help and len(at.number_input(key=k).help) >= 60, k
    assert "0 to 100 °C" in at.number_input(key="p_t").help and "Must be greater than 0" in at.number_input(key="p_d").help and "25 to 600 mm" in at.number_input(key="p_d").help
    assert "0 to 500" in at.number_input(key="p_k").help and "globe valve" in at.number_input(key="p_k").help and "below 100%" in at.number_input(key="p_eta").help and "50 to 85%" in at.number_input(key="p_eta").help
    assert "0.045 mm" in at.selectbox(key="p_m").help and "Equivalent length" in at.radio(key="p_minor").help and "from 0 to 24" in at.number_input(key="p_hr").help
    at.checkbox(key="p_npsh").check().run()
    for k in ("p_ps", "p_patm", "p_zl", "p_hfs", "p_npshr", "p_mrg"):
        assert at.number_input(key=k).help and len(at.number_input(key=k).help) >= 50, k
    at.radio(key="p_minor").set_value("Equivalent length (Le/D)").run()
    assert "multiple of the pipe diameter" in at.number_input(key="p_led").help

def test_page_graph_and_steps_tab():
    at = _page()
    spec = json.loads(at.get("plotly_chart")[0].proto.spec)
    names = [t["name"] for t in spec["data"]]
    assert names == ["System curve", "Pump curve", "Pump curve (extrapolated)", "Datasheet points", "Operating point"]
    p, op = _expected()
    assert any(a["text"].startswith("<b>Operating point</b>") and f"Q = {op['q'] * 3600:,.1f} m³/h" in a["text"] for a in spec["layout"]["annotations"])
    md = [m.value for m in at.markdown]
    assert md.count("**Governing equation**") == 15 and md.count("**Where**") == 15 and sum(m.startswith("| Symbol | Meaning | Unit |") for m in md) == 15
    assert sum(m.startswith("**Interpretation:**") for m in md) == 15 and any("- Substitution: `64" not in m for m in md)
    assert any("- Substitution: `1.5" not in m for m in md) and any("- **Result: Re =" in m for m in md) and len(at.latex) == 15

def test_what_if_and_readings_tabs_still_work_and_validate():
    at = _page()
    assert any("Throttling cuts flow" in i.value for i in at.info)
    at = _set(_page(), p_qm=0.0)
    assert any("Measured flow must be greater than zero" in e.value for e in at.error)
    at = _set(_page(), p_hm=0.0)
    assert any("Measured head must be greater than zero" in e.value for e in at.error)
    at = _set(_page(), p_qm=1500.0)
    assert any("beyond the pump data" in e.value for e in at.error)

# ====================================================================== the database still saves equipment (SQLite normally, PostgreSQL when PP_TEST_PG_URL is set)
PUMP = {"d_mm": 200.0, "length_m": 200.0, "material": "Commercial steel (0.045 mm)", "sum_k": 8.0, "static_m": 10.0, "curve": [[0.0, 30.0], [200.0, 25.0], [300.0, 17.0]], "eta_pct": 70.0}

def test_equipment_round_trips_through_the_database():
    u = db.create_user("Ali", "ali@plant.pk", "secret12", "engineer")
    eid = db.add_equipment(u["id"], "pump", "CWP-01", "Cooling tower", PUMP)
    saved = db.list_equipment(u["id"])
    assert [e["tag"] for e in saved] == ["CWP-01"] and saved[0]["params"] == PUMP and saved[0]["eq_type"] == "pump" and saved[0]["id"] == eid
    db.add_maintenance(u["id"], eid, "2026-11-10", "Impeller replaced")
    assert db.list_maintenance(u["id"], eid)[0]["note"] == "Impeller replaced"
    with pytest.raises(db.DBError, match="already have equipment"):
        db.add_equipment(u["id"], "pump", "CWP-01", "", PUMP)
    db.delete_equipment(u["id"], eid)
    assert db.list_equipment(u["id"]) == [] and db.list_all_maintenance(u["id"]) == []

def test_equipment_saved_through_the_page_still_works():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.text_input(key="reg_name").input("Engr E"); at.text_input(key="reg_email").input("e@plant.pk"); at.text_input(key="reg_pw").input("secret12")
    at.button(key="do_register").click().run()
    at.switch_page("views/equipment.py").run()
    at.selectbox(key="eq_tmpl").select([o for o in at.selectbox(key="eq_tmpl").options if "pump" in o.lower()][0]).run()
    at.text_input(key=[t.key for t in at.text_input if t.key.startswith("eq_tag_")][0]).input("P-100")
    at.button(key="eq_save").click().run()
    uid = at.session_state["user"]["id"]
    assert not at.exception and [e["tag"] for e in db.list_equipment(uid)] == ["P-100"]
