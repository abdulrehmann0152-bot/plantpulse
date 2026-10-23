import csv, io, json, os, sqlite3, sys
from datetime import date, timedelta
import pytest
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import db, session_cookie
from core.equipment_export import HEADERS, equipment_csv, maintenance_csv, safe, to_bytes
from core.equipment_tools import next_tag

ROOT = os.path.dirname(os.path.dirname(__file__))
HX = {"area_m2": 150.0, "u_clean": 1200.0, "flow": "shell_1_2"}
PUMP = {"d_mm": 200.0, "length_m": 200.0, "material": "Commercial steel (0.045 mm)", "sum_k": 8.0, "static_m": 10.0, "curve": [[0.0, 30.0], [200.0, 25.0], [300.0, 17.0]], "eta_pct": 70.0}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d13.db"))
    db.init_db()


def _user(email="a@plant.pk"):
    return db.create_user("Ali", email, "secret1", "engineer")


def _count(table):
    return sqlite3.connect(os.environ["PLANTPULSE_DB"]).execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ====================================================================== maintenance history (storage)
def test_notes_are_listed_newest_first_and_belong_to_their_owner():
    a, b = _user("a@b.com"), _user("c@d.com")
    eid = db.add_equipment(a["id"], "heat_exchanger", "JH-01", "", HX)
    n1 = db.add_maintenance(a["id"], eid, "2026-10-01", "Installed")
    n2 = db.add_maintenance(a["id"], eid, date(2026, 10, 10), "Cleaned tubes")
    db.add_maintenance(a["id"], eid, "2026-10-10", "Replaced gasket")                 # same date: the later entry comes first
    assert [n["note"] for n in db.list_maintenance(a["id"], eid)] == ["Replaced gasket", "Cleaned tubes", "Installed"]
    assert db.list_maintenance(b["id"], eid) == [] and db.delete_maintenance(b["id"], n1) is False
    with pytest.raises(db.DBError, match="not found"):
        db.add_maintenance(b["id"], eid, "2026-10-10", "x")
    assert db.delete_maintenance(a["id"], n2) is True and len(db.list_maintenance(a["id"], eid)) == 2

def test_note_validation():
    u = _user(); eid = db.add_equipment(u["id"], "pump", "P-1", "", PUMP)
    for note in ("", "   \n  "):
        with pytest.raises(db.DBError, match="type a note"):
            db.add_maintenance(u["id"], eid, "2026-10-10", note)
    with pytest.raises(db.DBError, match="too long"):
        db.add_maintenance(u["id"], eid, "2026-10-10", "x" * (db.MAX_NOTE + 1))
    for bad in ("10/10/2026", "not a date", "2026-13-40", "", None):
        with pytest.raises(db.DBError, match="valid date"):
            db.add_maintenance(u["id"], eid, bad, "ok")
    with pytest.raises(db.DBError, match="past"):
        db.add_maintenance(u["id"], eid, "1980-01-01", "ok")
    with pytest.raises(db.DBError, match="future"):
        db.add_maintenance(u["id"], eid, date.today() + timedelta(days=400), "ok")
    db.add_maintenance(u["id"], eid, date.today() + timedelta(days=30), "  Planned overhaul  ")
    assert db.list_maintenance(u["id"], eid)[0]["note"] == "Planned overhaul"

def test_notes_disappear_with_their_equipment_and_stay_per_user():
    a, b = _user("a@b.com"), _user("c@d.com")
    e1, e2 = db.add_equipment(a["id"], "pump", "P-1", "", PUMP), db.add_equipment(b["id"], "pump", "P-1", "", PUMP)
    db.add_maintenance(a["id"], e1, "2026-10-01", "A note"); db.add_maintenance(b["id"], e2, "2026-10-02", "B note")
    assert [r["note"] for r in db.list_all_maintenance(a["id"])] == ["A note"] and db.list_all_maintenance(a["id"])[0]["tag"] == "P-1"
    db.delete_equipment(a["id"], e1)
    assert db.list_all_maintenance(a["id"]) == [] and len(db.list_all_maintenance(b["id"])) == 1 and _count("maintenance_log") == 1

def test_equipment_and_notes_survive_a_restart():
    """A page refresh or an app restart starts a new session; the saved data is read back from the database file."""
    u = _user(); eid = db.add_equipment(u["id"], "heat_exchanger", "JH-01", "Juice station", HX); db.add_maintenance(u["id"], eid, "2026-10-10", "Cleaned tubes")
    assert os.path.exists(os.environ["PLANTPULSE_DB"])
    db.init_db()                                                                      # what the app does at every start
    assert db.authenticate("a@plant.pk", "secret1")["id"] == u["id"]
    e = db.list_equipment(u["id"])[0]
    assert (e["tag"], e["location"], e["params"]) == ("JH-01", "Juice station", HX) and db.list_maintenance(u["id"], eid)[0]["note"] == "Cleaned tubes"

