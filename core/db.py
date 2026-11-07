"""Storage for users, equipment, readings and notes (no Streamlit code needed to run it).

Two back ends share one set of functions:
  * a local SQLite file (the default, used on a laptop and in the tests), and
  * a hosted PostgreSQL database, used when a connection address is configured (DATABASE_URL, from the environment or Streamlit secrets).
If PLANTPULSE_DB is set it always wins, so tests and local experiments can never touch the hosted database by accident.
"""
import hashlib, hmac, json, os, re, secrets, sqlite3, threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "plantpulse.db"
ROLES = ("student", "engineer")
EQUIPMENT_TYPES = ("heat_exchanger", "pump")
ID_TABLES = {"users", "equipment", "validation_log", "maintenance_log", "operating_logs"}      # tables whose INSERT returns the new id


class DBError(ValueError):
    """Friendly, user-facing database or validation error."""


class IntegrityViolation(Exception):
    """A unique or foreign-key rule was broken (the same for both back ends)."""


# ---------------------------------------------------------------- which database?
def _database_url():
    """The hosted database address, from the environment or from Streamlit secrets, or None."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            import streamlit as st
            url = st.secrets.get("DATABASE_URL")
        except Exception:                                   # no secrets file, or not running inside Streamlit
            url = None
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url or None


def _target():
    explicit = os.environ.get("PLANTPULSE_DB")
    if explicit:
        return ("sqlite", Path(explicit))
    url = _database_url()
    if url:
        return ("pg", url)
    return ("sqlite", DEFAULT_DB)


def storage_info():
    """Describe where data is kept, for the page: {'kind', 'hosted', 'temporary'}."""
    kind = _target()[0]
    temporary = kind == "sqlite" and str(DEFAULT_DB).startswith("/mount/") and not os.environ.get("PLANTPULSE_DB")
    return {"kind": "PostgreSQL" if kind == "pg" else "SQLite file", "hosted": kind == "pg", "temporary": temporary}


# ---------------------------------------------------------------- one small connection wrapper for both
class _Result:
    def __init__(self, rows, lastrowid, rowcount):
        self.rows, self.lastrowid, self.rowcount = rows, lastrowid, rowcount

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _SqliteConn:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, args=()):
        try:
            cur = self.conn.execute(sql, args)
        except sqlite3.IntegrityError as e:
            raise IntegrityViolation(str(e)) from e
        return _Result(cur.fetchall(), cur.lastrowid, cur.rowcount)

    def executemany(self, sql, seq):
        try:
            self.conn.executemany(sql, seq)
        except sqlite3.IntegrityError as e:
            raise IntegrityViolation(str(e)) from e


class _PgConn:
    def __init__(self, conn):
        self.conn = conn

    @staticmethod
    def _sql(sql):
        sql = sql.replace("%", "%%").replace("?", "%s")
        m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", sql, re.I)
        if m and m.group(1) in ID_TABLES and "RETURNING" not in sql.upper():
            sql += " RETURNING id"
        return sql, bool(m and m.group(1) in ID_TABLES)

    def execute(self, sql, args=()):
        import psycopg
        sql, returning = self._sql(sql)
        try:
            cur = self.conn.execute(sql, tuple(args))
        except psycopg.errors.IntegrityError as e:
            raise IntegrityViolation(str(e)) from e
        rows = cur.fetchall() if cur.description else []
        return _Result(rows, rows[0]["id"] if returning and rows else None, cur.rowcount)

    def executemany(self, sql, seq):
        import psycopg
        sql, _ = self._sql(sql)
        sql = sql.replace(" RETURNING id", "")
        try:
            with self.conn.cursor() as cur:
                cur.executemany(sql, [tuple(r) for r in seq])
        except psycopg.errors.IntegrityError as e:
            raise IntegrityViolation(str(e)) from e


_POOLS, _POOL_LOCK, _READY = {}, threading.Lock(), set()


def _pool(url):
    with _POOL_LOCK:
        if url not in _POOLS:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            _POOLS[url] = ConnectionPool(url, min_size=1, max_size=5, timeout=float(os.environ.get("PLANTPULSE_DB_TIMEOUT") or 10), max_idle=240, max_lifetime=1500, open=True,
                                         check=ConnectionPool.check_connection, kwargs={"row_factory": dict_row, "prepare_threshold": None})   # no prepared statements: works behind PgBouncer
        return _POOLS[url]


@contextmanager
def _tx():
    """One transaction: commits when the block ends well, rolls back on any error."""
    kind, where = _target()
    if kind == "pg":
        import psycopg
        import psycopg_pool
        try:
            with _pool(where).connection() as conn:              # commits or rolls back by itself
                yield _PgConn(conn)
        except (psycopg.OperationalError, psycopg_pool.PoolTimeout):
            raise DBError("The database is not reachable right now. Please try again in a minute.") from None      # never show the address or password
        return
    where.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(where)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield _SqliteConn(conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _run(sql, args=()):
    """Run one statement in its own transaction and return (rows, lastrowid, rowcount)."""
    with _tx() as conn:
        r = conn.execute(sql, args)
        return r.rows, r.lastrowid, r.rowcount


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id {PK},
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student','engineer')),
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS equipment (
    id {PK},
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    eq_type TEXT NOT NULL CHECK (eq_type IN ('heat_exchanger','pump')),
    tag TEXT NOT NULL,
    location TEXT,
    params TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, tag));
CREATE TABLE IF NOT EXISTS validation_log (
    id {PK},
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    module TEXT NOT NULL,
    problem TEXT,
    quantity TEXT NOT NULL,
    unit TEXT,
    reference DOUBLE PRECISION NOT NULL,
    app_value DOUBLE PRECISION NOT NULL,
    notes TEXT);
CREATE TABLE IF NOT EXISTS maintenance_log (
    id {PK},
    equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    note_date TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alert_settings (
    equipment_id INTEGER PRIMARY KEY REFERENCES equipment(id) ON DELETE CASCADE,
    u_warn_pct DOUBLE PRECISION NOT NULL,
    u_crit_pct DOUBLE PRECISION NOT NULL,
    updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_failures (
    email TEXT PRIMARY KEY,
    fails INTEGER NOT NULL,
    locked_until TEXT,
    updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operating_logs (
    id {PK},
    equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    logged_at TEXT NOT NULL,
    data TEXT NOT NULL);
"""


