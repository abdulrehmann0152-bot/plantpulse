import hashlib, os, sys, time
from datetime import datetime, timedelta
import pytest
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import clock, db

ROOT = os.path.dirname(os.path.dirname(__file__))
PG_MODE = bool(os.environ.get("PP_TEST_PG_URL"))
skip_pg = pytest.mark.skipif(PG_MODE, reason="this test is about choosing the database, so it only runs in the normal SQLite mode")
HX = {"area_m2": 150.0, "u_clean": 1200.0, "flow": "shell_1_2"}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d16.db"))
    db.init_db()


def _user(email="a@plant.pk", pw="secret12"):
    return db.create_user("Ali", email, pw, "engineer")


def _count(table):
    return db._run(f"SELECT COUNT(*) AS n FROM {table}")[0][0]["n"]


# ====================================================================== which database is used
@skip_pg
def test_choice_of_database(monkeypatch):
    monkeypatch.delenv("PLANTPULSE_DB"); monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db._target() == ("sqlite", db.DEFAULT_DB)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/dbname?sslmode=require")
    assert db._target() == ("pg", "postgresql://u:p@host/dbname?sslmode=require")           # the old 'postgres://' form is accepted
    monkeypatch.setenv("PLANTPULSE_DB", "/tmp/x.db")
    assert db._target() == ("sqlite", __import__("pathlib").Path("/tmp/x.db"))              # the explicit local file always wins: tests can never touch the real database

@skip_pg
def test_the_address_can_come_from_streamlit_secrets(monkeypatch):
    import streamlit as st
    monkeypatch.delenv("PLANTPULSE_DB"); monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(st, "secrets", {"DATABASE_URL": "  postgres://u:p@h/d  "})
    assert db._target() == ("pg", "postgresql://u:p@h/d")
    monkeypatch.setattr(st, "secrets", {})
    assert db._target()[0] == "sqlite"

@skip_pg
def test_storage_info(monkeypatch):
    assert db.storage_info() == {"kind": "SQLite file", "hosted": False, "temporary": False}
    monkeypatch.delenv("PLANTPULSE_DB"); monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    assert db.storage_info() == {"kind": "PostgreSQL", "hosted": True, "temporary": False}
    monkeypatch.delenv("DATABASE_URL"); monkeypatch.setattr(db, "DEFAULT_DB", __import__("pathlib").Path("/mount/src/plantpulse/data/plantpulse.db"))
    assert db.storage_info() == {"kind": "SQLite file", "hosted": False, "temporary": True}       # the cloud's temporary disk

@skip_pg
def test_an_unreachable_hosted_database_gives_a_friendly_message_and_leaks_nothing(monkeypatch):
    monkeypatch.delenv("PLANTPULSE_DB"); monkeypatch.setenv("PLANTPULSE_DB_TIMEOUT", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://someuser:SECRETPASS@127.0.0.1:1/somedb?connect_timeout=1")
    try:
        with pytest.raises(db.DBError) as e:
            db.init_db()
        assert "not reachable" in str(e.value) and "SECRETPASS" not in str(e.value) and "127.0.0.1" not in str(e.value)
        at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=30).run()      # the whole app stops politely
        assert not at.exception and any("not reachable" in x.value for x in at.error) and not any(t.key == "login_email" for t in at.text_input)
    finally:
        for p in db._POOLS.values():
            p.close()
        db._POOLS.clear()

# ====================================================================== passwords
@pytest.mark.parametrize("pw", ["", "short", "1234567", "password", "PASSWORD", "12345678", "Password123"[:0], "aaaaaaaa", "abababab", "a" * 129, None])
def test_weak_passwords_are_refused(pw):
    with pytest.raises(db.DBError, match="Password must be"):
        db.create_user("Ali", "a@plant.pk", pw, "student")

def test_password_equal_to_the_email_is_refused():
    with pytest.raises(db.DBError, match="Password must be"):
        db.create_user("Ali", "plantpulse9@gmail.com", "plantpulse9@gmail.com", "student")
    with pytest.raises(db.DBError, match="Password must be"):
        db.create_user("Ali", "abdulrehman@gmail.com", "AbdulRehman", "student")