# ====================================================================== sign-in sessions (storage)
def test_session_token_signs_the_right_user_in_and_only_its_hash_is_stored():
    u = _user(); token = db.create_session(u["id"])
    assert db.user_from_session(token) == {"id": u["id"], "name": "Ali", "email": "a@plant.pk", "role": "engineer"}
    raw = sqlite3.connect(os.environ["PLANTPULSE_DB"]).execute("SELECT token_hash FROM sessions").fetchall()
    assert len(raw) == 1 and token not in raw[0][0] and len(raw[0][0]) == 64             # SHA-256 hex: a copy of the database cannot sign anyone in
    other = db.create_session(u["id"]); assert other != token and db.user_from_session(other)["id"] == u["id"]

def test_bad_expired_and_deleted_tokens_do_not_sign_in():
    u = _user(); good = db.create_session(u["id"])
    for bad in (None, "", "short", 12345, "x" * 300, good + "x", good[:-1] + ("A" if good[-1] != "A" else "B")):
        assert db.user_from_session(bad) is None
    expired = db.create_session(u["id"], days=-1)
    assert db.user_from_session(expired) is None
    db.delete_session(good); assert db.user_from_session(good) is None
    db.delete_session(None); db.delete_session("nonsense")                               # harmless

def test_expired_tokens_are_purged_and_deleting_a_user_removes_their_tokens():
    u = _user(); db.create_session(u["id"], days=-1); db.create_session(u["id"], days=-1)
    live = db.create_session(u["id"])                                                    # creating a session cleans out the expired ones
    assert _count("sessions") == 1
    c = sqlite3.connect(os.environ["PLANTPULSE_DB"]); c.execute("PRAGMA foreign_keys=ON"); c.execute("DELETE FROM users WHERE id=?", (u["id"],)); c.commit()
    assert db.user_from_session(live) is None

# ====================================================================== cookie page
def test_cookie_page_embeds_only_the_token_and_cannot_be_broken_out_of():
    h = session_cookie._page("abc-DEF_123", 14)
    assert json.dumps("abc-DEF_123") in h and "max-age" in h and "'; Secure'" in h and "SameSite=Lax" in h and str(14 * 86400) in h
    assert "window.parent.document.cookie" in h and session_cookie.COOKIE in h
    hostile = session_cookie._page("</script><script>alert(1)</script>", 14)
    assert hostile.count("</script>") == 1                                               # only our own closing tag
    assert 'T="",AGE=0' in session_cookie._page("", 0).replace(" ", "")

def test_reading_the_cookie_never_crashes():
    assert session_cookie.read_token() in (None, "") or isinstance(session_cookie.read_token(), str)

# ====================================================================== next tag, CSV export
@pytest.mark.parametrize("tag,existing,expected", [("CWP-01", (), "CWP-02"), ("P-9", (), "P-10"), ("JH-099", (), "JH-100"), ("Pump A", (), "Pump A-2"),
                                                   ("CWP-01", ("cwp-02", "CWP-03"), "CWP-04"), ("", (), ""), ("  JH-01  ", (), "JH-02"), ("E7", (), "E8")])
def test_next_tag(tag, existing, expected):
    assert next_tag(tag, existing) == expected

def _read(text):
    return list(csv.reader(io.StringIO(text)))

def test_equipment_csv_has_every_item_with_notes_and_survives_awkward_text():
    u = _user()
    e1 = db.add_equipment(u["id"], "heat_exchanger", "JH-01", 'Juice, "station"', HX)
    db.add_equipment(u["id"], "pump", "CWP-01", "", PUMP)
    db.add_maintenance(u["id"], e1, "2026-10-01", "Installed"); db.add_maintenance(u["id"], e1, "2026-10-10", "Cleaned tubes,\nreplaced gasket")
    items = db.list_equipment(u["id"]); notes = {e["id"]: db.list_maintenance(u["id"], e["id"]) for e in items}
    rows = _read(equipment_csv(items, notes))
    assert rows[0] == HEADERS and len(rows) == 3
    hx, pump = dict(zip(HEADERS, rows[1])), dict(zip(HEADERS, rows[2]))
    assert (hx["Tag"], hx["Type"], hx["Location"]) == ("JH-01", "Heat exchanger", 'Juice, "station"')
    assert hx["Heat transfer area (m2)"] == "150.0" and hx["Clean U (W/m2K)"] == "1200.0" and "1 shell pass / 2 tube passes" in hx["Flow arrangement"] and hx["Pipe diameter (mm)"] == ""
    assert hx["Maintenance notes"] == "2" and hx["Last maintenance date"] == "2026-10-10" and hx["Last maintenance note"] == "Cleaned tubes,\nreplaced gasket"
    assert pump["Type"] == "Pump and pipeline" and pump["Pipe diameter (mm)"] == "200.0" and pump["Curve head 3 (m)"] == "17.0" and pump["Curve flow 2 (m3/h)"] == "200.0"
    assert pump["Maintenance notes"] == "0" and pump["Last maintenance date"] == "" and pump["Heat transfer area (m2)"] == ""

