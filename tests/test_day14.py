import json, os, re, sqlite3, sys
from datetime import date, timedelta
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from calc_engine import monitor as mon, tutor
from calc_engine.heat_exchanger import InputError
from core import chart_notes, db, importer, validation as val
from core.report import build_report
from core.validation_report import build_certificate

ROOT = os.path.dirname(os.path.dirname(__file__))
HX = {"area_m2": 150.0, "u_clean": 1200.0, "flow": "shell_1_2"}
PUMP = {"d_mm": 200.0, "length_m": 200.0, "material": "Commercial steel (0.045 mm)", "sum_k": 8.0, "static_m": 10.0, "curve": [[0.0, 30.0], [200.0, 25.0], [300.0, 17.0]], "eta_pct": 70.0}
USER = {"name": "Abdul Rehman", "role": "student"}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d14.db"))
    db.init_db()


def _user(email="a@plant.pk"):
    return db.create_user("Ali", email, "secret12", "engineer")


def _pages(pdf):
    return pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")


def _text(pdf):
    """The text of an uncompressed PDF as a reader sees it: every shown string, with PDF escapes removed, in one line."""
    shown = re.findall(rb"\((.*?)\) Tj", pdf, re.S)
    return " ".join(s.replace(rb"\(", b"(").replace(rb"\)", b")").replace(rb"\\", b"\\").decode("latin-1") for s in shown)


def _fouled():
    return mon.analyze_hx(mon.demo_hx(HX), HX)                    # U falls to about 65% of clean over 60 days


# ====================================================================== configurable thresholds: engine
def test_defaults_are_unchanged():
    r = _fouled()
    assert mon.hx_status(r) == mon.hx_status(r, 10.0, 25.0) and mon.alerts_hx(r) == mon.alerts_hx(r, 10.0, 25.0)
    assert mon.hx_status(r)[0] == "critical"

@pytest.mark.parametrize("warn,crit,expected", [(5, 15, "critical"), (10, 25, "critical"), (20, 50, "warning"), (30, 34, "critical"), (30, 60, "warning"), (40, 60, "ok"), (36, 90, "ok")])
def test_status_follows_the_users_own_levels(warn, crit, expected):
    status, text = mon.hx_status(_fouled(), warn, crit)
    assert status == expected
    if expected == "critical":
        assert f"alarm level of {crit:g}%" in text
    elif expected == "warning":
        assert f"warning level of {warn:g}%" in text
    else:
        assert f"within {warn:g}% of clean" in text

def test_alerts_use_the_users_levels_and_fire_earlier_when_the_level_is_lower():
    r = _fouled()
    low, default = mon.alerts_hx(r, 5, 15), mon.alerts_hx(r)
    first = lambda alerts, sev: next(a["first_seen"] for a in alerts if a["severity"] == sev)
    assert any(a["rule"] == "U more than 5% below clean" for a in low) and any(a["rule"] == "U more than 15% below clean" for a in low)
    assert first(low, "warning") < first(default, "warning") and first(low, "critical") < first(default, "critical") and first(low, "warning") < first(low, "critical")
    assert not any(a["severity"] in ("warning", "critical") for a in mon.alerts_hx(r, 50, 80))

@pytest.mark.parametrize("warn,crit", [(0, 25), (-5, 25), (25, 25), (30, 20), (10, 96), (10, 100), (None, 25), ("10", 25), (float("nan"), 25)])
def test_bad_levels_are_rejected(warn, crit):
    with pytest.raises(InputError):
        mon.check_thresholds(warn, crit)
    with pytest.raises(InputError):
        mon.hx_status(_fouled(), warn, crit)
    with pytest.raises(InputError):
        mon.alerts_hx(_fouled(), warn, crit)

def test_good_levels_are_accepted():
    for warn, crit in ((0.5, 1), (7.5, 22.5), (10, 95), (94, 95)):
        mon.check_thresholds(warn, crit)

