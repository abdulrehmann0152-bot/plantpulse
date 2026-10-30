"""PDF 'validation note' built from the validation log."""
from datetime import date, datetime

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



class _CertPDF(_PDF):
    title_text = "PlantPulse | Validation Certificate"

    def footer(self):
        self.set_y(-16)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*NAVY)
        self.cell(0, 4, "Verified by PlantPulse Engineering Engine", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*GREY)
        self.cell(0, 4, f"Page {self.page_no()}", align="C")


RESULT_COLOR = {"Match": GRN, "Acceptable": AMB, "Check": RED}
RESULT_TEXT = {"Match": "Match (within 2%)", "Acceptable": "Acceptable (within 5%)", "Check": "OUTSIDE TOLERANCE"}


def build_certificate(entries, user, project="", on=None, compress=True):
    """A one-or-more page certificate listing each comparison. entries must be enriched (core.validation.enrich)."""
    on = on or date.today()
    pdf = _CertPDF(format="A4")
    pdf.set_compression(compress)
    pdf.set_margins(15, 20, 15)
    pdf.set_auto_page_break(True, margin=22)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 10, "Validation Certificate", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY)
    role = "Student" if user.get("role") == "student" else "Plant engineer"
    pdf.cell(0, 5, _t(f"Application: PlantPulse   |   Date: {on:%d %b %Y}   |   Prepared by: {user.get('name', '-')} ({role})"), new_x="LMARGIN", new_y="NEXT")
    if project.strip():
        pdf.cell(0, 5, _t(f"Project / course: {project.strip()}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    n = len(entries)
    counts = {k: sum(e["verdict"] == k for e in entries) for k in ("Match", "Acceptable", "Check")}
    _heading(pdf, "Summary")
    if n == 0:
        _para(pdf, "No entries were selected for this certificate.")
    else:
        _para(pdf, f"{n} quantity(ies) calculated by PlantPulse and compared with reference answers from the sources listed below.")
        _para(pdf, f"- Match (within 2%): {counts['Match']}    - Acceptable (within 5%): {counts['Acceptable']}    - Outside tolerance: {counts['Check']}")
        if counts["Check"]:
            _para(pdf, "This certificate includes entries outside the 5% tolerance. They are marked and are not confirmed by this document.", 9, RED, True)
    pdf.ln(2)

    if entries:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*NAVY)
        pdf.set_draw_color(200, 205, 210)
        with pdf.table(col_widths=(52, 34, 24, 24, 20, 26), text_align="LEFT", line_height=4.2,
                       headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=NAVY)) as table:
            row = table.row()
            for h in ("Source", "Quantity (unit)", "Textbook answer", "PlantPulse answer", "Difference %", "Result"):
                row.cell(h)
            for e in entries:
                row = table.row()
                for v in (e["source"], f"{e['quantity']} ({e['unit']})" if e["unit"] else e["quantity"], f"{e['reference']:.6g}", f"{e['app_value']:.6g}", fmt_diff(e["diff_pct"])):
                    row.cell(_t(v))
                row.cell(RESULT_TEXT[e["verdict"]], style=FontFace(emphasis="BOLD", color=RESULT_COLOR[e["verdict"]]))
        details = [e for e in entries if e["problem"] or e["notes"]]
        if details:
            pdf.ln(3)
            _heading(pdf, "Problems and notes")
            for e in details:
                bits = " | ".join(x for x in (e["problem"], e["notes"]) if x)
                _para(pdf, f"- {e['quantity']} ({e['source']}): {bits}", 8)
    pdf.ln(4)
    if pdf.get_y() > 200:
        pdf.add_page()
    _heading(pdf, "What this certificate shows")
    _para(pdf, "Each row compares the answer calculated by PlantPulse with a reference answer that the user typed in from the cited source. "
               "PlantPulse's calculation engine confirms that its own result matches that reference within the stated tolerance. "
               "It has not independently checked the reference answer or the source, which remain the responsibility of the person who entered them. "
               "Difference % = (PlantPulse - reference) / reference x 100.", 8.5)
    pdf.ln(8)
    y = pdf.get_y()
    pdf.set_draw_color(*GREY)
    pdf.line(15, y + 8, 85, y + 8)
    pdf.line(110, y + 8, 195, y + 8)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*GREY)
    pdf.set_xy(15, y + 9)
    pdf.cell(70, 4, "Prepared by (signature)")
    pdf.set_xy(110, y + 9)
    pdf.cell(85, 4, "Supervisor (signature and date)")
    return bytes(pdf.output())
