"""The pieces of a worked solution for the heat exchanger pages.

Every step has five parts:
  * the governing equation (LaTeX),
  * the definition of its variables,
  * the numerical substitution,
  * an intermediate calculation, and
  * the final result with its units.
The numbers come from the same engine as the answers, so the text can never disagree with the result.
Temperatures are in °C, flows in kg/s, Cp in kJ/(kg·K), duties in kW, area in m², U in W/(m²·K).
"""
import math

from . import heat_exchanger as hx

VARS = {
    "Q_h": "heat given up by the hot fluid [kW]", "Q_c": "heat taken up by the cold fluid [kW]", "Q": "heat duty used in the calculation [kW]",
    r"\dot m_h": "mass flow of the hot fluid [kg/s]", r"\dot m_c": "mass flow of the cold fluid [kg/s]",
    "C_{p,h}": "specific heat of the hot fluid [kJ/kg·K]", "C_{p,c}": "specific heat of the cold fluid [kJ/kg·K]",
    "T_{h,in}": "hot fluid inlet temperature [°C]", "T_{h,out}": "hot fluid outlet temperature [°C]",
    "T_{c,in}": "cold fluid inlet temperature [°C]", "T_{c,out}": "cold fluid outlet temperature [°C]",
    "A": "heat transfer area [m²]", "U": "overall heat transfer coefficient [W/m²·K]", "F": "LMTD correction factor [-], 1 for pure counter-flow",
    "R": "ratio of the two temperature changes (hot change ÷ cold change) [-]", "P": "cold-side temperature effectiveness (cold change ÷ largest possible change) [-]",
    r"\Delta T_{lm,corr}": "corrected mean temperature difference, F × LMTD [K]", "LMTD": "log mean temperature difference [K]",
}
COUNTER_DT = {r"\Delta T_1": "temperature difference at the hot-inlet end, T(h,in) − T(c,out) [K]",
              r"\Delta T_2": "temperature difference at the hot-outlet end, T(h,out) − T(c,in) [K]"}
PARALLEL_DT = {r"\Delta T_1": "temperature difference at the inlet end, T(h,in) − T(c,in) [K]",
               r"\Delta T_2": "temperature difference at the outlet end, T(h,out) − T(c,out) [K]"}


def _v(*symbols, extra=None):
    table = {**VARS, **(extra or {})}
    return [[s, table[s]] for s in symbols]


def _calc(label, substitution, result, intermediate=None):
    return {"label": label, "substitution": substitution, "intermediate": intermediate, "result": result}


def _g(x):
    return f"{x:.6g}"


# ---------------------------------------------------------------------------- heat duty
def duty_parts(side, m, cp, t_in, t_out, q_kw):
    """Variables and calculation blocks for Q = m·Cp·ΔT on the 'hot' or 'cold' side (cp in kJ/kg·K, result in kW)."""
    hot = side == "hot"
    dt = abs(t_in - t_out)
    first, second = ("T_{h,in}", "T_{h,out}") if hot else ("T_{c,out}", "T_{c,in}")
    a, b = (t_in, t_out) if hot else (t_out, t_in)
    sym = "h" if hot else "c"
    return {"variables": _v(f"Q_{sym}", rf"\dot m_{sym}", f"C_{{p,{sym}}}", first, second),
            "calc": [_calc(f"Q_{sym}", f"{_g(m)} × {_g(cp)} × ({_g(a)} − {_g(b)})", f"Q_{sym} = {q_kw:,.2f} kW", f"{_g(m)} × {_g(cp)} × {_g(dt)}")]}


