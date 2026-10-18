"""Plain-text summary of a solved problem, for pasting into a report."""


def build_text(title, notes, given, results, warnings=()):
    """given: [(label, number, unit)], results: [(label, text)], notes: lines under the title."""
    lines = [f"PlantPulse - {title}", *notes, "", "Given"]
    lines += [f"  {label}: {value:g} {unit}".rstrip() for label, value, unit in given]
    lines += ["", "Results"] + [f"  {label}: {value}" for label, value in results]
    if warnings:
        lines += ["", "Notes"] + [f"  - {w}" for w in warnings]
    lines += ["", "Calculated with PlantPulse. A learning and screening tool: check important results against your reference."]
    return "\n".join(lines)
