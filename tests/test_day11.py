import math, os, re, sys
import xml.etree.ElementTree as ET
import pytest
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import heat_exchanger as hx, solver as sv
from calc_engine.heat_exchanger import InputError
from core import animation as an, validation as val

ROOT = os.path.dirname(os.path.dirname(__file__))

# ====================================================================== F factor for 1, 2, ... shells
def _eps12(ntu, cr):
    s = math.sqrt(1 + cr * cr); e = math.exp(-ntu * s)
    return 2 / (1 + cr + s * (1 + e) / (1 - e))

def _simulate(n, cc, ch, ua_total, t_in, T_in):
    """Independent check: n identical 1-2 shells in series, overall counter-current, solved with plain energy balances (no F equations)."""
    cmin, cmax = min(cc, ch), max(cc, ch)
    e = _eps12(ua_total / n / cmin, cmin / cmax)
    a, b = e * cmin / cc, e * cmin / ch
    if n == 1:
        q = e * cmin * (T_in - t_in)
    else:
        t_mid = (t_in + a * (T_in - t_in) - a * b * T_in) / (1 - a * b)
        T_mid = T_in - b * (T_in - t_mid)
        q = cc * (t_mid + a * (T_in - t_mid) - t_in)
    return T_in, T_in - q / ch, t_in, t_in + q / cc, q

@pytest.mark.parametrize("n", [1, 2])
@pytest.mark.parametrize("ch", [800.0, 1000.0, 1500.0])      # 1000 gives R = 1
@pytest.mark.parametrize("ntu", [0.8, 1.5, 3.0])
def test_f_matches_an_independent_shell_by_shell_simulation(n, ch, ntu):
    cc = 1000.0
    ua = ntu * min(cc, ch)
    T_in, T_out, t_in, t_out, q = _simulate(n, cc, ch, ua, 20.0, 150.0)
    f_sim = q / (ua * hx.lmtd(T_in, T_out, t_in, t_out, "counter"))
    assert hx.correction_factor_n_shells(T_in, T_out, t_in, t_out, n) == pytest.approx(f_sim, rel=1e-9)

@pytest.mark.parametrize("temps", [(180, 120, 30, 70), (150, 90, 30, 100), (120, 80, 25, 70), (100, 60, 20, 60), (95, 60, 25, 45)])
def test_one_shell_is_the_classic_1_2_formula(temps):
    assert hx.correction_factor_n_shells(*temps, 1) == pytest.approx(hx.correction_factor_1_2(*temps), rel=1e-12)

def test_more_shells_move_f_towards_one():
    t = (180, 120, 30, 70)
    f = [hx.correction_factor_n_shells(*t, n) for n in (1, 2, 3, 4, 10)]
    assert f == sorted(f) and 0.95 < f[0] < f[1] < 1 and hx.correction_factor_n_shells(*t, 50) > 0.9999
    assert hx.correction_factor_n_shells(100, 55, 20, 66, 1) < 0.75 < 0.9 < hx.correction_factor_n_shells(100, 55, 20, 66, 2)

def test_a_case_that_needs_three_shells_says_how_many_it_cannot_do():
    t = (100, 60, 20, 95)
    with pytest.raises(InputError, match="one shell pass"):
        hx.correction_factor_n_shells(*t, 1)
    with pytest.raises(InputError, match="2 shell passes"):
        hx.correction_factor_n_shells(*t, 2)
    assert hx.correction_factor_n_shells(*t, 3) == pytest.approx(0.7477, abs=2e-4)

def test_per_shell_effectiveness_converts_back_to_the_overall_p():
    for r, p, n in ((1.75, 0.2857, 2), (0.6, 0.5, 3), (1.0, 0.4, 2), (2.0, 0.3, 4)):
        p1 = hx.shell_effectiveness(r, p, n)
        if abs(r - 1) < 1e-9:
            back = n * p1 / (1 + (n - 1) * p1)
        else:
            x = ((1 - p1 * r) / (1 - p1)) ** n
            back = (x - 1) / (x - r)
        assert back == pytest.approx(p, rel=1e-9)

