"""Monitoring and mini digital twin: batch analysis of operating logs, alerts, demo data, CSV parsing.

Heat exchanger twin: predicts outlet temperatures for the CLEAN exchanger (effectiveness-NTU) and
compares with the observed outlets. Pump twin: compares each (flow, head) reading with the expected
pump curve and system curve.
"""
import io
import math
import random
from datetime import date

import pandas as pd

from . import heat_exchanger as hx
from . import pump_pipe as pp
from .heat_exchanger import InputError

HX_COLUMNS = ["timestamp", "m_hot_kg_s", "cp_hot_kj_kgk", "t_hot_in_c", "t_hot_out_c",
              "m_cold_kg_s", "cp_cold_kj_kgk", "t_cold_in_c", "t_cold_out_c"]
PUMP_COLUMNS = ["timestamp", "flow_m3_h", "head_m"]
PUMP_OPTIONAL = ["water_temp_c"]
WARN_LOSS, CRIT_LOSS, MISMATCH_TOL = 10.0, 25.0, 5.0


# ---------------------------------------------------------------- heat exchanger twin
def effectiveness(flow, ntu, cr):
    """Effectiveness of counter, parallel or 1-shell/2-tube-pass exchangers."""
    if flow == "counter":
        if abs(cr - 1) < 1e-9:
            return ntu / (1 + ntu)
        e = math.exp(-ntu * (1 - cr))
        return (1 - e) / (1 - cr * e)
    if flow == "parallel":
        return (1 - math.exp(-ntu * (1 + cr))) / (1 + cr)
    if flow == "shell_1_2":
        s = math.sqrt(1 + cr * cr)
        e = math.exp(-ntu * s)
        return 2 / (1 + cr + s * (1 + e) / (1 - e))
    raise InputError("Unknown flow arrangement.")


def predict_outlets(flow, ua, c_hot, c_cold, th_in, tc_in):
    """Outlet temperatures and duty [W] for a given UA [W/K] and capacity rates [W/K]."""
    cmin, cmax = min(c_hot, c_cold), max(c_hot, c_cold)
    eps = effectiveness(flow, ua / cmin, cmin / cmax)
    q = eps * cmin * (th_in - tc_in)
    return th_in - q / c_hot, tc_in + q / c_cold, q


def analyze_hx(df, params):
    """Row-by-row performance and twin comparison. Bad rows are kept and flagged, not dropped."""
    rows = []
    for r in df.itertuples(index=False):
        rec = {"timestamp": r.timestamp, "error": ""}
        try:
            res = hx.analyze(r.m_hot_kg_s, r.cp_hot_kj_kgk * 1000, r.t_hot_in_c, r.t_hot_out_c,
                             r.m_cold_kg_s, r.cp_cold_kj_kgk * 1000, r.t_cold_in_c, r.t_cold_out_c,
                             params["area_m2"], params["flow"], params["u_clean"])
            c_hot, c_cold = r.m_hot_kg_s * r.cp_hot_kj_kgk * 1000, r.m_cold_kg_s * r.cp_cold_kj_kgk * 1000
            th_exp, tc_exp, q_exp = predict_outlets(params["flow"], params["area_m2"] * params["u_clean"],
                                                    c_hot, c_cold, r.t_hot_in_c, r.t_cold_in_c)
            rec.update(tc_out_observed=r.t_cold_out_c, q_kw=res["q_avg"] / 1000, lmtd=res["lmtd"], f=res["f"], u=res["u"], rf=res["rf"],
                       u_loss_pct=res["u_loss_pct"], mismatch_pct=res["mismatch_pct"],
                       th_out_expected=th_exp, tc_out_expected=tc_exp, q_expected_kw=q_exp / 1000,
                       shortfall_pct=(1 - res["q_avg"] / q_exp) * 100)
        except (InputError, ValueError, ZeroDivisionError) as e:
            rec["error"] = str(e)
        rows.append(rec)
    return pd.DataFrame(rows)


