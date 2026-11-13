"""Worked solution for the Pump & Pipeline page.

Every step has: a number and a concept (its title), the governing equation, the variables with their units, the numerical
substitution, an intermediate calculation, the result with units, and a short engineering interpretation.
The numbers come from the same engine as the answers (calc_engine.pump_pipe), so the text cannot disagree with the result.
Units here: diameter m, flow m3/s (also shown in m3/h), head m, power kW, g = 9.80665 m/s2.
"""
import math

from . import pump_pipe as pp

RHO20, MU20 = 998.21, 1.002e-3


def _g(x):
    """Six significant figures: used in every substitution, so a small pipe or flow never loses precision."""
    return f"{x:.6g}"


def _fmt(x):
    """Fixed decimals for ordinary numbers, four significant figures for small ones (a 5 mm pipe has an area of 0.0000196 m2)."""
    return f"{x:.6f}" if abs(x) >= 1e-3 else f"{x:.4g}"


def fmt_flow(x):
    """A flow or similar quantity with one decimal, or four significant figures below 1."""
    return f"{x:,.1f}" if abs(x) >= 1 else f"{x:.4g}"


def fmt_power(x):
    return f"{x:.3f}" if abs(x) >= 1e-3 else f"{x:.4g}"


def _calc(label, substitution, result, intermediate=None, numeric=True):
    c = {"label": label, "substitution": substitution, "intermediate": intermediate, "result": result}
    if not numeric:
        c["numeric"] = False          # text instead of arithmetic: nothing to evaluate
    return c


def _step(title, formula, variables, calcs, interpretation):
    return {"title": title, "formula": formula, "variables": variables, "calc": calcs, "interpretation": interpretation, "working": calcs[-1]["result"]}


REGIME_TEXT = {"laminar": "Laminar", "transition (uncertain)": "Transitional (uncertain)", "turbulent": "Turbulent"}


def velocity_comment(v):
    if v < 1.0:
        return f"{v:.2f} m/s is below the usual 1 to 3 m/s for water lines: friction losses are low, which suits a suction line, but a discharge line this slow is oversized."
    if v <= 3.0:
        return f"{v:.2f} m/s is inside the usual 1 to 3 m/s design range for water lines."
    return f"{v:.2f} m/s is above 3 m/s: expect high friction losses, noise and erosion, and a greater water-hammer risk. A larger pipe would help."


def regime_comment(re):
    if re < pp.RE_LAMINAR_MAX:
        return "Laminar flow (Re < 2,300): layers slide smoothly, friction depends only on Re and not on the pipe wall roughness."
    if re < pp.RE_TURBULENT_MIN:
        return "Transitional flow (2,300 to 4,000): the flow switches between laminar and turbulent, so the friction factor is uncertain here. A straight-line blend is used. Avoid designing in this range."
    return "Turbulent flow (Re > 4,000): eddies dominate, so the friction factor depends on both Re and the relative roughness. This is the normal case for water lines."


