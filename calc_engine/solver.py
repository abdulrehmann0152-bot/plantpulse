"""Step-by-step heat exchanger problem solver (LMTD method).

Give the four terminal temperatures and any optional data; the solver works out everything that
can be found and records every formula, substitution and assumption so a student can follow it.
Units: deg C, kg/s, kJ/(kg.K), kW, m2, W/(m2.K).
"""
import math

from . import heat_exchanger as hx
from . import hx_explain as ex
from . import pump_pipe as pp
from .heat_exchanger import InputError

ARRANGEMENTS = {"counter": "Counter-flow (1-1)", "parallel": "Parallel flow (1-1)", "shell_1_2": "1 shell pass / 2 tube passes (1-2)",
                "shell_2_4": "2 shell passes / 4 tube passes (2-4)"}
N_SHELLS = {"shell_1_2": 1, "shell_2_4": 2}

ASSUMPTIONS = [
    "Steady state operation.",
    "No heat loss to the surroundings, so the heat given by the hot fluid equals the heat taken by the cold fluid.",
    "Constant specific heats and a constant overall heat transfer coefficient U over the whole exchanger.",
    "No phase change in either stream.",
    "Fluid temperatures are uniform across each cross-section (well mixed).",
]
SHELL_NOTE = ("For shell-and-tube exchangers the LMTD is corrected with the factor F, calculated from R and P with the standard analytical (Bowman/Kern) "
              "equation for 1 shell pass, or by treating 2 shell passes as two identical 1-2 shells in series; equal area is assumed in every pass.")


def _step(title, formula, working):
    """A worked step. 'working' is the one-line summary; hx_explain adds 'variables' and 'calc' (substitution, intermediate, result)."""
    return {"title": title, "formula": formula, "working": working}


