"""PDF 'validation note' built from the validation log."""
from datetime import datetime

from fpdf import FontFace

from core.validation import fmt_diff
from core.report import NAVY, TEAL, RED, AMB, GRN, GREY, _PDF, _heading, _para, _t

COLORS = {"Match": GRN, "Acceptable": AMB, "Check": RED}


def build_validation_pdf(entries, summary, user):
    """entries must be enriched (see core.validation.enrich). Returns bytes."""
    pdf = _PDF(format="A4")
    pdf.title_text = "PlantPulse | Validation Note"
    pdf.set_margins(15, 20, 15)
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "Validation of PlantPulse against reference solutions", new_x="LMARGIN", new_y="NEXT")
    role = "Student" if user.get("role") == "student" else "Plant engineer"
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 5, _t(f"Prepared by: {user.get('name', '-')} ({role})   |   Date: {datetime.now():%d %b %Y}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    _heading(pdf, "Summary")
    if summary["n"] == 0:
        _para(pdf, "No validation entries recorded yet.")
    else:
        share = lambda k: f"{summary[k]} of {summary['n']} ({summary[k] / summary['n'] * 100:.0f}%)"
        _para(pdf, f"{summary['n']} quantities compared with textbook or independent reference answers.")
        _para(pdf, f"- Match (within 2%): {share('match')}")
        _para(pdf, f"- Acceptable (within 5%): {share('acceptable')}")
        _para(pdf, f"- To check (above 5%): {share('check')}")
        if summary["mean_abs"] is not None:
            _para(pdf, f"- Mean absolute difference: {summary['mean_abs']:.2f}%, largest: {summary['max_abs']:.2f}%")
    pdf.ln(2)

    _heading(pdf, "Results")
    if entries:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*NAVY)
        pdf.set_draw_color(200, 205, 210)
        with pdf.table(col_widths=(34, 22, 36, 22, 22, 18, 26), text_align="LEFT", line_height=4.2,
                       headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=NAVY)) as table:
            row = table.row()
            for h in ("Source", "Module", "Quantity", "Textbook", "PlantPulse", "Diff %", "Verdict"):
                row.cell(h)
            for e in entries:
                d = e["diff_pct"]
                row = table.row()
                for v in (e["source"], e["module"], f"{e['quantity']} ({e['unit']})" if e["unit"] else e["quantity"], f"{e['reference']:.5g}",
                          f"{e['app_value']:.5g}", fmt_diff(d), e["verdict"]):
                    row.cell(_t(v))
        notes = [e for e in entries if e["notes"]]
        if notes:
            pdf.ln(3)
            _heading(pdf, "Notes on individual entries")
            for e in notes:
                _para(pdf, f"- {e['quantity']} ({e['source']}): {e['notes']}", 8)
    pdf.ln(3)
    if pdf.get_y() > 215:
        pdf.add_page()
    _heading(pdf, "Method")
    _para(pdf, "Each row compares the value calculated by PlantPulse with the answer from a textbook or from an independent hand calculation. "
               "Difference % = (PlantPulse - reference) / reference x 100. Small differences are expected from rounding, property values, "
               "and chart-read factors (for example an LMTD correction factor F read from a chart instead of calculated).", 8.5)
    _heading(pdf, "Scope limits")
    _para(pdf, "PlantPulse currently covers single-phase heat exchangers using the LMTD and effectiveness-NTU methods (counter-flow, parallel flow, "
               "1 shell pass with 2 or more even tube passes), and single-pipe flow and pump problems for liquids. It does not yet cover condensation or "
               "boiling, other exchanger geometries, two-phase flow, pipe networks, or compressible flow.", 8.5)
    return bytes(pdf.output())