def test_bad_shell_counts_are_rejected():
    for n in (0, -1, 1.5):
        with pytest.raises(InputError):
            hx.correction_factor_n_shells(180, 120, 30, 70, n)

def test_solver_2_4_uses_the_automatic_f_with_full_steps():
    r = sv.solve_hx("shell_2_4", 180, 120, 30, 70)
    assert r["f_used"] == pytest.approx(hx.correction_factor_n_shells(180, 120, 30, 70, 2)) and r["R"] == pytest.approx(1.5)
    titles = [s["title"] for s in r["steps"]]
    assert any("Effectiveness of each shell" in t for t in titles) and any("2 shell passes, 4 tube passes" in t for t in titles)
    assert all(s["title"] and s["formula"] and s["working"] for s in r["steps"]) and r["lmtd_eff"] == pytest.approx(r["f_used"] * r["lmtd_counter"])
    assert list(sv.ARRANGEMENTS) == ["counter", "parallel", "shell_1_2", "shell_2_4"] and "(2-4)" in sv.ARRANGEMENTS["shell_2_4"]
    assert val.hx_values(r)["Correction factor F"][0] == r["f_used"]

def test_a_given_f_still_overrides_the_automatic_one():
    r = sv.solve_hx("shell_2_4", 95, 60, 25, 45, m_hot=12, cp_hot=3.6, cp_cold=4.18, area=80, f_given=0.92)
    assert r["f_used"] == 0.92 and r["f_computed"] != 0.92 and r["u"] == pytest.approx(1512e3 / (80 * 0.92 * r["lmtd_counter"]))

# ====================================================================== Sieder-Tate wall-viscosity correction
def test_phi_follows_the_formula_and_raises_the_given_u():
    r = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=800, mu_bulk=2.0, mu_wall=1.0)
    assert r["phi"] == pytest.approx(2 ** 0.14) and r["u_corrected"] == pytest.approx(800 * 2 ** 0.14)
    assert r["area"] == pytest.approx(1.2e6 / (800 * 2 ** 0.14 * r["lmtd_counter"]))
    assert r["area"] < 1.2e6 / (800 * r["lmtd_counter"])                         # a higher U needs less area
    assert any("Sieder-Tate" in s["title"] for s in r["steps"]) and any("controls" in w for w in r["warnings"])

def test_film_share_makes_the_correction_physically_consistent():
    phi = 2 ** 0.14
    r50 = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=800, mu_bulk=2.0, mu_wall=1.0, film_share_pct=50)
    assert r50["u_corrected"] == pytest.approx(800 / (0.5 / phi + 0.5))                       # series resistances: only half the resistance is divided by phi
    assert 800 < r50["u_corrected"] < 800 * phi and not any("controls" in w for w in r50["warnings"])
    # check against the resistance model directly: 1/U_corr = (x/phi + (1-x)) / U
    assert 1 / r50["u_corrected"] == pytest.approx(0.5 / (phi * 800) + 0.5 / 800)
    assert sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=800, mu_bulk=2.0, mu_wall=1.0, film_share_pct=100)["u_corrected"] == pytest.approx(800 * phi)

def test_equal_viscosities_change_nothing_and_cooling_wall_lowers_u():
    same = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=800, mu_bulk=1.5, mu_wall=1.5)
    assert same["phi"] == pytest.approx(1.0) and same["u_corrected"] == pytest.approx(800)
    cool = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=800, mu_bulk=1.0, mu_wall=2.0)    # wall more viscous than the bulk
    assert cool["phi"] < 1 and cool["u_corrected"] < 800