def build_steps(p):
    """p: dict with the inputs and results (see views/pump_pipeline.py). Returns the list of steps."""
    rho, mu, d, length, rough, sum_k, le_d = p["rho"], p["mu"], p["d"], p["length"], p["rough"], p["sum_k"], p["le_d"]
    op, coeffs, pts, static = p["op"], p["coeffs"], p["pts"], p["static"]
    a, b, c = coeffs
    q, h, v, re, f = op["q"], op["h"], op["v"], op["re"], op["f"]
    area = op["area"]
    vh = v * v / (2 * pp.G)
    hf, hle, hk = f * length / d * vh, f * le_d * vh, sum_k * vh
    steps = []

    # ---- 1. fluid properties
    t = p["temp"]
    expo = (1.3272 * (20 - t) - 0.001053 * (t - 20) ** 2) / (t + 105)
    drho, dmu = (rho / RHO20 - 1) * 100, (mu / MU20 - 1) * 100
    steps.append(_step(
        "Fluid properties of water", r"\rho(T)=\dfrac{999.83952+16.945176T-7.9870401{\times}10^{-3}T^2-46.170461{\times}10^{-6}T^3+105.56302{\times}10^{-9}T^4-280.54253{\times}10^{-12}T^5}{1+16.879850{\times}10^{-3}T},\qquad "
                           r"\log_{10}\dfrac{\mu}{\mu_{20}}=\dfrac{1.3272\,(20-T)-0.001053\,(T-20)^2}{T+105}",
        [["T", "water temperature", "°C"], [r"\rho", "density", "kg/m³"], [r"\mu", "dynamic viscosity", "mPa·s"], [r"\mu_{20}", "viscosity of water at 20 °C (reference)", "1.002 mPa·s"]],
        [_calc("ρ", f"Kell (1975) polynomial evaluated at T = {_g(t)} °C", f"ρ = {rho:.2f} kg/m³", numeric=False),
         _calc("μ", f"1.002 × 10^((1.3272 × (20 − {_g(t)}) − 0.001053 × ({_g(t)} − 20)²) / ({_g(t)} + 105))", f"μ = {mu * 1000:.4f} mPa·s", f"1.002 × 10^({expo:.5f})")],
        f"Compared with water at 20 °C this water is {abs(drho):.2f}% {'less' if drho < 0 else 'more'} dense and {abs(dmu):.0f}% {'less' if dmu < 0 else 'more'} viscous. "
        "Viscosity changes fast with temperature, so the temperature you enter matters for Re and for laminar friction."))

    # ---- 2. pump curve fit
    checks = [_calc(f"Check at datasheet point {i}", f"{_g(a)} + {_g(b)} × {_g(qi)} + {_g(c)} × {_g(qi)}²", f"H = {pp.pump_head(coeffs, qi):.3f} m  (datasheet {hi:g} m at {qi * 3600:g} m³/h)")
              for i, (qi, hi) in enumerate(pts, 1)]
    steps.append(_step(
        "Pump curve polynomial fit", r"H_{pump}=a+bQ+cQ^2",
        [["H_{pump}", "pump head", "m"], ["Q", "flow", "m³/s"], ["a", "head at zero flow (shut-off head)", "m"], ["b", "linear coefficient", "m / (m³/s)"], ["c", "quadratic coefficient", "m / (m³/s)²"]],
        [_calc("a, b, c", "the three equations H_i = a + b·Q_i + c·Q_i² solved together (Cramer's rule)", f"a = {a:.4f} m, b = {b:.3f} m/(m³/s), c = {c:.2f} m/(m³/s)²", numeric=False)] + checks,
        f"The curve starts at {a:.1f} m at zero flow and passes exactly through your three datasheet points. A quadratic is only trustworthy between the data points; "
        + ("it is falling over the whole range." if b + 2 * c * max(x[0] for x in pts) < 0 else "it is NOT falling at the largest datasheet flow, so check the points.")))

    # ---- 3. operating point
    share = q / p["q_data_max"] * 100
    steps.append(_step(
        "Operating point: pump curve meets system curve", r"H_{pump}(Q)=H_{sys}(Q)=H_{static}+\left(f\dfrac{L}{D}+\Sigma K\right)\dfrac{v^2}{2g}",
        [["Q^*", "operating flow", "m³/s"], ["H^*", "operating head", "m"], ["H_{static}", "static head", "m"], ["f", "Darcy friction factor", "-"], ["L, D", "pipe length and inside diameter", "m"], ["\\Sigma K", "fittings loss coefficients", "-"], ["v", "mean velocity", "m/s"], ["g", "standard gravity", "9.80665 m/s²"]],
        [_calc("Q* and H*", "pump head set equal to system head and solved numerically (bisection)", f"Q* = {fmt_flow(q * 3600)} m³/h = {_fmt(q)} m³/s;  H* = {h:.2f} m", numeric=False),
         _calc("Pump head at Q*", f"{_g(a)} + {_g(b)} × {_g(q)} + {_g(c)} × {_g(q)}²", f"H_pump = {h:.2f} m")],
        f"The pump delivers {fmt_flow(q * 3600)} m³/h at {h:.1f} m, which is {share:.0f}% of the largest datasheet flow ({p['q_data_max'] * 3600:g} m³/h). "
        + ("This is BEYOND the datasheet, so the curve there is an extrapolation: treat the results as indicative." if op["extrapolated"] else "It lies inside the datasheet range, so the curve is not extrapolated.")))

    # ---- 4. area
    steps.append(_step(
        "Cross-sectional area of the pipe", r"A=\dfrac{\pi D^2}{4}",
        [["A", "flow cross-section", "m²"], ["D", "inside diameter", "m"]],
        [_calc("A", f"π × {_g(d)}² / 4", f"A = {_fmt(area)} m²")],
        f"The inside diameter is {d * 1000:g} mm, so the flow area is {fmt_flow(area * 1e4)} cm². Doubling the diameter quadruples the area."))

    # ---- 5. flow rates
    m_dot = op["m_dot"]
    steps.append(_step(
        "Volumetric and mass flow rate", r"Q=\dfrac{Q_{m^3/h}}{3600},\qquad \dot m=\rho\,Q",
        [["Q", "volumetric flow", "m³/s"], ["Q_{m^3/h}", "volumetric flow", "m³/h"], [r"\dot m", "mass flow", "kg/s"], [r"\rho", "density", "kg/m³"]],
        [_calc("Q", f"{_g(q * 3600)} / 3600", f"Q = {_fmt(q)} m³/s"), _calc("ṁ", f"{rho:.2f} × {_g(q)}", f"ṁ = {fmt_power(m_dot)} kg/s")],
        f"That is {fmt_flow(q * 1000)} litres per second, or {fmt_flow(m_dot * 3.6)} tonnes of water per hour."))

    # ---- 6. velocity
    steps.append(_step(
        "Mean velocity", r"v=\dfrac{Q}{A}",
        [["v", "mean velocity", "m/s"], ["Q", "volumetric flow", "m³/s"], ["A", "flow area", "m²"]],
        [_calc("v", f"{_g(q)} / {_g(area)}", f"v = {v:.3f} m/s")], velocity_comment(v)))

    # ---- 7. Reynolds number and regime
    steps.append(_step(
        "Reynolds number and flow regime", r"Re=\dfrac{\rho\,v\,D}{\mu}\qquad\text{laminar }Re<2300,\ \ \text{transitional }2300\le Re<4000,\ \ \text{turbulent }Re\ge 4000",
        [["Re", "Reynolds number", "-"], [r"\rho", "density", "kg/m³"], ["v", "velocity", "m/s"], ["D", "inside diameter", "m"], [r"\mu", "dynamic viscosity", "Pa·s"]],
        [_calc("Re", f"{rho:.2f} × {_g(v)} × {_g(d)} / {_g(mu)}", f"Re = {re:,.0f}  ({REGIME_TEXT[op['regime']]})")], regime_comment(re)))

    # ---- 8. relative roughness
    rr = rough / d
    steps.append(_step(
        "Relative roughness", r"\dfrac{\varepsilon}{D}",
        [[r"\varepsilon", "absolute roughness of the pipe wall", "mm"], ["D", "inside diameter", "mm"]],
        [_calc("ε/D", f"{rough * 1000:g} / {d * 1000:g}", f"ε/D = {rr:.6f}")],
        f"A relative roughness of {rr:.5f} is {'small: a fairly smooth pipe' if rr < 1e-3 else 'moderate' if rr < 1e-2 else 'large: a rough or small pipe'}. The friction equations apply below 0.05."))

    # ---- 9. friction factor
    fd = pp.friction_detail(re, d, rough, op["method"])
    var_f = [["f", "Darcy friction factor", "-"], ["Re", "Reynolds number", "-"], [r"\varepsilon/D", "relative roughness", "-"]]
    if fd["kind"] == "laminar":
        fcalcs = [_calc("f", f"64 / {re:.1f}", f"f = {f:.5f}")]
        fformula, fnote = r"f=\dfrac{64}{Re}", "Laminar: friction is inversely proportional to Re, so the head loss is directly proportional to the viscosity and the flow."
    elif fd["kind"] == "transition":
        fl, ft, w = fd["f_lam_edge"], fd["f_turb_edge"], fd["weight"]
        fcalcs = [_calc("f at Re = 2300 (laminar)", "64 / 2300", f"f = {fl:.5f}"), _calc("f at Re = 4000 (Colebrook-White)", "Colebrook-White equation solved by iteration at Re = 4000", f"f = {ft:.5f}", numeric=False),
                  _calc("f in the transition zone", f"{fl:.5f} + ({re:.1f} − 2300) / 1700 × ({ft:.5f} − {fl:.5f})", f"f = {f:.5f}", f"{fl:.5f} + {w:.4f} × {ft - fl:.5f}")]
        fformula, fnote = r"f=f_{lam}(2300)+\dfrac{Re-2300}{1700}\left[f_{turb}(4000)-f_{lam}(2300)\right]", "No equation is reliable between Re 2,300 and 4,000. A straight-line blend between the two edge values avoids an artificial jump in the system curve; the result is only an estimate."
    else:
        sj = fd["f_swamee"]
        cw_label = "Colebrook-White (solved by iteration)" if op["method"] == "colebrook" else "Swamee-Jain (explicit)"
        if op["method"] == "colebrook":
            fcalcs = [_calc(cw_label, f"−2 × log10({_g(rr / 3.7)} + 2.51 / ({re:.0f} × √{_g(f)}))", f"1/√f = {1 / math.sqrt(f):.4f}, so f = {f:.5f}  ({fd['iterations']} iterations)", f"−2 × log10({_g(rr / 3.7)} + {_g(2.51 / (re * math.sqrt(f)))})")]
        else:
            fcalcs = []
        fcalcs.append(_calc("Swamee-Jain cross-check (explicit)", f"0.25 / log10({_g(rr / 3.7)} + 5.74 / {re:.0f}^0.9)^2", f"f = {sj:.5f}  ({(sj / f - 1) * 100:+.2f}% from the value used)"))
        fformula = (r"\dfrac{1}{\sqrt f}=-2\log_{10}\left(\dfrac{\varepsilon/D}{3.7}+\dfrac{2.51}{Re\sqrt f}\right)\quad\text{(Colebrook-White)}" if op["method"] == "colebrook"
                    else r"f=\dfrac{0.25}{\left[\log_{10}\left(\dfrac{\varepsilon/D}{3.7}+\dfrac{5.74}{Re^{0.9}}\right)\right]^2}\quad\text{(Swamee-Jain)}")
        fnote = (f"Colebrook-White is the implicit reference equation and was solved by iteration to 1e-13. The explicit Swamee-Jain formula, which can be repeated by hand, "
                 f"agrees within {abs(sj / f - 1) * 100:.2f}%.")
    steps.append(_step("Friction factor", fformula, var_f, fcalcs, fnote))

    # ---- 10. major loss
    dp_f_kpa = rho * pp.G * hf / 1000
    steps.append(_step(
        "Major loss in the straight pipe (Darcy-Weisbach)", r"h_f=f\,\dfrac{L}{D}\,\dfrac{v^2}{2g},\qquad \Delta P_f=\rho\,g\,h_f",
        [["h_f", "friction head loss", "m"], ["f", "friction factor", "-"], ["L", "pipe length", "m"], ["D", "inside diameter", "m"], ["v", "velocity", "m/s"], ["g", "gravity", "m/s²"], [r"\Delta P_f", "friction pressure drop", "kPa"]],
        [_calc("h_f", f"{_g(f)} × {length:g} / {_g(d)} × {_g(v)}² / (2 × {pp.G})", f"h_f = {fmt_power(hf)} m", f"{_g(f * length / d)} × {_g(vh)}"),
         _calc("ΔP_f", f"{rho:.2f} × {pp.G} × {_g(hf)} / 1000", f"ΔP_f = {fmt_power(dp_f_kpa)} kPa")],
        f"Friction in the straight pipe takes {hf:.2f} m of head, {hf / h * 100:.0f}% of the pump head. Because the loss grows with v², halving the flow would cut it to about a quarter."))

    # ---- 11. minor losses
    kcalcs, kformulas = [], []
    if sum_k > 0 or le_d == 0:
        kcalcs.append(_calc("h_K", f"{_g(sum_k)} × {_g(v)}² / (2 × {pp.G})", f"h_K = {fmt_power(hk)} m", f"{_g(sum_k)} × {_g(vh)}"))
        kformulas.append(r"h_K=\Sigma K\,\dfrac{v^2}{2g}")
    if le_d > 0:
        kcalcs.append(_calc("h_Le", f"{_g(f)} × {_g(le_d)} × {_g(v)}² / (2 × {pp.G})", f"h_Le = {fmt_power(hle)} m", f"{_g(f * le_d)} × {_g(vh)}"))
        kformulas.append(r"h_{Le}=f\,\dfrac{L_e}{D}\,\dfrac{v^2}{2g}")
    steps.append(_step(
        "Minor losses in fittings and valves", r",\qquad ".join(kformulas),
        [["h_K", "head lost in fittings (loss coefficients)", "m"], ["\\Sigma K", "sum of the loss coefficients", "-"], ["h_{Le}", "head lost in fittings (equivalent length)", "m"], ["L_e/D", "equivalent length of the fittings as a multiple of D", "-"]],
        kcalcs, f"Fittings and valves take {hk + hle:.2f} m, {(hk + hle) / h * 100:.0f}% of the pump head. " + ("There are no fittings in the model." if hk + hle == 0 else "Throttling a valve raises ΣK and moves the operating point to a lower flow.")))

    # ---- 12. system head and closure
    h_sys = static + hf + hle + hk
    steps.append(_step(
        "Total system head and check against the pump", r"H_{sys}=H_{static}+h_f+h_K",
        [["H_{sys}", "head the pipeline needs", "m"], ["H_{static}", "static head (height to lift)", "m"], ["h_f", "friction loss", "m"], ["h_K", "fittings loss", "m"]],
        [_calc("H_sys", f"{_g(static)} + {_g(hf)} + {_g(hle + hk)}", f"H_sys = {h_sys:.3f} m"),
         _calc("Check against the pump head", f"{_g(h)} − {_g(h_sys)}", f"difference = {h - h_sys:.4f} m  (it must be zero at the operating point)")],
        f"The pipeline needs {h_sys:.2f} m: {static / h_sys * 100:.0f}% static lift and {(hf + hle + hk) / h_sys * 100:.0f}% friction and fittings. The pump supplies the same {h:.2f} m, which confirms the intersection."))

    # ---- 13. hydraulic power
    phyd = op["hyd_w"] / 1000
    steps.append(_step(
        "Hydraulic power", r"P_{hyd}=\rho\,g\,Q\,H",
        [["P_{hyd}", "power delivered to the water", "kW"], [r"\rho", "density", "kg/m³"], ["g", "gravity", "m/s²"], ["Q", "flow", "m³/s"], ["H", "pump head", "m"]],
        [_calc("P_hyd", f"{rho:.2f} × {pp.G} × {_g(q)} × {_g(h)} / 1000", f"P_hyd = {fmt_power(phyd)} kW")],
        f"{fmt_power(phyd)} kW is the useful power the water receives (flow × pressure rise). It is the minimum the pump could ever need."))

    # ---- 14. shaft power
    eta, ps = p["eta"], p["p_shaft_w"] / 1000
    steps.append(_step(
        "Shaft power and pump efficiency", r"P_{shaft}=\dfrac{P_{hyd}}{\eta}",
        [["P_{shaft}", "power at the pump shaft", "kW"], ["P_{hyd}", "hydraulic power", "kW"], [r"\eta", "pump efficiency (fraction)", "-"]],
        [_calc("P_shaft", f"{_g(phyd)} / {eta:.4f}", f"P_shaft = {fmt_power(ps)} kW")],
        f"At {eta * 100:.0f}% efficiency, {fmt_power(ps - phyd)} kW of the shaft power ({(1 - eta) * 100:.0f}%) is lost as heat, leakage and friction inside the pump. "
        "The efficiency is assumed constant, but a real pump's efficiency changes with flow, so it is best near its best efficiency point."))

    # ---- 15. electrical power, energy and cost
    em, hours, tariff = p["eta_motor"], p["hours"], p["tariff"]
    pel = ps / em
    kwh = pel * hours
    steps.append(_step(
        "Electrical power, energy and running cost", r"P_{el}=\dfrac{P_{shaft}}{\eta_{motor}},\qquad E=P_{el}\,t,\qquad \text{Cost}=E\times\text{tariff}",
        [["P_{el}", "electrical power drawn by the motor", "kW"], [r"\eta_{motor}", "motor efficiency (fraction)", "-"], ["t", "running time", "h/day"], ["E", "energy", "kWh/day"], ["tariff", "electricity price", "Rs/kWh"]],
        [_calc("P_el", f"{_g(ps)} / {em:.4f}", f"P_el = {fmt_power(pel)} kW"), _calc("E", f"{_g(pel)} × {_g(hours)}", f"E = {fmt_power(kwh)} kWh/day"),
         _calc("Cost", f"{_g(kwh)} × {_g(tariff)}", f"Cost = Rs {kwh * tariff:,.2f} per day")],
        f"Running {hours:g} h a day for 365 days costs about Rs {kwh * tariff * 365:,.0f} a year. "
        + ("The motor efficiency is 100%, which means motor losses are NOT included: enter your motor's efficiency for a realistic cost." if em >= 0.999 else f"Motor losses of {(pel - ps):.2f} kW are included.")))

    # ---- 16. NPSH (optional)
    n = p.get("npsh")
    if n:
        r = n["result"]
        term = (r["p_abs_kpa"] - n["pv"]) * 1000 / (rho * pp.G)
        verdict = {"ok": "NPSHa is above NPSHr plus the margin: no cavitation risk.",
                   "risk": "NPSHa is above NPSHr but inside the safety margin: Cavitation Risk!",
                   "cavitation": "NPSHa is below NPSHr: the pump will cavitate. Cavitation Risk!"}[r["status"]]
        steps.append(_step(
            "NPSH available and cavitation check", r"NPSH_a=\dfrac{P_{abs}-P_v}{\rho g}+z-h_{f,s}",
            [["NPSH_a", "net positive suction head available", "m"], ["P_{abs}", "absolute pressure on the liquid surface", "kPa"], ["P_v", "vapour pressure at the pumping temperature", "kPa abs"], [r"\rho", "density", "kg/m³"],
             ["z", "liquid level above the pump (negative for a suction lift)", "m"], ["h_{f,s}", "friction loss in the suction line", "m"]],
            [_calc("Pressure term", f"({r['p_abs_kpa']:.3f} − {n['pv']:.3f}) × 1000 / ({rho:.2f} × {pp.G})", f"(P − Pv)/(ρg) = {term:.3f} m"),
             _calc("NPSH_a", f"{term:.4f} + ({_g(n['level'])}) − {_g(n['hfs'])}", f"NPSH_a = {r['npsha']:.3f} m"),
             _calc("Margin", f"{r['npsha']:.4f} − {_g(n['npshr'])}", f"NPSH_a − NPSH_r = {r['npsha'] - n['npshr']:.3f} m  (the margin asked for is {_g(n['margin'])} m)")],
            verdict + " NPSHr rises with flow, so use the NPSHr from the datasheet at the operating flow."))
    return steps
