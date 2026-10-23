import io, os, sys
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import monitor as m, pump_pipe as pp
from calc_engine.heat_exchanger import InputError
from core.templates import TEMPLATES, MATERIALS

HX = TEMPLATES["Sugar mill juice heater (example)"]["params"]
PUMP = TEMPLATES["Cooling-water pump loop (example)"]["params"]

def test_material_names_match_roughness_table():
    assert set(MATERIALS) == set(pp.ROUGHNESS_MM)

@pytest.mark.parametrize("flow", ["counter", "parallel", "shell_1_2"])
def test_twin_round_trip_recovers_design_u(flow):
    """Readings made with the effectiveness-NTU model, analysed with LMTD/F, must give back the same U."""
    p = {**HX, "flow": flow}
    r = m.analyze_hx(m.demo_hx(p, days=40, noise=0), p)
    assert (r["error"] == "").all()
    assert r["u"].iloc[0] == pytest.approx(p["u_clean"], rel=1e-3)
    assert r["u_loss_pct"].iloc[-1] == pytest.approx(35.0, abs=0.05)
    assert r["mismatch_pct"].max() < 0.05
    assert r["shortfall_pct"].iloc[0] == pytest.approx(0.0, abs=0.1)

def test_effectiveness_limits():
    assert m.effectiveness("counter", 1.0, 1.0) == pytest.approx(0.5)            # Cr = 1: NTU/(1+NTU)
    assert m.effectiveness("parallel", 50, 1.0) == pytest.approx(0.5, rel=1e-6)  # parallel flow limit (1/(1+Cr))
    assert m.effectiveness("counter", 50, 0.0) == pytest.approx(1.0, abs=1e-9)   # Cr = 0 -> boiling/condensing limit

def test_fouling_scenario_alerts_in_order():
    r = m.analyze_hx(m.demo_hx(HX), HX)
    assert m.hx_status(r)[0] == "critical"
    a = {x["severity"]: x["first_seen"] for x in m.alerts_hx(r) if x["severity"] in ("warning", "critical")}
    assert a["warning"] < a["critical"]

def test_clean_scenario_is_healthy_with_no_alerts():
    r = m.analyze_hx(m.demo_hx(HX, scenario="clean"), HX)
    assert m.hx_status(r)[0] == "ok" and m.alerts_hx(r) == []

def test_bad_hx_row_is_flagged_not_crashing():
    d = m.demo_hx(HX, days=5, noise=0)
    d.loc[2, "t_cold_out_c"] = 200.0    # impossible: hotter than hot inlet
    r = m.analyze_hx(d, HX)
    assert (r["error"] != "").sum() == 1 and any(a["rule"] == "Readings skipped" for a in m.alerts_hx(r))

@pytest.mark.parametrize("scenario,status", [("healthy", "healthy"), ("throttled", "system_resistance"), ("worn", "pump_degraded")])
@pytest.mark.parametrize("seed", [1, 2, 3, 7])
def test_pump_scenarios_are_diagnosed(scenario, status, seed):
    r = m.analyze_pump(m.demo_pump(PUMP, scenario, seed=seed), PUMP)
    assert r["status"].iloc[-1] == status
    if scenario == "healthy":
        assert m.alerts_pump(r) == [] and m.pump_status(r)[0] == "ok"
    else:
        assert m.pump_status(r)[0] == "critical"

def test_single_noisy_pump_reading_is_not_an_alert():
    d = m.demo_pump(PUMP, "healthy", days=20)
    d.loc[10, "head_m"] *= 0.8
    assert m.alerts_pump(m.analyze_pump(d, PUMP)) == []

def test_csv_templates_parse():
    for kind in ("heat_exchanger", "pump"):
        df, dropped = m.parse_csv(m.template_csv(kind), kind)
        assert len(df) == 2 and dropped == 0

def test_csv_column_names_are_forgiving():
    text = "Timestamp, Flow M3 H ,Head_m\n2026-10-01,290,17.9\n"
    df, _ = m.parse_csv(text, "pump")
    assert df["flow_m3_h"].iloc[0] == 290

def test_csv_missing_column_and_bad_rows():
    with pytest.raises(InputError):
        m.parse_csv("timestamp,flow_m3_h\n2026-10-01,290\n", "pump")
    df, dropped = m.parse_csv("timestamp,flow_m3_h,head_m\n2026-10-01,290,17.9\nnot-a-date,1,2\n2026-10-03,abc,5\n", "pump")
    assert len(df) == 1 and dropped == 2
    with pytest.raises(InputError):
        m.parse_csv("timestamp,flow_m3_h,head_m\nx,y,z\n", "pump")

def test_db_rows_round_trip():
    df = m.demo_pump(PUMP, days=5)
    rows = m.rows_for_db(df)
    logs = [{"logged_at": ts, "data": d} for ts, d in rows]
    back = m.df_from_logs(logs, "pump")
    assert back["flow_m3_h"].tolist() == pytest.approx(df["flow_m3_h"].tolist())