def solve_hx(arrangement, th_in, th_out, tc_in, tc_out, m_hot=None, cp_hot=None, m_cold=None, cp_cold=None,
             q_kw=None, area=None, u=None, f_given=None, *, hot_side="shell", mu_bulk=None, mu_wall=None,
             visc_label="the fluid", film_share_pct=100.0, tube_od_mm=None, tube_length_m=None, n_tubes=None, balance_tol_pct=hx.HEAT_BALANCE_TOL_PCT):
    """Return a dict with results, steps, assumptions and warnings. Optional inputs may be None.

    hot_side: 'shell' or 'tube' (which side the hot fluid is on). mu_bulk, mu_wall: viscosities in mPa.s for the
    Sieder-Tate correction of a GIVEN U. tube_od_mm, tube_length_m, n_tubes: tube geometry (outside surface basis).
    """
    if arrangement not in ARRANGEMENTS:
        raise InputError("Unknown flow arrangement.")
    if hot_side not in ("shell", "tube"):
        raise InputError("The hot fluid must be on the shell side or the tube side.")
    for name, v in (("hot flow", m_hot), ("hot Cp", cp_hot), ("cold flow", m_cold), ("cold Cp", cp_cold),
                    ("duty", q_kw), ("area", area), ("U", u), ("F", f_given), ("bulk viscosity", mu_bulk), ("wall viscosity", mu_wall),
                    ("tube outside diameter", tube_od_mm), ("tube length", tube_length_m), ("number of tubes", n_tubes)):
        if v is not None and v <= 0:
            raise InputError(f"The {name} must be a positive number (or left empty).")
    if f_given is not None and f_given > 1:
        raise InputError("A correction factor F cannot be greater than 1.")
    hx._check_temps(th_in, th_out, tc_in, tc_out)
    steps, warnings = [], []
    if (mu_bulk is None) != (mu_wall is None):
        raise InputError("Enter both the bulk and the wall viscosity, or neither.")
    if not 0 < film_share_pct <= 100:
        raise InputError("The film's share of the resistance must be between 0 and 100%.")
    if n_tubes is not None and int(n_tubes) != n_tubes:
        raise InputError("The number of tubes must be a whole number.")
    r = {"arrangement": arrangement, "steps": steps, "warnings": warnings, "assumptions": list(ASSUMPTIONS), "hot_side": hot_side,
         "phi": None, "u_corrected": None, "area_required": None, "n_tubes_exact": None, "n_tubes_needed": None, "tube_length_found": None, "area_from_tubes": None}

    # ---- terminal differences and LMTD
    d1c, d2c = th_in - tc_out, th_out - tc_in
    d1p, d2p = th_in - tc_in, th_out - tc_out
    r["lmtd_counter"] = hx.lmtd(th_in, th_out, tc_in, tc_out, "counter")
    steps.append(_step("Counter-current LMTD", r"\Delta T_1 = T_{h,in}-T_{c,out},\quad \Delta T_2 = T_{h,out}-T_{c,in},\quad LMTD=\dfrac{\Delta T_1-\Delta T_2}{\ln(\Delta T_1/\Delta T_2)}",
                       f"ΔT₁ = {th_in:g} − {tc_out:g} = {d1c:g} K;  ΔT₂ = {th_out:g} − {tc_in:g} = {d2c:g} K;  "
                       f"LMTD = ({d1c:g} − {d2c:g}) / ln({d1c:g}/{d2c:g}) = {r['lmtd_counter']:.3f} K"
                       if not math.isclose(d1c, d2c) else f"ΔT₁ = ΔT₂ = {d1c:g} K, so LMTD = {d1c:g} K"))
    steps[-1].update(ex.lmtd_parts("counter", th_in, th_out, tc_in, tc_out, r["lmtd_counter"]))
    warnings.extend(hx.approach_warnings(d1c, d2c))
    try:
        r["lmtd_parallel"] = hx.lmtd(th_in, th_out, tc_in, tc_out, "parallel")
        steps.append(_step("Parallel-flow LMTD (for comparison)", r"\Delta T_1 = T_{h,in}-T_{c,in},\quad \Delta T_2 = T_{h,out}-T_{c,out}",
                           f"ΔT₁ = {th_in:g} − {tc_in:g} = {d1p:g} K;  ΔT₂ = {th_out:g} − {tc_out:g} = {d2p:g} K;  LMTD = {r['lmtd_parallel']:.3f} K"
                           if not math.isclose(d1p, d2p) else f"ΔT₁ = ΔT₂ = {d1p:g} K, so LMTD = {d1p:g} K"))
        steps[-1].update(ex.lmtd_parts("parallel", th_in, th_out, tc_in, tc_out, r["lmtd_parallel"]))
    except InputError:
        r["lmtd_parallel"] = None
        warnings.append("These temperatures are impossible in parallel flow (the cold outlet would be hotter than the hot outlet).")
        if arrangement == "parallel":
            raise InputError("These temperatures cannot occur in parallel flow: the cold outlet is hotter than the hot outlet. Use counter-flow or a multi-pass exchanger.")

    # ---- R, P, F
    r["R"] = r["P"] = r["f_computed"] = None
    n_sh = N_SHELLS.get(arrangement)
    if n_sh:
        r["R"], r["P"] = (th_in - th_out) / (tc_out - tc_in), (tc_out - tc_in) / (th_in - tc_in)
        r["f_computed"] = hx.correction_factor_n_shells(th_in, th_out, tc_in, tc_out, n_sh)
        steps.append(_step("R, P and the correction factor F", r"R=\dfrac{T_{h,in}-T_{h,out}}{T_{c,out}-T_{c,in}},\quad P=\dfrac{T_{c,out}-T_{c,in}}{T_{h,in}-T_{c,in}}",
                           f"R = ({th_in:g} − {th_out:g}) / ({tc_out:g} − {tc_in:g}) = {r['R']:.4f};  P = ({tc_out:g} − {tc_in:g}) / ({th_in:g} − {tc_in:g}) = {r['P']:.4f}"))
        steps[-1].update(ex.rp_parts(th_in, th_out, tc_in, tc_out))
        if n_sh == 1:
            steps.append(_step("Correction factor F (1 shell pass, 2 tube passes)",
                               r"F=\dfrac{\sqrt{R^2+1}}{R-1}\,\dfrac{\ln\left[\frac{1-P}{1-PR}\right]}{\ln\left[\frac{2-P(R+1-\sqrt{R^2+1})}{2-P(R+1+\sqrt{R^2+1})}\right]}",
                               f"F (from the equation) = {r['f_computed']:.4f}"))
            steps[-1].update(ex.f_parts_1_2(r["R"], r["P"]))
        else:
            p1 = hx.shell_effectiveness(r["R"], r["P"], n_sh)
            r["p_per_shell"] = p1
            steps.append(_step(f"Effectiveness of each shell ({n_sh} shells in series)", r"x=\left(\dfrac{1-PR}{1-P}\right)^{1/N},\qquad P_1=\dfrac{x-1}{x-R}",
                               f"N = {n_sh};  x = (({1 - r['P'] * r['R']:.4f})/({1 - r['P']:.4f}))^(1/{n_sh});  P₁ = {p1:.4f} for each shell"))
            steps[-1].update(ex.p1_parts(r["R"], r["P"], n_sh))
            steps.append(_step("Correction factor F (2 shell passes, 4 tube passes)",
                               r"F=\dfrac{\frac{1}{R-1}\ln\frac{1-P}{1-PR}}{N\cdot\frac{1}{\sqrt{R^2+1}}\ln\frac{2-P_1(R+1-\sqrt{R^2+1})}{2-P_1(R+1+\sqrt{R^2+1})}}",
                               f"F (from the equation) = {r['f_computed']:.4f}"))
            steps[-1].update(ex.f_parts_n(r["R"], r["P"], n_sh, include_p1=False))
    r["f_used"] = f_given if f_given is not None else (r["f_computed"] if r["f_computed"] is not None else 1.0)
    if f_given is not None and r["f_computed"] is not None and abs(f_given - r["f_computed"]) > 0.005:
        warnings.append(f"The F you entered ({f_given:g}) differs from the value calculated from R and P ({r['f_computed']:.4f}). The entered value is used, as in a textbook problem that reads F from a chart.")
    f_warning = hx.f_assessment(r["f_used"])
    if f_warning:
        warnings.append(f_warning)
    base = r["lmtd_parallel"] if arrangement == "parallel" else r["lmtd_counter"]
    r["lmtd_eff"] = r["f_used"] * base
    if n_sh or f_given is not None:
        src = "given in the problem" if f_given is not None else "calculated"
        steps.append(_step("Corrected mean temperature difference", r"\Delta T_{lm,corr} = F\cdot LMTD_{counter}",
                           f"ΔT_lm,corr = {r['f_used']:.4f} ({src}) × {base:.3f} = {r['lmtd_eff']:.3f} K"))
        steps[-1].update(ex.corrected_parts(r["f_used"], base, r["lmtd_eff"]))

    # ---- duty and unknown flows
    q_hot = q_cold = None
    if m_hot and cp_hot:
        q_hot = m_hot * cp_hot * (th_in - th_out)
        steps.append(_step("Heat given by the hot fluid", r"Q_h=\dot m_h\,C_{p,h}\,(T_{h,in}-T_{h,out})", f"Q_h = {m_hot:g} × {cp_hot:g} × ({th_in:g} − {th_out:g}) = {q_hot:,.2f} kW"))
        steps[-1].update(ex.duty_parts("hot", m_hot, cp_hot, th_in, th_out, q_hot))
    if m_cold and cp_cold:
        q_cold = m_cold * cp_cold * (tc_out - tc_in)
        steps.append(_step("Heat taken by the cold fluid", r"Q_c=\dot m_c\,C_{p,c}\,(T_{c,out}-T_{c,in})", f"Q_c = {m_cold:g} × {cp_cold:g} × ({tc_out:g} − {tc_in:g}) = {q_cold:,.2f} kW"))
        steps[-1].update(ex.duty_parts("cold", m_cold, cp_cold, tc_in, tc_out, q_cold))
    if q_kw is not None:
        q = q_kw
        steps.append(_step("Duty given in the problem", r"Q", f"Q = {q:,.2f} kW"))
        steps[-1].update(ex.given_duty_parts(q))
    elif q_hot is not None:
        q = q_hot
    elif q_cold is not None:
        q = q_cold
    else:
        q = None
    if q_hot is not None and q_cold is not None:
        r["mismatch_pct"] = hx.heat_balance_mismatch_pct(q_hot, q_cold)
        r["balance"] = hx.heat_balance_status(q_hot * 1000, q_cold * 1000, balance_tol_pct)
        if not r["balance"]["ok"]:
            warnings.append(r["balance"]["message"] + " The hot-side duty is used for the calculation.")
    else:
        r["mismatch_pct"] = None
        r["balance"] = None
    r["m_hot"], r["m_cold"] = m_hot, m_cold
    if q is not None:
        if not m_cold and cp_cold:
            r["m_cold"] = q / (cp_cold * (tc_out - tc_in))
            steps.append(_step("Cold-side flow from the heat balance", r"\dot m_c=\dfrac{Q}{C_{p,c}\,(T_{c,out}-T_{c,in})}",
                               f"ṁ_c = {q:,.2f} / ({cp_cold:g} × ({tc_out:g} − {tc_in:g})) = {r['m_cold']:.3f} kg/s"))
            steps[-1].update(ex.flow_parts("cold", q, cp_cold, tc_out, tc_in, r["m_cold"]))
        if not m_hot and cp_hot:
            r["m_hot"] = q / (cp_hot * (th_in - th_out))
            steps.append(_step("Hot-side flow from the heat balance", r"\dot m_h=\dfrac{Q}{C_{p,h}\,(T_{h,in}-T_{h,out})}",
                               f"ṁ_h = {q:,.2f} / ({cp_hot:g} × ({th_in:g} − {th_out:g})) = {r['m_hot']:.3f} kg/s"))
            steps[-1].update(ex.flow_parts("hot", q, cp_hot, th_in, th_out, r["m_hot"]))
    r["q_kw"], r["q_hot_kw"], r["q_cold_kw"] = q, q_hot, q_cold

    # ---- Sieder-Tate wall-viscosity correction (applies to a GIVEN U)
    u_eff = u
    if mu_bulk and mu_wall:
        phi = (mu_bulk / mu_wall) ** 0.14
        share = film_share_pct / 100.0
        r["phi"] = phi
        steps.append(_step("Wall-viscosity correction factor (Sieder-Tate)", r"\phi=\left(\dfrac{\mu_{bulk}}{\mu_{wall}}\right)^{0.14}",
                           f"φ = ({mu_bulk:g} / {mu_wall:g})^0.14 = {phi:.4f}   (viscosities of {visc_label})"))
        if not 0.1 <= mu_bulk / mu_wall <= 10:
            warnings.append("The bulk-to-wall viscosity ratio is outside 0.1 to 10, which is beyond where the Sieder-Tate correction is normally applied. Check your data and your textbook's validity range.")
        if u:
            factor = 1.0 / (share / phi + (1.0 - share))
            u_eff = u * factor
            r["u_corrected"] = u_eff
            if share == 1.0:
                steps.append(_step("Corrected overall U", r"U_{corr}=\phi\,U", f"U_corr = {phi:.4f} × {u:g} = {u_eff:,.1f} W/m²K"))
            else:
                steps.append(_step("Corrected overall U (the film is only part of the resistance)", r"U_{corr}=\dfrac{U}{x/\phi+(1-x)}",
                                   f"x = {share:.2f};  U_corr = {u:g} / ({share:.2f}/{phi:.4f} + {1 - share:.2f}) = {u_eff:,.1f} W/m²K"))
            if share == 1.0:
                warnings.append("φ strictly corrects the film coefficient of one fluid. Applying it to the whole U is exact only if that film controls the overall resistance; "
                                "enter the film's share of the resistance to be more accurate.")
        else:
            warnings.append("The viscosity correction is applied to a given U. Here U is calculated from the data, so it already contains the wall-viscosity effect and the correction was not applied.")

    # ---- tube geometry (outside surface basis)
    od = tube_od_mm / 1000.0 if tube_od_mm else None
    installed = None
    if od and tube_length_m and n_tubes:
        installed = n_tubes * math.pi * od * tube_length_m
        r["area_from_tubes"] = installed
        steps.append(_step("Heat transfer area from the tube geometry", r"A=N\,\pi\,D_o\,L",
                           f"A = {n_tubes:g} × π × {od:.4f} × {tube_length_m:g} = {installed:.3f} m²  (outside surface of the tubes)"))
        steps[-1].update(ex.tube_area_parts(n_tubes, od, tube_length_m, installed))
        if area and abs(area - installed) / installed > 0.02:
            warnings.append(f"The area you entered ({area:g} m²) differs by more than 2% from the area of the tubes ({installed:.2f} m²). The entered area is used.")
        if not area and not u_eff:
            area = installed
    if od or installed:
        r["assumptions"].append("The heat transfer area and U refer to the outside surface of the tubes. Which fluid is on the shell side or the tube side does not change the LMTD, F or the duty.")

    # ---- area / U
    r["area"], r["u"] = area, u
    required = False
    if q is not None and area and not u:
        r["u"] = q * 1000 / (area * r["lmtd_eff"])
        steps.append(_step("Overall heat transfer coefficient", r"U=\dfrac{Q}{A\,\Delta T_{lm,corr}}",
                           f"U = {q * 1000:,.0f} W / ({area:g} m² × {r['lmtd_eff']:.3f} K) = {r['u']:,.1f} W/m²K"))
        steps[-1].update(ex.u_parts(q, area, r["lmtd_eff"], r["u"]))
    elif q is not None and u and not area:
        r["area"] = q * 1000 / (u_eff * r["lmtd_eff"])
        r["area_required"] = r["area"]
        required = True
        steps.append(_step("Required heat transfer area", r"A=\dfrac{Q}{U\,\Delta T_{lm,corr}}",
                           f"A = {q * 1000:,.0f} W / ({u_eff:g} W/m²K × {r['lmtd_eff']:.3f} K) = {r['area']:,.2f} m²"
                           + ("  (using the corrected U)" if r["u_corrected"] else "")))
        steps[-1].update(ex.area_parts(q, u_eff, r["lmtd_eff"], r["area"]))
        if installed:
            over = (installed / r["area"] - 1) * 100
            r["over_surface_pct"] = over
            steps.append(_step("Installed area compared with the required area", r"\text{over-surface}=\left(\dfrac{A_{installed}}{A_{required}}-1\right)\times 100",
                               f"({installed:.2f} / {r['area']:.2f} − 1) × 100 = {over:+.1f} %"))
            steps[-1].update(ex.over_surface_parts(installed, r["area"], over))
            if over < 0:
                warnings.append(f"The tubes give {installed:.2f} m² but {r['area']:.2f} m² are required: the exchanger is too small by {-over:.1f}%.")
    elif q is not None and u and area:
        warnings.append("Both area and U were entered, so neither was calculated. Leave one empty to solve for it.")
    if q is None and (area or u):
        warnings.append("Add flow and Cp data (or the duty) to calculate area or U.")
    if required and od and not installed:
        if tube_length_m:
            n_exact = r["area"] / (math.pi * od * tube_length_m)
            r["n_tubes_exact"], r["n_tubes_needed"] = n_exact, math.ceil(n_exact - 1e-9)
            steps.append(_step("Number of tubes needed", r"N=\dfrac{A}{\pi\,D_o\,L}",
                               f"N = {r['area']:.3f} / (π × {od:.4f} × {tube_length_m:g}) = {n_exact:.2f}, so {r['n_tubes_needed']} tubes"))
            steps[-1].update(ex.tubes_needed_parts(r["area"], od, tube_length_m, n_exact, r["n_tubes_needed"]))
        elif n_tubes:
            r["tube_length_found"] = r["area"] / (n_tubes * math.pi * od)
            steps.append(_step("Tube length needed", r"L=\dfrac{A}{N\,\pi\,D_o}",
                               f"L = {r['area']:.3f} / ({n_tubes:g} × π × {od:.4f}) = {r['tube_length_found']:.3f} m"))
            steps[-1].update(ex.tube_length_parts(r["area"], n_tubes, od, r["tube_length_found"]))
        else:
            warnings.append("Enter the tube length or the number of tubes to turn the required area into a tube count or a tube length.")
    elif (tube_length_m or n_tubes) and not od:
        warnings.append("Enter the tube outside diameter to use the tube length or the number of tubes.")
    if n_sh:
        r["assumptions"].append(SHELL_NOTE)
    return r