@pytest.mark.parametrize("pw", ["secret12", "Tr1cky!pass", "long enough passphrase", "abcdefgh" * 16])
def test_reasonable_passwords_are_accepted(pw):
    assert db.create_user("Ali", "a@plant.pk", pw, "student")["email"] == "a@plant.pk" and db.authenticate("a@plant.pk", pw)

def test_name_and_email_length_limits():
    with pytest.raises(db.DBError, match="too long"):
        db.create_user("N" * 101, "a@plant.pk", "secret12", "student")
    with pytest.raises(db.DBError, match="too long"):
        db.create_user("Ali", "a" * 250 + "@x.com", "secret12", "student")

def test_hash_format_records_the_number_of_rounds(monkeypatch):
    monkeypatch.setenv("PLANTPULSE_PBKDF2_ITERATIONS", "1234")
    _user("a@b.com"); _user("c@d.com")
    rows = db._run("SELECT salt, password_hash FROM users ORDER BY id")[0]
    assert all(r["password_hash"].startswith("pbkdf2_sha256$1234$") for r in rows) and rows[0]["password_hash"] != rows[1]["password_hash"]
    monkeypatch.delenv("PLANTPULSE_PBKDF2_ITERATIONS")
    assert db._iterations() == 600_000

def test_accounts_with_the_old_hash_still_work_and_are_upgraded_on_login():
    salt = "ab" * 16
    legacy = hashlib.pbkdf2_hmac("sha256", b"oldpassword1", bytes.fromhex(salt), 200_000).hex()
    db._run("INSERT INTO users (name,email,salt,password_hash,role,created_at) VALUES (?,?,?,?,?,?)", ("Old", "old@plant.pk", salt, legacy, "student", "2026-01-01T00:00:00"))
    assert db.authenticate("old@plant.pk", "wrongpassword") is None
    assert db._run("SELECT password_hash FROM users")[0][0]["password_hash"] == legacy             # a wrong password changes nothing
    assert db.authenticate("old@plant.pk", "oldpassword1")["email"] == "old@plant.pk"
    assert db._run("SELECT password_hash FROM users")[0][0]["password_hash"].startswith("pbkdf2_sha256$")
    assert db.authenticate("old@plant.pk", "oldpassword1") and db.authenticate("old@plant.pk", "wrongpassword") is None

def test_hashes_with_fewer_rounds_are_upgraded(monkeypatch):
    monkeypatch.setenv("PLANTPULSE_PBKDF2_ITERATIONS", "1000"); _user()
    monkeypatch.setenv("PLANTPULSE_PBKDF2_ITERATIONS", "2000")
    assert db.authenticate("a@plant.pk", "secret12")
    assert db._run("SELECT password_hash FROM users")[0][0]["password_hash"].startswith("pbkdf2_sha256$2000$")

# ====================================================================== lockout after repeated failures
def test_five_wrong_passwords_lock_the_account_even_for_the_right_password():
    _user()
    for _ in range(4):
        assert db.authenticate("a@plant.pk", "wrong-pass") is None
    with pytest.raises(db.DBError, match="Too many failed attempts"):
        db.authenticate("a@plant.pk", "wrong-pass")                                            # the fifth failure locks it
    with pytest.raises(db.DBError, match=r"Too many failed attempts. Please try again in (1[0-5]|[1-9]) minute"):
        db.authenticate("a@plant.pk", "secret12")                                              # the right password is refused while locked

def test_the_lock_ends_and_a_good_login_clears_the_count():
    _user()
    for _ in range(4):
        db.authenticate("a@plant.pk", "wrong-pass")
    assert db.authenticate("a@plant.pk", "secret12")                                           # success resets the count
    for _ in range(4):
        db.authenticate("a@plant.pk", "wrong-pass")                                            # four more are fine again
    with pytest.raises(db.DBError):
        db.authenticate("a@plant.pk", "wrong-pass")
    db._run("UPDATE login_failures SET locked_until = ?", ((datetime.now() - timedelta(seconds=1)).isoformat(timespec="seconds"),))
    assert db.authenticate("a@plant.pk", "secret12")["email"] == "a@plant.pk"

