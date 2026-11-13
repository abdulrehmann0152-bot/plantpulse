"""Independent checks for the heat exchanger audit fixes: counter-flow profile, F factor, heat balance, LMTD validation,
worked-solution format, tooltips and KPI cards. The expected values are computed here by other routes, not copied from the code."""
import ast, math, os, random, re, sys
import pytest
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import heat_exchanger as hx, hx_explain as ex, solver as sv
from core import branding, hx_plot, step_view

ROOT = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d18.db"))


# ====================================================================== 1. temperature profile
def test_counter_flow_cold_line_is_reversed_hot_inlet_end_meets_cold_outlet():
    p = hx.temperature_profile("counter", 100, 60, 20, 50, n=21)
    assert (p["hot"][0], p["hot"][-1]) == (100, 60)
    assert (p["cold"][0], p["cold"][-1]) == (50, 20)                                  # Tc,out on the LEFT, Tc,in on the right
    assert all(a > b for a, b in zip(p["cold"], p["cold"][1:])) and all(a > b for a, b in zip(p["hot"], p["hot"][1:]))
    assert p["flow"] == "counter" and not p["equivalent"] and (p["d1"], p["d2"]) == (50, 40)

def test_parallel_flow_cold_line_rises_from_its_inlet():
    p = hx.temperature_profile("parallel", 100, 60, 20, 50)
    assert (p["cold"][0], p["cold"][-1]) == (20, 50) and all(a < b for a, b in zip(p["cold"], p["cold"][1:]))
    assert (p["d1"], p["d2"]) == (80, 10) and p["flow"] == "parallel"

def test_multi_pass_is_shown_as_its_counter_flow_equivalent():
    p = hx.temperature_profile("shell_1_2", 100, 60, 20, 50)
    q = hx.temperature_profile("counter", 100, 60, 20, 50)
    assert p["equivalent"] and p["cold"] == q["cold"] and p["hot"] == q["hot"] and hx.temperature_profile("shell_2_4", 100, 60, 20, 50)["equivalent"]

@pytest.mark.parametrize("n", [2, 3, 21, 101])
def test_profiles_are_straight_lines_against_heat_transferred(n):
    for arr in ("counter", "parallel"):
        p = hx.temperature_profile(arr, 150, 70, 25, 65, n=n)
        assert len(p["x"]) == n and p["x"][0] == 0 and p["x"][-1] == 1
        for line in (p["hot"], p["cold"]):
            steps = [b - a for a, b in zip(line, line[1:])]
            assert max(steps) - min(steps) < 1e-9

def test_a_profile_needs_two_points():
    with pytest.raises(hx.InputError):
        hx.temperature_profile("counter", 100, 60, 20, 50, n=1)

def _inverse_lmtd_from_profile(p, n=4001):
    """LMTD = 1 / integral over the heat fraction of dq / (T_hot - T_cold), by the trapezoid rule on the plotted lines."""
    gaps = [h - c for h, c in zip(p["hot"], p["cold"])]
    dq = 1 / (len(gaps) - 1)
    return 1 / sum((1 / gaps[i] + 1 / gaps[i + 1]) / 2 * dq for i in range(len(gaps) - 1))

@pytest.mark.parametrize("temps", [(100, 60, 20, 50), (180, 120, 30, 70), (200, 110, 40, 90), (90, 70, 20, 45), (150, 140, 20, 100)])
def test_plotted_lines_reproduce_the_lmtd_for_each_arrangement(temps):
    for arr in ("counter", "parallel"):
        try:
            expected = hx.lmtd(*temps, arr)
        except hx.InputError:
            continue
        p = hx.temperature_profile(arr, *temps, n=4001)
        assert _inverse_lmtd_from_profile(p) == pytest.approx(expected, rel=1e-6)

def test_an_unreversed_cold_line_would_give_the_wrong_lmtd():
    """The negative control: if the cold line were drawn like the parallel case, the counter-flow LMTD would come out wrong."""
    p = hx.temperature_profile("counter", 100, 60, 20, 50, n=4001)
    wrong = dict(p, cold=[20 + 30 * x for x in p["x"]])
    assert _inverse_lmtd_from_profile(wrong) == pytest.approx(hx.lmtd(100, 60, 20, 50, "parallel"), rel=1e-6)
    assert abs(_inverse_lmtd_from_profile(wrong) - hx.lmtd(100, 60, 20, 50, "counter")) > 5