# ---------------------------------------------------------------------------- LMTD
def lmtd_parts(flow, th_in, th_out, tc_in, tc_out, lm):
    d1, d2 = hx.terminal_differences(th_in, th_out, tc_in, tc_out, flow)
    c_hot_in, c_hot_out = (tc_out, tc_in) if flow == "counter" else (tc_in, tc_out)
    dts = COUNTER_DT if flow == "counter" else PARALLEL_DT
    calcs = [_calc("ΔT₁", f"{_g(th_in)} − {_g(c_hot_in)}", f"ΔT₁ = {_g(d1)} K"),
             _calc("ΔT₂", f"{_g(th_out)} − {_g(c_hot_out)}", f"ΔT₂ = {_g(d2)} K")]
    if math.isclose(d1, d2, rel_tol=1e-9):
        calcs.append(_calc("LMTD", "ΔT₁ = ΔT₂, so LMTD = ΔT", f"LMTD = {_g(d1)} K"))
    else:
        ratio = d1 / d2
        calcs.append(_calc("LMTD", f"({_g(d1)} − {_g(d2)}) / ln({_g(d1)} / {_g(d2)})", f"LMTD = {lm:.3f} K",
                           f"{_g(d1 - d2)} / ln({ratio:.5g}) = {_g(d1 - d2)} / {math.log(ratio):.5f}"))
    return {"variables": _v(r"\Delta T_1", r"\Delta T_2", "LMTD", extra=dts), "calc": calcs}


# ---------------------------------------------------------------------------- R, P and F
def rp_parts(th_in, th_out, tc_in, tc_out):
    r, p = (th_in - th_out) / (tc_out - tc_in), (tc_out - tc_in) / (th_in - tc_in)
    return {"variables": _v("R", "P", "T_{h,in}", "T_{h,out}", "T_{c,in}", "T_{c,out}"),
            "calc": [_calc("R", f"({_g(th_in)} − {_g(th_out)}) / ({_g(tc_out)} − {_g(tc_in)})", f"R = {r:.4f}", f"{_g(th_in - th_out)} / {_g(tc_out - tc_in)}"),
                     _calc("P", f"({_g(tc_out)} − {_g(tc_in)}) / ({_g(th_in)} − {_g(tc_in)})", f"P = {p:.4f}", f"{_g(tc_out - tc_in)} / {_g(th_in - tc_in)}")]}


def f_pieces_1_2(r, p):
    """The parts of the closed-form F for one shell pass and two tube passes (Underwood / Bowman)."""
    special = abs(r - 1.0) < 1e-6
    s = math.sqrt(2.0) if special else math.sqrt(r * r + 1.0)
    if special:
        num = s * p / (1 - p)
        top, bot = 2 - p * (2 - s), 2 - p * (2 + s)
    else:
        num = s / (r - 1) * math.log((1 - p) / (1 - p * r))
        top, bot = 2 - p * (r + 1 - s), 2 - p * (r + 1 + s)
    den = math.log(top / bot)
    return {"special": special, "s": s, "num": num, "top": top, "bot": bot, "arg": top / bot, "den": den, "f": num / den}


def f_parts_1_2(r, p):
    k = f_pieces_1_2(r, p)
    s, f = k["s"], k["f"]
    if k["special"]:
        calcs = [_calc("s (R = 1)", "√2", f"s = {s:.4f}"),
                 _calc("Numerator", f"{s:.4f} × {p:.4f} / (1 − {p:.4f})", f"Numerator = {k['num']:.4f}", f"{s:.4f} × {p:.4f} / {1 - p:.4f}"),
                 _calc("Denominator", f"ln[(2 − {p:.4f} × (2 − {s:.4f})) / (2 − {p:.4f} × (2 + {s:.4f}))]", f"Denominator = {k['den']:.4f}",
                       f"ln({k['top']:.4f} / {k['bot']:.4f}) = ln({k['arg']:.4f})")]
    else:
        a, b = 1 - p, 1 - p * r
        calcs = [_calc("s", f"√({r:.4f}² + 1)", f"s = {s:.4f}", f"√{r * r + 1:.4f}"),
                 _calc("Numerator", f"{s:.4f} / ({r:.4f} − 1) × ln[(1 − {p:.4f}) / (1 − {p:.4f} × {r:.4f})]", f"Numerator = {k['num']:.4f}",
                       f"{s / (r - 1):.4f} × ln({a:.4f} / {b:.4f}) = {s / (r - 1):.4f} × ln({a / b:.4f})"),
                 _calc("Denominator", f"ln[(2 − {p:.4f} × ({r:.4f} + 1 − {s:.4f})) / (2 − {p:.4f} × ({r:.4f} + 1 + {s:.4f}))]", f"Denominator = {k['den']:.4f}",
                       f"ln({k['top']:.4f} / {k['bot']:.4f}) = ln({k['arg']:.4f})")]
    calcs.append(_calc("F", f"{k['num']:.4f} / {k['den']:.4f}", f"F = {f:.4f}"))
    return {"variables": _v("F", "R", "P", extra={"s": r"intermediate quantity, √(R² + 1) [-]"}), "calc": calcs}


