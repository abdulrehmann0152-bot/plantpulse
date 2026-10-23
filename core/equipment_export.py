"""CSV export of the equipment list and the maintenance history. Opens correctly in Excel (UTF-8 with a byte-order mark)."""
import csv
import io

from core.templates import FLOW_LABELS

HEADERS = ["Tag", "Type", "Location", "Added", "Heat transfer area (m2)", "Clean U (W/m2K)", "Flow arrangement", "Pipe diameter (mm)", "Pipe length (m)",
           "Pipe material", "Fittings K", "Static head (m)", "Pump efficiency (%)", "Curve flow 1 (m3/h)", "Curve head 1 (m)", "Curve flow 2 (m3/h)",
           "Curve head 2 (m)", "Curve flow 3 (m3/h)", "Curve head 3 (m)", "Maintenance notes", "Last maintenance date", "Last maintenance note"]
TYPE_NAMES = {"heat_exchanger": "Heat exchanger", "pump": "Pump and pipeline"}


def safe(value):
    """Stop a spreadsheet from running text as a formula (a cell that starts with = + - @ is prefixed with an apostrophe)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _write(rows):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\r\n").writerows(rows)
    return buf.getvalue()


def equipment_csv(items, notes_by_equipment=None):
    """items: db.list_equipment() rows. notes_by_equipment: {equipment_id: [notes newest first]}."""
    notes_by_equipment = notes_by_equipment or {}
    rows = [HEADERS]
    for e in items:
        p, notes = e["params"], notes_by_equipment.get(e["id"], [])
        curve = p.get("curve") or []
        curve_cells = []
        for i in range(3):
            curve_cells += list(curve[i]) if i < len(curve) else ["", ""]
        rows.append([safe(e["tag"]), TYPE_NAMES.get(e["eq_type"], e["eq_type"]), safe(e["location"] or ""), e["created_at"][:10],
                     p.get("area_m2", ""), p.get("u_clean", ""), FLOW_LABELS.get(p.get("flow"), p.get("flow", "")), p.get("d_mm", ""), p.get("length_m", ""),
                     p.get("material", ""), p.get("sum_k", ""), p.get("static_m", ""), p.get("eta_pct", "")] + curve_cells +
                    [len(notes), notes[0]["note_date"] if notes else "", safe(notes[0]["note"]) if notes else ""])
    return _write(rows)


def maintenance_csv(rows):
    """rows: db.list_all_maintenance()."""
    out = [["Tag", "Type", "Date", "Note"]]
    out += [[safe(r["tag"]), TYPE_NAMES.get(r["eq_type"], r["eq_type"]), r["note_date"], safe(r["note"])] for r in rows]
    return _write(out)


def to_bytes(text):
    return ("\ufeff" + text).encode("utf-8")