def init_db():
    """Create the tables if they are missing. On a hosted database this runs once per server process, not on every page click."""
    kind, where = _target()
    key = (kind, str(where))
    if kind == "pg" and key in _READY:
        return
    pk = "BIGSERIAL PRIMARY KEY" if kind == "pg" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with _tx() as conn:
        for stmt in SCHEMA.replace("{PK}", pk).split(";"):
            if stmt.strip():
                conn.execute(stmt)
    _READY.add(key)


def _now():
    return datetime.now().isoformat(timespec="seconds")


LEGACY_ITERATIONS = 200_000
MAX_FAILS, LOCK_MINUTES = 5, 15
COMMON_PASSWORDS = {"password", "password1", "password12", "password123", "12345678", "123456789", "1234567890", "qwertyui", "qwerty123", "qwertyuiop",
                    "11111111", "00000000", "abcd1234", "abc12345", "iloveyou", "admin123", "welcome1", "letmein1", "plantpulse", "chemical1"}


def _iterations():
    return int(os.environ.get("PLANTPULSE_PBKDF2_ITERATIONS") or 600_000)


def _hash(password, salt_hex, iterations=None):
    """New hashes are stored as 'pbkdf2_sha256$rounds$hex' so the number of rounds can be raised later without locking anyone out."""
    n = iterations or _iterations()
    return f"pbkdf2_sha256${n}${hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), n).hex()}"


def _verify(password, salt_hex, stored):
    """Returns (is_correct, needs_upgrade). Accepts the old format (plain hex, 200,000 rounds) too."""
    if stored.startswith("pbkdf2_sha256$"):
        _, n, digest = stored.split("$")
        n = int(n)
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), n).hex()
        return hmac.compare_digest(digest, calc), n < _iterations()
    calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), LEGACY_ITERATIONS).hex()
    return hmac.compare_digest(stored, calc), True


def check_password(password, email=""):
    """Raise DBError if the password is too weak."""
    p, e = password or "", (email or "").strip().lower()
    local = e.split("@")[0]
    if len(p) < 8 or len(p) > 128 or p.lower() in COMMON_PASSWORDS or len(set(p)) < 4 or (e and p.lower() in (e, local)):
        raise DBError("Password must be 8 to 128 characters and not an easy-to-guess one (like password or 12345678).")