def p1_parts(r, p, n):
    """The effectiveness of each shell when n identical 1-2 shells in series give the overall P."""
    p1 = hx.shell_effectiveness(r, p, n)
    if abs(r - 1.0) < 1e-9:
        calcs = [_calc("P₁ (each shell)", f"{p:.4f} / ({n} − ({n} − 1) × {p:.4f})", f"P₁ = {p1:.4f}")]
    else:
        x = ((1 - p * r) / (1 - p)) ** (1.0 / n)
        calcs = [_calc("x", f"((1 − {p:.4f} × {r:.4f}) / (1 − {p:.4f}))^(1/{n})", f"x = {x:.4f}", f"({(1 - p * r) / (1 - p):.4f})^(1/{n})"),
                 _calc("P₁ (each shell)", f"({x:.4f} − 1) / ({x:.4f} − {r:.4f})", f"P₁ = {p1:.4f}")]
    return {"variables": [["P", VARS["P"]], ["R", VARS["R"]], ["N", "number of shell passes in series [-]"], ["x", "intermediate quantity [-]"],
                          ["P_1", "effectiveness of one shell [-]"]], "calc": calcs}


def given_duty_parts(q_kw):
    return {"variables": [["Q", "heat duty given in the problem [kW]"]], "calc": [_calc("Q", "as given in the problem", f"Q = {q_kw:,.2f} kW")]}


def f_parts_n(r, p, n, include_p1=True):
    """Blocks for N identical 1-2 shells in series: F = NTU(counter-flow) / (N × NTU of one shell)."""
    special = abs(r - 1.0) < 1e-9
    s = math.sqrt(2.0) if special else math.sqrt(r * r + 1.0)
    ntu_c = hx._ntu_counter(r, p)
    p1 = hx.shell_effectiveness(r, p, n)
    ntu_s = hx._ntu_1_2(r, p1, n)
    f = ntu_c / (n * ntu_s)
    if special:
        calcs = [_calc("NTU (counter-flow)", f"{p:.4f} / (1 − {p:.4f})", f"NTU_counter = {ntu_c:.4f}"),
                 _calc("P₁ (each shell)", f"{p:.4f} / ({n} − ({n} − 1) × {p:.4f})", f"P₁ = {p1:.4f}")]
    else:
        x = ((1 - p * r) / (1 - p)) ** (1.0 / n)
        calcs = [_calc("NTU (counter-flow)", f"ln[(1 − {p:.4f}) / (1 − {p:.4f} × {r:.4f})] / ({r:.4f} − 1)", f"NTU_counter = {ntu_c:.4f}",
                       f"ln({(1 - p) / (1 - p * r):.4f}) / {r - 1:.4f}"),
                 _calc("x", f"((1 − {p:.4f} × {r:.4f}) / (1 − {p:.4f}))^(1/{n})", f"x = {x:.4f}", f"({(1 - p * r) / (1 - p):.4f})^(1/{n})"),
                 _calc("P₁ (each shell)", f"({x:.4f} − 1) / ({x:.4f} − {r:.4f})", f"P₁ = {p1:.4f}")]
    if not include_p1:                                   # the previous step already showed x and P1
        calcs = [c for c in calcs if c["label"] not in ("x", "P₁ (each shell)")]
    top, bot = 2 - p1 * (r + 1 - s), 2 - p1 * (r + 1 + s)
    calcs += [_calc("NTU (one shell)", f"ln[(2 − {p1:.4f} × ({r:.4f} + 1 − {s:.4f})) / (2 − {p1:.4f} × ({r:.4f} + 1 + {s:.4f}))] / {s:.4f}", f"NTU_shell = {ntu_s:.4f}",
                    f"ln({top:.4f} / {bot:.4f}) / {s:.4f} = ln({top / bot:.4f}) / {s:.4f}"),
              _calc("F", f"{ntu_c:.4f} / ({n} × {ntu_s:.4f})", f"F = {f:.4f}")]
    variables = [["F", VARS["F"]], ["R", VARS["R"]], ["P", VARS["P"]], ["N", "number of shell passes in series [-]"], ["P_1", "effectiveness of one shell [-]"],
                 ["NTU", "number of transfer units, UA ÷ smallest heat capacity rate [-]"]]
    return {"variables": variables, "calc": calcs}