def hx_status(results):
    """('ok'|'warning'|'critical'|'nodata', text) from the latest valid reading."""
    ok = results[results["error"] == ""]
    if ok.empty:
        return "nodata", "No valid readings yet."
    loss = ok.iloc[-1]["u_loss_pct"]
    if loss > CRIT_LOSS:
        return "critical", f"U is {loss:.0f}% below clean. Cleaning is needed."
    if loss > WARN_LOSS:
        return "warning", f"U is {loss:.0f}% below clean. Watch the trend and plan cleaning."
    return "ok", f"U is within {WARN_LOSS:.0f}% of clean. Exchanger looks healthy."


def _fmt(ts):
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def alerts_hx(results):
    out = []
    ok = results[results["error"] == ""]
    for level, sev, name in ((WARN_LOSS, "warning", "10%"), (CRIT_LOSS, "critical", "25%")):
        hit = ok[ok["u_loss_pct"] > level]
        if not hit.empty:
            out.append({"first_seen": _fmt(hit.iloc[0]["timestamp"]), "severity": sev,
                        "rule": f"U more than {name} below clean",
                        "detail": f"{len(hit)} reading(s) above the limit; latest U loss {ok.iloc[-1]['u_loss_pct']:.1f}%"})
    bad = ok[ok["mismatch_pct"] > MISMATCH_TOL]
    if not bad.empty:
        out.append({"first_seen": _fmt(bad.iloc[0]["timestamp"]), "severity": "info", "rule": "Heat balance mismatch",
                    "detail": f"{len(bad)} reading(s) with hot/cold duty differing by more than {MISMATCH_TOL:.0f}%: check instruments"})
    skipped = results[results["error"] != ""]
    if not skipped.empty:
        out.append({"first_seen": _fmt(skipped.iloc[0]["timestamp"]), "severity": "info", "rule": "Readings skipped",
                    "detail": f"{len(skipped)} reading(s) could not be analysed, e.g. {skipped.iloc[0]['error']}"})
    return out


# ---------------------------------------------------------------- pump twin
def _pump_setup(params):
    d, rough = params["d_mm"] / 1000.0, pp.ROUGHNESS_MM[params["material"]] / 1000.0
    coeffs = pp.fit_pump_curve([(q / 3600.0, h) for q, h in params["curve"]])
    return d, rough, coeffs


def analyze_pump(df, params):
    d, rough, coeffs = _pump_setup(params)
    rows = []
    for r in df.itertuples(index=False):
        rec = {"timestamp": r.timestamp, "error": ""}
        try:
            temp = getattr(r, "water_temp_c", 30.0)
            rho, mu = pp.water_properties(30.0 if pd.isna(temp) else temp)
            dg = pp.diagnose(r.flow_m3_h / 3600.0, r.head_m, coeffs, params["static_m"], d, params["length_m"],
                             rough, params["sum_k"], rho, mu)
            rec.update(flow_m3_h=r.flow_m3_h, head_m=r.head_m, h_pump_expected=dg["h_pump"],
                       h_sys_expected=dg["h_sys"], pump_dev_pct=dg["pump_dev"] * 100,
                       sys_dev_pct=dg["sys_dev"] * 100, status=dg["status"], message=dg["message"])
        except (InputError, ValueError, ZeroDivisionError) as e:
            rec["error"] = str(e)
        rows.append(rec)
    return pd.DataFrame(rows)


PUMP_RULES = {"pump_degraded": "Head below pump curve (possible pump wear)",
              "system_resistance": "Head above system curve (extra line resistance)",
              "check_data": "Reading fits no single cause"}


