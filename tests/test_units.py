import os, re, sys
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import units
from calc_engine import monitor as mon, heat_exchanger as hx
from calc_engine.heat_exchanger import InputError

ALL = [(cat, u) for cat, d in units.UNITS.items() for u in d]


def test_known_conversions():
    c = units.to_si
    assert c("temp", "°F", 212) == pytest.approx(100) and c("temp", "°F", 32) == pytest.approx(0) and c("temp", "°F", -40) == pytest.approx(-40)
    assert c("temp", "K", 273.15) == pytest.approx(0) and c("temp", "°R", 491.67) == pytest.approx(0) and c("temp", "°R", 671.67) == pytest.approx(100)
    assert c("pressure", "atm", 1) == pytest.approx(101.325) and c("pressure", "bar", 1) == pytest.approx(100) and c("pressure", "psi", 14.696) == pytest.approx(101.325, rel=1e-4)
    assert c("pressure", "mmHg", 760) == pytest.approx(101.325, rel=1e-4) and c("pressure", "Pa", 101325) == pytest.approx(101.325)
    assert c("mass_flow", "kg/h", 3600) == pytest.approx(1) and c("mass_flow", "lb/h", 1) == pytest.approx(1.2599788e-4, rel=1e-6) and c("mass_flow", "t/h", 3.6) == pytest.approx(1)
    assert c("vol_flow", "L/s", 1) == pytest.approx(3.6) and c("vol_flow", "gpm (US)", 100) == pytest.approx(22.71247, rel=1e-6) and c("vol_flow", "m³/s", 1) == pytest.approx(3600)
    assert c("cp", "BTU/lb·°F", 1) == pytest.approx(4.1868) and c("cp", "J/kg·K", 4180) == pytest.approx(4.18)
    assert c("power", "BTU/h", 3412.14) == pytest.approx(1, rel=1e-4) and c("power", "hp", 1) == pytest.approx(0.7457, rel=1e-4) and c("power", "MW", 1.2) == pytest.approx(1200)
    assert c("area", "ft²", 1) == pytest.approx(0.09290304) and c("area", "cm²", 10000) == pytest.approx(1)
    assert c("diameter", "in", 4) == pytest.approx(101.6) and c("length", "ft", 100) == pytest.approx(30.48) and c("head", "ft", 10) == pytest.approx(3.048)
    assert c("density", "g/cm³", 0.87) == pytest.approx(870) and c("viscosity", "Pa·s", 0.2) == pytest.approx(200) and c("viscosity", "P (poise)", 1) == pytest.approx(100)
    assert c("velocity", "km/h", 36) == pytest.approx(10) and c("velocity", "ft/s", 10) == pytest.approx(3.048) and c("roughness", "µm", 45) == pytest.approx(0.045)

def test_derived_units_agree_with_their_definitions():
    cal, btu, lb, ft, gal = 4186.8, 1055.056, 0.45359237, 0.3048, 0.003785411784
    assert units.to_si("u_coeff", "kcal/h·m²·°C", 1) == pytest.approx(cal / 3600, rel=1e-4)                       # W/m2K
    assert units.to_si("u_coeff", "BTU/h·ft²·°F", 1) == pytest.approx(btu / 3600 / (ft * ft * 5 / 9), rel=1e-5)
    assert units.to_si("viscosity", "lb/ft·s", 1) == pytest.approx(lb / ft * 1000, rel=1e-6)                      # mPa.s
    assert units.to_si("density", "lb/ft³", 1) == pytest.approx(lb / ft ** 3, rel=1e-6)
    assert units.to_si("density", "lb/gal (US)", 1) == pytest.approx(lb / gal, rel=1e-6)
    assert units.to_si("vol_flow", "ft³/s", 1) == pytest.approx(ft ** 3 * 3600, rel=1e-6)
    assert units.to_si("vol_flow", "bbl/day", 1) == pytest.approx(0.158987295 / 24, rel=1e-6)
    assert units.to_si("power", "kcal/h", 1) == pytest.approx(cal / 3600 / 1000, rel=1e-4)
    assert units.to_si("power", "TR", 1) == pytest.approx(12000 * btu / 3600 / 1000, rel=1e-4)
    assert units.to_si("mass_flow", "lb/s", 1) == pytest.approx(lb)

@pytest.mark.parametrize("cat", list(units.UNITS))
def test_each_category_starts_with_the_engine_unit(cat):
    names = units.unit_names(cat)
    assert units.UNITS[cat][names[0]] == (1.0, 0.0) and units.si_unit(cat) == names[0] and len(set(names)) == len(names) >= 3

@pytest.mark.parametrize("cat,unit", ALL)
def test_round_trip_and_ordering(cat, unit):
    for x in (0.5, 1.0, 37.25, 1234.5):
        assert units.from_si(cat, unit, units.to_si(cat, unit, x)) == pytest.approx(x, rel=1e-12)
    assert units.to_si(cat, unit, 1.0) < units.to_si(cat, unit, 2.0)                 # bigger number, bigger quantity
    assert units.convert(cat, 7.0, unit, unit) == pytest.approx(7.0)