def test_viscosity_is_ignored_with_a_warning_when_u_is_calculated():
    r = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, area=30, mu_bulk=2.0, mu_wall=1.0)
    assert r["u"] == pytest.approx(1.2e6 / (30 * r["lmtd_counter"])) and r["u_corrected"] is None and r["phi"] == pytest.approx(2 ** 0.14)
    assert any("already contains" in w for w in r["warnings"])

def test_viscosity_inputs_are_checked():
    with pytest.raises(InputError, match="both"):
        sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=800, mu_bulk=2.0)
    for bad in (dict(mu_bulk=-1.0, mu_wall=1.0), dict(mu_bulk=1.0, mu_wall=0.0)):
        with pytest.raises(InputError):
            sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=800, **bad)
    for share in (0, -5, 120):
        with pytest.raises(InputError):
            sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=800, mu_bulk=2.0, mu_wall=1.0, film_share_pct=share)
    far = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=800, mu_bulk=50.0, mu_wall=1.0)
    assert any("outside 0.1 to 10" in w for w in far["warnings"])

# ====================================================================== tube side / shell side and tube geometry
def test_the_side_does_not_change_lmtd_f_duty_or_u():
    kw = dict(m_hot=12, cp_hot=3.6, cp_cold=4.18, area=80)
    shell, tube = sv.solve_hx("shell_1_2", 95, 60, 25, 45, hot_side="shell", **kw), sv.solve_hx("shell_1_2", 95, 60, 25, 45, hot_side="tube", **kw)
    for key in ("lmtd_counter", "lmtd_eff", "f_used", "q_kw", "u", "m_cold"):
        assert shell[key] == tube[key]
    assert shell["hot_side"] == "shell" and tube["hot_side"] == "tube"
    with pytest.raises(InputError):
        sv.solve_hx("counter", 95, 60, 25, 45, hot_side="annulus")

def test_required_area_becomes_a_number_of_tubes():
    r = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=500, tube_od_mm=25.4, tube_length_m=4.0)
    exact = r["area"] / (math.pi * 0.0254 * 4.0)
    assert r["n_tubes_exact"] == pytest.approx(exact) and r["n_tubes_needed"] == math.ceil(exact) == 85
    assert r["n_tubes_needed"] * math.pi * 0.0254 * 4.0 >= r["area"] and any(s["title"] == "Number of tubes needed" for s in r["steps"])
    assert any("outside surface" in a for a in r["assumptions"])

def test_required_area_becomes_a_tube_length_when_the_count_is_known():
    r = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=500, tube_od_mm=25.4, n_tubes=100)
    assert r["tube_length_found"] == pytest.approx(r["area"] / (100 * math.pi * 0.0254)) and r["n_tubes_needed"] is None

def test_tube_bundle_gives_the_area_and_then_u():
    r = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, tube_od_mm=19.05, tube_length_m=5.0, n_tubes=150)
    a = 150 * math.pi * 0.01905 * 5.0
    assert r["area_from_tubes"] == pytest.approx(a) and r["area"] == pytest.approx(a) and r["u"] == pytest.approx(1.2e6 / (a * r["lmtd_counter"]))

def test_installed_area_is_compared_with_the_required_area():
    big = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=500, tube_od_mm=25.4, tube_length_m=4.0, n_tubes=100)
    assert big["over_surface_pct"] == pytest.approx((big["area_from_tubes"] / big["area_required"] - 1) * 100) and big["over_surface_pct"] > 10 and not big["warnings"]
    small = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=500, tube_od_mm=25.4, tube_length_m=4.0, n_tubes=60)
    assert small["over_surface_pct"] < 0 and any("too small" in w for w in small["warnings"])

def test_geometry_warnings_and_validation():
    assert any("outside diameter" in w for w in sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=500, tube_length_m=4.0)["warnings"])
    mism = sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, area=10, tube_od_mm=25.4, tube_length_m=4.0, n_tubes=100)
    assert any("differs by more than 2%" in w for w in mism["warnings"]) and mism["area"] == 10
    for bad in (dict(tube_od_mm=0), dict(tube_length_m=-1), dict(n_tubes=2.5), dict(n_tubes=0)):
        with pytest.raises(InputError):
            sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=500, **{**dict(tube_od_mm=25.4, tube_length_m=4.0), **bad})