def test_lockout_is_per_email_and_applies_to_unknown_emails_too():
    _user("a@plant.pk"); _user("b@plant.pk")
    for _ in range(4):
        assert db.authenticate("nobody@plant.pk", "whatever12") is None
    with pytest.raises(db.DBError, match="Too many failed attempts"):
        db.authenticate("nobody@plant.pk", "whatever12")                                        # same behaviour as a real account, so attackers learn nothing
    assert db.authenticate("b@plant.pk", "secret12") and db.authenticate("a@plant.pk", "secret12")
    with pytest.raises(db.DBError):
        db.authenticate("  NOBODY@plant.pk ", "x")                                              # case and spaces do not get around it

def test_old_failure_records_are_cleaned_up_and_unknown_emails_do_the_same_work(monkeypatch):
    db._run("INSERT INTO login_failures (email,fails,locked_until,updated_at) VALUES (?,?,?,?)", ("old@x.com", 3, None, (datetime.now() - timedelta(days=3)).isoformat(timespec="seconds")))
    calls = []
    real = db._hash
    monkeypatch.setattr(db, "_hash", lambda *a, **k: calls.append(a) or real(*a, **k))
    assert db.authenticate("ghost@x.com", "pw12345678") is None
    assert len(calls) == 1                                                                      # a dummy hash is computed, so timing does not reveal that the email is unknown
    assert db._run("SELECT email FROM login_failures")[0][0]["email"] == "ghost@x.com"

# ====================================================================== deleting an account
def test_deleting_an_account_removes_everything_it_owns_and_nothing_else():
    a, b = _user("a@plant.pk"), _user("b@plant.pk")
    ea, eb = db.add_equipment(a["id"], "heat_exchanger", "JH-01", "", HX), db.add_equipment(b["id"], "heat_exchanger", "JH-01", "", HX)
    db.add_log(a["id"], ea, {"x": 1}); db.add_maintenance(a["id"], ea, "2026-10-10", "Cleaned"); db.set_alert_settings(a["id"], ea, 5, 15)
    db.add_validation(a["id"], "Kern", "Heat exchanger", "", "Area", "m2", 1.0, 1.0); db.create_session(a["id"]); db.add_maintenance(b["id"], eb, "2026-10-10", "B note")
    assert db.delete_account(a["id"], "secret12") is True
    for table in ("equipment", "operating_logs", "maintenance_log", "alert_settings", "validation_log", "sessions"):
        assert _count(table) == (1 if table in ("equipment", "maintenance_log") else 0), table
    assert db.authenticate("a@plant.pk", "secret12") is None and db.authenticate("b@plant.pk", "secret12") and db.list_equipment(b["id"])[0]["tag"] == "JH-01"

def test_deleting_needs_the_right_password_and_counts_wrong_tries():
    u = _user()
    for _ in range(4):
        with pytest.raises(db.DBError, match="password is not correct"):
            db.delete_account(u["id"], "wrong-pass")
    with pytest.raises(db.DBError):
        db.delete_account(u["id"], "wrong-pass")                                                # the fifth wrong try locks it, as for logging in
    assert _count("users") == 1
    with pytest.raises(db.DBError, match="not found"):
        db.delete_account(None, "x")
    with pytest.raises(db.DBError, match="not found"):
        db.delete_account(99999, "x")

# ====================================================================== time zone
@pytest.fixture
def restore_tz():
    old = os.environ.get("TZ")
    yield
    os.environ.pop("TZ", None) if old is None else os.environ.__setitem__("TZ", old)
    if hasattr(time, "tzset"):
        time.tzset()

@pytest.mark.skipif(not hasattr(time, "tzset"), reason="Windows uses the computer's own time zone")
def test_the_server_uses_pakistan_time_unless_told_otherwise(monkeypatch, restore_tz):
    monkeypatch.delenv("PLANTPULSE_TZ", raising=False)
    assert clock.apply_timezone() == "Asia/Karachi" and time.timezone == -5 * 3600 and time.strftime("%Z") == "PKT"
    monkeypatch.setenv("PLANTPULSE_TZ", "UTC")
    assert clock.apply_timezone() == "UTC" and time.timezone == 0

