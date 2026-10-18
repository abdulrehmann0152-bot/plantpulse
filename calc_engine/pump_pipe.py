"""Pump and pipeline calculations (SI units: m, m3/s, Pa, W, kg/m3, Pa.s)."""
import math
from .heat_exchanger import InputError

G = 9.80665
_T = [0, 20, 40, 60, 80, 100]
_RHO = [999.8, 998.2, 992.2, 983.2, 971.8, 958.4]
_MU = [1.792e-3, 1.002e-3, 0.653e-3, 0.467e-3, 0.355e-3, 0.282e-3]


def _interp(x, xs, ys):
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            w = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + w * (ys[i + 1] - ys[i])
    raise InputError("Water temperature must be between 0 and 100 °C.")


def water_properties(t_c):
    """Density [kg/m3] and viscosity [Pa.s] of liquid water (linear table interpolation)."""
    return _interp(t_c, _T, _RHO), _interp(t_c, _T, _MU)


def velocity(q, d):
    return q / (math.pi * d * d / 4.0)


def reynolds(rho, v, d, mu):
    return rho * v * d / mu


def flow_regime(re):
    if re < 2300:
        return "laminar"
    if re < 4000:
        return "transition (uncertain)"
    return "turbulent"


def friction_factor(re, d, rough):
    """Darcy friction factor: 64/Re (laminar) or Swamee-Jain (turbulent)."""
    if re <= 0:
        raise InputError("Reynolds number must be positive.")
    if re < 2300:
        return 64.0 / re
    return 0.25 / math.log10(rough / (3.7 * d) + 5.74 / re ** 0.9) ** 2


def pipe_losses(q, d, length, rough, sum_k, rho, mu):
    """Darcy-Weisbach friction + fittings loss. Returns dict (head in m, dp in Pa)."""
    if min(d, length) <= 0 or rough < 0 or sum_k < 0 or q < 0:
        raise InputError("Diameter and length must be positive; roughness, K and flow cannot be negative.")
    if q == 0:
        return {"v": 0.0, "re": 0.0, "f": 0.0, "head": 0.0, "dp": 0.0}
    v = velocity(q, d)
    re = reynolds(rho, v, d, mu)
    f = friction_factor(re, d, rough)
    head = (f * length / d + sum_k) * v * v / (2 * G)
    return {"v": v, "re": re, "f": f, "head": head, "dp": rho * G * head}


def system_head(q, static_head, d, length, rough, sum_k, rho, mu):
    """System curve: H = static head + pipe and fittings losses [m]."""
    return static_head + pipe_losses(q, d, length, rough, sum_k, rho, mu)["head"]


def fit_pump_curve(points):
    """Fit H = a + b*Q + c*Q^2 through three (Q [m3/s], H [m]) points."""
    if len(points) != 3 or len({round(p[0], 12) for p in points}) != 3:
        raise InputError("Enter three pump curve points with different flows.")
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


def operating_point(coeffs, static_head, d, length, rough, sum_k, rho, mu, q_max):
    """Intersection of pump curve and system curve (bisection). Returns dict."""
    def gap(q):
        return pump_head(coeffs, q) - system_head(q, static_head, d, length, rough, sum_k, rho, mu)
    if gap(0.0) <= 0:
        raise InputError("The pump's shut-off head is below the static head: it cannot deliver any flow.")
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
    return {"q": q, "h": pump_head(coeffs, q), "hyd_w": rho * G * q * pump_head(coeffs, q), **loss}


def shaft_power(hyd_w, efficiency):
    if not 0 < efficiency <= 1:
        raise InputError("Efficiency must be between 0 and 100%.")
    return hyd_w / efficiency


def diagnose(q_meas, h_meas, coeffs, static_head, d, length, rough, sum_k, rho, mu, tol=0.05):
    """Compare a measured (Q, H) point with the twin's pump and system curves."""
    h_pump = pump_head(coeffs, q_meas)
    h_sys = system_head(q_meas, static_head, d, length, rough, sum_k, rho, mu)
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
