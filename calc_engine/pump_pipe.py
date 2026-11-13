"""Pump and pipeline calculations (SI units: m, m3/s, Pa, W, kg/m3, Pa.s).

Methods used (all checked by independent tests):
  * Water density: Kell (1975) polynomial. Water viscosity: Hardy-Cottington / Swindells equation. Both are continuous in temperature.
  * Friction factor: 64/Re (laminar, Re < 2300); Colebrook-White solved iteratively (turbulent, Re >= 4000); a straight-line blend between
    the two edge values in the transitional zone, so the system curve has no jump. Swamee-Jain is available as the explicit method
    (method="swamee_jain") and is used as the starting guess and as a cross-check.
  * Darcy-Weisbach: head loss = (f L/D + sum K) v^2 / (2 g), with standard gravity g = 9.80665 m/s2.
Every input is validated with a message that names the input and the value; nothing is replaced by a default.
"""
import math

from .heat_exchanger import InputError

G = 9.80665
RE_LAMINAR_MAX, RE_TURBULENT_MIN = 2300.0, 4000.0
MAX_REL_ROUGHNESS = 0.05           # Colebrook-White and Swamee-Jain are not valid above this relative roughness


# ---------------------------------------------------------------------------- input checks
def _number(name, value, unit=""):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(f"{name} must be a number (you entered {value!r}).")
    return value


def check_positive(name, value, unit=""):
    _number(name, value)
    if value <= 0:
        raise InputError(f"{name} must be greater than zero (you entered {value:g}{unit}).")
    return value


def check_non_negative(name, value, unit=""):
    _number(name, value)
    if value < 0:
        raise InputError(f"{name} cannot be negative (you entered {value:g}{unit}).")
    return value


def check_pipeline(d, length, rough, sum_k):
    """Validate the pipe data. d, length and rough in m. Raises InputError naming the input."""
    check_positive("Pipe inside diameter", d * 1000 if isinstance(d, (int, float)) and not isinstance(d, bool) else d, " mm")
    check_positive("Pipe length", length, " m")
    check_non_negative("Pipe roughness", rough * 1000 if isinstance(rough, (int, float)) and not isinstance(rough, bool) else rough, " mm")
    check_non_negative("Fittings loss ΣK", sum_k)
    if rough / d >= MAX_REL_ROUGHNESS:
        raise InputError(f"Relative roughness ε/D = {rough / d:.3f} (roughness {rough * 1000:g} mm on a {d * 1000:g} mm pipe) is not below {MAX_REL_ROUGHNESS}, "
                         "outside the range of the friction equations. Check that the diameter and the roughness are in the right units.")


def check_fluid(rho, mu):
    check_positive("Fluid density", rho, " kg/m³")
    check_positive("Fluid viscosity", mu * 1000 if isinstance(mu, (int, float)) and not isinstance(mu, bool) else mu, " mPa·s")


def check_efficiency(eta):
    """eta as a fraction. A pump cannot be 0% or 100% efficient."""
    _number("Pump efficiency", eta)
    if not 0 < eta < 1:
        raise InputError(f"Pump efficiency must be above 0% and below 100% (you entered {eta * 100:g}%).")
    return eta


def check_motor_efficiency(eta):
    """eta as a fraction. 100% is allowed here and means 'do not include motor losses'."""
    _number("Motor efficiency", eta)
    if not 0 < eta <= 1:
        raise InputError(f"Motor efficiency must be above 0% and at most 100% (you entered {eta * 100:g}%).")
    return eta


def efficiency_note(eta):
    """A note (not an error) if the efficiency is unusual for a centrifugal pump."""
    if eta > 0.90:
        return f"An efficiency of {eta * 100:.0f}% is unusually high for a centrifugal pump. Check that it is the pump efficiency at this flow."
    if eta < 0.30:
        return f"An efficiency of {eta * 100:.0f}% is very low. The pump is probably far from its best efficiency point, or the value is mistyped."
    return None