def test_the_app_applies_the_time_zone(restore_tz):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=30).run()
    assert not at.exception
    if hasattr(time, "tzset"):
        assert time.timezone == -5 * 3600

# ====================================================================== the pages
def _app():
    return AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60)

def _register(email="e@plant.pk", pw="secret12"):
    at = _app().run()
    at.text_input(key="reg_name").input("Engr E"); at.text_input(key="reg_email").input(email); at.text_input(key="reg_pw").input(pw)
    at.button(key="do_register").click().run()
    return at

def _login(at, email, pw):
    at.text_input(key="login_email").input(email); at.text_input(key="login_pw").input(pw)
    at.button(key="do_login").click().run()

def test_registration_refuses_weak_passwords_and_explains_the_rule():
    at = _app().run()
    assert "Password (at least 8 characters)" in [t.label for t in at.text_input]
    at.text_input(key="reg_name").input("E"); at.text_input(key="reg_email").input("e@plant.pk"); at.text_input(key="reg_pw").input("password")
    at.button(key="do_register").click().run()
    assert any("Password must be" in e.value for e in at.error) and "user" not in at.session_state

def test_login_page_locks_after_five_wrong_passwords_and_says_so():
    _register("lock@plant.pk").button(key="logout").click().run()
    at = _app().run()
    for i in range(4):
        _login(at, "lock@plant.pk", "wrong-pass1")
        assert any("incorrect" in e.value for e in at.error), i
    _login(at, "lock@plant.pk", "wrong-pass1")
    assert any("Too many failed attempts" in e.value for e in at.error) and "user" not in at.session_state
    _login(at, "lock@plant.pk", "secret12")
    assert any("Too many failed attempts" in e.value for e in at.error) and "user" not in at.session_state

def test_privacy_text_is_on_the_login_page():
    at = _app().run()
    assert any(e.label == "Privacy and data" for e in at.expander)
    text = " ".join(m.value for m in at.markdown)
    assert "hashed password" in text and "five wrong passwords" in text and "delete your account" in text

def test_temporary_storage_is_flagged_on_the_login_page_and_the_sidebar(monkeypatch):
    monkeypatch.setattr(db, "storage_info", lambda: {"kind": "SQLite file", "hosted": False, "temporary": True})
    at = _app().run()
    assert any("temporary file" in w.value for w in at.warning)
    at.button(key="do_guest").click().run()
    assert any("Storage: SQLite file (temporary)" in c.value for c in at.sidebar.caption)

def test_the_sidebar_names_the_storage():
    at = _register()
    assert any(c.value.startswith("Storage:") for c in at.sidebar.caption)

def test_guests_see_an_explanation_on_the_account_page():
    at = _app().run(); at.button(key="do_guest").click().run()
    at.switch_page("views/account.py").run()
    assert not at.exception and any("guest" in i.value for i in at.info) and not any(b.key == "acc_delete" for b in at.button)

def test_account_page_deletes_the_account_after_the_password_and_a_tick():
    at = _register("del@plant.pk"); uid = at.session_state["user"]["id"]
    db.add_equipment(uid, "pump", "P-1", "", {"x": 1})
    at.switch_page("views/account.py").run()
    assert at.button(key="acc_delete").disabled and any("del@plant.pk" in m.value for m in at.markdown)
    at.checkbox(key="acc_sure").check().run()                                                   # ticking the box reruns the page and enables the button
    assert not at.button(key="acc_delete").disabled
    at.text_input(key="acc_pw").input("wrong-pass1")
    at.button(key="acc_delete").click().run()
    assert any("password is not correct" in e.value for e in at.error) and _count("users") == 1
    at.text_input(key="acc_pw").input("secret12"); at.button(key="acc_delete").click().run()
    assert not at.exception and "user" not in at.session_state and _count("users") == 0 and _count("equipment") == 0
    assert any("were deleted" in s.value for s in at.success)                                 # the login page says so
    _login(at, "del@plant.pk", "secret12")
    assert "user" not in at.session_state