def corrected_parts(f, base, eff):
    return {"variables": _v("F", "LMTD", r"\Delta T_{lm,corr}"), "calc": [_calc("ΔT_lm,corr", f"{f:.4f} × {base:.3f}", f"ΔT_lm,corr = {eff:.3f} K")]}


# ---------------------------------------------------------------------------- U, area and the rest
def u_parts(q_kw, area, lm_eff, u):
    return {"variables": _v("U", "Q", "A", r"\Delta T_{lm,corr}", extra={r"\Delta T_{lm,corr}": "mean temperature difference used (LMTD × F) [K]"}),
            "calc": [_calc("U", f"{q_kw:,.2f} × 1,000 / ({_g(area)} × {lm_eff:.3f})", f"U = {u:,.1f} W/m²K", f"{q_kw * 1000:,.0f} / {area * lm_eff:.3f}")]}


def area_parts(q_kw, u_eff, lm_eff, area):
    return {"variables": _v("A", "Q", "U", r"\Delta T_{lm,corr}", extra={r"\Delta T_{lm,corr}": "mean temperature difference used (LMTD × F) [K]"}),
            "calc": [_calc("A", f"{q_kw:,.2f} × 1,000 / ({_g(u_eff)} × {lm_eff:.3f})", f"A = {area:,.2f} m²", f"{q_kw * 1000:,.0f} / {u_eff * lm_eff:.3f}")]}


def flow_parts(side, q_kw, cp, t_a, t_b, m):
    sym = "c" if side == "cold" else "h"
    dt = abs(t_a - t_b)
    hi, lo = (t_a, t_b) if t_a > t_b else (t_b, t_a)
    return {"variables": _v(rf"\dot m_{sym}", "Q", f"C_{{p,{sym}}}"),
            "calc": [_calc(rf"ṁ_{sym}", f"{q_kw:,.2f} / ({_g(cp)} × ({_g(hi)} − {_g(lo)}))", f"ṁ_{sym} = {m:.3f} kg/s", f"{q_kw:,.2f} / ({_g(cp)} × {_g(dt)}) = {q_kw:,.2f} / {cp * dt:.4f}")]}


def tube_area_parts(n_tubes, od, length, installed):
    return {"variables": [["N", "number of tubes [-]"], ["D_o", "tube outside diameter [m]"], ["L", "tube length [m]"], ["A", "outside heat transfer area of the tubes [m²]"]],
            "calc": [_calc("A", f"{_g(n_tubes)} × π × {od:.4f} × {_g(length)}", f"A = {installed:.3f} m²", f"{n_tubes * math.pi:.4f} × {od:.4f} × {_g(length)}")]}