def alerts_pump(results):
    out = []
    ok = results[results["error"] == ""]
    recent = ok.tail(5)
    for status, rule in PUMP_RULES.items():
        is_s = ok["status"] == status
        twice = ok[is_s & is_s.shift(1, fill_value=False)]   # a single noisy reading is not an alert
        if twice.empty:
            continue
        persistent = (recent["status"] == status).sum() >= 3
        out.append({"first_seen": _fmt(twice.iloc[0]["timestamp"]), "severity": "critical" if persistent else "warning",
                    "rule": rule, "detail": f"{int(is_s.sum())} reading(s); {'persistent in the latest readings' if persistent else 'not persistent yet'}"})
    skipped = results[results["error"] != ""]
    if not skipped.empty:
        out.append({"first_seen": _fmt(skipped.iloc[0]["timestamp"]), "severity": "info", "rule": "Readings skipped",
                    "detail": f"{len(skipped)} reading(s) could not be analysed, e.g. {skipped.iloc[0]['error']}"})
    return out


def pump_status(results):
    ok = results[results["error"] == ""]
    if ok.empty:
        return "nodata", "No valid readings yet."
    last = ok.iloc[-1]["status"]
    if last == "healthy":
        return "ok", "Latest reading matches the twin. Pump and pipeline look healthy."
    persistent = (ok.tail(5)["status"] == last).sum() >= 3
    return ("critical" if persistent else "warning"), ok.iloc[-1]["message"]


# ---------------------------------------------------------------- demo data
def _dates(days):
    return pd.date_range(end=pd.Timestamp(date.today()), periods=days, freq="D")


def demo_hx(params, days=60, scenario="fouling", seed=7, noise=0.15, final_loss=0.35):
    """Synthetic daily readings generated from the physical model (NTU 1.2 clean, Cr 0.9)."""
    rng = random.Random(seed)
    ua0 = params["area_m2"] * params["u_clean"]
    c_hot0 = ua0 / 1.2
    cp_h, cp_c = 4.18, 3.90
    m_hot0, m_cold0 = c_hot0 / (cp_h * 1000), (c_hot0 / 0.9) / (cp_c * 1000)
    rf_final = 1 / (params["u_clean"] * (1 - final_loss)) - 1 / params["u_clean"]
    rows = []
    for i, ts in enumerate(_dates(days)):
        rf = rf_final * i / (days - 1) if scenario == "fouling" else 0.0
        ua = params["area_m2"] / (1 / params["u_clean"] + rf)
        m_h, m_c = m_hot0 * (1 + rng.gauss(0, .01)), m_cold0 * (1 + rng.gauss(0, .01))
        th_in, tc_in = 110 + rng.gauss(0, .5), 35 + rng.gauss(0, .5)
        th_out, tc_out, _ = predict_outlets(params["flow"], ua, m_h * cp_h * 1000, m_c * cp_c * 1000, th_in, tc_in)
        rows.append({"timestamp": ts, "m_hot_kg_s": round(m_h, 4), "cp_hot_kj_kgk": cp_h, "t_hot_in_c": round(th_in, 3),
                     "t_hot_out_c": round(th_out + rng.gauss(0, noise), 3), "m_cold_kg_s": round(m_c, 4),
                     "cp_cold_kj_kgk": cp_c, "t_cold_in_c": round(tc_in, 3),
                     "t_cold_out_c": round(tc_out + rng.gauss(0, noise), 3)})
    return pd.DataFrame(rows)