def test_deleting_the_account_also_ends_the_remembered_sign_in():
    at = _register("rem@plant.pk", "secret12")
    at.button(key="logout").click().run()
    at.text_input(key="login_email").input("rem@plant.pk"); at.text_input(key="login_pw").input("secret12"); at.checkbox(key="keep_in").check()
    at.button(key="do_login").click().run()
    token = at.session_state["session_token"]
    assert db.user_from_session(token)
    at.switch_page("views/account.py").run()
    at.checkbox(key="acc_sure").check().run(); at.text_input(key="acc_pw").input("secret12"); at.button(key="acc_delete").click().run()
    assert db.user_from_session(token) is None

def test_equipment_page_reads_all_notes_in_one_query(monkeypatch):
    at = _register("n1@plant.pk"); uid = at.session_state["user"]["id"]
    for i in range(3):
        eid = db.add_equipment(uid, "heat_exchanger", f"JH-0{i}", "", HX); db.add_maintenance(uid, eid, "2026-10-10", f"note {i}")
    calls = {"one": 0, "all": 0}
    one, allr = db.list_maintenance, db.list_all_maintenance
    monkeypatch.setattr(db, "list_maintenance", lambda *a, **k: calls.__setitem__("one", calls["one"] + 1) or one(*a, **k))
    monkeypatch.setattr(db, "list_all_maintenance", lambda *a, **k: calls.__setitem__("all", calls["all"] + 1) or allr(*a, **k))
    at.switch_page("views/equipment.py").run()
    assert not at.exception and calls == {"one": 0, "all": 1} and any("Maintenance history (1)" in e.label for e in at.expander)

# ====================================================================== repository safety files
def _read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()

def test_gitignore_keeps_databases_and_secrets_out_of_the_repository():
    lines = {l.strip() for l in _read(".gitignore").splitlines()}
    for must in ("*.db", ".streamlit/secrets.toml", "venv/", "__pycache__/"):
        assert must in lines, must

def test_secrets_template_has_placeholders_only_and_requirements_list_the_driver():
    example = _read(".streamlit/secrets.toml.example")
    assert "DATABASE_URL" in example and "USER:PASSWORD@HOST" in example and "NEVER commit" in example
    assert not os.path.exists(os.path.join(ROOT, ".streamlit", "secrets.toml"))                 # a real secrets file must never be in the project folder we hand over
    req = _read("requirements.txt").lower()
    assert "psycopg[binary,pool]" in req and "tzdata" in req and "streamlit" in req
    assert "[theme]" in _read(".streamlit/config.toml")                                         # the existing theme is untouched

# ====================================================================== the connection checker
def _check(env_extra, drop=()):
    import subprocess
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_extra)
    return subprocess.run([sys.executable, os.path.join(ROOT, "check_database.py")], capture_output=True, text=True, env=env, cwd=ROOT, timeout=60)

@skip_pg
def test_connection_checker_works_on_the_local_file(tmp_path):
    r = _check({"PLANTPULSE_DB": str(tmp_path / "chk.db")}, drop=("DATABASE_URL",))
    assert r.returncode == 0 and "Storage: SQLite file" in r.stdout and "OK: connected" in r.stdout and "set DATABASE_URL" in r.stdout
    assert db._run("SELECT COUNT(*) AS n FROM login_failures")[0][0]["n"] == 0                  # the test row is removed

@skip_pg
def test_connection_checker_fails_politely_and_never_prints_the_password():
    r = _check({"DATABASE_URL": "postgresql://someuser:SECRETPASS@127.0.0.1:1/somedb?connect_timeout=1", "PLANTPULSE_DB_TIMEOUT": "1"}, drop=("PLANTPULSE_DB",))
    out = r.stdout + r.stderr
    assert r.returncode == 1 and "FAILED" in r.stdout and "not reachable" in r.stdout and "SECRETPASS" not in out and "127.0.0.1" not in r.stdout