def test_hot_stays_above_cold_everywhere_for_valid_data():
    rng = random.Random(18)
    checked = 0
    while checked < 300:
        th_in, tc_in = rng.uniform(80, 300), rng.uniform(5, 60)
        th_out, tc_out = rng.uniform(tc_in, th_in), rng.uniform(tc_in, th_in)
        if th_out >= th_in or tc_out <= tc_in:
            continue
        for arr in ("counter", "parallel"):
            try:
                p = hx.temperature_profile(arr, th_in, th_out, tc_in, tc_out)
            except hx.InputError:
                continue
            assert all(h > c for h, c in zip(p["hot"], p["cold"]))
            checked += 1

def test_profile_note_explains_the_reversal_with_the_actual_temperatures():
    note = hx.profile_note(hx.temperature_profile("counter", 100, 60, 20, 50))
    assert "Counter-flow" in note and "cold line is reversed" in note and "starts at T(c,out) on the left" in note and "flows right to left" in note
    assert "hot in 100 °C meets cold OUT 50 °C" in note and "ΔT₁ = 50 K" in note and "hot out 60 °C meets cold IN 20 °C" in note and "ΔT₂ = 40 K" in note
    par = hx.profile_note(hx.temperature_profile("parallel", 100, 60, 20, 50))
    assert "both fluids enter at the left end" in par and "reversed" not in par and "can never leave hotter" in par
    assert "counter-flow equivalent" in hx.profile_note(hx.temperature_profile("shell_1_2", 100, 60, 20, 50))

def test_the_figure_draws_those_lines_and_carries_the_annotation():
    p = hx.temperature_profile("counter", 100, 60, 20, 50)
    fig = hx_plot.profile_figure(p)
    hot, cold = fig.data
    assert list(hot.y) == p["hot"] and list(cold.y) == p["cold"] and cold.y[0] > cold.y[-1]
    notes = [a.text for a in fig.layout.annotations]
    assert any(t == "<b>Cold OUT 50 °C</b>" for t in notes) and any(t == "<b>Cold IN 20 °C</b>" for t in notes) and any("ΔT₁ = 50 K" in t for t in notes)
    explanation = [a for a in fig.layout.annotations if a.xref == "paper"]
    assert len(explanation) == 1 and "cold line is reversed" in explanation[0].text
    assert " ".join(explanation[0].text.replace("<br>", " ").split()) == " ".join(hx.profile_note(p).split())         # wrapped for narrow screens, but the same words
    assert all(len(line) <= 58 for line in explanation[0].text.split("<br>")) and fig.layout.margin.b >= 85 + len(explanation[0].text.split("<br>")) * 15
    par = hx_plot.profile_figure(hx.temperature_profile("parallel", 100, 60, 20, 50))
    assert any(a.text == "<b>Cold in 20 °C</b>" for a in par.layout.annotations) and not any("reversed" in a.text for a in par.layout.annotations)

# ====================================================================== 2. LMTD validation (physically impossible inputs)
CROSSES = [("counter", (100, 60, 20, 110), "hot-inlet end", "100 − 110"), ("counter", (100, 60, 20, 100), "hot-inlet end", "100 − 100"),
           ("counter", (100, 60, 65, 90), "hot-outlet end", "60 − 65"), ("counter", (100, 60, 60, 90), "hot-outlet end", "60 − 60"),
           ("parallel", (100, 60, 20, 70), "outlet end", "60 − 70"), ("parallel", (100, 60, 20, 60), "outlet end", "60 − 60"),
           ("parallel", (100, 60, 110, 120), "inlet end", "100 − 110")]

@pytest.mark.parametrize("flow,temps,end,numbers", CROSSES)
def test_temperature_crossover_is_rejected_with_a_message_naming_the_end(flow, temps, end, numbers):
    for call in (lambda: hx.lmtd(*temps, flow), lambda: hx.terminal_differences(*temps, flow), lambda: hx.temperature_profile(flow, *temps)):
        with pytest.raises(hx.InputError) as e:
            call()
        assert "Temperature cross" in str(e.value) and end in str(e.value) and numbers in str(e.value) and "zero or negative" in str(e.value)

