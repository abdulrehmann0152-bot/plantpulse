"""End-to-end smoke tests: drive the real app with Streamlit's test runner."""
import os, sys
import pytest
from streamlit.testing.v1 import AppTest
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "smoke.db"))


def _app():
    return AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60)

def test_shows_login_first():
    at = _app().run()
    assert not at.exception
    assert any(t.key == "login_email" for t in at.text_input)

def test_register_then_home_then_logout():
    at = _app().run()
    at.text_input(key="reg_name").input("Abdul")
    at.text_input(key="reg_email").input("abdul@uet.edu.pk")
    at.text_input(key="reg_pw").input("secret12")
    at.button(key="do_register").click().run()
    assert not at.exception
    assert at.session_state["user"]["name"] == "Abdul" and at.session_state["user"]["role"] == "student"
    at.button(key="logout").click().run()
    assert "user" not in at.session_state

def test_wrong_password_shows_error():
    at = _app().run()
    at.text_input(key="login_email").input("nobody@uet.edu.pk")
    at.text_input(key="login_pw").input("badpass")
    at.button(key="do_login").click().run()
    assert len(at.error) == 1 and "user" not in at.session_state

def test_guest_can_use_calculators():
    at = _app().run()
    at.button(key="do_guest").click().run()
    assert at.session_state["user"]["id"] is None
    for page in ["views/heat_exchanger.py", "views/pump_pipeline.py", "views/equipment.py"]:
        at.switch_page(page).run()
        assert not at.exception, page

def test_engineer_saves_and_sees_equipment():
    at = _app().run()
    at.text_input(key="reg_name").input("Engr Khan")
    at.text_input(key="reg_email").input("khan@plant.pk")
    at.text_input(key="reg_pw").input("secret12")
    at.radio(key="reg_role").set_value("Plant engineer")
    at.button(key="do_register").click().run()
    assert at.session_state["user"]["role"] == "engineer"
    at.switch_page("views/equipment.py").run()
    at.selectbox(key="eq_tmpl").select("Sugar mill juice heater (example)").run()
    at.button(key="eq_save").click().run()
    assert not at.exception
    from core import db
    items = db.list_equipment(at.session_state["user"]["id"])
    assert [e["tag"] for e in items] == ["JH-01"] and items[0]["params"]["flow"] == "shell_1_2"


def _login_with_equipment(template):
    at = _app().run()
    at.text_input(key="reg_name").input("Engr Test")
    at.text_input(key="reg_email").input("test@plant.pk")
    at.text_input(key="reg_pw").input("secret12")
    at.radio(key="reg_role").set_value("Plant engineer")
    at.button(key="do_register").click().run()
    at.switch_page("views/equipment.py").run()
    at.selectbox(key="eq_tmpl").select(template).run()
    at.button(key="eq_save").click().run()
    return at

@pytest.mark.parametrize("template,scenario,expect", [
    ("Sugar mill juice heater (example)", "Fouling builds up over 60 days", "ACTION NEEDED"),
    ("Cooling-water pump loop (example)", "Worn pump", "ACTION NEEDED"),
    ("Cooling-water pump loop (example)", "Healthy pump", "HEALTHY")])
def test_monitor_demo_data_end_to_end(template, scenario, expect):
    at = _login_with_equipment(template)
    at.switch_page("views/monitor.py").run()
    assert not at.exception
    at.selectbox(key="mon_scn").select(scenario).run()
    at.button(key="mon_demo").click().run()
    assert not at.exception
    at.switch_page("views/monitor.py").run()
    assert not at.exception
    banner = " ".join(x.value for x in list(at.success) + list(at.error) + list(at.warning))
    assert expect in banner
    assert any("synthetic demo" in i.value for i in at.info)
    assert any(getattr(el, "type", "") == "download_button" for el in at.main)
    at.button(key="mon_delete").click().run()
    assert not at.exception

def test_monitor_for_guest_is_polite():
    at = _app().run()
    at.button(key="do_guest").click().run()
    at.switch_page("views/monitor.py").run()
    assert not at.exception and len(at.info) >= 1