def check_pump_points(points):
    """Validate three (Q [m3/s], H [m]) pump curve points. Raises InputError; returns a list of warnings."""
    if len(points) != 3:
        raise InputError("Enter exactly three pump curve points.")
    for i, (q, h) in enumerate(points, 1):
        check_non_negative(f"Pump curve point {i} flow", q * 3600 if isinstance(q, (int, float)) and not isinstance(q, bool) else q, " m³/h")
        check_positive(f"Pump curve point {i} head", h, " m")
    if len({round(p[0], 12) for p in points}) != 3:
        raise InputError("Enter three pump curve points with different flows.")
    ordered = sorted(points)
    warnings = []
    for (q1, h1), (q2, h2) in zip(ordered, ordered[1:]):
        if h2 > h1:
            warnings.append(f"The head rises from {h1:g} m at {q1 * 3600:g} m³/h to {h2:g} m at {q2 * 3600:g} m³/h. A normal centrifugal pump curve falls as the flow increases, "
                            "so check the points (an unstable curve gives unreliable operating points).")
            break
    return warnings


# ---------------------------------------------------------------------------- fluid properties
def water_properties(t_c):
    """Density [kg/m3] and dynamic viscosity [Pa.s] of liquid water at atmospheric pressure, 0 to 100 °C.

    Density: Kell (1975). Viscosity: log10(mu/mu20) = (1.3272 (20 - T) - 0.001053 (T - 20)^2) / (T + 105), mu20 = 1.002 mPa.s (Hardy-Cottington / Swindells).
    """
    _number("Water temperature", t_c)
    if not 0.0 <= t_c <= 100.0:
        raise InputError(f"Water temperature must be between 0 and 100 °C, the range of liquid water at atmospheric pressure (you entered {t_c:g} °C).")
    t = float(t_c)
    rho = ((999.83952 + 16.945176 * t - 7.9870401e-3 * t ** 2 - 46.170461e-6 * t ** 3 + 105.56302e-9 * t ** 4 - 280.54253e-12 * t ** 5)
           / (1 + 16.879850e-3 * t))
    mu = 1.002e-3 * 10 ** ((1.3272 * (20 - t) - 0.001053 * (t - 20) ** 2) / (t + 105))
    return rho, mu


# ---------------------------------------------------------------------------- geometry, flow and Reynolds number
def area(d):
    """Cross-sectional flow area of a circular pipe [m2]."""
    return math.pi * d * d / 4.0


def velocity(q, d):
    return q / area(d)


def mass_flow(rho, q):
    return rho * q


def reynolds(rho, v, d, mu):
    return rho * v * d / mu


def flow_regime(re):
    if re < RE_LAMINAR_MAX:
        return "laminar"
    if re < RE_TURBULENT_MIN:
        return "transition (uncertain)"
    return "turbulent"


# ---------------------------------------------------------------------------- friction factor
def swamee_jain(re, d, rough):
    return 0.25 / math.log10(rough / (3.7 * d) + 5.74 / re ** 0.9) ** 2


def colebrook_white(re, d, rough):
    """Solve 1/sqrt(f) = -2 log10(eps/(3.7 D) + 2.51/(Re sqrt(f))) by fixed-point iteration. Returns (f, iterations)."""
    rr = rough / d
    f = swamee_jain(re, d, rough)
    for i in range(1, 201):
        f_new = (-2.0 * math.log10(rr / 3.7 + 2.51 / (re * math.sqrt(f)))) ** -2
        if abs(f_new - f) <= 1e-13 * f_new:
            return f_new, i
        f = f_new
    raise InputError("The Colebrook-White iteration did not converge. Check the Reynolds number and roughness.")