def test_other_impossible_inputs_are_rejected():
    for args in ((60, 100, 20, 50), (100, 100, 20, 50), (100, 60, 50, 20), (100, 60, 50, 50), (100, 60, -300, 50), (100, -300, 20, 50)):
        with pytest.raises(hx.InputError):
            hx.lmtd(*args, "counter")
    with pytest.raises(hx.InputError):
        hx.lmtd(100, 60, 20, 50, "crossflow")
    for bad in ((0, 4180, 1), (1.5, 0, 1), (-1, 4180, 1)):
        with pytest.raises(hx.InputError):
            hx.heat_duty(bad[0], bad[1], 100, 60)

def test_valid_data_gives_the_textbook_lmtd_and_equal_differences_are_allowed():
    assert hx.lmtd(100, 60, 20, 50, "counter") == pytest.approx((50 - 40) / math.log(50 / 40), rel=1e-12)
    assert hx.lmtd(100, 60, 20, 50, "parallel") == pytest.approx((80 - 10) / math.log(80 / 10), rel=1e-12)
    assert hx.lmtd(100, 60, 50, 90, "counter") == pytest.approx(10.0)                    # dT1 = dT2: the limit is the common difference

def test_a_very_small_approach_gets_a_warning_but_is_not_an_error():
    assert hx.approach_warnings(50, 40) == [] and hx.approach_warnings(3, 40) == []
    w = hx.approach_warnings(2, 40)
    assert len(w) == 1 and "only 2 K" in w[0] and "25%" in w[0]                          # 0.5 K on 2 K is 25%
    assert hx.approach_warnings(40, 1)[0].count("1 K") >= 1

# ====================================================================== 3. heat balance
def _mismatch(qh, qc):
    return abs(qh - qc) / ((qh + qc) / 2) * 100

@pytest.mark.parametrize("qh,qc", [(100.5, 99.5), (100, 100), (250.8, 253.0), (250.8, 263.34), (1254, 1128.6), (10, 30)])
def test_heat_balance_percentage_is_exact_and_symmetric(qh, qc):
    s = hx.heat_balance_status(qh * 1000, qc * 1000)
    assert s["mismatch_pct"] == pytest.approx(_mismatch(qh, qc), rel=1e-12)
    assert hx.heat_balance_status(qc * 1000, qh * 1000)["mismatch_pct"] == pytest.approx(s["mismatch_pct"])
    assert f"{s['mismatch_pct']:.2f}%" in s["message"] or s["ok"]

def test_tolerance_boundary_is_inclusive_at_one_percent():
    assert hx.heat_balance_status(100.5, 99.5)["level"] == "ok"                          # exactly 1.00%
    assert hx.heat_balance_status(100.51, 99.5)["level"] == "error" and hx.heat_balance_status(100, 100)["level"] == "ok"

def test_messages_never_claim_consistency_when_the_mismatch_is_too_large():
    ok = hx.heat_balance_status(250800, 253000)
    bad = hx.heat_balance_status(250800, 263340)
    assert ok["ok"] and "closes" in ok["message"] and "0.87%" in ok["message"] and "DOES NOT" not in ok["message"]
    assert not bad["ok"] and bad["level"] == "error" and "HEAT BALANCE DOES NOT CLOSE" in bad["message"] and "4.88%" in bad["message"] and "tolerance 1%" in bad["message"]
    assert "closes" not in bad["message"].replace("DOES NOT CLOSE", "") and "consistent" not in bad["message"].lower()
    assert bad["higher"] == "cold" and "cold-side duty is higher" in bad["message"] and "250.80 kW" in bad["message"] and "263.34 kW" in bad["message"]