def test_convert_between_two_units_and_series_and_errors():
    assert units.convert("temp", 100, "°C", "°F") == pytest.approx(212) and units.convert("pressure", 1, "atm", "psi") == pytest.approx(14.696, rel=1e-4)
    assert units.convert("diameter", 4, "in", "mm") == pytest.approx(101.6)
    s = pd.Series([32.0, 212.0])
    assert units.to_si_series("temp", "°F", s).tolist() == pytest.approx([0.0, 100.0])
    with pytest.raises(ValueError):
        units.to_si("temp", "degrees", 1)
    with pytest.raises(KeyError):
        units.unit_names("nope")

def test_absolute_zero_is_rejected_with_a_unit_hint():
    for bad in ((100, 60, 20, -300), (-273.15, -280, 20, 50)):
        with pytest.raises(InputError, match="absolute zero"):
            hx._check_temps(*bad)
    hx._check_temps(100, 60, -50, 20)       # cold temperatures below 0 C are fine

# ---------------------------------------------------------------- CSV import in other units
def test_pump_csv_in_litres_per_second_feet_and_fahrenheit():
    df = pd.DataFrame({"timestamp": pd.to_datetime(["2026-10-01"]), "flow_m3_h": [100.0], "head_m": [60.0], "water_temp_c": [86.0]})
    out = mon.convert_units(df, "pump", {"vol_flow": "L/s", "head": "ft", "temp": "°F"})
    assert out["flow_m3_h"].iloc[0] == pytest.approx(360.0) and out["head_m"].iloc[0] == pytest.approx(18.288) and out["water_temp_c"].iloc[0] == pytest.approx(30.0)
    assert df["flow_m3_h"].iloc[0] == 100.0                                       # the original is not changed

def test_hx_csv_in_plant_units_gives_the_same_analysis():
    params = {"area_m2": 150.0, "u_clean": 1200.0, "flow": "counter"}
    si = mon.demo_hx(params, days=5, noise=0)
    plant = si.copy()
    for c in ("t_hot_in_c", "t_hot_out_c", "t_cold_in_c", "t_cold_out_c"):
        plant[c] = si[c] * 9 / 5 + 32
    for c in ("m_hot_kg_s", "m_cold_kg_s"):
        plant[c] = si[c] * 3600
    for c in ("cp_hot_kj_kgk", "cp_cold_kj_kgk"):
        plant[c] = si[c] / 4.1868
    back = mon.convert_units(plant, "heat_exchanger", {"temp": "°F", "mass_flow": "kg/h", "cp": "BTU/lb·°F"})
    a, b = mon.analyze_hx(si, params), mon.analyze_hx(back, params)
    assert (b["error"] == "").all() and b["u"].tolist() == pytest.approx(a["u"].tolist(), rel=1e-9)

def test_no_conversion_when_units_match_or_missing():
    df = mon.demo_pump({"d_mm": 200, "length_m": 200, "material": "Commercial steel (0.045 mm)", "sum_k": 8, "static_m": 10, "curve": [[0, 30], [200, 25], [300, 17]], "eta_pct": 70}, days=3)
    assert mon.convert_units(df, "pump", {}).equals(df) and mon.convert_units(df, "pump", {"temp": "°C", "vol_flow": "m³/h", "head": "m"}).equals(df)

# ---------------------------------------------------------------- the dropdowns on the pages
from streamlit.testing.v1 import AppTest
ROOT = os.path.dirname(os.path.dirname(__file__))

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "u.db"))

def _guest(page):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.button(key="do_guest").click().run()
    return at.switch_page(page).run()

def _n(text):
    return float(re.search(r"-?[\d,]*\.?\d+", text).group(0).replace(",", ""))

def _metrics(at):
    return {m.label: _n(m.value) for m in at.metric}

def test_heat_exchanger_solver_same_answer_in_other_units(temp_db):
    at = _guest("views/solver.py")
    at.selectbox(key="sv_arr").select("shell_1_2").run()
    spec = [("sv_thi", "temp", "°F", 95), ("sv_tho", "temp", "°F", 60), ("sv_tci", "temp", "°F", 25), ("sv_tco", "temp", "°F", 45),
            ("sv_mh", "mass_flow", "kg/h", 12), ("sv_cph", "cp", "kcal/kg·°C", 3.6), ("sv_cpc", "cp", "BTU/lb·°F", 4.18), ("sv_a", "area", "ft²", 80)]
    for key, cat, unit, si_value in spec:
        at.selectbox(key=f"{key}_u").select(unit)
        at.number_input(key=key).set_value(units.from_si(cat, unit, si_value))
    at.number_input(key="sv_f").set_value(0.92)
    at.run()
    assert not at.exception
    m = _metrics(at)
    assert m["Heat duty Q"] == pytest.approx(1512.0, rel=1e-3) and m["Overall U"] == pytest.approx(488.5, rel=2e-3)
    assert m["Cold flow (found)"] == pytest.approx(18.086, rel=1e-3) and m["Corrected LMTD"] == pytest.approx(38.69, rel=1e-3)
    assert any("= " in c.value and "kg/s" in c.value for c in at.caption)         # the converted value is shown

