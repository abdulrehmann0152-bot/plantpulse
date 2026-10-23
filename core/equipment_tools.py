"""Small helpers for the equipment page."""
import re


def next_tag(tag, existing=()):
    """Suggest the next free tag: CWP-01 -> CWP-02, P-9 -> P-10, 'Pump A' -> 'Pump A-2'. Case-insensitive against `existing`."""
    tag = (tag or "").strip()
    if not tag:
        return ""
    taken = {t.strip().lower() for t in existing}
    m = re.match(r"^(.*?)(\d+)$", tag)
    prefix, number = (m.group(1), m.group(2)) if m else (tag + "-", "1")
    width, n = len(number), int(number)
    while True:
        n += 1
        candidate = f"{prefix}{n:0{width}d}"
        if candidate.lower() not in taken:
            return candidate