def test_severe_level_and_a_custom_tolerance():
    sev = hx.heat_balance_status(1000, 1200)
    assert sev["level"] == "severe" and "at least one reading is wrong" in sev["message"] and "18.18%" in sev["message"]        # 200 / 1100
    assert hx.heat_balance_status(1000, 1030, 5)["level"] == "ok" and hx.heat_balance_status(1000, 1030, 1)["level"] == "error"
    assert hx.heat_balance_status(1000, 1150, 8)["level"] == "error" and hx.heat_balance_status(1000, 1250, 8)["level"] == "severe"      # severe above max(5%, twice the tolerance)
    for bad in (0, -1):
        with pytest.raises(hx.InputError):
            hx.heat_balance_status(1000, 1000, bad)

def test_analyze_reports_the_balance_and_uses_the_average_duty():
    r = hx.analyze(1.5, 4180, 100, 60, 2.1, 4180, 20, 50, 10, "counter")
    assert not r["balance"]["ok"] and r["mismatch_pct"] == pytest.approx(r["balance"]["mismatch_pct"]) and r["q_avg"] == pytest.approx((r["q_hot"] + r["q_cold"]) / 2)
    assert r["u"] == pytest.approx(r["q_avg"] / (10 * r["lmtd"]))
    assert hx.analyze(1.5, 4180, 100, 60, 2.0, 4180, 20, 50, 10, "counter")["balance"]["ok"]
    assert hx.analyze(1.5, 4180, 100, 60, 2.1, 4180, 20, 50, 10, "counter", balance_tol_pct=5)["balance"]["ok"]

def test_solver_raises_the_same_high_visibility_message():
    ok = sv.solve_hx("counter", 100, 60, 20, 50, m_hot=1.5, cp_hot=4.18, m_cold=2.0, cp_cold=4.18, area=10)
    bad = sv.solve_hx("counter", 100, 60, 20, 50, m_hot=1.5, cp_hot=4.18, m_cold=2.1, cp_cold=4.18, area=10)
    assert ok["balance"]["ok"] and not ok["warnings"]
    assert bad["warnings"][0].startswith("HEAT BALANCE DOES NOT CLOSE") and "4.88%" in bad["warnings"][0] and "hot-side duty is used" in bad["warnings"][0]
    assert sv.solve_hx("counter", 100, 60, 20, 50, m_hot=1.5, cp_hot=4.18, m_cold=2.1, cp_cold=4.18, area=10, balance_tol_pct=5)["warnings"] == []

# ====================================================================== 4. correction factor F
def _f_by_effectiveness_ntu(th_in, th_out, tc_in, tc_out):
    """F for 1 shell pass / 2 tube passes found a different way: Kays-London effectiveness-NTU, with F = Q / (UA x LMTD_counter)."""
    cc = 1.0
    dtc = tc_out - tc_in
    ch = cc * dtc / (th_in - th_out)
    q = cc * dtc
    cmin, cmax = min(cc, ch), max(cc, ch)
    cr, eps = cmin / cmax, q / (cmin * (th_in - tc_in))
    s = math.sqrt(1 + cr * cr)
    ntu = -math.log((2 / eps - 1 - cr - s) / (2 / eps - 1 - cr + s)) / s
    return q / (ntu * cmin * hx.lmtd(th_in, th_out, tc_in, tc_out, "counter"))

def _temps(r, p, th_in=150.0, tc_in=30.0):
    tc_out = tc_in + p * (th_in - tc_in)
    return th_in, th_in - r * (tc_out - tc_in), tc_in, tc_out

@pytest.mark.parametrize("r", [0.3, 0.7, 1.0, 1.5, 2.5])
@pytest.mark.parametrize("p", [0.1, 0.2, 0.3, 0.45])
def test_f_matches_the_effectiveness_ntu_method_over_a_grid(r, p):
    temps = _temps(r, p)
    try:
        f = hx.correction_factor_1_2(*temps)
    except hx.InputError:
        pytest.skip("not achievable with one shell")
    assert f == pytest.approx(_f_by_effectiveness_ntu(*temps), rel=1e-7) and 0 < f <= 1