# ============================================================================ pipe and pump (fluid flow)
G_TEXT = 9.81   # textbook value, so hand calculations match


def _pipe_checks(d_mm, length_m, rho, mu_pas, rough_mm, sum_k, equiv_len_d=0.0):
    if min(d_mm, length_m, rho, mu_pas) <= 0:
        raise InputError("Diameter, length, density and viscosity must be positive.")
    if rough_mm < 0 or sum_k < 0 or equiv_len_d < 0:
        raise InputError("Roughness, ΣK and Le/D cannot be negative.")


def _pipe_state(v, d, length, rho, mu, rough, sum_k, led=0.0):
    """Friction (hf), fittings by K (hk) and fittings by equivalent length Le/D (hle), all as head in m."""
    re = rho * v * d / mu
    f = pp.friction_factor(re, d, rough, method="swamee_jain")      # the Problem Solver shows the explicit formula so that it can be repeated by hand
    hv = v * v / (2 * G_TEXT)
    return {"re": re, "f": f, "hf": f * length / d * hv, "hk": sum_k * hv, "hle": f * led * hv}


PIPE_ASSUMPTIONS = [
    "Steady, incompressible flow of a single liquid with constant density and viscosity.",
    "Fully developed flow in a full, circular pipe of constant diameter.",
    "Both ends are large tanks or vessels, so the velocity at the two ends is negligible.",
    "Friction loss from the Darcy-Weisbach equation with the Swamee-Jain friction factor (within about 1-3% of the Colebrook equation); laminar flow uses f = 64/Re.",
    "Fittings and valves are included through the loss coefficient ΣK and/or their equivalent length Le/D.",
    "g = 9.81 m/s².",
]