def friction_detail(re, d, rough, method="colebrook"):
    """The Darcy friction factor with how it was found: regime, method, iterations and the Swamee-Jain cross-check."""
    _number("Reynolds number", re)
    if re <= 0:
        raise InputError(f"Reynolds number must be greater than zero (it is {re:g}).")
    check_positive("Pipe inside diameter", d * 1000, " mm")
    check_non_negative("Pipe roughness", rough * 1000, " mm")
    if rough / d >= MAX_REL_ROUGHNESS:
        raise InputError(f"Relative roughness ε/D = {rough / d:.3f} is not below {MAX_REL_ROUGHNESS}; the friction equations do not apply. Check the units of the diameter and roughness.")
    if method not in ("colebrook", "swamee_jain"):
        raise InputError("The friction method must be 'colebrook' or 'swamee_jain'.")

    def turbulent(r):
        if method == "swamee_jain":
            return swamee_jain(r, d, rough), 0
        return colebrook_white(r, d, rough)

    out = {"regime": flow_regime(re), "method": method, "iterations": 0, "re": re}
    if re < RE_LAMINAR_MAX:
        out.update(f=64.0 / re, kind="laminar")
    elif re < RE_TURBULENT_MIN:
        f_lam, (f_turb, _) = 64.0 / RE_LAMINAR_MAX, turbulent(RE_TURBULENT_MIN)
        w = (re - RE_LAMINAR_MAX) / (RE_TURBULENT_MIN - RE_LAMINAR_MAX)
        out.update(f=f_lam + w * (f_turb - f_lam), kind="transition", f_lam_edge=f_lam, f_turb_edge=f_turb, weight=w)
    else:
        f, n = turbulent(re)
        out.update(f=f, iterations=n, kind="turbulent")
        out["f_swamee"] = swamee_jain(re, d, rough)
        out["f_colebrook"] = f if method == "colebrook" else colebrook_white(re, d, rough)[0]
    return out


def friction_factor(re, d, rough, method="colebrook"):
    """Darcy friction factor: 64/Re (laminar), Colebrook-White (turbulent), a blend in between. method='swamee_jain' uses the explicit formula instead."""
    return friction_detail(re, d, rough, method)["f"]


# ---------------------------------------------------------------------------- losses
def pipe_losses(q, d, length, rough, sum_k, rho, mu, method="colebrook"):
    """Darcy-Weisbach friction + fittings loss. Returns dict (head in m, dp in Pa). q = 0 gives zero losses (used for the system curve)."""
    check_pipeline(d, length, rough, sum_k)
    check_fluid(rho, mu)
    check_non_negative("Flow", q * 3600 if isinstance(q, (int, float)) and not isinstance(q, bool) else q, " m³/h")
    a = area(d)
    base = {"area": a, "rel_rough": rough / d, "method": method}
    if q == 0:
        return {"v": 0.0, "re": 0.0, "f": 0.0, "head": 0.0, "dp": 0.0, "m_dot": 0.0, "regime": "no flow", "head_friction": 0.0, "head_fittings": 0.0, "iterations": 0, **base}
    v = q / a
    re = reynolds(rho, v, d, mu)
    fd = friction_detail(re, d, rough, method)
    f, vh = fd["f"], v * v / (2 * G)
    hf, hk = f * length / d * vh, sum_k * vh
    return {"v": v, "re": re, "f": f, "head": hf + hk, "dp": rho * G * (hf + hk), "m_dot": rho * q, "regime": fd["regime"],
            "head_friction": hf, "head_fittings": hk, "iterations": fd["iterations"], **base}


def system_head(q, static_head, d, length, rough, sum_k, rho, mu):
    """System curve: H = static head + pipe and fittings losses [m]."""
    return static_head + pipe_losses(q, d, length, rough, sum_k, rho, mu)["head"]