def test_f_known_values_and_it_is_not_a_constant():
    assert hx.correction_factor_1_2(180, 120, 30, 70) == pytest.approx(0.9583, abs=5e-4)           # textbook problem verified earlier in the project
    assert hx.correction_factor_1_2(*_temps(1.0, 0.5)) == pytest.approx(0.8023, abs=5e-4)             # R = 1 special case, by hand
    fs = [hx.correction_factor_1_2(*_temps(1.5, p)) for p in (0.1, 0.2, 0.3, 0.4, 0.45)]
    assert fs == sorted(fs, reverse=True) and len(set(round(f, 6) for f in fs)) == 5 and fs[0] > 0.97
    with pytest.raises(hx.InputError, match="Not achievable"):                                            # R = 1.5 cannot reach P = 0.5 with one shell (the limit is about 0.465)
        hx.correction_factor_1_2(*_temps(1.5, 0.5))
    assert hx.correction_factor_n_shells(*_temps(1.5, 0.45), 2) > hx.correction_factor_1_2(*_temps(1.5, 0.45))     # more shells, higher F

def test_the_displayed_steps_for_f_use_the_same_numbers_as_the_engine():
    for r, p in ((1.3333, 0.375), (1.0, 0.4), (0.5, 0.3)):
        temps = _temps(r, p)
        f = hx.correction_factor_1_2(*temps)
        k = ex.f_pieces_1_2((temps[0] - temps[1]) / (temps[3] - temps[2]), (temps[3] - temps[2]) / (temps[0] - temps[2]))
        assert k["f"] == pytest.approx(f, rel=1e-12) and k["num"] / k["den"] == pytest.approx(f, rel=1e-12)

def test_low_f_gets_a_warning_with_the_extra_area():
    assert hx.f_assessment(0.75) is None and hx.f_assessment(0.9) is None and hx.f_assessment(1.0) is None
    w = hx.f_assessment(0.749)
    assert "0.749" in w and "below 0.75" in w and "34% more" in w and "uneconomical" in w
    assert "100% more" in hx.f_assessment(0.5)                                                         # area is proportional to 1/F
    low = hx.analyze(1.5, 4180, 100, 55, 1.5, 4180, 20, 66, 10, "shell_1_2")
    assert low["f"] < 0.75 and low["f_warning"] and hx.analyze(1.5, 4180, 100, 60, 2.0, 4180, 20, 50, 10, "shell_1_2")["f_warning"] is None
    assert hx.analyze(1.5, 4180, 100, 55, 1.5, 4180, 20, 66, 10, "counter")["f_warning"] is None      # pure counter-flow has F = 1

# ====================================================================== 5. worked solution format
def _eval(expr):
    e = expr.replace("×", "*").replace("−", "-").replace("²", "**2").replace("^", "**").replace("π", "pi").replace("[", "(").replace("]", ")")
    e = re.sub(r"\|([^|]+)\|", r"abs(\1)", e).replace("√", "sqrt")
    e = re.sub(r"sqrt(\d+\.?\d*)", r"sqrt(\1)", e)
    e = re.sub(r"(?<=\d),(?=\d{3})", "", e)
    funcs = {"ln": math.log, "sqrt": math.sqrt, "abs": abs}

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

def _result_value(text):
    return float(re.search(r"=\s*([+-]?[\d,]*\.?\d+)", text).group(1).replace(",", ""))

def _close(a, b):
    return abs(a - b) <= 5e-3 * max(1.0, abs(b))

def _check_steps(steps):
    n_checked = 0
    for s in steps:
        assert s["title"] and s["formula"] and s["variables"] and s["calc"], s["title"]
        assert all(len(v) == 2 and v[0] and v[1] for v in s["variables"])
        for c in s["calc"]:
            assert c["label"] and c["substitution"] and c["result"]
            if "given" in c["substitution"] or "ΔT₁ = ΔT₂" in c["substitution"]:
                continue
            target = _result_value(c["result"])
            assert _close(_eval(c["substitution"]), target), (s["title"], c)
            if c.get("intermediate"):
                for part in c["intermediate"].split(" = "):
                    assert _close(_eval(part), target), (s["title"], part, c)
            n_checked += 1
    return n_checked

