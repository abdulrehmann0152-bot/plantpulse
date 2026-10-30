"""Pick the notes to draw as markers on a time chart."""
import pandas as pd


def event_markers(notes, t_min, t_max, limit=8, width=28):
    """notes: db.list_maintenance() rows. Returns [{'date': Timestamp, 'text': short label}] for notes inside [t_min, t_max], oldest first.

    Only the `limit` most recent notes are kept so a chart never fills with labels.
    """
    lo, hi = pd.Timestamp(t_min).normalize(), pd.Timestamp(t_max).normalize()
    inside = []
    for n in notes:
        d = pd.Timestamp(n["note_date"])
        if lo <= d <= hi:
            first_line = n["note"].strip().splitlines()[0].strip()
            inside.append({"date": d, "text": first_line if len(first_line) <= width else first_line[:width - 1].rstrip() + "…"})
    inside.sort(key=lambda m: m["date"])
    return inside[-limit:]