def test_the_tutor_explanation_follows_the_levels():
    r = _fouled()
    custom = " ".join(tutor.explain_hx(r, HX, 5, 15))
    assert "your 15% alarm level" in custom and "25%" not in custom
    mid = " ".join(tutor.explain_hx(r, HX, 20, 50))
    assert "your 20% warning level" in mid and "before it reaches 50%" in mid
    assert "your 25% alarm level" in " ".join(tutor.explain_hx(r, HX))

# ====================================================================== configurable thresholds: storage
def test_settings_default_save_replace_and_reset():
    u = _user(); eid = db.add_equipment(u["id"], "heat_exchanger", "JH-01", "", HX)
    assert db.get_alert_settings(u["id"], eid) == {"u_warn_pct": 10.0, "u_crit_pct": 25.0, "custom": False}
    db.set_alert_settings(u["id"], eid, 7.5, 20)
    assert db.get_alert_settings(u["id"], eid) == {"u_warn_pct": 7.5, "u_crit_pct": 20.0, "custom": True}
    db.set_alert_settings(u["id"], eid, 12, 30)                                   # saving again replaces, it does not add
    assert db.get_alert_settings(u["id"], eid)["u_warn_pct"] == 12.0
    assert db._run("SELECT COUNT(*) AS n FROM alert_settings")[0][0]["n"] == 1
    db.reset_alert_settings(u["id"], eid)
    assert db.get_alert_settings(u["id"], eid)["custom"] is False

def test_settings_belong_to_one_piece_of_equipment_and_one_owner():
    a, b = _user("a@b.com"), _user("c@d.com")
    e1, e2 = db.add_equipment(a["id"], "heat_exchanger", "JH-01", "", HX), db.add_equipment(a["id"], "heat_exchanger", "JH-02", "", HX)
    eb = db.add_equipment(b["id"], "heat_exchanger", "JH-01", "", HX)
    db.set_alert_settings(a["id"], e1, 5, 15)
    assert db.get_alert_settings(a["id"], e2)["custom"] is False                   # another exchanger of the same owner keeps the defaults
    assert db.get_alert_settings(b["id"], e1)["custom"] is False                   # another user cannot read it
    with pytest.raises(db.DBError, match="not found"):
        db.set_alert_settings(b["id"], e1, 1, 2)
    db.reset_alert_settings(b["id"], e1)                                           # nor reset it
    assert db.get_alert_settings(a["id"], e1)["u_warn_pct"] == 5.0
    db.set_alert_settings(b["id"], eb, 8, 18)
    assert db.get_alert_settings(a["id"], e1)["u_warn_pct"] == 5.0 and db.get_alert_settings(b["id"], eb)["u_warn_pct"] == 8.0

def test_settings_validation_and_cascade():
    u = _user(); eid = db.add_equipment(u["id"], "heat_exchanger", "JH-01", "", HX)
    for warn, crit in ((0, 25), (25, 25), (30, 20), (10, 96), (True, 25), ("a", 25), (float("nan"), 30)):
        with pytest.raises(db.DBError):
            db.set_alert_settings(u["id"], eid, warn, crit)
    assert db.get_alert_settings(u["id"], eid)["custom"] is False
    db.set_alert_settings(u["id"], eid, 10, 25); db.delete_equipment(u["id"], eid)
    assert db._run("SELECT COUNT(*) AS n FROM alert_settings")[0][0]["n"] == 0

# ====================================================================== report: thresholds and notes
def _report(**kw):
    eq = {"tag": "JH-01", "location": "Juice station", "params": HX}
    r = _fouled(); s, t = mon.hx_status(r, *kw.get("thresholds", (10, 25)))
    return build_report("heat_exchanger", eq, r, mon.alerts_hx(r, *kw.get("thresholds", (10, 25))), s, t, USER, compress=False, **kw)

def test_report_draws_and_describes_the_users_levels():
    custom = _text(_report(thresholds=(5, 15)))
    assert "5% loss (watch)" in custom and "15% loss (act)" in custom and "10% loss (watch)" not in custom and "25% loss (act)" not in custom
    assert "5% (watch) or 15% (act) below clean" in custom
    default = _text(_report())
    assert "10% loss (watch)" in default and "25% loss (act)" in default and "10% (watch) or 25% (act) below clean" in default

