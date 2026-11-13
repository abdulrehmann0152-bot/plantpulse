import math, os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import pump_pipe as pp
from calc_engine.heat_exchanger import InputError

# NOTE: hand-calculation and cross-method checks. Add textbook cases (book, page, answer) when available.
RHO, MU = pp.water_properties(30)
D, L, E, K, HS = 0.2, 200, 0.045e-3, 8, 10
COEFFS = pp.fit_pump_curve([(0, 30), (200 / 3600, 25), (300 / 3600, 17)])
ARGS = (HS, D, L, E)

def test_water_properties_table_points():
    assert pp.water_properties(20) == pytest.approx((998.21, 1.002e-3), rel=1e-4)       # Kell density and the viscosity reference point at 20 deg C
    rho, mu = pp.water_properties(30)
    assert 992.2 < rho < 998.2 and 0.653e-3 < mu < 1.002e-3

def test_water_temperature_out_of_range():
    with pytest.raises(InputError):
        pp.water_properties(120)

def test_reynolds_hand_calc():
    # 998.2*2*0.1/1.002e-3 = 199,242
    assert pp.reynolds(998.2, 2.0, 0.1, 1.002e-3) == pytest.approx(199242, rel=1e-3)

def test_laminar_friction_factor():
    assert pp.friction_factor(1000, 0.1, 0.0) == pytest.approx(0.064)

def test_regimes():
    assert pp.flow_regime(1000) == "laminar" and pp.flow_regime(3000).startswith("transition")
    assert pp.flow_regime(50000) == "turbulent"

def _colebrook(re, d, e):
    f = 0.02
    for _ in range(100):
        f = (-2 * math.log10(e / (3.7 * d) + 2.51 / (re * math.sqrt(f)))) ** -2
    return f

@pytest.mark.parametrize("re", [1e4, 1e5, 1e6, 1e7])
@pytest.mark.parametrize("rel_rough", [1e-5, 1e-3, 1e-2])
def test_swamee_jain_close_to_colebrook(re, rel_rough):
    # Swamee-Jain is an approximation; it can be ~2% off in very rough pipe at low Re.
    d = 0.1
    assert pp.friction_factor(re, d, rel_rough * d) == pytest.approx(_colebrook(re, d, rel_rough * d), rel=0.03)

def test_pipe_losses_match_darcy_weisbach():
    r = pp.pipe_losses(0.05, D, L, E, K, RHO, MU)
    v = 0.05 / (math.pi * D * D / 4)
    assert r["v"] == pytest.approx(v)
    assert r["head"] == pytest.approx((r["f"] * L / D + K) * v * v / (2 * 9.80665))
    assert r["dp"] == pytest.approx(RHO * 9.80665 * r["head"])

def test_zero_flow_gives_static_head_only():
    assert pp.system_head(0.0, *ARGS, K, RHO, MU) == pytest.approx(HS)

def test_pump_curve_fit_exact_coefficients():
    a, b, c = pp.fit_pump_curve([(0, 30), (1, 28), (2, 22)])
    assert (a, b, c) == pytest.approx((30, 0, -2))

def test_pump_curve_fit_needs_distinct_flows():
    with pytest.raises(InputError):
        pp.fit_pump_curve([(0, 30), (1, 28), (1, 22)])

def test_operating_point_is_intersection():
    op = pp.operating_point(COEFFS, *ARGS, K, RHO, MU, 450 / 3600)
    assert pp.pump_head(COEFFS, op["q"]) == pytest.approx(pp.system_head(op["q"], *ARGS, K, RHO, MU), abs=1e-6)
    assert 250 < op["q"] * 3600 < 330

def test_hydraulic_power_hand_calc():
    assert 1000 * 9.80665 * 0.05 * 20 == pytest.approx(9806.65)
    op = pp.operating_point(COEFFS, *ARGS, K, RHO, MU, 450 / 3600)
    assert op["hyd_w"] == pytest.approx(RHO * 9.80665 * op["q"] * op["h"])

def test_more_resistance_reduces_flow():
    a = pp.operating_point(COEFFS, *ARGS, K, RHO, MU, 450 / 3600)
    b = pp.operating_point(COEFFS, *ARGS, K + 20, RHO, MU, 450 / 3600)
    assert b["q"] < a["q"] and b["h"] > a["h"]

def test_pump_cannot_overcome_static_head():
    with pytest.raises(InputError):
        pp.operating_point(COEFFS, 50, D, L, E, K, RHO, MU, 450 / 3600)

def test_shaft_power_and_bad_efficiency():
    assert pp.shaft_power(7000, 0.7) == pytest.approx(10000)
    with pytest.raises(InputError):
        pp.shaft_power(7000, 0)

def _diag(q, h):
    return pp.diagnose(q, h, COEFFS, *ARGS, K, RHO, MU)["status"]

def test_diagnose_healthy_point():
    op = pp.operating_point(COEFFS, *ARGS, K, RHO, MU, 450 / 3600)
    assert _diag(op["q"], op["h"]) == "healthy"

def test_diagnose_throttled_line_is_system_resistance():
    op = pp.operating_point(COEFFS, *ARGS, K, RHO, MU, 450 / 3600)
    q = 0.85 * op["q"]
    assert _diag(q, pp.pump_head(COEFFS, q)) == "system_resistance"

def test_diagnose_worn_pump():
    op = pp.operating_point(COEFFS, *ARGS, K, RHO, MU, 450 / 3600)
    q = 0.85 * op["q"]
    assert _diag(q, pp.system_head(q, *ARGS, K, RHO, MU)) == "pump_degraded"
