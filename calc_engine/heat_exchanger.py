"""Heat exchanger calculations.

SI units everywhere: temperature in deg C, flow in kg/s, Cp in J/(kg.K),
heat in W, area in m2, U in W/(m2.K), fouling resistance in m2.K/W.
"""
import math


class InputError(ValueError):
    """Raised when the operating data is physically impossible."""


def heat_duty(m_dot, cp, t_in, t_out):
    """Q = m * Cp * |T_out - T_in|   [W]"""
    if m_dot <= 0 or cp <= 0:
        raise InputError("Mass flow and Cp must be positive.")
    return m_dot * cp * abs(t_out - t_in)


def _check_temps(th_in, th_out, tc_in, tc_out):
    if min(th_in, th_out, tc_in, tc_out) <= -273.15:
        raise InputError("A temperature cannot be at or below absolute zero (-273.15 °C). Check the unit you selected.")
    if th_in <= th_out:
        raise InputError("Hot fluid must cool down: hot inlet must be higher than hot outlet.")
    if tc_out <= tc_in:
        raise InputError("Cold fluid must heat up: cold outlet must be higher than cold inlet.")


F_MIN = 0.75                  # below this a shell-and-tube exchanger needs far more area than a counter-flow one
HEAT_BALANCE_TOL_PCT = 1.0    # default tolerance for the hot-side / cold-side duty mismatch
SEVERE_BALANCE_PCT = 5.0
MIN_APPROACH_K = 3.0          # a terminal temperature difference below this makes U and the area very sensitive to reading errors


def terminal_differences(th_in, th_out, tc_in, tc_out, flow="counter"):
    """The two terminal temperature differences (dT1 at the hot-inlet end, dT2 at the hot-outlet end) for pure counter-flow or parallel flow.

    Rejects temperature crossover: if either difference is zero or negative the data are physically impossible, and the message names
    the end, the temperatures and the numbers.
    """
    _check_temps(th_in, th_out, tc_in, tc_out)
    if flow == "counter":
        ends = (("hot-inlet end", "ΔT₁", "T(h,in) − T(c,out)", th_in, tc_out,
                 "The cold fluid would leave hotter than the hot fluid enters, which would need heat to flow from cold to hot."),
                ("hot-outlet end", "ΔT₂", "T(h,out) − T(c,in)", th_out, tc_in,
                 "The hot fluid would leave colder than the cold fluid enters, which would need heat to flow from cold to hot."))
    elif flow == "parallel":
        ends = (("inlet end", "ΔT₁", "T(h,in) − T(c,in)", th_in, tc_in,
                 "The hot inlet must be hotter than the cold inlet for heat to flow."),
                ("outlet end", "ΔT₂", "T(h,out) − T(c,out)", th_out, tc_out,
                 "In parallel flow the cold outlet can never be hotter than the hot outlet. Use counter-flow or a multi-pass exchanger."))
    else:
        raise InputError("flow must be 'counter' or 'parallel'.")
    out = []
    for end, name, expr, hot, cold, reason in ends:
        d = hot - cold
        if d <= 0:
            raise InputError(f"Temperature cross at the {end} of a {flow}-flow exchanger: {name} = {expr} = {hot:g} − {cold:g} = {d:g} K, "
                             f"which is zero or negative. {reason} Check the readings or the flow arrangement.")
        out.append(d)
    return out[0], out[1]


def approach_warnings(d1, d2):
    """Soft warnings (not errors) when a terminal difference is very small."""
    small = min(d1, d2)
    if small < MIN_APPROACH_K:
        return [f"The smallest terminal temperature difference is only {small:g} K. A reading error of 0.5 K would change it by {0.5 / small * 100:.0f}%, "
                "so the LMTD, U and any area found from them are very sensitive. Check the temperatures carefully."]
    return []


