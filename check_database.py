"""Check the database connection BEFORE you deploy.

Run:  python check_database.py

It reports where PlantPulse would keep its data, creates the tables if they are missing, and does one safe write-and-delete test.
It never prints the database address or password.
"""
import sys
from datetime import datetime

from core import db


def main():
    try:
        info = db.storage_info()
        print(f"Storage: {info['kind']}" + (" (TEMPORARY: data can disappear on the cloud)" if info["temporary"] else ""))
        db.init_db()
        stamp = datetime.now().isoformat(timespec="seconds")
        db._run("INSERT INTO login_failures (email,fails,locked_until,updated_at) VALUES (?,0,NULL,?)", ("connection-check@plantpulse.invalid", stamp))
        db._run("DELETE FROM login_failures WHERE email = ?", ("connection-check@plantpulse.invalid",))
        print("OK: connected, the tables are ready, and a test write and delete worked.")
        if not info["hosted"]:
            print("Note: this is the local file. To use the hosted database, set DATABASE_URL (see DEPLOY.md).")
        return 0
    except db.DBError as err:
        print(f"FAILED: {err}")
    except Exception as err:                                  # never print the details: they could include the address
        print(f"FAILED: unexpected {type(err).__name__}. Check the address, the password and that the database allows connections.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