def test_the_audit_example_is_written_exactly_as_asked():
    r = hx.analyze(1.5, 4180, 100, 60, 2.0, 4180, 20, 50, 10, "counter", 800)
    steps = ex.page_steps(1.5, 4.18, 100, 60, 2.0, 4.18, 20, 50, 10, "counter", 800, r)
    c = steps[0]["calc"][0]
    assert (c["substitution"], c["intermediate"], c["result"]) == ("1.5 × 4.18 × (100 − 60)", "1.5 × 4.18 × 40", "Q_h = 250.80 kW")
    assert steps[0]["formula"] == r"Q_h=\dot m_h\,C_{p,h}\,(T_{h,in}-T_{h,out})" and ["Q_h", "heat given up by the hot fluid [kW]"] in steps[0]["variables"]
    u = next(s for s in steps if s["title"] == "Overall heat transfer coefficient")["calc"][0]
    assert u["result"] == "U = 559.6 W/m²K" and u["substitution"] == "250.80 × 1,000 / (10 × 44.814)"

@pytest.mark.parametrize("flow", ["counter", "parallel", "shell_1_2"])
@pytest.mark.parametrize("u_clean", [None, 800.0])
def test_every_page_step_has_five_parts_and_its_arithmetic_is_right(flow, u_clean):
    r = hx.analyze(1.5, 4180, 100, 60, 2.0, 4180, 20, 50, 10, flow, u_clean)
    steps = ex.page_steps(1.5, 4.18, 100, 60, 2.0, 4.18, 20, 50, 10, flow, u_clean, r)
    titles = [s["title"] for s in steps]
    assert titles[:4] == ["Heat given up by the hot fluid", "Heat taken up by the cold fluid", "Heat balance check", "Duty used for U"]
    assert ("Correction factor F (1 shell pass, 2 tube passes)" in titles) == (flow == "shell_1_2") and ("Fouling resistance" in titles) == (u_clean is not None)
    assert _check_steps(steps) >= 8
    f_result = [c for s in steps for c in s["calc"] if c["label"] == "F"]
    if flow == "shell_1_2":
        assert _result_value(f_result[0]["result"]) == pytest.approx(r["f"], abs=5e-5)

def test_steps_show_a_failed_balance_honestly():
    r = hx.analyze(1.5, 4180, 100, 60, 2.1, 4180, 20, 50, 10, "counter")
    s = next(s for s in ex.page_steps(1.5, 4.18, 100, 60, 2.1, 4.18, 20, 50, 10, "counter", None, r) if s["title"] == "Heat balance check")
    assert "DOES NOT close" in s["calc"][0]["result"] and "4.88" in s["calc"][0]["result"]

@pytest.mark.parametrize("arr", list(sv.ARRANGEMENTS))
def test_solver_steps_have_the_same_five_parts_and_correct_arithmetic(arr):
    r = sv.solve_hx(arr, 180, 120, 30, 70, m_hot=5.0, cp_hot=4.18, m_cold=6.0, cp_cold=4.18, area=40.0)
    structured = [s for s in r["steps"] if s.get("calc")]
    assert len(structured) == len(r["steps"]) and len(structured) >= 5
    assert _check_steps(structured) >= 8
    if arr.startswith("shell"):
        assert _result_value([c for s in r["steps"] for c in s["calc"] if c["label"] == "F"][0]["result"]) == pytest.approx(r["f_computed"], abs=5e-5)

def test_solver_steps_for_a_design_problem_are_also_structured():
    r = sv.solve_hx("shell_1_2", 180, 120, 30, 70, q_kw=1200.0, u=500.0, tube_od_mm=25.0, tube_length_m=3.0)
    assert all(s.get("calc") for s in r["steps"]) and _check_steps(r["steps"]) >= 6

def test_the_renderer_shows_all_five_parts_and_still_shows_older_steps():
    script = (f"import sys; sys.path.insert(0, {ROOT!r})\nimport streamlit as st\nfrom calc_engine import solver as sv\nfrom core import step_view\n"
              "r = sv.solve_hx('counter', 100, 60, 20, 50, m_hot=1.5, cp_hot=4.18, m_cold=2.0, cp_cold=4.18, area=10)\n"
              "step_view.show_steps(r['steps'] + [{'title': 'Old kind of step', 'formula': 'Z', 'working': 'Z = 3 units'}])\n")
    at = AppTest.from_string(script, default_timeout=30).run()
    assert not at.exception
    md = [m.value for m in at.markdown]
    for label in ("**Governing equation**", "**Where**", "**Calculation**"):
        assert label in md
    assert any(m.startswith("**Q_h**") and "- Substitution: `1.5 × 4.18 × (100 − 60)`" in m and "- Intermediate: `1.5 × 4.18 × 40`" in m and "- **Result: Q_h = 250.80 kW**" in m for m in md)
    assert any("$Q_h$: heat given up by the hot fluid [kW]" in m for m in md) and len(at.latex) == 6 and "Z = 3 units" in " ".join(md)