def _regime_warnings(re, v, warnings):
    if 2300 <= re < 4000:
        warnings.append("The flow is in the transition zone (Re between 2,300 and 4,000), so the friction factor is uncertain.")
    if v > 3:
        warnings.append("The velocity is above 3 m/s, which is high for most liquid lines. Check the diameter or flow.")


def solve_pipe(q_m3h, d_mm, length_m, rho, mu_pas, rough_mm, sum_k=0.0, static_head_m=0.0, delta_p_kpa=0.0, eta_pct=None, equiv_len_d=0.0):
    """Head, pressure drop and pump power for a given flow. Fittings: ΣK and/or equivalent length Le/D."""
    _pipe_checks(d_mm, length_m, rho, mu_pas, rough_mm, sum_k, equiv_len_d)
    if q_m3h <= 0:
        raise InputError("The flow must be positive.")
    if eta_pct is not None and not 0 < eta_pct <= 100:
        raise InputError("Efficiency must be between 0 and 100%.")
    d, q = d_mm / 1000.0, q_m3h / 3600.0
    area = math.pi * d * d / 4
    v = q / area
    st = _pipe_state(v, d, length_m, rho, mu_pas, rough_mm / 1000.0, sum_k, equiv_len_d)
    dp_fric, dp_all = rho * G_TEXT * st["hf"], rho * G_TEXT * (st["hf"] + st["hk"] + st["hle"])
    head_dp = delta_p_kpa * 1000 / (rho * G_TEXT)
    head = static_head_m + head_dp + st["hf"] + st["hk"] + st["hle"]
    r = {"q_m3h": q_m3h, "v": v, "re": st["re"], "f": st["f"], "hf": st["hf"], "hk": st["hk"], "hle": st["hle"], "dp_friction_kpa": dp_fric / 1000,
         "dp_losses_kpa": dp_all / 1000, "head_m": head, "hyd_kw": None, "shaft_kw": None, "warnings": [], "assumptions": list(PIPE_ASSUMPTIONS)}
    regime = "laminar" if st["re"] < 2300 else ("transition" if st["re"] < 4000 else "turbulent")
    steps = [
        _step("Velocity in the pipe", r"v=\dfrac{Q}{A}=\dfrac{Q}{\pi D^2/4}", f"Q = {q_m3h:g}/3600 = {q:.5f} m³/s;  A = π × {d:.4f}² / 4 = {area:.5f} m²;  v = {v:.3f} m/s"),
        _step("Reynolds number", r"Re=\dfrac{\rho\, v\, D}{\mu}", f"Re = {rho:g} × {v:.3f} × {d:.4f} / {mu_pas:g} = {st['re']:,.0f}  ({regime})"),
        _step("Friction factor", r"f=\dfrac{64}{Re}\ \text{(laminar)}\qquad f=\dfrac{0.25}{\left[\log_{10}\left(\frac{\varepsilon}{3.7D}+\frac{5.74}{Re^{0.9}}\right)\right]^2}\ \text{(turbulent)}",
              f"ε/D = {rough_mm / 1000.0 / d:.6f};  f = {st['f']:.5f}"),
        _step("Friction head loss in the pipe", r"h_f=f\,\dfrac{L}{D}\,\dfrac{v^2}{2g}", f"h_f = {st['f']:.5f} × ({length_m:g}/{d:.4f}) × {v:.3f}² / (2 × 9.81) = {st['hf']:.3f} m"),
        _step("Friction pressure drop", r"\Delta P_f=\rho\, g\, h_f=f\,\dfrac{L}{D}\,\dfrac{\rho v^2}{2}", f"ΔP_f = {rho:g} × 9.81 × {st['hf']:.3f} = {dp_fric:,.0f} Pa = {dp_fric / 1000:.2f} kPa"),
    ]
    if sum_k:
        steps.append(_step("Head loss in fittings and valves", r"h_K=\Sigma K\,\dfrac{v^2}{2g}", f"h_K = {sum_k:g} × {v:.3f}² / (2 × 9.81) = {st['hk']:.3f} m"))
    if equiv_len_d:
        steps.append(_step("Head loss in fittings given as equivalent length", r"h_{Le}=f\,\dfrac{L_e}{D}\,\dfrac{v^2}{2g}",
                           f"h_Le = {st['f']:.5f} × {equiv_len_d:g} × {v:.3f}² / (2 × 9.81) = {st['hle']:.3f} m"))
    steps.append(_step("Total head the pump must supply", r"H=\Delta z+\dfrac{\Delta P}{\rho g}+h_f+h_K" + (r"+h_{Le}" if equiv_len_d else ""),
                       f"H = {static_head_m:g} + {head_dp:.3f} + {st['hf']:.3f} + {st['hk']:.3f}" + (f" + {st['hle']:.3f}" if equiv_len_d else "") + f" = {head:.3f} m"))
    if head > 0:
        r["hyd_kw"] = rho * G_TEXT * q * head / 1000
        steps.append(_step("Hydraulic power", r"P_{hyd}=\rho\, g\, Q\, H", f"P_hyd = {rho:g} × 9.81 × {q:.5f} × {head:.3f} = {r['hyd_kw'] * 1000:,.0f} W = {r['hyd_kw']:.3f} kW"))
        if eta_pct:
            r["shaft_kw"] = r["hyd_kw"] / (eta_pct / 100)
            steps.append(_step("Shaft power", r"P_{shaft}=\dfrac{P_{hyd}}{\eta}", f"P_shaft = {r['hyd_kw']:.3f} / {eta_pct / 100:.2f} = {r['shaft_kw']:.3f} kW"))
    else:
        r["warnings"].append("The required head is zero or negative: the liquid would flow by gravity at this rate and no pump head is needed.")
    _regime_warnings(st["re"], v, r["warnings"])
    r["steps"] = steps
    return r


