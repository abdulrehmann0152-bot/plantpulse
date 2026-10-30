"""Save an imported dataset and, if the user wrote one, its note."""
import pandas as pd

from calc_engine import monitor as mon
from core import db


def save_import(user_id, equipment_id, df, note_date=None, note=""):
    """Store the readings of `df` (already parsed and converted to engine units). Returns (new_rows, message).

    A note such as 'After chemical cleaning' is saved in the equipment's maintenance history, with the dated range of the import.
    """
    new = db.add_logs_bulk(user_id, equipment_id, mon.rows_for_db(df))
    message = f"Imported {new} new reading(s)."
    if note and note.strip():
        first, last = pd.Timestamp(df["timestamp"].min()).date(), pd.Timestamp(df["timestamp"].max()).date()
        text = f"{note.strip()}\nData import: {new} new reading(s), {first} to {last}."
        try:
            db.add_maintenance(user_id, equipment_id, note_date or last, text)
            message += " The note was saved with the equipment history."
        except db.DBError as err:
            message += f" The readings are saved, but the note was not: {err}"
    return new, message