def test_csv_cannot_run_formulas_in_a_spreadsheet():
    u = _user()
    eid = db.add_equipment(u["id"], "pump", "=HYPERLINK(\"http://x\")", "+cmd|' /C calc'!A0", PUMP)
    db.add_maintenance(u["id"], eid, "2026-10-10", "@SUM(1+1)")
    items = db.list_equipment(u["id"]); notes = {eid: db.list_maintenance(u["id"], eid)}
    row = dict(zip(HEADERS, _read(equipment_csv(items, notes))[1]))
    assert row["Tag"].startswith("'=") and row["Location"].startswith("'+") and row["Last maintenance note"].startswith("'@")
    m = _read(maintenance_csv(db.list_all_maintenance(u["id"])))
    assert m[0] == ["Tag", "Type", "Date", "Note"] and m[1][0].startswith("'=") and m[1][3] == "'@SUM(1+1)"
    assert safe("normal") == "normal" and safe(-5.0) == -5.0 and safe("-dash") == "'-dash" and safe("") == ""

def test_csv_bytes_open_correctly_in_excel():
    b = to_bytes("Tag\nµ ² °\n")
    assert b.startswith(b"\xef\xbb\xbf") and b.decode("utf-8-sig") == "Tag\nµ ² °\n"
    assert _read(equipment_csv([], {})) == [HEADERS]

# ====================================================================== the page
def _app():
    return AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60)

def _register(at, email="e@plant.pk", keep=False):
    at.text_input(key="reg_name").input("Engr E"); at.text_input(key="reg_email").input(email); at.text_input(key="reg_pw").input("secret1")
    if keep:
        at.checkbox(key="keep_up").check()
    at.button(key="do_register").click().run()
    return at

def _equipment_page(at):
    return at.switch_page("views/equipment.py").run()

def test_list_shows_a_clone_and_delete_button_for_every_item():
    at = _register(_app().run()); uid = at.session_state["user"]["id"]
    ids = [db.add_equipment(uid, "heat_exchanger", "JH-01", "Juice station", HX), db.add_equipment(uid, "pump", "CWP-01", "Cooling", PUMP)]
    _equipment_page(at)
    assert not at.exception
    for i in ids:
        assert at.button(key=f"eq_clone_{i}") and at.button(key=f"eq_delete_{i}")
    assert any("Registered equipment (2)" in h.value for h in at.subheader)

def test_clone_prefills_everything_except_the_tag_and_saves_a_second_unit():
    at = _register(_app().run()); uid = at.session_state["user"]["id"]
    src = db.add_equipment(uid, "heat_exchanger", "JH-01", "Juice station", {"area_m2": 321.5, "u_clean": 987.0, "flow": "parallel"})
    db.add_maintenance(uid, src, "2026-10-10", "Cleaned tubes")
    _equipment_page(at)
    at.button(key=f"eq_clone_{src}").click().run()
    k = f"clone{src}_Heat exchanger"
    assert not at.exception and any("Cloning" in i.value and "JH-02" in i.value for i in at.info)
    assert at.text_input(key=f"eq_tag_{k}").value == "" and at.text_input(key=f"eq_tag_{k}").placeholder == "e.g. JH-02"      # a blank tag, with the next free tag suggested
    assert at.text_input(key=f"eq_loc_{k}").value == "Juice station" and at.number_input(key=f"eq_a_{k}").value == 321.5 and at.number_input(key=f"eq_u_{k}").value == 987.0
    assert at.selectbox(key=f"eq_f_{k}").value == "parallel" and at.radio(key=f"eq_kind_clone{src}").disabled
    at.button(key="eq_save").click().run()                                             # saving without a tag is refused
    assert any("tag" in e.value.lower() for e in at.error) and len(db.list_equipment(uid)) == 1
    at.text_input(key=f"eq_tag_{k}").input("JH-02")                                    # typed values are submitted together with the Save button
    at.button(key="eq_save").click().run()
    items = db.list_equipment(uid)
    assert not at.exception and [e["tag"] for e in items] == ["JH-01", "JH-02"] and items[1]["params"] == items[0]["params"] and items[1]["location"] == "Juice station"
    assert db.list_maintenance(uid, items[1]["id"]) == []                              # the history belongs to the original unit
    assert not any("Cloning" in i.value for i in at.info) and any("Saved JH-02" in s.value for s in at.success)