def flow_from_head(head_m, d_mm, length_m, rho, mu_pas, rough_mm, sum_k=0.0, equiv_len_d=0.0):
    """Flow that a given head can drive through the pipe (head = friction + fittings loss)."""
    _pipe_checks(d_mm, length_m, rho, mu_pas, rough_mm, sum_k, equiv_len_d)
    if head_m <= 0:
        raise InputError("The available head must be positive.")
    d, rough = d_mm / 1000.0, rough_mm / 1000.0
    area = math.pi * d * d / 4

    def gap(v):
        s = _pipe_state(v, d, length_m, rho, mu_pas, rough, sum_k, equiv_len_d)
        return s["hf"] + s["hk"] + s["hle"] - head_m
    lo, hi = 1e-8, 200.0
    if gap(hi) < 0:
        raise InputError("This head would need an unrealistic velocity. Check the data.")
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if gap(mid) > 0:
            hi = mid
        else:
            lo = mid
    v = math.sqrt(lo * hi)
    st = _pipe_state(v, d, length_m, rho, mu_pas, rough, sum_k, equiv_len_d)
    q = v * area
    regime = "laminar" if st["re"] < 2300 else ("transition" if st["re"] < 4000 else "turbulent")
    r = {"q_m3h": q * 3600, "v": v, "re": st["re"], "f": st["f"], "hf": st["hf"], "hk": st["hk"], "hle": st["hle"], "head_m": head_m, "warnings": [], "assumptions": list(PIPE_ASSUMPTIONS)}
    r["steps"] = [
        _step("Energy balance", r"h_{available}=h_f+h_K" + (r"+h_{Le}" if equiv_len_d else "") + r"=\left(f\dfrac{L}{D}+\Sigma K" + (r"+f\dfrac{L_e}{D}" if equiv_len_d else "") + r"\right)\dfrac{v^2}{2g}",
              f"{head_m:g} m = ({st['f']:.5f} × {length_m:g}/{d:.4f} + {sum_k:g}" + (f" + {st['f']:.5f} × {equiv_len_d:g}" if equiv_len_d else "") + ") × v² / (2 × 9.81)"),
        _step("Solve for the velocity (f depends on v, so the equation is solved by iteration)", r"v=\sqrt{\dfrac{2g\,h}{f\,L/D+\Sigma K}}", f"v = {v:.4f} m/s"),
        _step("Check the Reynolds number and friction factor", r"Re=\dfrac{\rho v D}{\mu}", f"Re = {rho:g} × {v:.4f} × {d:.4f} / {mu_pas:g} = {st['re']:,.0f} ({regime});  f = {st['f']:.5f}"),
        _step("Check that the losses equal the available head", r"h_f+h_K=h_{available}", f"h_f = {st['hf']:.3f} m, h_K = {st['hk']:.3f} m" + (f", h_Le = {st['hle']:.3f} m" if equiv_len_d else "") + f", sum = {st['hf'] + st['hk'] + st['hle']:.3f} m"),
        _step("Flow rate", r"Q=v\,A", f"Q = {v:.4f} × {area:.5f} = {q:.6f} m³/s = {q * 3600:.2f} m³/h"),
    ]
    _regime_warnings(st["re"], v, r["warnings"])
    return r