def test_tutor_page_for_guest_concepts_and_practice():
    from calc_engine import tutor
    at = _app().run()
    at.button(key="do_guest").click().run()
    at.switch_page("views/tutor.py").run()
    assert not at.exception
    c = next(x for x in tutor.CONCEPTS if x["id"] == "heat_duty")
    at.radio(key="chk_radio_heat_duty").set_value(c["check"]["options"][c["check"]["answer"]])
    at.button(key="chk_btn_heat_duty").click().run()
    assert any("Correct" in s.value for s in at.success)
    at.radio(key="chk_radio_lmtd").set_value("Parallel flow")
    at.button(key="chk_btn_lmtd").click().run()
    assert any("Not quite" in e.value for e in at.error)
    # practice: right answers accepted, wrong answer rejected
    prob = tutor.make_problem("foul_rf", 1)
    at.selectbox(key="pr_kind").select("Fouling resistance").run()
    for a in prob["answers"]:
        at.text_input(key=f"pr_foul_rf_1_{a['key']}").input(str(a["value"]))
    at.button(key="pr_check").click().run()
    assert not at.exception and len(at.success) >= 2
    at.button(key="pr_new").click().run()
    assert at.session_state["pr_seed"] == 2 and not at.exception

def test_tutor_explain_tab_with_demo_data():
    at = _login_with_equipment("Sugar mill juice heater (example)")
    at.switch_page("views/monitor.py").run()
    at.button(key="mon_demo").click().run()
    at.switch_page("views/tutor.py").run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "What the numbers say" in text and "gradually" in text


@pytest.mark.parametrize("label", ["Heat exchanger: LMTD", "Heat exchanger: duty and U value", "Fouling resistance", "Pipe pressure drop", "Pump power"])
def test_every_practice_problem_type_renders(label):
    at = _app().run()
    at.button(key="do_guest").click().run()
    at.switch_page("views/tutor.py").run()
    at.selectbox(key="pr_kind").select(label).run()
    assert not at.exception
    at.button(key="pr_check").click().run()      # empty answers -> polite warnings, no crash
    assert not at.exception and len(at.warning) >= 1


def test_problem_solver_page_default_and_problem_2b():
    at = _app().run()
    at.button(key="do_guest").click().run()
    at.switch_page("views/solver.py").run()
    assert not at.exception
    labels = {m.label: m.value for m in at.metric}
    assert labels["LMTD, counter-flow"] == "99.67 K" and labels["LMTD, parallel flow"] == "91.02 K"
    at.selectbox(key="sv_arr").select("shell_1_2").run()     # Problem 1: R, P, F and corrected LMTD
    labels = {m.label: m.value for m in at.metric}
    assert labels["R"] == "1.5000" and labels["P"] == "0.2667" and labels["Correction factor F"] == "0.9583" and labels["Corrected LMTD"] == "95.51 K"
    # Problem 2b from the student's numericals
    for key, val in dict(sv_thi=95.0, sv_tho=60.0, sv_tci=25.0, sv_tco=45.0, sv_mh=12.0, sv_cph=3.6, sv_cpc=4.18, sv_a=80.0, sv_f=0.92).items():
        at.number_input(key=key).set_value(val)
    at.run()
    labels = {m.label: m.value for m in at.metric}
    assert not at.exception
    assert labels["Heat duty Q"] == "1,512.0 kW" and labels["Cold flow (found)"] == "18.086 kg/s"
    assert labels["Overall U"] == "488.5 W/m²K" and labels["Corrected LMTD"] == "38.69 K"
    assert any("differs" in w.value for w in at.warning)

def test_problem_solver_shows_friendly_error_for_bad_data():
    at = _app().run()
    at.button(key="do_guest").click().run()
    at.switch_page("views/solver.py").run()
    at.number_input(key="sv_tco").set_value(200.0).run()      # cold outlet above hot inlet: impossible
    assert not at.exception and len(at.error) == 1