def test_cloning_a_pump_copies_the_curve_and_a_duplicate_tag_is_refused():
    at = _register(_app().run()); uid = at.session_state["user"]["id"]
    params = {**PUMP, "d_mm": 150.0, "curve": [[0.0, 41.0], [100.0, 38.0], [180.0, 25.0]], "eta_pct": 66.0}
    src = db.add_equipment(uid, "pump", "CWP-01", "Cooling tower", params)
    _equipment_page(at); at.button(key=f"eq_clone_{src}").click().run()
    k = f"clone{src}_Pump & pipeline"
    at.text_input(key=f"eq_tag_{k}").input("CWP-01")
    at.button(key="eq_save").click().run()
    assert any("already have equipment" in e.value for e in at.error) and len(db.list_equipment(uid)) == 1
    at.text_input(key=f"eq_tag_{k}").input("CWP-02")
    at.button(key="eq_save").click().run()
    assert db.list_equipment(uid)[1]["params"] == params and db.list_equipment(uid)[1]["tag"] == "CWP-02"

def test_cancelling_a_clone_returns_to_the_normal_form():
    at = _register(_app().run()); uid = at.session_state["user"]["id"]
    src = db.add_equipment(uid, "pump", "CWP-01", "", PUMP)
    _equipment_page(at); at.button(key=f"eq_clone_{src}").click().run()
    assert any(c.key == "eq_clone_cancel" for c in at.button)
    at.button(key="eq_clone_cancel").click().run()
    assert not at.exception and not any("Cloning" in i.value for i in at.info) and at.selectbox(key="eq_tmpl")

def test_maintenance_history_add_and_delete_on_the_page():
    at = _register(_app().run()); uid = at.session_state["user"]["id"]
    eid = db.add_equipment(uid, "heat_exchanger", "JH-01", "", HX)
    _equipment_page(at)
    at.text_area(key=f"eq_nt_{eid}").input("Cleaned tubes on 10/10/2026")
    at.button(key=f"eq_na_{eid}").click().run()
    notes = db.list_maintenance(uid, eid)
    assert not at.exception and [n["note"] for n in notes] == ["Cleaned tubes on 10/10/2026"] and notes[0]["note_date"] == date.today().isoformat()
    assert any("Note added to JH-01" in s.value for s in at.success) and any("Cleaned tubes on 10/10/2026" in t.value for t in at.text)
    at.button(key=f"eq_na_{eid}").click().run()                                         # an empty note is refused politely
    assert any("type a note" in e.value for e in at.error) and len(db.list_maintenance(uid, eid)) == 1
    at.button(key=f"eq_dn_{notes[0]['id']}").click().run()
    assert not at.exception and db.list_maintenance(uid, eid) == []

def test_a_first_note_can_be_saved_with_new_equipment():
    at = _register(_app().run()); uid = at.session_state["user"]["id"]
    _equipment_page(at)
    at.selectbox(key="eq_tmpl").select("Sugar mill juice heater (example)").run()
    k = "Sugar mill juice heater (example)_Heat exchanger"
    at.text_area(key=f"eq_n0_{k}").input("Installed and commissioned")
    at.button(key="eq_save").click().run()
    e = db.list_equipment(uid)[0]
    assert not at.exception and [n["note"] for n in db.list_maintenance(uid, e["id"])] == ["Installed and commissioned"] and any("note was added" in s.value for s in at.success)

def test_deleting_equipment_asks_first_and_removes_its_notes():
    at = _register(_app().run()); uid = at.session_state["user"]["id"]
    eid = db.add_equipment(uid, "pump", "CWP-01", "", PUMP); db.add_maintenance(uid, eid, "2026-10-10", "Seal replaced")
    _equipment_page(at)
    at.button(key=f"eq_delete_{eid}").click().run()
    assert any("This cannot be undone" in w.value for w in at.warning) and len(db.list_equipment(uid)) == 1
    at.button(key=f"eq_no_{eid}").click().run()
    assert not any("This cannot be undone" in w.value for w in at.warning) and len(db.list_equipment(uid)) == 1
    at.button(key=f"eq_delete_{eid}").click().run(); at.button(key=f"eq_yes_{eid}").click().run()
    assert not at.exception and db.list_equipment(uid) == [] and db.list_all_maintenance(uid) == [] and any("Deleted CWP-01" in s.value for s in at.success)