# ============================================================================ NPSH
def npsh_check(p_vessel_kpa, basis, p_atm_kpa, level_m, hf_suction_m, p_vapor_kpa, rho, npshr_m, margin_m=0.5, g=G_TEXT):
    """NPSH available at the pump suction, compared with NPSH required plus a safety margin.

    basis: 'absolute' or 'gauge' (the vessel pressure). level_m: liquid level above the pump centreline (negative for a suction lift).
    """
    if basis not in ("absolute", "gauge"):
        raise InputError("The suction pressure must be absolute or gauge.")
    if rho <= 0:
        raise InputError("The density must be positive.")
    if p_vapor_kpa < 0 or npshr_m < 0 or margin_m < 0 or hf_suction_m < 0:
        raise InputError("Vapour pressure, NPSH required, the safety margin and the suction friction loss cannot be negative.")
    if p_atm_kpa <= 0:
        raise InputError("The atmospheric pressure must be positive.")
    p_abs = p_vessel_kpa + (p_atm_kpa if basis == "gauge" else 0.0)
    if p_abs <= 0:
        raise InputError("The absolute suction pressure must be above zero. If the vessel pressure is a gauge reading, select 'gauge'.")
    head_p = (p_abs - p_vapor_kpa) * 1000 / (rho * g)
    npsha = head_p + level_m - hf_suction_m
    needed = npshr_m + margin_m
    status = "ok" if npsha >= needed else ("cavitation" if npsha < npshr_m else "risk")
    steps = []
    if basis == "gauge":
        steps.append(_step("Absolute pressure at the suction vessel", r"P_{abs}=P_{gauge}+P_{atm}", f"P_abs = {p_vessel_kpa:g} + {p_atm_kpa:g} = {p_abs:.3f} kPa"))
    steps.append(_step("NPSH available", r"NPSH_a=\dfrac{P_{abs}-P_v}{\rho g}+z-h_{f,s}",
                       f"NPSH_a = ({p_abs:.3f} − {p_vapor_kpa:.3f}) × 1000 / ({rho:g} × {g:g}) + {level_m:g} − {hf_suction_m:g} = {head_p:.3f} + {level_m:g} − {hf_suction_m:g} = {npsha:.3f} m"))
    steps.append(_step("Compare with the NPSH required plus the safety margin", r"NPSH_a \ge NPSH_r + \text{margin}",
                       f"NPSH_a = {npsha:.3f} m  versus  NPSH_r + margin = {npshr_m:g} + {margin_m:g} = {needed:g} m  →  margin of safety = {npsha - npshr_m:+.3f} m over NPSH_r"))
    warnings = []
    if npsha <= 0:
        warnings.append("NPSH available is zero or negative: the liquid would boil at the pump suction.")
    return {"npsha": npsha, "npshr": npshr_m, "margin_m": margin_m, "needed": needed, "p_abs_kpa": p_abs, "excess": npsha - npshr_m,
            "status": status, "steps": steps, "warnings": warnings}