def test_wrong_temperature_unit_gets_a_helpful_error(temp_db):
    at = _guest("views/solver.py")
    at.number_input(key="sv_tci").set_value(-300.0).run()
    assert not at.exception and any("absolute zero" in e.value for e in at.error)

def test_pipe_solver_diameter_in_inches_and_velocity_in_feet_per_second(temp_db):
    at = _guest("views/pipe_solver.py")
    base = _metrics(at)
    at.selectbox(key="pp_d_u").select("in")
    at.number_input(key="pp_d").set_value(units.from_si("diameter", "in", 100.0))
    at.run()
    assert not at.exception and _metrics(at)["Velocity"] == pytest.approx(base["Velocity"], rel=1e-4)
    at.radio(key="pp_given").set_value("Velocity").run()
    at.selectbox(key="pp_vel_u").select("ft/s")
    at.number_input(key="pp_vel").set_value(units.from_si("velocity", "ft/s", 2.0))
    at.run()
    assert not at.exception and _metrics(at)["Velocity"] == pytest.approx(2.0, rel=1e-4)
    at.selectbox(key="pp_vel_u").select("ft/s")
    assert any("Flow = v × A" in c.value for c in at.caption)

def test_pipe_solver_viscosity_and_density_units(temp_db):
    at = _guest("views/pipe_solver.py")
    at.radio(key="pp_fluid").set_value("Other liquid (enter density and viscosity)").run()
    base = _metrics(at)
    at.selectbox(key="pp_rho_u").select("g/cm³"); at.number_input(key="pp_rho").set_value(0.87)
    at.selectbox(key="pp_mu_u").select("Pa·s"); at.number_input(key="pp_mu").set_value(0.01)
    at.run()
    assert not at.exception and _metrics(at)["Reynolds number"] == pytest.approx(base["Reynolds number"], rel=1e-9)

def test_pump_page_flow_in_litres_per_second(temp_db):
    at = _guest("views/pump_pipeline.py")
    base = _metrics(at)
    at.selectbox(key="p_q1_u").select("L/s"); at.number_input(key="p_q1").set_value(200 / 3.6)
    at.selectbox(key="p_q2_u").select("L/s"); at.number_input(key="p_q2").set_value(300 / 3.6)
    at.selectbox(key="p_h1_u").select("ft"); at.number_input(key="p_h1").set_value(25 / 0.3048)
    at.run()
    assert not at.exception and _metrics(at)["Operating flow"] == pytest.approx(base["Operating flow"], rel=1e-9)

def test_heat_exchanger_calculator_page_units(temp_db):
    at = _guest("views/heat_exchanger.py")
    base = _metrics(at)
    at.selectbox(key="thi_u").select("°F"); at.number_input(key="thi").set_value(212.0)
    at.selectbox(key="mh_u").select("kg/min"); at.number_input(key="mh").set_value(90.0)
    at.run()
    assert not at.exception and base["Heat duty Q"] == pytest.approx(250.8, rel=1e-3)
    assert _metrics(at)["Heat duty Q"] == pytest.approx(250.8, rel=1e-3)        # 212 F = 100 C and 90 kg/min = 1.5 kg/s: same answer

def test_equipment_form_stores_si_units_and_rejects_zero(temp_db):
    from core import db
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.text_input(key="reg_name").input("U"); at.text_input(key="reg_email").input("u@plant.pk"); at.text_input(key="reg_pw").input("secret1")
    at.button(key="do_register").click().run()
    at.switch_page("views/equipment.py").run()
    at.selectbox(key="eq_tmpl").select("Cooling-water pump loop (example)").run()
    k = "Cooling-water pump loop (example)_Pump & pipeline"
    at.selectbox(key=f"eq_d_{k}_u").select("in"); at.number_input(key=f"eq_d_{k}").set_value(200 / 25.4)
    at.selectbox(key=f"eq_q1_{k}_u").select("L/s"); at.number_input(key=f"eq_q1_{k}").set_value(200 / 3.6)
    at.button(key="eq_save").click().run()
    assert not at.exception
    p = db.list_equipment(at.session_state["user"]["id"])[0]["params"]
    assert p["d_mm"] == pytest.approx(200.0) and p["curve"][1][0] == pytest.approx(200.0)
    at.selectbox(key="eq_tmpl").select("Sugar mill juice heater (example)").run()
    k2 = "Sugar mill juice heater (example)_Heat exchanger"
    at.number_input(key=f"eq_a_{k2}").set_value(0.0)
    at.button(key="eq_save").click().run()
    assert any("greater than zero" in e.value for e in at.error)
    assert len(db.list_equipment(at.session_state["user"]["id"])) == 1
