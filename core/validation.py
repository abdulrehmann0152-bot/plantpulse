"""Validation log helpers: compare PlantPulse answers with textbook (or independent) answers."""
import csv
import io

MATCH_PCT, OK_PCT = 2.0, 5.0
MODULES = ["Heat exchanger", "Pipe flow", "Pump", "Monitoring / twin", "Other"]


def diff_pct(reference, app):
    """Percentage difference of the PlantPulse value from the reference value."""
    if reference == 0:
        return 0.0 if app == 0 else float("inf")
    return (app - reference) / abs(reference) * 100.0


def fmt_diff(d):
    """Signed difference for display, without a misleading '-0.00'."""
    if d == float("inf"):
        return "n/a"
    return "0.00" if abs(d) < 0.005 else f"{d:+.2f}"


def verdict(d):
    a = abs(d)
    if a <= MATCH_PCT:
        return "Match"
    return "Acceptable" if a <= OK_PCT else "Check"


def enrich(entries):
    out = []
    for e in entries:
        d = diff_pct(e["reference"], e["app_value"])
        out.append({**e, "diff_pct": d, "verdict": verdict(d)})
    return out


def summarize(entries):
    """entries must be enriched. Returns counts and mean/max absolute difference."""
    n = len(entries)
    finite = [abs(e["diff_pct"]) for e in entries if e["diff_pct"] != float("inf")]
    return {"n": n, "match": sum(e["verdict"] == "Match" for e in entries), "acceptable": sum(e["verdict"] == "Acceptable" for e in entries),
            "check": sum(e["verdict"] == "Check" for e in entries),
            "mean_abs": (sum(finite) / len(finite)) if finite else None, "max_abs": max(finite) if finite else None}


def to_csv(entries):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Source", "Module", "Problem", "Quantity", "Unit", "Textbook answer", "PlantPulse answer", "Difference %", "Verdict", "Notes"])
    for e in entries:
        d = e["diff_pct"]
        w.writerow([e["created_at"][:10], e["source"], e["module"], e["problem"], e["quantity"], e["unit"], f"{e['reference']:.6g}",
                    f"{e['app_value']:.6g}", "n/a" if d == float("inf") else f"{d:+.2f}", e["verdict"], e["notes"]])
    return buf.getvalue()


def hx_values(r):
    """Quantities of a heat exchanger solution, as {name: (value, unit)}."""
    v = {"LMTD, counter-flow": (r["lmtd_counter"], "K")}
    if r.get("lmtd_parallel") is not None:
        v["LMTD, parallel flow"] = (r["lmtd_parallel"], "K")
    if r.get("R") is not None:
        v["R"], v["P"] = (r["R"], "-"), (r["P"], "-")
    if r["arrangement"].startswith("shell") or r["f_used"] != 1.0:
        v["Correction factor F"], v["Corrected LMTD"] = (r["f_used"], "-"), (r["lmtd_eff"], "K")
    for key, name, unit in (("phi", "Viscosity factor phi", "-"), ("u_corrected", "Corrected U", "W/m2K"), ("n_tubes_exact", "Number of tubes (exact)", "-"),
                            ("tube_length_found", "Tube length", "m"), ("q_kw", "Heat duty Q", "kW"), ("m_cold", "Cold flow", "kg/s"), ("m_hot", "Hot flow", "kg/s"), ("area", "Area", "m2"), ("u", "Overall U", "W/m2K")):
        if r.get(key):
            v[name] = (r[key], unit)
    return v


def pipe_values(r):
    v = {"Velocity": (r["v"], "m/s"), "Reynolds number": (r["re"], "-"), "Friction factor f": (r["f"], "-"), "Friction head loss": (r["hf"], "m")}
    fit = r.get("hk", 0) + r.get("hle", 0)
    if fit > 0:
        v["Fittings head loss"] = (fit, "m")
    if "dp_friction_kpa" in r:
        v["Friction pressure drop"] = (r["dp_friction_kpa"], "kPa")
        v["Total head required"] = (r["head_m"], "m")
        if r.get("hyd_kw") is not None:
            v["Hydraulic power"] = (r["hyd_kw"], "kW")
        if r.get("shaft_kw") is not None:
            v["Shaft power"] = (r["shaft_kw"], "kW")
    else:
        v["Flow found"] = (r["q_m3h"], "m3/h")
    return v