# ====================================================================== 6. the pages
def _page(page="views/heat_exchanger.py"):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.button(key="do_guest").click().run()
    return at.switch_page(page).run()

def _set(at, **values):
    for key, v in values.items():
        at.number_input(key=key).set_value(v)
    return at.run()

def test_default_page_shows_full_kpis_a_success_balance_and_no_warnings():
    at = _page()
    assert not at.exception
    kpi = {m.label: m.value for m in at.metric}
    assert kpi == {"Heat duty Q": "250.8 kW", "LMTD": "44.81 K", "Correction factor F": "1.000", "Overall U": "559.6 W/m²K"}     # the full number and unit, as text
    assert any("Heat balance closes" in s.value and "0.00%" in s.value for s in at.success) and not at.error and not at.warning
    assert all(m.help for m in at.metric)

def test_a_mismatch_above_one_percent_is_a_red_error_with_the_exact_percentage():
    at = _set(_page(), mc=2.1)
    assert any("HEAT BALANCE DOES NOT CLOSE" in e.value and "4.88%" in e.value and "tolerance 1%" in e.value for e in at.error)
    assert not any("closes" in s.value for s in at.success) and any("only the hot-side duty" in c.value for c in at.caption)
    at = _set(_page(), mc=2.03)
    assert any("1.49%" in e.value for e in at.error)                                                     # just above the 1% tolerance is still an error
    assert any("Heat balance closes" in s.value for s in _set(_page(), mc=2.004).success)                # 0.2% is fine

def test_a_severe_mismatch_says_so_and_the_tolerance_can_be_raised_for_plant_data():
    at = _set(_page(), mc=2.5)
    assert any("at least one reading is wrong" in e.value for e in at.error)
    at = _set(_page(), mc=2.1, hx_tol=5.0)
    assert not at.error and any("tolerance 5%" in s.value for s in at.success)

def test_temperature_crossover_stops_the_page_with_a_clear_error():
    at = _set(_page(), tco=110.0)
    assert any("Temperature cross at the hot-inlet end" in e.value and "100 − 110" in e.value for e in at.error) and len(at.metric) == 0
    at = _set(_page(), tci=65.0, tco=90.0)                                                              # the cold side heats up, but the hot outlet (60) is below the cold inlet (65)
    assert any("hot-outlet end" in e.value and "60 − 65" in e.value for e in at.error)
    at = _page(); at.selectbox(key="hx_flow").select("Parallel flow").run()
    at = _set(at, tco=70.0)
    assert any("Temperature cross at the outlet end of a parallel-flow exchanger" in e.value for e in at.error)

def test_small_approach_and_low_f_warnings_appear_on_the_page():
    at = _set(_page(), tco=98.0)
    assert any("only 2 K" in w.value for w in at.warning)
    at = _page(); at.selectbox(key="hx_flow").select("1 shell pass / 2 tube passes").run()
    assert not at.warning and any("R = 1.333 and P = 0.375" in c.value and "not read from a chart" in c.value for c in at.caption)
    at = _set(at, tho=55.0, tco=66.0, mc=1.5)
    assert any("below 0.75" in w.value and "more heat transfer area" in w.value for w in at.warning) and float(at.metric[2].value) < 0.75