def lmtd(th_in, th_out, tc_in, tc_out, flow="counter"):
    """Log mean temperature difference for pure counter-flow or parallel flow [K]."""
    d1, d2 = terminal_differences(th_in, th_out, tc_in, tc_out, flow)
    if math.isclose(d1, d2, rel_tol=1e-9):
        return (d1 + d2) / 2.0
    return (d1 - d2) / math.log(d1 / d2)


def correction_factor_1_2(th_in, th_out, tc_in, tc_out):
    """LMTD correction factor F for 1 shell pass / 2 (or more even) tube passes."""
    _check_temps(th_in, th_out, tc_in, tc_out)
    r = (th_in - th_out) / (tc_out - tc_in)
    p = (tc_out - tc_in) / (th_in - tc_in)
    if not 0 < p < 1:
        raise InputError("Cold-side temperature effectiveness P must be between 0 and 1.")
    if 1 - p * r <= 0:
        raise InputError("Not achievable with one shell pass (temperature cross). Use more shells.")
    s = math.sqrt(r * r + 1.0)
    if abs(r - 1.0) < 1e-6:
        sq2 = math.sqrt(2.0)
        arg = (2 - p * (2 - sq2)) / (2 - p * (2 + sq2))
        num = sq2 * p / (1 - p)
    else:
        arg = (2 - p * (r + 1 - s)) / (2 - p * (r + 1 + s))
        num = s / (r - 1) * math.log((1 - p) / (1 - p * r))
    if arg <= 0 or arg == 1:
        raise InputError("Not achievable with one shell pass. Use more shells.")
    return num / math.log(arg)


def overall_u(q, area, lmtd_value, f=1.0):
    """U = Q / (A * F * LMTD)   [W/(m2.K)]"""
    if area <= 0 or lmtd_value <= 0 or f <= 0:
        raise InputError("Area, LMTD and F must be positive.")
    return q / (area * f * lmtd_value)


def fouling_resistance(u_fouled, u_clean):
    """Rf = 1/U_fouled - 1/U_clean   [m2.K/W]"""
    if u_fouled <= 0 or u_clean <= 0:
        raise InputError("U values must be positive.")
    return 1.0 / u_fouled - 1.0 / u_clean


def heat_balance_mismatch_pct(q_hot, q_cold):
    """Difference between hot-side and cold-side duty as % of their average."""
    return abs(q_hot - q_cold) / ((q_hot + q_cold) / 2.0) * 100.0


def heat_balance_status(q_hot, q_cold, tol_pct=HEAT_BALANCE_TOL_PCT):
    """Judge the hot-side / cold-side duty mismatch (as % of their average) against a tolerance.

    level: 'ok' (mismatch <= tolerance), 'error' (above the tolerance) or 'severe' (above 5%, or twice the tolerance if that is larger).
    """
    if tol_pct <= 0:
        raise InputError("The heat balance tolerance must be above zero.")
    m = heat_balance_mismatch_pct(q_hot, q_cold)
    higher = "hot" if q_hot > q_cold else "cold"
    severe_at = max(SEVERE_BALANCE_PCT, 2 * tol_pct)
    if m <= tol_pct + 1e-9:
        level = "ok"
        text = f"Heat balance closes: hot side {q_hot / 1000:,.2f} kW, cold side {q_cold / 1000:,.2f} kW, mismatch {m:.2f}% (tolerance {tol_pct:g}%)."
    else:
        level = "severe" if m > severe_at else "error"
        text = (f"HEAT BALANCE DOES NOT CLOSE: mismatch {m:.2f}% (tolerance {tol_pct:g}%). Hot side {q_hot / 1000:,.2f} kW against cold side "
                f"{q_cold / 1000:,.2f} kW; the {higher}-side duty is higher. Check the flows, Cp values and temperatures (the heat balance should close), "
                "or allow for heat loss and instrument error.")
        if level == "severe":
            text += f" A mismatch above {severe_at:g}% usually means at least one reading is wrong: do not rely on U or on fouling conclusions until it is found."
    return {"mismatch_pct": m, "tol_pct": tol_pct, "level": level, "ok": level == "ok", "higher": higher, "message": text}