# ---------------------------------------------------------------------------- pump curve and operating point
def fit_pump_curve(points):
    """Fit H = a + b*Q + c*Q^2 exactly through three (Q [m3/s], H [m]) points (Cramer's rule)."""
    check_pump_points(points)
    (q1, h1), (q2, h2), (q3, h3) = points

    def det(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    a_mat = [[1, q1, q1 * q1], [1, q2, q2 * q2], [1, q3, q3 * q3]]
    hs = [h1, h2, h3]
    d0 = det(a_mat)
    coeffs = []
    for col in range(3):
        m = [row[:] for row in a_mat]
        for r in range(3):
            m[r][col] = hs[r]
        coeffs.append(det(m) / d0)
    return tuple(coeffs)


def pump_head(coeffs, q):
    a, b, c = coeffs
    return a + b * q + c * q * q


def hydraulic_power(rho, q, h):
    """Hydraulic power [W] = rho g Q H."""
    return rho * G * q * h


def operating_point(coeffs, static_head, d, length, rough, sum_k, rho, mu, q_max, q_data_max=None):
    """Intersection of pump curve and system curve (bisection). Returns dict. q_data_max: the last flow of the pump datasheet, to flag extrapolation."""
    check_non_negative("Static head", static_head, " m")

    def gap(q):
        return pump_head(coeffs, q) - system_head(q, static_head, d, length, rough, sum_k, rho, mu)
    if gap(0.0) <= 0:
        raise InputError(f"The pump's shut-off head ({pump_head(coeffs, 0.0):.2f} m) is not above the static head ({static_head:g} m): it cannot deliver any flow.")
    hi = q_max
    if gap(hi) > 0:
        raise InputError("No operating point inside the pump curve range. Check the pump curve points.")
    lo = 0.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if gap(mid) > 0:
            lo = mid
        else:
            hi = mid
    q = (lo + hi) / 2
    loss = pipe_losses(q, d, length, rough, sum_k, rho, mu)
    h = pump_head(coeffs, q)
    return {"q": q, "h": h, "hyd_w": hydraulic_power(rho, q, h), "extrapolated": q_data_max is not None and q > q_data_max * (1 + 1e-9), "q_data_max": q_data_max, **loss}


def shaft_power(hyd_w, efficiency):
    check_efficiency(efficiency)
    check_positive("Hydraulic power", hyd_w, " W")
    return hyd_w / efficiency


def diagnose(q_meas, h_meas, coeffs, static_head, d, length, rough, sum_k, rho, mu, tol=0.05):
    """Compare a measured (Q, H) point with the twin's pump and system curves."""
    check_positive("Measured flow", q_meas * 3600, " m³/h")
    check_positive("Measured head", h_meas, " m")
    h_pump = pump_head(coeffs, q_meas)
    h_sys = system_head(q_meas, static_head, d, length, rough, sum_k, rho, mu)
    if h_pump <= 0:
        raise InputError(f"The fitted pump curve gives {h_pump:.2f} m at the measured flow of {q_meas * 3600:g} m³/h, which is beyond the pump data. The comparison would not be meaningful.")
    if h_sys <= 0:
        raise InputError("The system curve gives zero head at the measured flow (no static head and almost no friction), so the comparison is not meaningful.")
    pump_dev = (h_meas - h_pump) / h_pump
    sys_dev = (h_meas - h_sys) / h_sys
    if abs(pump_dev) <= tol and abs(sys_dev) <= tol:
        status, msg = "healthy", "Reading matches the twin. Pump and pipeline look healthy."
    elif pump_dev < -tol and abs(sys_dev) <= tol:
        status = "pump_degraded"
        msg = ("Head is below the pump curve while the pipeline matches the model: possible impeller wear, "
               "internal leakage, wrong speed or suction problem.")
    elif sys_dev > tol and abs(pump_dev) <= tol:
        status = "system_resistance"
        msg = ("Head is above the system curve while the pump matches its curve: extra resistance in the line, "
               "such as a throttled or partly closed valve, blockage or scaling.")
    else:
        status, msg = "check_data", "Reading does not fit a single clear cause. Re-check the instruments and inputs."
    return {"status": status, "message": msg, "pump_dev": pump_dev, "sys_dev": sys_dev,
            "h_pump": h_pump, "h_sys": h_sys}


ROUGHNESS_MM = {"Commercial steel (0.045 mm)": 0.045, "Cast iron (0.26 mm)": 0.26,
                "Galvanised iron (0.15 mm)": 0.15, "PVC / drawn tubing (0.0015 mm)": 0.0015}


def water_vapor_pressure_kpa(t_c):
    """Vapour pressure of water [kPa absolute] from the Antoine equation (valid 1 to 100 deg C, within about 0.5%)."""
    if not 1.0 <= t_c <= 100.0:
        raise InputError("The water vapour pressure equation is valid from 1 to 100 °C.")
    return 10 ** (8.07131 - 1730.63 / (233.426 + t_c)) * 0.133322