# ============================================================================ viscosity correction of a pump curve (ANSI/HI 9.6.7)
HI_NOTE = ("ANSI/HI 9.6.7 method (parameter B). Valid for Newtonian liquids, radial centrifugal pumps (Ns up to 3000 US units), "
           "1 to 4000 cSt, and B below 40. Head is taken per stage. Pump makers' own viscous curves are better when available.")


def hi_parameter_b(nu_cst, h_bep_stage_m, q_bep_m3h, n_rpm):
    """B = 16.5 nu^0.5 H^0.0625 / (Q^0.375 N^0.25): nu in cSt, H in m (per stage, water BEP), Q in m3/h (water BEP), N in rpm."""
    if min(nu_cst, h_bep_stage_m, q_bep_m3h, n_rpm) <= 0:
        raise InputError("Viscosity, BEP head, BEP flow and speed must be positive.")
    return 16.5 * nu_cst ** 0.5 * h_bep_stage_m ** 0.0625 / (q_bep_m3h ** 0.375 * n_rpm ** 0.25)


def hi_factors(b, q_ratio=1.0):
    """Correction factors for flow, head (at Q/Q_BEP = q_ratio) and efficiency. No correction when B <= 1."""
    if b <= 1.0:
        return {"cq": 1.0, "ch": 1.0, "ceta": 1.0, "applies": False}
    if b >= 40.0:
        raise InputError(f"The viscosity parameter B is {b:.1f}. The Hydraulic Institute method is only defined for B below 40: a detailed loss analysis or the pump maker's data is needed.")
    cq = 2.71 ** (-0.165 * math.log10(b) ** 3.15)
    return {"cq": cq, "ch": 1.0 - (1.0 - cq) * q_ratio ** 0.75, "ceta": b ** (-0.0547 * b ** 0.69), "applies": True}


def system_head_curve(q_m3h, d_mm, length_m, rho, mu_pas, rough_mm, sum_k=0.0, static_head_m=0.0, delta_p_kpa=0.0, equiv_len_d=0.0):
    """Head the pipeline needs at a given flow [m]."""
    base = static_head_m + delta_p_kpa * 1000 / (rho * G_TEXT)
    if q_m3h <= 0:
        return base
    d = d_mm / 1000.0
    v = q_m3h / 3600.0 / (math.pi * d * d / 4)
    st = _pipe_state(v, d, length_m, rho, mu_pas, rough_mm / 1000.0, sum_k, equiv_len_d)
    return base + st["hf"] + st["hk"] + st["hle"]


def _interp(xs, ys, x):
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            return ys[i] + (ys[i + 1] - ys[i]) * (x - xs[i]) / (xs[i + 1] - xs[i])
    return None


def _crossing(f, lo, hi, n=400):
    """First sign change of f(x) from positive to non-positive on [lo, hi] (bisection). None if there is none."""
    prev_x, prev_f = lo, f(lo)
    if prev_f is None or prev_f <= 0:
        return None
    for i in range(1, n + 1):
        x = lo + (hi - lo) * i / n
        fx = f(x)
        if fx is None:
            return None
        if fx <= 0:
            a, b = prev_x, x
            for _ in range(80):
                m = (a + b) / 2
                (a, b) = (m, b) if f(m) > 0 else (a, m)
            return (a + b) / 2
        prev_x, prev_f = x, fx
    return None