def f_assessment(f):
    """A warning text if the correction factor is below 0.75, else None. Area is proportional to 1/F."""
    if f < F_MIN:
        return (f"F = {f:.3f} is below {F_MIN}. For the same duty this arrangement needs about {(1 / f - 1) * 100:.0f}% more heat transfer area than pure counter-flow "
                "(area is proportional to 1/F), and F falls steeply with small temperature changes, so it is normally uneconomical and unstable. "
                "Use more shells in series or a true counter-flow arrangement.")
    return None


def temperature_profile(arrangement, th_in, th_out, tc_in, tc_out, n=21):
    """Hot and cold temperatures against the fraction of the heat duty transferred, measured from the hot-inlet end (x = 0 on the left).

    With constant Cp both temperatures are straight lines against heat transferred.
    * Counter-flow (and a multi-pass exchanger, shown as its counter-flow equivalent): the cold fluid flows the other way, so on the
      LEFT it is at its OUTLET temperature and on the right at its inlet temperature. The cold line is therefore reversed.
    * Parallel flow: both fluids enter at the left, so the cold line rises from its inlet temperature.
    """
    if n < 2:
        raise InputError("A profile needs at least two points.")
    flow = "parallel" if arrangement == "parallel" else "counter"
    d1, d2 = terminal_differences(th_in, th_out, tc_in, tc_out, flow)
    xs = [i / (n - 1) for i in range(n)]
    hot = [th_in - (th_in - th_out) * x for x in xs]
    cold = [tc_in + (tc_out - tc_in) * x for x in xs] if flow == "parallel" else [tc_out - (tc_out - tc_in) * x for x in xs]
    return {"x": xs, "hot": hot, "cold": cold, "flow": flow, "equivalent": arrangement.startswith("shell"), "d1": d1, "d2": d2,
            "th_in": th_in, "th_out": th_out, "tc_in": tc_in, "tc_out": tc_out}


def profile_note(p):
    """The explanation printed on the temperature graph (plain text, lines separated by newlines)."""
    if p["flow"] == "counter":
        lines = ["Counter-flow: the two fluids enter at opposite ends.",
                 f"Left end (hot inlet): hot in {p['th_in']:g} °C meets cold OUT {p['tc_out']:g} °C, ΔT₁ = {p['d1']:g} K.",
                 f"Right end (hot outlet): hot out {p['th_out']:g} °C meets cold IN {p['tc_in']:g} °C, ΔT₂ = {p['d2']:g} K.",
                 "So the cold line is reversed: it starts at T(c,out) on the left and falls to T(c,in) on the right, because the cold fluid flows right to left."]
        if p["equivalent"]:
            lines.append("A multi-pass exchanger is shown as its overall counter-flow equivalent (the basis of the F factor). The real profile bends because the cold stream makes two passes.")
    else:
        lines = ["Parallel flow: both fluids enter at the left end.",
                 f"Left end: hot in {p['th_in']:g} °C meets cold in {p['tc_in']:g} °C, ΔT₁ = {p['d1']:g} K.",
                 f"Right end: hot out {p['th_out']:g} °C meets cold out {p['tc_out']:g} °C, ΔT₂ = {p['d2']:g} K.",
                 "Both lines move the same way and the gap closes; the cold fluid can never leave hotter than the hot fluid."]
    return "\n".join(lines)