def test_pipe_solver_page_given_flow_and_given_head():
    at = _app().run()
    at.button(key="do_guest").click().run()
    at.switch_page("views/pipe_solver.py").run()
    assert not at.exception
    labels = {m.label: m.value for m in at.metric}
    assert labels["Velocity"].endswith("m/s") and "Total head required" in labels and "Hydraulic power" in labels
    at.number_input(key="pp_eta").set_value(70.0).run()
    assert "Shaft power" in {m.label for m in at.metric}
    at.radio(key="pp_mode").set_value("The flow for a given available head").run()
    assert not at.exception and "Flow found" in {m.label for m in at.metric}
    at.radio(key="pp_fluid").set_value("Other liquid (enter density and viscosity)").run()
    at.number_input(key="pp_mu").set_value(200.0).run()           # thick oil, laminar
    assert not at.exception and any("Flow found" == m.label for m in at.metric)
    at.selectbox(key="pp_mat").select("Custom (enter roughness)").run()
    assert not at.exception

def test_pipe_solver_friendly_error():
    at = _app().run()
    at.button(key="do_guest").click().run()
    at.switch_page("views/pipe_solver.py").run()
    at.number_input(key="pp_static").set_value(-500.0).run()       # gravity: no pump head, a warning but no crash
    assert not at.exception and any("gravity" in w.value for w in at.warning)

def test_heat_exchanger_solver_page_shows_the_animation():
    at = _app().run()
    at.button(key="do_guest").click().run()
    at.switch_page("views/solver.py").run()
    assert not at.exception
    assert any("How the fluids flow" in h.value for h in at.subheader)
    at.selectbox(key="sv_arr").select("parallel").run()
    assert not at.exception and any("How the fluids flow" in h.value for h in at.subheader)


def _register_engineer(email="v@plant.pk"):
    at = _app().run()
    at.text_input(key="reg_name").input("Abdul")
    at.text_input(key="reg_email").input(email)
    at.text_input(key="reg_pw").input("secret12")
    at.button(key="do_register").click().run()
    return at

def test_validation_log_end_to_end():
    at = _register_engineer()
    # solve problem 2b, then copy a result into the log
    at.switch_page("views/solver.py").run()
    at.selectbox(key="sv_arr").select("shell_1_2").run()
    for key, val in dict(sv_thi=95.0, sv_tho=60.0, sv_tci=25.0, sv_tco=45.0, sv_mh=12.0, sv_cph=3.6, sv_cpc=4.18, sv_a=80.0, sv_f=0.92).items():
        at.number_input(key=key).set_value(val)
    at.run()
    at.switch_page("views/validation.py").run()
    assert not at.exception
    at.selectbox(key="vl_pick").select("Overall U").run()
    at.button(key="vl_use").click().run()
    assert at.text_input(key="vl_app").value.startswith("488.4")
    at.text_input(key="vl_source").input("Problem sheet, Problem 2")
    at.text_input(key="vl_quantity").input("Overall U")
    at.text_input(key="vl_unit").input("W/m2K")
    at.text_input(key="vl_ref").input("488")
    at.button(key="vl_save").click().run()
    assert not at.exception
    labels = {m.label: m.value for m in at.metric}
    assert labels["Entries"] == "1" and labels["Match (within 2%)"] == "1 of 1"
    assert any(getattr(el, "type", "") == "download_button" for el in at.main)
    # a bad answer is rejected politely, a far-off one is flagged
    at.text_input(key="vl_source").input("Book p.9"); at.text_input(key="vl_quantity").input("LMTD")
    at.text_input(key="vl_ref").input("abc"); at.text_input(key="vl_app").input("1")
    at.button(key="vl_save").click().run()
    assert len(at.error) == 1
    at.text_input(key="vl_source").input("Book p.9"); at.text_input(key="vl_quantity").input("LMTD")
    at.text_input(key="vl_ref").input("50"); at.text_input(key="vl_app").input("60")
    at.button(key="vl_save").click().run()
    assert any("more than 5%" in w.value for w in at.warning)
    at.button(key="vl_del").click().run()
    assert not at.exception

def test_validation_page_for_guest():
    at = _app().run()
    at.button(key="do_guest").click().run()
    at.switch_page("views/validation.py").run()
    assert not at.exception and len(at.info) >= 1

def test_home_lists_every_module():
    at = _register_engineer("home@plant.pk")
    at.switch_page("views/home.py").run()
    assert not at.exception
