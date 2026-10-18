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


def lmtd(th_in, th_out, tc_in, tc_out, flow="counter"):
    """Log mean temperature difference for pure counter-flow or parallel flow [K]."""
    _check_temps(th_in, th_out, tc_in, tc_out)
    if flow == "counter":
        d1, d2 = th_in - tc_out, th_out - tc_in
    elif flow == "parallel":
        d1, d2 = th_in - tc_in, th_out - tc_out
    else:
        raise InputError("flow must be 'counter' or 'parallel'.")
    if d1 <= 0 or d2 <= 0:
        raise InputError("Temperature cross: a terminal temperature difference is zero or negative. "
                         "Check the readings or the flow arrangement.")
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


def analyze(m_hot, cp_hot, th_in, th_out, m_cold, cp_cold, tc_in, tc_out,
            area, flow="counter", u_clean=None):
    """Full performance check. flow: 'counter', 'parallel' or 'shell_1_2'."""
    q_hot = heat_duty(m_hot, cp_hot, th_in, th_out)
    q_cold = heat_duty(m_cold, cp_cold, tc_in, tc_out)
    q_avg = (q_hot + q_cold) / 2.0
    if flow == "shell_1_2":
        lm = lmtd(th_in, th_out, tc_in, tc_out, "counter")
        f = correction_factor_1_2(th_in, th_out, tc_in, tc_out)
    else:
        lm = lmtd(th_in, th_out, tc_in, tc_out, flow)
        f = 1.0
    u = overall_u(q_avg, area, lm, f)
    result = {"q_hot": q_hot, "q_cold": q_cold, "q_avg": q_avg,
              "mismatch_pct": heat_balance_mismatch_pct(q_hot, q_cold),
              "lmtd": lm, "f": f, "u": u, "rf": None, "u_loss_pct": None}
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
