import os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "test.db"))
    db.init_db()


def _user(email="a@uet.edu.pk", role="student"):
    return db.create_user("Ali", email, "secret1", role)


def test_init_is_repeatable():
    db.init_db(); db.init_db()

def test_create_and_login():
    u = _user()
    assert u["role"] == "student"
    assert db.authenticate("a@uet.edu.pk", "secret1")["id"] == u["id"]

def test_wrong_password_and_unknown_user():
    _user()
    assert db.authenticate("a@uet.edu.pk", "wrong") is None
    assert db.authenticate("nobody@uet.edu.pk", "secret1") is None

def test_email_is_case_insensitive():
    _user("Ali@UET.edu.pk")
    assert db.authenticate("ali@uet.edu.pk", "secret1") is not None

def test_duplicate_email_rejected():
    _user()
    with pytest.raises(db.DBError):
        _user()

@pytest.mark.parametrize("name,email,pw,role", [("", "a@b.com", "secret1", "student"), ("A", "not-an-email", "secret1", "student"),
                                                ("A", "a@b.com", "123", "student"), ("A", "a@b.com", "secret1", "admin")])
def test_validation(name, email, pw, role):
    with pytest.raises(db.DBError):
        db.create_user(name, email, pw, role)

def test_password_not_stored_in_plain_text():
    _user("a@b.com"); _user("c@d.com")
    import sqlite3
    rows = sqlite3.connect(os.environ["PLANTPULSE_DB"]).execute("SELECT salt, password_hash FROM users").fetchall()
    assert all("secret1" not in r[1] for r in rows)
    assert rows[0][1] != rows[1][1] and rows[0][0] != rows[1][0]   # different salts -> different hashes

def test_equipment_add_list_delete():
    u = _user()
    eid = db.add_equipment(u["id"], "heat_exchanger", "JH-01", "Juice station", {"area_m2": 150.0})
    items = db.list_equipment(u["id"])
    assert len(items) == 1 and items[0]["params"]["area_m2"] == 150.0 and items[0]["tag"] == "JH-01"
    assert db.delete_equipment(u["id"], eid) is True
    assert db.list_equipment(u["id"]) == []

def test_equipment_tag_unique_per_user_only():
    a, b = _user("a@b.com"), _user("c@d.com")
    db.add_equipment(a["id"], "pump", "P-1", "", {})
    with pytest.raises(db.DBError):
        db.add_equipment(a["id"], "pump", "P-1", "", {})
    db.add_equipment(b["id"], "pump", "P-1", "", {})   # another user may reuse the tag

def test_users_cannot_see_or_delete_each_others_equipment():
    a, b = _user("a@b.com"), _user("c@d.com")
    eid = db.add_equipment(a["id"], "pump", "P-1", "", {})
    assert db.list_equipment(b["id"]) == []
    assert db.delete_equipment(b["id"], eid) is False
    assert len(db.list_equipment(a["id"])) == 1

def test_equipment_validation():
    u = _user()
    with pytest.raises(db.DBError):
        db.add_equipment(u["id"], "boiler", "B-1", "", {})
    with pytest.raises(db.DBError):
        db.add_equipment(u["id"], "pump", "  ", "", {})

def test_logs_follow_ownership():
    a, b = _user("a@b.com"), _user("c@d.com")
    eid = db.add_equipment(a["id"], "pump", "P-1", "", {})
    db.add_log(a["id"], eid, {"flow": 280.0})
    assert db.list_logs(a["id"], eid)[0]["data"]["flow"] == 280.0
    assert db.list_logs(b["id"], eid) == []
    with pytest.raises(db.DBError):
        db.add_log(b["id"], eid, {"flow": 1})

def test_deleting_equipment_removes_its_logs():
    u = _user()
    eid = db.add_equipment(u["id"], "pump", "P-1", "", {})
    db.add_log(u["id"], eid, {"x": 1})
    db.delete_equipment(u["id"], eid)
    import sqlite3
    assert sqlite3.connect(os.environ["PLANTPULSE_DB"]).execute("SELECT COUNT(*) FROM operating_logs").fetchone()[0] == 0


def test_bulk_logs_skip_duplicates_and_enforce_ownership():
    a, b = _user("a@b.com"), _user("c@d.com")
    eid = db.add_equipment(a["id"], "pump", "P-1", "", {})
    rows = [("2026-10-01T00:00:00", {"x": 1}), ("2026-10-02T00:00:00", {"x": 2})]
    assert db.add_logs_bulk(a["id"], eid, rows) == 2
    assert db.add_logs_bulk(a["id"], eid, rows + [("2026-10-03T00:00:00", {"x": 3})]) == 1
    assert len(db.list_logs(a["id"], eid)) == 3
    with pytest.raises(db.DBError):
        db.add_logs_bulk(b["id"], eid, rows)
    assert db.delete_logs(b["id"], eid) == 0
    assert db.delete_logs(a["id"], eid) == 3 and db.list_logs(a["id"], eid) == []