def test_profile_tab_carries_the_counter_flow_annotation_and_the_steps_tab_the_new_format():
    at = _page()
    charts = at.get("plotly_chart")
    assert len(charts) == 1
    import json
    spec = json.loads(charts[0].proto.spec)
    texts = [a["text"] for a in spec["layout"]["annotations"]]
    cold = next(t for t in spec["data"] if t["name"] == "Cold fluid")
    assert cold["y"][0] > cold["y"][-1] and any("cold line is reversed" in t for t in texts) and any(t == "<b>Cold OUT 50 °C</b>" for t in texts)
    md = [m.value for m in at.markdown]
    assert "**Governing equation**" in md and "**Where**" in md and any("- Intermediate: `1.5 × 4.18 × 40`" in m for m in md) and any("Result: U = 559.6 W/m²K" in m for m in md)
    assert any("not the length" in c.value for c in at.caption)

def test_parallel_flow_page_has_no_reversal_note():
    at = _page(); at.selectbox(key="hx_flow").select("Parallel flow").run()
    spec = __import__("json").loads(at.get("plotly_chart")[0].proto.spec)
    assert not any("reversed" in a["text"] for a in spec["layout"]["annotations"]) and any(a["text"] == "<b>Cold in 20 °C</b>" for a in spec["layout"]["annotations"])

def test_solver_page_uses_the_error_style_for_the_balance_and_the_new_steps():
    at = _page("views/solver.py")
    for key, v in (("sv_mh", 5.0), ("sv_cph", 4.18), ("sv_mc", 6.75), ("sv_cpc", 4.18), ("sv_a", 40.0)):
        at.number_input(key=key).set_value(v)
    at.run()
    assert not at.exception and any(e.value.startswith("HEAT BALANCE DOES NOT CLOSE") for e in at.error) and not any("HEAT BALANCE" in w.value for w in at.warning)
    md = [m.value for m in at.markdown]
    assert "**Governing equation**" in md and any(m.startswith("- Substitution:") or "- Substitution:" in m for m in md)
    spec = __import__("json").loads(at.get("plotly_chart")[0].proto.spec)
    assert any("cold line is reversed" in a["text"] for a in spec["layout"]["annotations"])

# ====================================================================== 7. tooltips
def test_every_input_on_the_heat_exchanger_page_has_a_useful_tooltip():
    at = _page()
    keys = ["mh", "cph", "thi", "tho", "mc", "cpc", "tci", "tco", "hx_area", "hx_tol"]
    for k in keys:
        h = at.number_input(key=k).help
        assert h and len(h) >= 60, k
    assert "Must be greater than 0" in at.number_input(key="mh").help and "kg/h" in at.number_input(key="mh").help
    assert "4.18" in at.number_input(key="cph").help and "greater than 0" in at.number_input(key="cph").help
    for k in ("thi", "tho", "tci", "tco"):
        assert "Must be" in at.number_input(key=k).help or "must be" in at.number_input(key=k).help.lower()
    assert "absolute zero" in at.number_input(key="thi").help and "temperature cross" in at.number_input(key="thi").help
    assert "1 to 1,000 m²" in at.number_input(key="hx_area").help and "1%" in at.number_input(key="hx_tol").help and "2 to 5%" in at.number_input(key="hx_tol").help
    assert "Counter-flow" in at.selectbox(key="hx_flow").help and "F" in at.selectbox(key="hx_flow").help and at.checkbox(key="hx_know").help
    at.checkbox(key="hx_know").check().run()
    assert "800 to 1,500" in at.number_input(key="hx_uc").help

# ====================================================================== 8. KPI cards
def test_the_stylesheet_stops_streamlit_from_cutting_kpi_values():
    css = branding.CSS
    block = re.search(r'\[data-testid="stMetricValue"\], \[data-testid="stMetricValue"\] \*.*?\{(.*?)\}', css, re.S).group(1)
    for rule in ("overflow: visible !important", "text-overflow: clip !important", "white-space: normal !important", "overflow-wrap: anywhere"):
        assert rule in block, rule
    assert "text-overflow: ellipsis" not in css and "clamp(" in css and 'stMetricLabel"] *' in css and 'stMetricDelta"] *' in css

@pytest.mark.parametrize("value", [559.6, 5559.6, 123456.7, 98765432.1])
def test_long_values_reach_the_page_in_full(value):
    text = f"{value:,.1f} W/m²K"
    script = f"import streamlit as st\nst.metric('Overall U', {text!r})\n"
    at = AppTest.from_string(script).run()
    assert at.metric[0].value == text and text.endswith("W/m²K")
