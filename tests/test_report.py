import os, sys
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import monitor as m
from core import report
from core.templates import TEMPLATES

USER = {"name": "Abdul Rehman", "role": "student"}

def _case(name, kind, scenario=None, **kw):
    t = TEMPLATES[name]
    eq = {"tag": kw.get("tag", t["tag"]), "location": kw.get("location", t["location"]), "params": t["params"]}
    if kind == "heat_exchanger":
        res = m.analyze_hx(m.demo_hx(eq["params"], scenario=scenario or "fouling"), eq["params"])
        return eq, res, m.hx_status(res), m.alerts_hx(res)
    res = m.analyze_pump(m.demo_pump(eq["params"], scenario or "healthy"), eq["params"])
    return eq, res, m.pump_status(res), m.alerts_pump(res)

def _pages(pdf):
    return pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")

HX, PUMP = "Sugar mill juice heater (example)", "Cooling-water pump loop (example)"

@pytest.mark.parametrize("name,kind,scenario", [(HX, "heat_exchanger", "fouling"), (HX, "heat_exchanger", "clean"),
                                                (PUMP, "pump", "healthy"), (PUMP, "pump", "throttled"), (PUMP, "pump", "worn")])
def test_report_builds_for_every_scenario(name, kind, scenario):
    eq, res, (status, text), alerts = _case(name, kind, scenario)
    pdf = report.build_report(kind, eq, res, alerts, status, text, USER, "Daily log sheets", True)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 4000 and 1 <= _pages(pdf) <= 3

def test_report_handles_non_latin_text():
    eq, res, (status, text), alerts = _case(PUMP, "pump", tag="P-\u03b7\u2265\u2212", location="Plant \u2013 Unit \u00b2")
    pdf = report.build_report("pump", eq, res, alerts, status, text, {"name": "\u0627\u0628\u062f\u0644", "role": "engineer"}, "\u2265 note")
    assert pdf[:5] == b"%PDF-"

def test_report_with_no_valid_readings_does_not_crash():
    eq, res, _, _ = _case(HX, "heat_exchanger")
    res = res.assign(error="bad row")
    pdf = report.build_report("heat_exchanger", eq, res, [], "nodata", "No valid readings yet.", USER)
    assert pdf[:5] == b"%PDF-"

def test_demo_flag_round_trip():
    df = m.demo_pump(TEMPLATES[PUMP]["params"], days=5)
    plain = m.df_from_logs([{"logged_at": ts, "data": d} for ts, d in m.rows_for_db(df)], "pump")
    demo = m.df_from_logs([{"logged_at": ts, "data": d} for ts, d in m.rows_for_db(df, demo=True)], "pump")
    assert not m.has_demo_rows(plain) and m.has_demo_rows(demo)
    # the extra flag column must not disturb the analysis
    assert (m.analyze_pump(demo, TEMPLATES[PUMP]["params"])["error"] == "").all()
    hxd = m.df_from_logs([{"logged_at": ts, "data": d} for ts, d in m.rows_for_db(m.demo_hx(TEMPLATES[HX]["params"], days=5), demo=True)], "heat_exchanger")
    assert (m.analyze_hx(hxd, TEMPLATES[HX]["params"])["error"] == "").all()