def create_user(name, email, password, role):
    name, email = (name or "").strip(), (email or "").strip().lower()
    if not name:
        raise DBError("Please enter your name.")
    if len(name) > 100 or len(email) > 254:
        raise DBError("The name or email is too long.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise DBError("Please enter a valid email address.")
    check_password(password, email)
    if role not in ROLES:
        raise DBError("Role must be student or engineer.")
    salt = secrets.token_hex(16)
    try:
        _, uid, _ = _run("INSERT INTO users (name,email,salt,password_hash,role,created_at) VALUES (?,?,?,?,?,?)",
                         (name, email, salt, _hash(password, salt), role, _now()))
    except IntegrityViolation:
        raise DBError("An account with this email already exists.")
    return {"id": uid, "name": name, "email": email, "role": role}


def _lock_minutes_left(email):
    rows, _, _ = _run("SELECT locked_until FROM login_failures WHERE email = ?", (email,))
    if rows and rows[0]["locked_until"]:
        left = (datetime.fromisoformat(rows[0]["locked_until"]) - datetime.now()).total_seconds()
        if left > 0:
            return max(1, int(left // 60) + (1 if left % 60 else 0))
    return 0


def _record_failure(email):
    """Count a failed attempt (for unknown emails too, so lockouts do not reveal which emails exist). Locks after MAX_FAILS."""
    now = datetime.now()
    _run("DELETE FROM login_failures WHERE updated_at < ?", ((now - timedelta(days=1)).isoformat(timespec="seconds"),))
    _run("""INSERT INTO login_failures (email,fails,locked_until,updated_at) VALUES (?,1,NULL,?)
            ON CONFLICT (email) DO UPDATE SET fails = login_failures.fails + 1, updated_at = excluded.updated_at""", (email, now.isoformat(timespec="seconds")))
    rows, _, _ = _run("SELECT fails FROM login_failures WHERE email = ?", (email,))
    if rows and rows[0]["fails"] >= MAX_FAILS:
        _run("UPDATE login_failures SET fails = 0, locked_until = ? WHERE email = ?", ((now + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds"), email))
        raise DBError(f"Too many failed attempts. Please try again in {LOCK_MINUTES} minutes.")


def _check_not_locked(email):
    left = _lock_minutes_left(email)
    if left:
        raise DBError(f"Too many failed attempts. Please try again in {left} minute(s).")


def authenticate(email, password):
    """The user dict if the email and password are right, else None. Raises DBError when the account is temporarily locked."""
    email = (email or "").strip().lower()[:254]
    _check_not_locked(email)
    rows, _, _ = _run("SELECT * FROM users WHERE email = ?", (email,))
    if not rows:
        _hash(password or "", "00" * 16)                        # same work as a real check, so timing does not reveal whether the email exists
        _record_failure(email)
        return None
    u = rows[0]
    ok, upgrade = _verify(password or "", u["salt"], u["password_hash"])
    if not ok:
        _record_failure(email)
        return None
    _run("DELETE FROM login_failures WHERE email = ?", (email,))
    if upgrade:                                                  # an old or weaker hash: store it again with the current number of rounds
        _run("UPDATE users SET password_hash = ? WHERE id = ?", (_hash(password, u["salt"]), u["id"]))
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"]}


def delete_account(user_id, password):
    """Permanently delete a user and everything they own, after checking their password."""
    rows, _, _ = _run("SELECT email FROM users WHERE id = ?", (user_id,))
    if not rows:
        raise DBError("Account not found.")
    if authenticate(rows[0]["email"], password) is None:
        raise DBError("The password is not correct.")
    _run("DELETE FROM users WHERE id = ?", (user_id,))
    return True


def add_equipment(user_id, eq_type, tag, location, params):
    tag = (tag or "").strip()
    if eq_type not in EQUIPMENT_TYPES:
        raise DBError("Equipment type must be heat_exchanger or pump.")
    if not tag:
        raise DBError("Please enter an equipment tag, for example JH-01.")
    try:
        _, eid, _ = _run("INSERT INTO equipment (user_id,eq_type,tag,location,params,created_at) VALUES (?,?,?,?,?,?)",
                         (user_id, eq_type, tag, (location or "").strip(), json.dumps(params), _now()))
    except IntegrityViolation:
        raise DBError(f"You already have equipment with the tag '{tag}'.")
    return eid


def list_equipment(user_id):
    rows, _, _ = _run("SELECT * FROM equipment WHERE user_id = ? ORDER BY id", (user_id,))
    return [{**dict(r), "params": json.loads(r["params"])} for r in rows]


def delete_equipment(user_id, equipment_id):
    """Delete only if the equipment belongs to this user. Returns True if something was deleted."""
    _, _, n = _run("DELETE FROM equipment WHERE id = ? AND user_id = ?", (equipment_id, user_id))
    return n > 0


def add_log(user_id, equipment_id, data):
    rows, _, _ = _run("SELECT id FROM equipment WHERE id = ? AND user_id = ?", (equipment_id, user_id))
    if not rows:
        raise DBError("Equipment not found.")
    _, lid, _ = _run("INSERT INTO operating_logs (equipment_id,logged_at,data) VALUES (?,?,?)",
                     (equipment_id, _now(), json.dumps(data)))
    return lid


def list_logs(user_id, equipment_id):
    rows, _, _ = _run("""SELECT l.* FROM operating_logs l JOIN equipment e ON e.id = l.equipment_id
                         WHERE e.id = ? AND e.user_id = ? ORDER BY l.id""", (equipment_id, user_id))
    return [{**dict(r), "data": json.loads(r["data"])} for r in rows]


def add_logs_bulk(user_id, equipment_id, rows):
    """Insert [(logged_at_iso, data_dict)] for this user's equipment. Skips timestamps already stored.
    Returns the number of rows inserted."""
    with _tx() as conn:
        if not conn.execute("SELECT 1 FROM equipment WHERE id = ? AND user_id = ?", (equipment_id, user_id)).fetchone():
            raise DBError("Equipment not found.")
        have = {r["logged_at"] for r in conn.execute("SELECT logged_at FROM operating_logs WHERE equipment_id = ?", (equipment_id,)).fetchall()}
        new = [(equipment_id, ts, json.dumps(d)) for ts, d in rows if ts not in have]
        conn.executemany("INSERT INTO operating_logs (equipment_id,logged_at,data) VALUES (?,?,?)", new)
        return len(new)


def delete_logs(user_id, equipment_id):
    """Delete all readings of this user's equipment. Returns the number deleted."""
    _, _, n = _run("DELETE FROM operating_logs WHERE equipment_id IN (SELECT id FROM equipment WHERE id = ? AND user_id = ?)",
                   (equipment_id, user_id))
    return n


# ---------------------------------------------------------------- validation log
def add_validation(user_id, source, module, problem, quantity, unit, reference, app_value, notes=""):
    source, quantity = (source or "").strip(), (quantity or "").strip()
    if not source:
        raise DBError("Please enter the source, for example the book name and page.")
    if not quantity:
        raise DBError("Please enter the quantity you compared, for example LMTD.")
    for name, v in (("textbook answer", reference), ("PlantPulse answer", app_value)):
        if not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
            raise DBError(f"The {name} must be a number.")
    _, vid, _ = _run("INSERT INTO validation_log (user_id,created_at,source,module,problem,quantity,unit,reference,app_value,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (user_id, _now(), source, module or "Other", (problem or "").strip(), quantity, (unit or "").strip(), float(reference), float(app_value), (notes or "").strip()))
    return vid


def list_validation(user_id):
    rows, _, _ = _run("SELECT * FROM validation_log WHERE user_id = ? ORDER BY id", (user_id,))
    return [dict(r) for r in rows]


def delete_validation(user_id, entry_id):
    _, _, n = _run("DELETE FROM validation_log WHERE id = ? AND user_id = ?", (entry_id, user_id))
    return n > 0


# ---------------------------------------------------------------- maintenance history
MAX_NOTE = 2000


def _parse_date(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        d = value
    else:
        try:
            d = date.fromisoformat(str(value).strip())
        except ValueError:
            raise DBError("Please enter a valid date.")
    if d.year < 1990:
        raise DBError("The date is too far in the past. Check the year.")
    if d > date.today() + timedelta(days=366):
        raise DBError("The date is more than a year in the future. Check the year.")
    return d


def _owns(conn, user_id, equipment_id):
    return conn.execute("SELECT 1 FROM equipment WHERE id = ? AND user_id = ?", (equipment_id, user_id)).fetchone() is not None


def add_maintenance(user_id, equipment_id, note_date, note):
    """Add a dated note to the maintenance history of this user's equipment. Returns the note id."""
    note = (note or "").strip()
    if not note:
        raise DBError("Please type a note.")
    if len(note) > MAX_NOTE:
        raise DBError(f"The note is too long (the limit is {MAX_NOTE} characters).")
    d = _parse_date(note_date)
    with _tx() as conn:
        if not _owns(conn, user_id, equipment_id):
            raise DBError("Equipment not found.")
        r = conn.execute("INSERT INTO maintenance_log (equipment_id,note_date,note,created_at) VALUES (?,?,?,?)",
                         (equipment_id, d.isoformat(), note, _now()))
        return r.lastrowid


def list_maintenance(user_id, equipment_id):
    rows, _, _ = _run("""SELECT m.* FROM maintenance_log m JOIN equipment e ON e.id = m.equipment_id
                         WHERE e.id = ? AND e.user_id = ? ORDER BY m.note_date DESC, m.id DESC""", (equipment_id, user_id))
    return [dict(r) for r in rows]


def list_all_maintenance(user_id):
    """Every note of every piece of equipment of this user, with the equipment tag."""
    rows, _, _ = _run("""SELECT e.tag, e.eq_type, m.id, m.equipment_id, m.note_date, m.note FROM maintenance_log m
                         JOIN equipment e ON e.id = m.equipment_id WHERE e.user_id = ? ORDER BY e.tag, m.note_date DESC, m.id DESC""", (user_id,))
    return [dict(r) for r in rows]


def delete_maintenance(user_id, note_id):
    _, _, n = _run("DELETE FROM maintenance_log WHERE id = ? AND equipment_id IN (SELECT id FROM equipment WHERE user_id = ?)", (note_id, user_id))
    return n > 0


# ---------------------------------------------------------------- 'keep me signed in' sessions
SESSION_DAYS = 14


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id, days=SESSION_DAYS):
    """Create a sign-in token. Only its hash is stored, so a copy of the database cannot be used to sign in."""
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    _run("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(timespec="seconds"),))
    _run("INSERT INTO sessions (token_hash,user_id,created_at,expires_at) VALUES (?,?,?,?)",
         (_hash_token(token), user_id, now.isoformat(timespec="seconds"), (now + timedelta(days=days)).isoformat(timespec="seconds")))
    return token


def user_from_session(token):
    """The user a valid, unexpired token belongs to, or None."""
    if not isinstance(token, str) or not 20 <= len(token) <= 200:
        return None
    rows, _, _ = _run("""SELECT u.id, u.name, u.email, u.role FROM sessions s JOIN users u ON u.id = s.user_id
                         WHERE s.token_hash = ? AND s.expires_at > ?""", (_hash_token(token), datetime.now().isoformat(timespec="seconds")))
    return dict(rows[0]) if rows else None


def delete_session(token):
    if isinstance(token, str) and token:
        _run("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))


# ---------------------------------------------------------------- alert settings (per piece of equipment)
DEFAULT_U_WARN, DEFAULT_U_CRIT = 10.0, 25.0


def _check_levels(warn, crit):
    if isinstance(warn, bool) or isinstance(crit, bool) or not all(isinstance(v, (int, float)) and v == v for v in (warn, crit)):
        raise DBError("The warning and alarm levels must be numbers.")
    if warn <= 0:
        raise DBError("The warning level must be above 0%.")
    if crit <= warn:
        raise DBError("The alarm level must be higher than the warning level.")
    if crit > 95:
        raise DBError("The alarm level cannot be above 95% loss.")


def get_alert_settings(user_id, equipment_id):
    """The user's own warning and alarm levels for the loss of U of this equipment, or the defaults (10% and 25%)."""
    rows, _, _ = _run("""SELECT a.u_warn_pct, a.u_crit_pct FROM alert_settings a JOIN equipment e ON e.id = a.equipment_id
                         WHERE e.id = ? AND e.user_id = ?""", (equipment_id, user_id))
    if rows:
        return {"u_warn_pct": rows[0]["u_warn_pct"], "u_crit_pct": rows[0]["u_crit_pct"], "custom": True}
    return {"u_warn_pct": DEFAULT_U_WARN, "u_crit_pct": DEFAULT_U_CRIT, "custom": False}


def set_alert_settings(user_id, equipment_id, warn, crit):
    _check_levels(warn, crit)
    with _tx() as conn:
        if not _owns(conn, user_id, equipment_id):
            raise DBError("Equipment not found.")
        conn.execute("""INSERT INTO alert_settings (equipment_id,u_warn_pct,u_crit_pct,updated_at) VALUES (?,?,?,?)
                        ON CONFLICT (equipment_id) DO UPDATE SET u_warn_pct = excluded.u_warn_pct, u_crit_pct = excluded.u_crit_pct, updated_at = excluded.updated_at""",
                     (equipment_id, float(warn), float(crit), _now()))


def reset_alert_settings(user_id, equipment_id):
    _run("DELETE FROM alert_settings WHERE equipment_id IN (SELECT id FROM equipment WHERE id = ? AND user_id = ?)", (equipment_id, user_id))
