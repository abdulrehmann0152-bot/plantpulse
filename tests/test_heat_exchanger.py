import math, os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import heat_exchanger as hx

# NOTE: these are hand-calculation checks. Replace/add textbook examples
# (book, page, answer) from the team in tests/textbook_cases when available.

def test_heat_duty_hand_calc():
    assert hx.heat_duty(1.5, 4180, 100, 60) == pytest.approx(250800)

def test_lmtd_counter_hand_calc():
    # dT1 = 100-50 = 50, dT2 = 60-20 = 40 -> 10 / ln(1.25) = 44.8142
    assert hx.lmtd(100, 60, 20, 50, "counter") == pytest.approx(44.8142, rel=1e-4)

def test_lmtd_parallel_hand_calc():
    # dT1 = 80, dT2 = 10 -> 70 / ln(8) = 33.6636
    assert hx.lmtd(100, 60, 20, 50, "parallel") == pytest.approx(33.6636, rel=1e-4)

def test_lmtd_equal_differences():
    assert hx.lmtd(100, 80, 60, 80, "counter") == pytest.approx(20.0)

def test_counter_flow_beats_parallel():
    assert hx.lmtd(100, 60, 20, 50, "counter") > hx.lmtd(100, 60, 20, 50, "parallel")

def test_temperature_cross_rejected():
    with pytest.raises(hx.InputError):
        hx.lmtd(100, 60, 20, 110, "counter")  # cold outlet above hot inlet
    with pytest.raises(hx.InputError):
        hx.lmtd(100, 60, 20, 70, "parallel")  # cold outlet above hot outlet in parallel flow
    with pytest.raises(hx.InputError):
        hx.lmtd(100, 110, 20, 50)             # hot fluid heating up

def test_overall_u_hand_calc():
    assert hx.overall_u(250800, 10, 44.8142) == pytest.approx(559.65, rel=1e-3)

def test_fouling_resistance():
    assert hx.fouling_resistance(500, 800) == pytest.approx(0.00075)

def test_balance_mismatch():
    assert hx.heat_balance_mismatch_pct(100, 110) == pytest.approx(9.524, rel=1e-3)

def _ntu_1_2(eps, cr):
    s = math.sqrt(1 + cr * cr)
    return -1 / s * math.log((2 / eps - 1 - cr - s) / (2 / eps - 1 - cr + s))

@pytest.mark.parametrize("th_in,th_out,tc_in,tc_out",
                         [(100, 60, 20, 40), (150, 90, 30, 100), (120, 80, 25, 70), (100, 60, 20, 60)])
def test_F_matches_independent_effectiveness_NTU(th_in, th_out, tc_in, tc_out):
    """Cross-check F-LMTD against the eps-NTU relation for a 1-2 shell exchanger."""
    cc = 1000.0
    q = cc * (tc_out - tc_in)
    ch = q / (th_in - th_out)
    cmin, cmax = min(cc, ch), max(cc, ch)
    eps = q / (cmin * (th_in - tc_in))
    ua_ntu = _ntu_1_2(eps, cmin / cmax) * cmin
    f = hx.correction_factor_1_2(th_in, th_out, tc_in, tc_out)
    ua_lmtd = q / (f * hx.lmtd(th_in, th_out, tc_in, tc_out, "counter"))
    assert 0 < f <= 1
    assert ua_lmtd == pytest.approx(ua_ntu, rel=1e-6)

def test_F_continuous_around_R_equals_1():
    a = hx.correction_factor_1_2(100, 60 + 0.004, 20, 60)
    b = hx.correction_factor_1_2(100, 60, 20, 60)
    assert a == pytest.approx(b, rel=1e-3)

def test_F_infeasible_raises():
    with pytest.raises(hx.InputError):
        hx.correction_factor_1_2(100, 40, 60, 95)

def test_analyze_default_case():
    r = hx.analyze(1.5, 4180, 100, 60, 2.0, 4180, 20, 50, 10, "counter", u_clean=800)
    assert r["mismatch_pct"] == pytest.approx(0, abs=1e-9)
    assert r["u"] == pytest.approx(559.65, rel=1e-3)
    assert r["rf"] == pytest.approx(1 / 559.65 - 1 / 800, rel=1e-3)