def test_new_results_can_be_copied_into_the_validation_log():
    v = val.hx_values(sv.solve_hx("counter", 200, 110, 40, 90, q_kw=1200, u=500, mu_bulk=2.0, mu_wall=1.0, tube_od_mm=25.4, tube_length_m=4.0))
    assert {"Viscosity factor phi", "Corrected U", "Number of tubes (exact)", "Area"} <= set(v)

# ====================================================================== the diagram follows the sides
def _circles(html):
    out = {}
    for chunk in html.split("<circle")[1:]:
        fill, path = re.search(r'fill="(#\w+)"', chunk).group(1), re.search(r'path="([^"]+)"', chunk).group(1)
        out.setdefault(path, set()).add(fill)
    return out

def test_hot_fluid_in_the_tubes_swaps_labels_paths_and_colours():
    default = an.animated_hx_html("counter", 180, 120, 30, 70)
    swapped = an.animated_hx_html("counter", 180, 120, 30, 70, hot_in_tubes=True)
    for html in (default, swapped):
        ET.fromstring(re.search(r"<svg.*</svg>", html, re.S).group(0))
    assert "Shell (hot fluid)" in default and "Tube bundle (cold fluid)" in default
    assert "Shell (cold fluid)" in swapped and "Tube bundle (hot fluid)" in swapped
    for text in ("Hot in 180 °C", "Hot out 120 °C", "Cold in 30 °C", "Cold out 70 °C"):
        assert text in default and text in swapped
    tube_path, shell_path = "M760,160 L40,160", "M230,40 L230,115 L570,115 L570,290"
    assert _circles(default)[tube_path] <= {an.COLD0} and _circles(default)[shell_path] <= {an.HOT0}
    assert _circles(swapped)[tube_path] <= {an.HOT0} and _circles(swapped)[shell_path] <= {an.COLD0}
    assert re.search(r'<text x="230" y="22"[^>]*>Cold in 30 °C', swapped) and re.search(r'<text x="760" y="146"[^>]*>Hot in 180 °C', swapped)

@pytest.mark.parametrize("arr", ["counter", "parallel", "shell_1_2", "shell_2_4"])
@pytest.mark.parametrize("tubes", [False, True])
def test_every_type_and_side_gives_a_valid_labelled_diagram(arr, tubes):
    html = an.animated_hx_html(arr, 180, 120, 30, 70, tubes)
    ET.fromstring(re.search(r"<svg.*</svg>", html, re.S).group(0))
    assert html.count("<animateMotion") >= 20 and "Tube sheet" in html and "Shell inlet nozzle" in html
    assert ("Return head" in html and "Baffle" in html) == arr.startswith("shell")
    assert ("two of these 1-2 shells in series" in html) == (arr == "shell_2_4")

# ====================================================================== the page
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d11.db"))

def _page():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.button(key="do_guest").click().run()
    return at.switch_page("views/solver.py").run()

def _n(text):
    return float(re.search(r"-?[\d,]*\.?\d+", text).group(0).replace(",", ""))

def _m(at):
    return {m.label: _n(m.value) for m in at.metric}

def test_page_offers_all_exchanger_types_and_calculates_f_automatically():
    at = _page()
    assert len(at.selectbox(key="sv_arr").options) == 4
    for arr, label in (("shell_1_2", "F1"), ("shell_2_4", "F2")):
        at.selectbox(key="sv_arr").select(arr).run()
        assert not at.exception
        expected = hx.correction_factor_n_shells(180, 120, 30, 70, 1 if arr == "shell_1_2" else 2)
        assert _m(at)["Correction factor F"] == pytest.approx(expected, abs=6e-5) and "Correction factor F (given)" not in _m(at)
    assert any("Effectiveness of each shell" in m.value for m in at.markdown)