def test_report_lists_the_notes_on_the_data():
    events = [{"note_date": "2026-09-20", "note": "After chemical cleaning"}, {"note_date": "2026-09-28", "note": "Flow meter recalibrated"}]
    pdf = _report(events=events)
    text = _text(pdf)
    assert "Notes on the data" in text and "2026-09-20: After chemical cleaning" in text and "Flow meter recalibrated" in text
    assert "Notes on the data" not in _text(_report()) and _pages(pdf) in (2, 3)

# ====================================================================== notes on charts
def _n(date_text, text):
    return {"note_date": date_text, "note": text}

def test_only_notes_inside_the_data_range_become_markers_oldest_first():
    notes = [_n("2026-09-25", "After chemical cleaning"), _n("2026-08-01", "too early"), _n("2026-09-01", "Start"), _n("2026-12-01", "too late")]
    m = chart_notes.event_markers(notes, pd.Timestamp("2026-09-01 08:00"), pd.Timestamp("2026-09-30 17:00"))
    assert [x["text"] for x in m] == ["Start", "After chemical cleaning"] and [x["date"] for x in m] == [pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-25")]
    assert chart_notes.event_markers(notes, "2026-09-30", "2026-09-30") == [] and chart_notes.event_markers([], "2026-09-01", "2026-09-30") == []
    assert len(chart_notes.event_markers(notes, "2026-09-25", "2026-09-25")) == 1                            # both ends of the range are included

def test_markers_are_short_use_the_first_line_and_are_limited():
    m = chart_notes.event_markers([_n("2026-09-10", "Cleaned the tubes with the citric acid solution and rinsed twice\nsecond line")], "2026-09-01", "2026-09-30")
    assert len(m[0]["text"]) <= 28 and m[0]["text"].endswith("…") and "second" not in m[0]["text"]
    many = [_n(f"2026-09-{d:02d}", f"note {d}") for d in range(1, 21)]
    kept = chart_notes.event_markers(many, "2026-09-01", "2026-09-30", limit=8)
    assert len(kept) == 8 and kept[-1]["text"] == "note 20" and kept[0]["text"] == "note 13"

# ====================================================================== tagging an imported dataset
def test_import_with_a_note_saves_it_in_the_history_with_the_import_details():
    u = _user(); eid = db.add_equipment(u["id"], "heat_exchanger", "JH-01", "", HX)
    df = mon.demo_hx(HX, days=10)
    n, msg = importer.save_import(u["id"], eid, df, date(2026, 9, 20), "  After chemical cleaning  ")
    assert n == 10 and "10 new reading" in msg and "note was saved" in msg and len(db.list_logs(u["id"], eid)) == 10
    note = db.list_maintenance(u["id"], eid)[0]
    first, last = df["timestamp"].min().date(), df["timestamp"].max().date()
    assert note["note_date"] == "2026-09-20" and note["note"].startswith("After chemical cleaning\n") and f"{first} to {last}" in note["note"] and "10 new reading" in note["note"]

def test_import_without_a_note_or_with_a_bad_date_still_saves_the_readings():
    u = _user(); eid = db.add_equipment(u["id"], "heat_exchanger", "JH-01", "", HX)
    df = mon.demo_hx(HX, days=5)
    n, msg = importer.save_import(u["id"], eid, df, date.today(), "   ")
    assert n == 5 and "note" not in msg.lower() and db.list_maintenance(u["id"], eid) == []
    n2, msg2 = importer.save_import(u["id"], eid, mon.demo_hx(HX, days=8), date.today() + timedelta(days=900), "Too far ahead")
    assert n2 == 3 and "the note was not" in msg2 and "future" in msg2 and db.list_maintenance(u["id"], eid) == []
    n3, _ = importer.save_import(u["id"], eid, mon.demo_hx(HX, days=8), None, "Repeated file")                  # no date given: the last reading's date is used
    assert n3 == 0 and db.list_maintenance(u["id"], eid)[0]["note_date"] == mon.demo_hx(HX, days=8)["timestamp"].max().date().isoformat()

# ====================================================================== validation certificate
def _entry(i, source="Kern, Example 6.1, p. 113", quantity="Required area", unit="m2", ref=100.0, app=101.0, problem="", notes=""):
    return {"id": i, "created_at": "2026-10-10T10:00:00", "source": source, "module": "Heat exchanger", "problem": problem, "quantity": quantity,
            "unit": unit, "reference": ref, "app_value": app, "notes": notes}

def _cert(entries, project="", **kw):
    return build_certificate(val.enrich(entries), USER, project, on=date(2026, 10, 26), compress=False, **kw)

def test_certificate_has_everything_the_supervisor_needs():
    text = _text(_cert([_entry(1, ref=4.6, app=4.62, problem="Counter-flow oil cooler", notes="F read from chart")], "Heat Transfer project"))
    for expected in ("Validation Certificate", "Application: PlantPulse", "26 Oct 2026", "Abdul Rehman", "Heat Transfer project", "Kern, Example 6.1, p. 113",
                     "Required area (m2)", "4.6", "4.62", "+0.43", "Match (within 2%)", "Counter-flow oil cooler", "F read from chart",
                     "Prepared by (signature)", "Supervisor (signature and date)", "Textbook answer", "PlantPulse answer", "Difference %"):
        assert expected in text, expected

def test_certificate_footer_is_on_every_page_and_never_overclaims():
    one = _cert([_entry(1)])
    assert _text(one).count("Verified by PlantPulse Engineering Engine") == _pages(one) == 1
    many = _cert([_entry(i, source=f"Book {i}, p. {i}") for i in range(1, 61)])
    text = _text(many)
    assert _pages(many) >= 2 and text.count("Verified by PlantPulse Engineering Engine") == _pages(many)
    assert text.count("Validation Certificate") >= _pages(many)                                # the header repeats too
    one_text = _text(one)
    assert "has not independently checked the reference answer or the source" in one_text and "typed in from the cited source" in one_text

def test_entries_outside_tolerance_are_flagged_not_confirmed():
    text = _text(_cert([_entry(1, app=101.0), _entry(2, quantity="LMTD", unit="K", ref=50.0, app=56.0)]))
    assert "OUTSIDE TOLERANCE" in text and "+12.00" in text and "Outside tolerance: 1" in text and "are not confirmed by this document" in text
    clean = _text(_cert([_entry(1), _entry(2, quantity="U", ref=488.5, app=488.49)]))
    assert "OUTSIDE TOLERANCE" not in clean and "not confirmed" not in clean and "Outside tolerance: 0" in clean

def test_certificate_edge_cases():
    assert "No entries were selected" in _text(_cert([])) and build_certificate([], USER)[:5] == b"%PDF-"
    assert "Project / course" not in _text(_cert([_entry(1)])) and "Project / course: Course X" in _text(_cert([_entry(1)], "Course X"))
    odd = build_certificate(val.enrich([_entry(1, source="Çengel – p.640 η", notes="F ≥ 0.9")]), {"name": "عبد", "role": "engineer"}, "Projet œuvre")
    assert odd[:5] == b"%PDF-"
    zero = _text(_cert([_entry(1, ref=0.0, app=0.0), _entry(2, ref=0.0, app=3.0, quantity="X")]))
    assert "n/a" in zero and "OUTSIDE TOLERANCE" in zero and "0.00" in zero

# ====================================================================== the pages
def _app():
    return AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60)