def analyze(m_hot, cp_hot, th_in, th_out, m_cold, cp_cold, tc_in, tc_out,
            area, flow="counter", u_clean=None, *, balance_tol_pct=HEAT_BALANCE_TOL_PCT):
    """Full performance check. flow: 'counter', 'parallel' or 'shell_1_2'."""
    q_hot = heat_duty(m_hot, cp_hot, th_in, th_out)
    q_cold = heat_duty(m_cold, cp_cold, tc_in, tc_out)
    q_avg = (q_hot + q_cold) / 2.0
    base_flow = "counter" if flow == "shell_1_2" else flow
    d1, d2 = terminal_differences(th_in, th_out, tc_in, tc_out, base_flow)
    lm = lmtd(th_in, th_out, tc_in, tc_out, base_flow)
    f = correction_factor_1_2(th_in, th_out, tc_in, tc_out) if flow == "shell_1_2" else 1.0
    u = overall_u(q_avg, area, lm, f)
    result = {"q_hot": q_hot, "q_cold": q_cold, "q_avg": q_avg,
              "mismatch_pct": heat_balance_mismatch_pct(q_hot, q_cold),
              "balance": heat_balance_status(q_hot, q_cold, balance_tol_pct),
              "lmtd": lm, "f": f, "u": u, "rf": None, "u_loss_pct": None,
              "d1": d1, "d2": d2, "approach_warnings": approach_warnings(d1, d2), "f_warning": f_assessment(f),
              "r_ratio": (th_in - th_out) / (tc_out - tc_in), "p_ratio": (tc_out - tc_in) / (th_in - tc_in)}
    if u_clean:
        result["rf"] = fouling_resistance(u, u_clean)
        result["u_loss_pct"] = (1 - u / u_clean) * 100.0
    return result


def _ntu_counter(r, p):
    """NTU (based on the cold stream) a pure counter-flow exchanger needs for the same R and P."""
    if abs(r - 1.0) < 1e-9:
        return p / (1 - p)
    return math.log((1 - p) / (1 - p * r)) / (r - 1)


def _shells_text(n):
    return "one shell pass" if n == 1 else f"{n} shell passes"


def _ntu_1_2(r, p1, n_shells=1):
    """NTU (based on the cold stream) of one shell pass with two tube passes that reaches effectiveness P1."""
    s = math.sqrt(r * r + 1.0)
    num, den = 2 - p1 * (r + 1 - s), 2 - p1 * (r + 1 + s)
    if num <= 0 or den <= 0:
        raise InputError(f"Not achievable with {_shells_text(n_shells)}. Use more shells.")
    return math.log(num / den) / s


def shell_effectiveness(r, p, n_shells):
    """P of ONE shell pass when n identical 1-2 shells in series (overall counter-current) give the overall P."""
    if n_shells == 1:
        return p
    if abs(r - 1.0) < 1e-9:
        return p / (n_shells - (n_shells - 1) * p)
    x = ((1 - p * r) / (1 - p)) ** (1.0 / n_shells)
    return (x - 1) / (x - r)


def correction_factor_n_shells(th_in, th_out, tc_in, tc_out, n_shells):
    """LMTD correction factor F for n shell passes in series, each with 2 (or more even) tube passes.

    n_shells = 1 is the 1-2 exchanger, 2 is the 2-4 exchanger. F = NTU(counter-flow) / (n x NTU(one 1-2 shell)),
    because the area needed is the counter-flow area divided by F.
    """
    _check_temps(th_in, th_out, tc_in, tc_out)
    if n_shells < 1 or int(n_shells) != n_shells:
        raise InputError("The number of shell passes must be a whole number of at least 1.")
    r = (th_in - th_out) / (tc_out - tc_in)
    p = (tc_out - tc_in) / (th_in - tc_in)
    if not 0 < p < 1:
        raise InputError("Cold-side temperature effectiveness P must be between 0 and 1.")
    if 1 - p * r <= 0:
        raise InputError("Not achievable (temperature cross): the hot outlet must be above the cold inlet.")
    p1 = shell_effectiveness(r, p, n_shells)
    if not 0 < p1 < 1:
        raise InputError(f"Not achievable with {_shells_text(n_shells)}. Use more shells.")
    return _ntu_counter(r, p) / (n_shells * _ntu_1_2(r, p1, n_shells))
