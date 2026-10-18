"""SQLite storage: users, equipment and operating logs (no Streamlit code here)."""
import hashlib, hmac, json, os, re, secrets, sqlite3
from contextlib import closing
from datetime import datetime
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