def _register(email="e@plant.pk"):
    at = _app().run()
    at.text_input(key="reg_name").input("Engr E"); at.text_input(key="reg_email").input(email); at.text_input(key="reg_pw").input("secret12")
    at.button(key="do_register").click().run()
    return at

def _downloads(at, start):
    return [d for d in at.get("download_button") if d.proto.label.startswith(start)]

def test_validation_page_certificate_defaults_to_the_entries_that_pass():
    at = _register(); uid = at.session_state["user"]["id"]
    db.add_validation(uid, "Kern p.113", "Heat exchanger", "", "Area", "m2", 100.0, 101.0)
    db.add_validation(uid, "Kern p.200", "Heat exchanger", "", "U", "W/m2K", 100.0, 104.0)
    db.add_validation(uid, "Problem sheet", "Heat exchanger", "", "LMTD", "K", 50.0, 56.0)
    ids = [e["id"] for e in db.list_validation(uid)]
    at.switch_page("views/validation.py").run()
    assert not at.exception
    pick = at.multiselect[0]
    assert sorted(pick.value) == ids[:2]                                                    # the entry 12% out is not pre-selected
    d = _downloads(at, "Generate Validation Certificate")
    assert len(d) == 1 and d[0].proto.disabled is False and not any("outside the 5% tolerance" in w.value for w in at.warning)
    assert any("1 entry outside the tolerance is not selected" in c.value for c in at.caption)
    pick.set_value(ids).run()
    assert any("1 selected entry is outside the 5% tolerance" in w.value and "does not confirm" in w.value for w in at.warning)
    at.multiselect[0].set_value([]).run()
    assert _downloads(at, "Generate Validation Certificate")[0].proto.disabled is True and not at.exception