def over_surface_parts(installed, required, over):
    return {"variables": [["A_{installed}", "area of the installed tubes [m²]"], ["A_{required}", "area required for the duty [m²]"]],
            "calc": [_calc("over-surface", f"({installed:.2f} / {required:.2f} − 1) × 100", f"over-surface = {over:+.1f} %", f"({installed / required:.4f} − 1) × 100")]}


def tubes_needed_parts(area, od, length, n_exact, n_whole):
    return {"variables": [["N", "number of tubes [-]"], ["A", "required area [m²]"], ["D_o", "tube outside diameter [m]"], ["L", "tube length [m]"]],
            "calc": [_calc("N", f"{area:.3f} / (π × {od:.4f} × {_g(length)})", f"N = {n_exact:.2f}, so {n_whole} tubes", f"{area:.3f} / {math.pi * od * length:.4f}")]}


def tube_length_parts(area, n_tubes, od, length):
    return {"variables": [["L", "tube length [m]"], ["A", "required area [m²]"], ["N", "number of tubes [-]"], ["D_o", "tube outside diameter [m]"]],
            "calc": [_calc("L", f"{area:.3f} / ({_g(n_tubes)} × π × {od:.4f})", f"L = {length:.3f} m", f"{area:.3f} / {n_tubes * math.pi * od:.4f}")]}


# ---------------------------------------------------------------------------- the Heat Exchanger page
def _step(title, formula, parts, working):
    return {"title": title, "formula": formula, "working": working, **parts}