def test_export_buttons_appear_only_when_there_is_something_to_export():
    at = _register(_app().run()); uid = at.session_state["user"]["id"]
    _equipment_page(at)
    assert len(at.get("download_button")) == 0
    eid = db.add_equipment(uid, "pump", "CWP-01", "", PUMP)
    _equipment_page(at)
    d = at.get("download_button")
    assert len(d) == 2 and d[0].proto.label.startswith("Export equipment list") and d[1].proto.disabled is True
    db.add_maintenance(uid, eid, "2026-10-10", "Seal replaced")
    _equipment_page(at)
    assert at.get("download_button")[1].proto.disabled is False

# ====================================================================== staying signed in
def test_keep_me_signed_in_creates_a_token_and_logging_out_removes_it():
    at = _register(_app().run(), keep=True)
    token = at.session_state["session_token"]
    assert not at.exception and db.user_from_session(token)["email"] == "e@plant.pk" and "set_cookie" not in at.session_state    # the cookie page has been written
    at.button(key="logout").click().run()
    assert db.user_from_session(token) is None and "user" not in at.session_state and "session_token" not in at.session_state

def test_no_token_without_the_checkbox_and_none_for_guests():
    at = _register(_app().run(), keep=False)
    assert "session_token" not in at.session_state and _count("sessions") == 0
    g = _app().run(); g.button(key="do_guest").click().run()
    assert _count("sessions") == 0

def test_log_in_with_the_checkbox_creates_a_token_too():
    first = _register(_app().run(), "l@plant.pk")
    first.button(key="logout").click().run()
    first.text_input(key="login_email").input("l@plant.pk"); first.text_input(key="login_pw").input("secret1"); first.checkbox(key="keep_in").check()
    first.button(key="do_login").click().run()
    assert not first.exception and db.user_from_session(first.session_state["session_token"])["email"] == "l@plant.pk"

def test_a_refresh_with_a_valid_cookie_keeps_the_user_and_their_equipment(monkeypatch):
    """A page refresh = a brand-new session. With the cookie, the user is signed in again and sees the saved equipment and notes."""
    before = _register(_app().run(), "r@plant.pk", keep=True)
    uid, token = before.session_state["user"]["id"], before.session_state["session_token"]
    eid = db.add_equipment(uid, "heat_exchanger", "JH-01", "Juice station", HX); db.add_maintenance(uid, eid, "2026-10-10", "Cleaned tubes")
    monkeypatch.setattr(session_cookie, "read_token", lambda: token)
    after = _app().run()                                                               # the 'refreshed' page
    assert not after.exception and after.session_state["user"]["email"] == "r@plant.pk"
    _equipment_page(after)
    assert any("Registered equipment (1)" in h.value for h in after.subheader) and any("JH-01" in m.value for m in after.markdown) and after.button(key=f"eq_clone_{eid}")

def test_a_refresh_with_a_wrong_or_expired_or_deleted_cookie_shows_the_login_page(monkeypatch):
    user = _user("w@plant.pk")
    for token in ("not-a-real-token-0123456789abcdef", db.create_session(user["id"], days=-1)):
        monkeypatch.setattr(session_cookie, "read_token", lambda t=token: t)
        at = _app().run()
        assert not at.exception and "user" not in at.session_state and any(t.key == "login_email" for t in at.text_input)
    good = db.create_session(user["id"]); db.delete_session(good)
    monkeypatch.setattr(session_cookie, "read_token", lambda: good)
    assert "user" not in _app().run().session_state

def test_without_a_cookie_the_user_logs_in_and_finds_everything_there():
    first = _register(_app().run(), "n@plant.pk")
    uid = first.session_state["user"]["id"]; db.add_equipment(uid, "pump", "CWP-01", "", PUMP)
    again = _app().run()
    assert "user" not in again.session_state                                            # a refresh without the 'keep me signed in' cookie: log in again
    again.text_input(key="login_email").input("n@plant.pk"); again.text_input(key="login_pw").input("secret1"); again.button(key="do_login").click().run()
    _equipment_page(again)
    assert any("Registered equipment (1)" in h.value for h in again.subheader)