def test_validation_page_with_no_passing_entries_starts_empty_and_disabled():
    at = _register(); uid = at.session_state["user"]["id"]
    db.add_validation(uid, "Problem sheet", "Heat exchanger", "", "LMTD", "K", 50.0, 56.0)
    at.switch_page("views/validation.py").run()
    assert at.multiselect[0].value == [] and _downloads(at, "Generate Validation Certificate")[0].proto.disabled is True

def _monitor_with_demo(email="m@plant.pk"):
    at = _register(email); uid = at.session_state["user"]["id"]
    eid = db.add_equipment(uid, "heat_exchanger", "JH-01", "Juice station", HX)
    at.switch_page("views/monitor.py").run()
    at.button(key="mon_demo").click().run()
    return at, uid, eid

def _banner(at):
    return " ".join(x.value for x in list(at.success) + list(at.error) + list(at.warning) if any(k in x.value for k in ("HEALTHY", "WATCH", "ACTION NEEDED")))

def test_monitor_alert_settings_change_the_status_and_persist():
    at, uid, eid = _monitor_with_demo()
    assert "ACTION NEEDED" in _banner(at) and any("warn at 10% loss of U, alarm at 25% loss (default)" in e.label for e in at.expander)
    assert at.get("download_button") and not db.get_alert_settings(uid, eid)["custom"]
    at.number_input(key=f"mon_warn_{eid}").set_value(40.0); at.number_input(key=f"mon_crit_{eid}").set_value(60.0)
    at.button(key=f"mon_alert_save_{eid}").click().run()
    assert not at.exception and "HEALTHY" in _banner(at) and db.get_alert_settings(uid, eid) == {"u_warn_pct": 40.0, "u_crit_pct": 60.0, "custom": True}
    assert any("warn at 40% loss of U, alarm at 60% loss" in e.label and "(default)" not in e.label for e in at.expander) and any("Alert settings saved" in s.value for s in at.success)
    at.number_input(key=f"mon_warn_{eid}").set_value(20.0); at.number_input(key=f"mon_crit_{eid}").set_value(50.0)
    at.button(key=f"mon_alert_save_{eid}").click().run()
    assert "WATCH" in _banner(at) and "past your warning level of 20%" in _banner(at)
    # a brand-new session (a refresh and a new login) still finds the saved levels
    assert db.get_alert_settings(uid, eid)["u_warn_pct"] == 20.0

def test_monitor_alert_settings_reject_nonsense_and_can_be_reset():
    at, uid, eid = _monitor_with_demo("n@plant.pk")
    at.number_input(key=f"mon_warn_{eid}").set_value(30.0); at.number_input(key=f"mon_crit_{eid}").set_value(20.0)
    at.button(key=f"mon_alert_save_{eid}").click().run()
    assert any("alarm level must be higher" in e.value for e in at.error) and not db.get_alert_settings(uid, eid)["custom"]
    assert at.button(key=f"mon_alert_reset_{eid}").disabled
    db.set_alert_settings(uid, eid, 40, 60); at.switch_page("views/monitor.py").run()
    assert not at.button(key=f"mon_alert_reset_{eid}").disabled and "HEALTHY" in _banner(at)
    at.button(key=f"mon_alert_reset_{eid}").click().run()
    assert not at.exception and not db.get_alert_settings(uid, eid)["custom"] and "ACTION NEEDED" in _banner(at)
    assert at.number_input(key=f"mon_warn_{eid}").value == 10.0 and at.number_input(key=f"mon_crit_{eid}").value == 25.0