def page_steps(m_h, cp_h, th_in, th_out, m_c, cp_c, tc_in, tc_out, area, flow, u_clean, result, tol_pct=hx.HEAT_BALANCE_TOL_PCT):
    """The full worked solution for the Heat Exchanger page. cp_h and cp_c in kJ/(kg·K). `result` is hx.analyze() output."""
    r, qh, qc = result, result["q_hot"] / 1000, result["q_cold"] / 1000
    base_flow = "counter" if flow == "shell_1_2" else flow
    steps = []
    steps.append(_step("Heat given up by the hot fluid", r"Q_h=\dot m_h\,C_{p,h}\,(T_{h,in}-T_{h,out})", duty_parts("hot", m_h, cp_h, th_in, th_out, qh), f"Q_h = {qh:,.2f} kW"))
    steps.append(_step("Heat taken up by the cold fluid", r"Q_c=\dot m_c\,C_{p,c}\,(T_{c,out}-T_{c,in})", duty_parts("cold", m_c, cp_c, tc_in, tc_out, qc), f"Q_c = {qc:,.2f} kW"))
    m = r["mismatch_pct"]
    verdict = "the heat balance closes" if r["balance"]["ok"] else "the heat balance DOES NOT close"
    steps.append(_step("Heat balance check", r"\text{mismatch}=\dfrac{|Q_h-Q_c|}{(Q_h+Q_c)/2}\times 100",
                       {"variables": _v("Q_h", "Q_c", extra={}) + [["tolerance", f"accepted mismatch, {tol_pct:g} % [%]"]],
                        "calc": [_calc("mismatch", f"|{qh:.2f} − {qc:.2f}| / (({qh:.2f} + {qc:.2f}) / 2) × 100", f"mismatch = {m:.2f} %  (tolerance {tol_pct:g} %: {verdict})",
                                       f"{abs(qh - qc):.4f} / {(qh + qc) / 2:.4f} × 100")]}, f"mismatch = {m:.2f} %"))
    q = r["q_avg"] / 1000
    steps.append(_step("Duty used for U", r"Q=\dfrac{Q_h+Q_c}{2}",
                       {"variables": _v("Q", "Q_h", "Q_c"), "calc": [_calc("Q", f"({qh:.2f} + {qc:.2f}) / 2", f"Q = {q:,.2f} kW")]}, f"Q = {q:,.2f} kW"))
    lm_title = "Log mean temperature difference (counter-flow)" if base_flow == "counter" else "Log mean temperature difference (parallel flow)"
    lm_formula = (r"\Delta T_1=T_{h,in}-T_{c,out},\ \ \Delta T_2=T_{h,out}-T_{c,in},\ \ LMTD=\dfrac{\Delta T_1-\Delta T_2}{\ln(\Delta T_1/\Delta T_2)}" if base_flow == "counter"
                  else r"\Delta T_1=T_{h,in}-T_{c,in},\ \ \Delta T_2=T_{h,out}-T_{c,out},\ \ LMTD=\dfrac{\Delta T_1-\Delta T_2}{\ln(\Delta T_1/\Delta T_2)}")
    steps.append(_step(lm_title, lm_formula, lmtd_parts(base_flow, th_in, th_out, tc_in, tc_out, r["lmtd"]), f"LMTD = {r['lmtd']:.3f} K"))
    if flow == "shell_1_2":
        steps.append(_step("R and P", r"R=\dfrac{T_{h,in}-T_{h,out}}{T_{c,out}-T_{c,in}},\quad P=\dfrac{T_{c,out}-T_{c,in}}{T_{h,in}-T_{c,in}}", rp_parts(th_in, th_out, tc_in, tc_out),
                           f"R = {r['r_ratio']:.4f}, P = {r['p_ratio']:.4f}"))
        steps.append(_step("Correction factor F (1 shell pass, 2 tube passes)",
                           r"F=\dfrac{\dfrac{\sqrt{R^2+1}}{R-1}\ln\dfrac{1-P}{1-PR}}{\ln\dfrac{2-P\left(R+1-\sqrt{R^2+1}\right)}{2-P\left(R+1+\sqrt{R^2+1}\right)}}",
                           f_parts_1_2(r["r_ratio"], r["p_ratio"]), f"F = {r['f']:.4f}"))
        steps.append(_step("Corrected mean temperature difference", r"\Delta T_{lm,corr}=F\cdot LMTD", corrected_parts(r["f"], r["lmtd"], r["f"] * r["lmtd"]), f"{r['f'] * r['lmtd']:.3f} K"))
    steps.append(_step("Overall heat transfer coefficient", r"U=\dfrac{Q}{A\,F\,LMTD}", u_parts(q, area, r["f"] * r["lmtd"], r["u"]), f"U = {r['u']:,.1f} W/m²K"))
    if r["rf"] is not None:
        steps.append(_step("Fouling resistance", r"R_f=\dfrac{1}{U_{fouled}}-\dfrac{1}{U_{clean}}",
                           {"variables": [["R_f", "fouling resistance [m²·K/W]"], ["U_{fouled}", "U calculated from the readings [W/m²·K]"], ["U_{clean}", "clean (design) U [W/m²·K]"]],
                            "calc": [_calc("R_f", f"1 / {r['u']:.1f} − 1 / {_g(u_clean)}", f"R_f = {r['rf']:.6f} m²K/W", f"{1 / r['u']:.7f} − {1 / u_clean:.7f}")]},
                           f"Rf = {r['rf']:.6f}"))
        steps.append(_step("Loss of U compared with clean", r"\text{loss}=\left(1-\dfrac{U_{fouled}}{U_{clean}}\right)\times 100",
                           {"variables": [["U_{fouled}", "U calculated from the readings [W/m²·K]"], ["U_{clean}", "clean (design) U [W/m²·K]"]],
                            "calc": [_calc("loss", f"(1 − {r['u']:.1f} / {_g(u_clean)}) × 100", f"loss = {r['u_loss_pct']:.1f} %", f"(1 − {r['u'] / u_clean:.4f}) × 100")]},
                           f"loss = {r['u_loss_pct']:.1f} %"))
    return steps