def demo_pump(params, scenario="healthy", days=60, seed=7, noise=0.01):
    """scenario: healthy, throttled (valve/blockage ramps up) or worn (pump head falls)."""
    rng = random.Random(seed)
    d, rough, coeffs = _pump_setup(params)
    rho, mu = pp.water_properties(30.0)
    q_max = max(q for q, _ in params["curve"]) * 1.5 / 3600.0
    rows = []
    for i, ts in enumerate(_dates(days)):
        ramp = max(0.0, (i - 20) / max(1, days - 21))
        k = params["sum_k"] + (25.0 * ramp if scenario == "throttled" else 0.0)
        scale = 1 - 0.15 * ramp if scenario == "worn" else 1.0
        op = pp.operating_point(tuple(c * scale for c in coeffs), params["static_m"], d, params["length_m"],
                                rough, k, rho, mu, q_max)
        rows.append({"timestamp": ts, "flow_m3_h": round(op["q"] * 3600 * (1 + rng.gauss(0, noise)), 2),
                     "head_m": round(op["h"] * (1 + rng.gauss(0, noise)), 3)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- CSV in / out
def template_csv(kind):
    if kind == "heat_exchanger":
        return ("timestamp,m_hot_kg_s,cp_hot_kj_kgk,t_hot_in_c,t_hot_out_c,m_cold_kg_s,cp_cold_kj_kgk,t_cold_in_c,t_cold_out_c\n"
                "2026-10-01,1.5,4.18,100,60,2.0,4.18,20,50\n2026-10-02,1.5,4.18,100,61,2.0,4.18,20,49.5\n")
    return "timestamp,flow_m3_h,head_m,water_temp_c\n2026-10-01,290,17.9,30\n2026-10-02,285,18.3,30\n"


def parse_csv(source, kind):
    """Read and validate a CSV. Returns (clean DataFrame, number of rows dropped)."""
    required = HX_COLUMNS if kind == "heat_exchanger" else PUMP_COLUMNS
    try:
        df = pd.read_csv(io.StringIO(source) if isinstance(source, str) else source)
    except Exception:
        raise InputError("Could not read the file. Save it as a .csv file with a header row.")
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise InputError(f"Missing column(s): {', '.join(missing)}. Download the template to see the expected columns.")
    keep = required + [c for c in PUMP_OPTIONAL if kind == "pump" and c in df.columns]
    df = df[keep].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for c in keep[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    must = [c for c in keep if c not in PUMP_OPTIONAL]
    good = df.dropna(subset=must).sort_values("timestamp").reset_index(drop=True)
    if good.empty:
        raise InputError("No valid rows found. Check dates and numbers in the file.")
    return good, len(df) - len(good)


def rows_for_db(df, demo=False):
    """DataFrame -> [(timestamp_iso, data_dict)] for the operating_logs table. demo=True flags synthetic rows."""
    out = []
    for rec in df.to_dict("records"):
        ts = pd.Timestamp(rec.pop("timestamp")).isoformat()
        data = {k: (None if pd.isna(v) else float(v)) for k, v in rec.items()}
        if demo:
            data["demo"] = 1.0
        out.append((ts, data))
    return out


def has_demo_rows(df):
    """True if any stored reading was flagged as synthetic demo data."""
    return "demo" in df.columns and bool(pd.to_numeric(df["demo"], errors="coerce").fillna(0).sum() > 0)


def df_from_logs(logs, kind):
    """Stored logs -> DataFrame sorted by time."""
    if not logs:
        return pd.DataFrame()
    df = pd.DataFrame([{"timestamp": pd.Timestamp(l["logged_at"]), **l["data"]} for l in logs])
    return df.sort_values("timestamp").reset_index(drop=True)


# ---------------------------------------------------------------- CSV unit conversion
COLUMN_CATEGORIES = {
    "heat_exchanger": {"t_hot_in_c": "temp", "t_hot_out_c": "temp", "t_cold_in_c": "temp", "t_cold_out_c": "temp",
                       "m_hot_kg_s": "mass_flow", "m_cold_kg_s": "mass_flow", "cp_hot_kj_kgk": "cp", "cp_cold_kj_kgk": "cp"},
    "pump": {"flow_m3_h": "vol_flow", "head_m": "head", "water_temp_c": "temp"},
}


def convert_units(df, kind, chosen):
    """Convert a parsed CSV to the engine units. chosen: {category: unit the file uses}, e.g. {'temp': '°F', 'mass_flow': 'kg/h'}."""
    from core import units
    out = df.copy()
    for col, cat in COLUMN_CATEGORIES[kind].items():
        unit = chosen.get(cat)
        if col in out.columns and unit and unit != units.si_unit(cat):
            out[col] = units.to_si_series(cat, unit, out[col])
    return out