def _annotations(at):
    return [[a.get("text") for a in json.loads(c.proto.spec).get("layout", {}).get("annotations", [])] for c in at.get("plotly_chart")]

def test_the_u_chart_draws_the_users_levels():
    at, uid, eid = _monitor_with_demo("c@plant.pk")
    assert any("10% loss (watch)" in t and "25% loss (act)" in t for t in _annotations(at))
    at.number_input(key=f"mon_warn_{eid}").set_value(5.0); at.number_input(key=f"mon_crit_{eid}").set_value(15.0)
    at.button(key=f"mon_alert_save_{eid}").click().run()
    notes = _annotations(at)
    assert any("5% loss (watch)" in t and "15% loss (act)" in t for t in notes) and not any("10% loss (watch)" in t for t in notes)

def test_monitor_data_notes_are_saved_listed_and_drawn_on_every_chart():
    at, uid, eid = _monitor_with_demo("d@plant.pk")
    assert any(e.label == "Data notes (0)" for e in at.expander)
    when = date.today() - timedelta(days=20)
    at.date_input(key=f"mon_dn_date_{eid}").set_value(when); at.text_area(key=f"mon_dn_text_{eid}").input("After chemical cleaning")
    at.button(key=f"mon_dn_add_{eid}").click().run()
    saved = db.list_maintenance(uid, eid)
    assert not at.exception and [n["note"] for n in saved] == ["After chemical cleaning"] and saved[0]["note_date"] == when.isoformat()
    assert any(e.label == "Data notes (1)" for e in at.expander) and any("Note added" in s.value for s in at.success)
    charts = _annotations(at)
    assert len(charts) >= 3 and all("After chemical cleaning" in t for t in charts)               # every time chart carries the marker
    at.button(key=f"mon_dn_add_{eid}").click().run()                                               # an empty note is refused politely
    assert any("type a note" in e.value for e in at.error) and len(db.list_maintenance(uid, eid)) == 1

def test_a_note_outside_the_data_range_is_not_drawn():
    at, uid, eid = _monitor_with_demo("o@plant.pk")
    db.add_maintenance(uid, eid, (date.today() - timedelta(days=300)).isoformat(), "Old overhaul")
    at.switch_page("views/monitor.py").run()
    assert not any("Old overhaul" in t for t in sum(_annotations(at), [])) and any(e.label == "Data notes (1)" for e in at.expander)

def test_upload_area_has_a_date_and_a_note_with_explanations():
    at, uid, eid = _monitor_with_demo("u@plant.pk")
    d, t = at.date_input(key=f"mon_nd_{eid}"), at.text_input(key=f"mon_nt_{eid}")
    assert d.help and "marked on the trend charts" in d.help and t.placeholder == "e.g. After chemical cleaning" and "maintenance history" in t.help

def test_pumps_have_no_u_alert_settings_but_do_have_data_notes():
    at = _register("p@plant.pk"); uid = at.session_state["user"]["id"]
    eid = db.add_equipment(uid, "pump", "CWP-01", "", PUMP)
    at.switch_page("views/monitor.py").run(); at.button(key="mon_demo").click().run()
    assert not at.exception and not any("Alert settings" in e.label for e in at.expander) and any(e.label == "Data notes (0)" for e in at.expander)

def test_the_tutor_explains_with_the_saved_levels():
    at, uid, eid = _monitor_with_demo("t@plant.pk")
    db.set_alert_settings(uid, eid, 5, 15)
    at.switch_page("views/tutor.py").run()
    assert not at.exception and "your 15% alarm level" in " ".join(m.value for m in at.markdown)