def pump_viscosity(curve_pts, q_bep_m3h, eta_bep_pct, n_rpm, stages, nu_cst, rho, system_fn=None):
    """Correct a water pump curve for a viscous liquid (HI 9.6.7). curve_pts: three (Q m3/h, total head m) water points.

    system_fn(Q m3/h) -> head m, built with the viscous liquid's properties, gives the operating points.
    """
    if not 0 < eta_bep_pct <= 100:
        raise InputError("The BEP efficiency must be between 0 and 100%.")
    if stages < 1 or int(stages) != stages:
        raise InputError("The number of stages must be a whole number of at least 1.")
    if nu_cst > 4000:
        raise InputError("The viscosity is above 4000 cSt, which is outside the Hydraulic Institute method.")
    a, b, c = pp.fit_pump_curve(list(curve_pts))
    hw = lambda q: a + b * q + c * q * q
    h_bep_total = hw(q_bep_m3h)
    if h_bep_total <= 0:
        raise InputError("The water curve gives no head at the BEP flow. Check the BEP flow and the curve points.")
    h_stage = h_bep_total / stages
    big_b = hi_parameter_b(nu_cst, h_stage, q_bep_m3h, n_rpm)
    f_bep = hi_factors(big_b, 1.0)
    warnings = []
    ns = n_rpm * math.sqrt(q_bep_m3h * 4.40287) / (h_stage * 3.28084) ** 0.75
    if ns > 3000:
        warnings.append(f"The specific speed is {ns:,.0f} (US units), above 3000. The method is meant for radial pumps; treat the result as indicative.")
    if nu_cst < 1:
        warnings.append("The viscosity is below 1 cSt, so no correction is applied.")
    steps = [_step("Viscosity parameter B", r"B=\dfrac{16.5\,\nu^{0.5}\,H_{BEP}^{0.0625}}{Q_{BEP}^{0.375}\,N^{0.25}}",
                   f"H_BEP (water, per stage) = {h_stage:.2f} m;  B = 16.5 × {nu_cst:.2f}^0.5 × {h_stage:.2f}^0.0625 / ({q_bep_m3h:g}^0.375 × {n_rpm:g}^0.25) = {big_b:.3f}")]
    if f_bep["applies"]:
        steps += [_step("Flow and efficiency correction factors", r"C_Q=2.71^{-0.165(\log_{10}B)^{3.15}}\qquad C_\eta=B^{-0.0547\,B^{0.69}}",
                        f"C_Q = {f_bep['cq']:.4f};  C_η = {f_bep['ceta']:.4f}"),
                  _step("Head correction factor", r"C_H=1-(1-C_Q)\left(\dfrac{Q}{Q_{BEP}}\right)^{0.75}",
                        f"At the BEP C_H = C_Q = {f_bep['cq']:.4f};  at zero flow C_H = 1 (shut-off head is not affected)")]
    else:
        steps.append(_step("No correction needed", r"B \le 1\ \Rightarrow\ C_Q=C_H=C_\eta=1", f"B = {big_b:.3f} is not above 1, so the water curve applies."))
    q_v, h_v, eta_v = f_bep["cq"] * q_bep_m3h, f_bep["cq"] * h_bep_total, f_bep["ceta"] * eta_bep_pct / 100.0
    p_v = rho * G_TEXT * (q_v / 3600.0) * h_v / eta_v / 1000.0
    steps.append(_step("Viscous performance at the best efficiency point", r"Q_{vis}=C_QQ,\quad H_{vis}=C_HH,\quad \eta_{vis}=C_\eta\eta,\quad P=\dfrac{\rho g Q H}{\eta}",
                       f"Q = {f_bep['cq']:.4f} × {q_bep_m3h:g} = {q_v:.1f} m³/h;  H = {f_bep['cq']:.4f} × {h_bep_total:.2f} = {h_v:.2f} m;  η = {f_bep['ceta']:.4f} × {eta_bep_pct:g}% = {eta_v * 100:.1f}%;  P = {p_v:.2f} kW"))
    ratios = [i * 0.05 for i in range(0, 25)]                      # 0 to 1.2 x Q_BEP, the range the method covers
    water_q = [r * q_bep_m3h for r in ratios]
    water_h = [hw(q) for q in water_q]
    visc_q = [f_bep["cq"] * q for q in water_q]
    visc_h = [hi_factors(big_b, r)["ch"] * h for r, h in zip(ratios, water_h)]
    table = []
    for r in (0.6, 0.8, 1.0, 1.2):
        fr = hi_factors(big_b, r)
        table.append({"ratio": r, "q_water": r * q_bep_m3h, "h_water": hw(r * q_bep_m3h), "ch": fr["ch"], "q_visc": fr["cq"] * r * q_bep_m3h, "h_visc": fr["ch"] * hw(r * q_bep_m3h)})
    out = {"b": big_b, "cq": f_bep["cq"], "ch_bep": f_bep["cq"], "ceta": f_bep["ceta"], "applies": f_bep["applies"], "ns": ns, "h_bep_total": h_bep_total,
           "q_bep_visc": q_v, "h_bep_visc": h_v, "eta_bep_visc_pct": eta_v * 100, "p_bep_visc_kw": p_v, "table": table, "water_curve": (water_q, water_h),
           "visc_curve": (visc_q, visc_h), "water_op": None, "visc_op": None, "steps": steps, "warnings": warnings, "note": HI_NOTE}
    if system_fn is not None:
        q_top = max(max(q for q, _ in curve_pts), q_bep_m3h * 1.2)
        qw = _crossing(lambda q: hw(q) - system_fn(q), 0.0, q_top)
        if qw is not None:
            out["water_op"] = {"q": qw, "h": hw(qw)}
        qv = _crossing(lambda q: (None if q > visc_q[-1] else _interp(visc_q, visc_h, q) - system_fn(q)), 0.0, visc_q[-1])
        if qv is not None:
            out["visc_op"] = {"q": qv, "h": _interp(visc_q, visc_h, qv)}
        elif out["water_op"] is not None:
            warnings.append("The corrected pump curve does not meet the system curve inside the range the method covers (up to 1.2 times the BEP flow), so no viscous operating point is given.")
        if out["water_op"] is None:
            warnings.append("The water pump curve does not meet the system curve within its range, so no operating point is given.")
    return out
