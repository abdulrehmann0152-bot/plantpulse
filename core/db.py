"""SQLite storage: users, equipment and operating logs (no Streamlit code here)."""
import hashlib, hmac, json, os, re, secrets, sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "plantpulse.db"
ROLES = ("student", "engineer")
EQUIPMENT_TYPES = ("heat_exchanger", "pump")


class DBError(ValueError):
    """Friendly, user-facing database or validation error."""


def _path():
    return Path(os.environ.get("PLANTPULSE_DB") or DEFAULT_DB)


def _connect():
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _run(sql, args=()):
    """Run one statement, commit, and return (rows, lastrowid, rowcount)."""
    with closing(_connect()) as conn:
        with conn:
            cur = conn.execute(sql, args)
            return cur.fetchall(), cur.lastrowid, cur.rowcount


def init_db():
    with closing(_connect()) as conn:
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('student','engineer')),
                created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                eq_type TEXT NOT NULL CHECK (eq_type IN ('heat_exchanger','pump')),
                tag TEXT NOT NULL,
                location TEXT,
                params TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (user_id, tag));
            CREATE TABLE IF NOT EXISTS validation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                module TEXT NOT NULL,
                problem TEXT,
                quantity TEXT NOT NULL,
                unit TEXT,
                reference REAL NOT NULL,
                app_value REAL NOT NULL,
                notes TEXT);
            CREATE TABLE IF NOT EXISTS maintenance_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
                note_date TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS alert_settings (
                equipment_id INTEGER PRIMARY KEY REFERENCES equipment(id) ON DELETE CASCADE,
                u_warn_pct REAL NOT NULL,
                u_crit_pct REAL NOT NULL,
                updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS operating_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
                logged_at TEXT NOT NULL,
                data TEXT NOT NULL);
            """)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _hash(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200_000).hex()


def create_user(name, email, password, role):
    name, email = (name or "").strip(), (email or "").strip().lower()
    if not name:
        raise DBError("Please enter your name.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise DBError("Please enter a valid email address.")
    if len(password or "") < 6:
        raise DBError("Password must be at least 6 characters.")
    if role not in ROLES:
        raise DBError("Role must be student or engineer.")
    salt = secrets.token_hex(16)
    try:
        _, uid, _ = _run("INSERT INTO users (name,email,salt,password_hash,role,created_at) VALUES (?,?,?,?,?,?)",
                         (name, email, salt, _hash(password, salt), role, _now()))
    except sqlite3.IntegrityError:
        raise DBError("An account with this email already exists.")
    return {"id": uid, "name": name, "email": email, "role": role}


def authenticate(email, password):
    rows, _, _ = _run("SELECT * FROM users WHERE email = ?", ((email or "").strip().lower(),))
    if not rows:
        return None
    u = rows[0]
    if hmac.compare_digest(u["password_hash"], _hash(password or "", u["salt"])):
        return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"]}
    return None


def add_equipment(user_id, eq_type, tag, location, params):
    tag = (tag or "").strip()
    if eq_type not in EQUIPMENT_TYPES:
        raise DBError("Equipment type must be heat_exchanger or pump.")
    if not tag:
        raise DBError("Please enter an equipment tag, for example JH-01.")
    try:
        _, eid, _ = _run("INSERT INTO equipment (user_id,eq_type,tag,location,params,created_at) VALUES (?,?,?,?,?,?)",
                         (user_id, eq_type, tag, (location or "").strip(), json.dumps(params), _now()))
    except sqlite3.IntegrityError:
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
    with closing(_connect()) as conn:
        with conn:
            if not conn.execute("SELECT 1 FROM equipment WHERE id = ? AND user_id = ?", (equipment_id, user_id)).fetchone():
                raise DBError("Equipment not found.")
            have = {r[0] for r in conn.execute("SELECT logged_at FROM operating_logs WHERE equipment_id = ?", (equipment_id,))}
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
    with closing(_connect()) as conn:
        with conn:
            if not _owns(conn, user_id, equipment_id):
                raise DBError("Equipment not found.")
            cur = conn.execute("INSERT INTO maintenance_log (equipment_id,note_date,note,created_at) VALUES (?,?,?,?)",
                               (equipment_id, d.isoformat(), note, _now()))
            return cur.lastrowid


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
    with closing(_connect()) as conn:
        with conn:
            if not _owns(conn, user_id, equipment_id):
                raise DBError("Equipment not found.")
            conn.execute("INSERT OR REPLACE INTO alert_settings (equipment_id,u_warn_pct,u_crit_pct,updated_at) VALUES (?,?,?,?)",
                         (equipment_id, float(warn), float(crit), _now()))


def reset_alert_settings(user_id, equipment_id):
    _run("DELETE FROM alert_settings WHERE equipment_id IN (SELECT id FROM equipment WHERE id = ? AND user_id = ?)", (equipment_id, user_id))