def test_page_tube_side_toggle_keeps_the_numbers_and_changes_the_text():
    at = _page()
    at.selectbox(key="sv_arr").select("shell_1_2").run()
    base = _m(at)
    at.radio(key="sv_side").set_value("Hot fluid in the tubes, cold fluid in the shell").run()
    assert not at.exception and _m(at) == base
    assert any("Tubes carry the hot fluid" in c.value for c in at.code)
    assert at.radio(key="sv_side").help and "does not change" in at.radio(key="sv_side").help

def test_page_viscosity_correction_end_to_end():
    at = _page()
    at.number_input(key="sv_q").set_value(1200.0); at.number_input(key="sv_u").set_value(800.0)
    at.number_input(key="sv_mub").set_value(2.0); at.number_input(key="sv_muw").set_value(1.0)
    at.run()
    m = _m(at)
    ref = sv.solve_hx("counter", 180, 120, 30, 70, q_kw=1200, u=800, mu_bulk=2.0, mu_wall=1.0)
    assert not at.exception and m["Viscosity factor φ"] == pytest.approx(2 ** 0.14, abs=1e-4) and m["Corrected U"] == pytest.approx(800 * 2 ** 0.14, abs=0.1)
    assert m["Required area A"] == pytest.approx(ref["area"], abs=0.01)
    text = "\n".join(c.value for c in at.code)
    assert "Bulk viscosity: 2 mPa·s" in text and "Wall viscosity: 1 mPa·s" in text
    at.number_input(key="sv_film").set_value(50.0).run()
    assert _m(at)["Corrected U"] == pytest.approx(800 / (0.5 / 2 ** 0.14 + 0.5), abs=0.1)
    at.number_input(key="sv_mub").set_value(None).run()                       # only one viscosity: a polite error, not a crash
    assert not at.exception and any("both" in e.value for e in at.error)

def test_page_tube_geometry_in_other_units():
    at = _page()
    at.number_input(key="sv_q").set_value(1200.0); at.number_input(key="sv_u").set_value(500.0)
    at.selectbox(key="sv_od_u").select("in"); at.number_input(key="sv_od").set_value(1.0)
    at.selectbox(key="sv_tl_u").select("ft"); at.number_input(key="sv_tl").set_value(4.0 / 0.3048)
    at.run()
    ref = sv.solve_hx("counter", 180, 120, 30, 70, q_kw=1200, u=500, tube_od_mm=25.4, tube_length_m=4.0)
    m = {x.label: x.value for x in at.metric}
    assert not at.exception and str(ref["n_tubes_needed"]) in m["Tubes needed"] and _n(m["Required area A"]) == pytest.approx(ref["area"], abs=0.01)
    at.number_input(key="sv_nt").set_value(150).run()
    assert "Installed vs required area" in {x.label for x in at.metric} and "Tubes needed" not in {x.label for x in at.metric}

def test_new_inputs_have_tooltips_and_reset_clears_them():
    at = _page()
    for key, word in (("sv_mub", "bulk"), ("sv_muw", "wall"), ("sv_film", "film"), ("sv_od", "OUTSIDE"), ("sv_tl", "length"), ("sv_nt", "number of tubes")):
        assert word.lower() in (at.number_input(key=key).help or "").lower(), key
    assert "automatically" in at.number_input(key="sv_f").help and "2-4" in at.selectbox(key="sv_arr").help
    at.number_input(key="sv_mub").set_value(2.0); at.number_input(key="sv_nt").set_value(10); at.run()
    at.button(key="sv_reset").click().run()
    assert not at.exception and at.number_input(key="sv_mub__1").value is None and at.number_input(key="sv_nt__1").value is None and at.number_input(key="sv_od__1").value is None
