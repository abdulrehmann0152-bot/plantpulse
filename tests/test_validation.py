import os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import db, validation as val
from core.validation_report import build_validation_pdf
from calc_engine import solver as sv


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "v.db"))
    db.init_db()

def _user(email="a@uet.edu.pk"):
    return db.create_user("Ali", email, "secret12", "student")

def test_difference_and_verdict_thresholds():
    assert val.diff_pct(100, 101) == pytest.approx(1.0) and val.diff_pct(100, 98) == pytest.approx(-2.0)
    assert [val.verdict(d) for d in (0, 2.0, -2.0, 2.01, 5.0, -5.0, 5.01, -30)] == ["Match", "Match", "Match", "Acceptable", "Acceptable", "Acceptable", "Check", "Check"]
    assert val.diff_pct(0, 0) == 0.0 and val.diff_pct(0, 1) == float("inf") and val.verdict(float("inf")) == "Check"
    assert val.diff_pct(-50, -51) == pytest.approx(-2.0)         # relative to the magnitude of the reference: -51 is below -50

def test_summary_counts_and_averages():
    rows = val.enrich([dict(created_at="2026-10-10T10:00:00", source="b", module="m", problem="", quantity="q", unit="", reference=100.0, app_value=v, notes="") for v in (100, 101.5, 104, 120)])
    s = val.summarize(rows)
    assert (s["n"], s["match"], s["acceptable"], s["check"]) == (4, 2, 1, 1)
    assert s["mean_abs"] == pytest.approx((0 + 1.5 + 4 + 20) / 4) and s["max_abs"] == pytest.approx(20)
    assert val.summarize([])["mean_abs"] is None

def test_crud_and_ownership():
    a, b = _user("a@b.com"), _user("c@d.com")
    vid = db.add_validation(a["id"], "Cengel p.640", "Heat exchanger", "Oil cooler", "LMTD", "K", 99.7, 99.67, "chart F")
    assert db.list_validation(b["id"]) == [] and db.delete_validation(b["id"], vid) is False
    e = db.list_validation(a["id"])[0]
    assert (e["source"], e["quantity"], e["reference"], e["app_value"], e["notes"]) == ("Cengel p.640", "LMTD", 99.7, 99.67, "chart F")
    assert db.delete_validation(a["id"], vid) is True and db.list_validation(a["id"]) == []

def test_validation_rules():
    u = _user()
    for bad in (dict(source=" "), dict(quantity=""), dict(reference=float("nan")), dict(app_value=float("inf")), dict(reference="12")):
        a = dict(user_id=u["id"], source="s", module="m", problem="", quantity="q", unit="", reference=1.0, app_value=1.0); a.update(bad)
        with pytest.raises(db.DBError):
            db.add_validation(**a)

def test_csv_export_has_every_entry():
    u = _user()
    db.add_validation(u["id"], "Book, p.1", "Pump", "Pump power", "Shaft power", "kW", 10.0, 10.1, "note, with comma")
    db.add_validation(u["id"], "Book p.2", "Other", "", "X", "", 0.0, 3.0)
    csv_text = val.to_csv(val.enrich(db.list_validation(u["id"])))
    lines = csv_text.strip().splitlines()
    assert len(lines) == 3 and "+1.00" in lines[1] and "Match" in lines[1] and '"note, with comma"' in lines[1] and "n/a" in lines[2]

def test_solver_results_can_be_copied_into_the_log():
    hx = val.hx_values(sv.solve_hx("shell_1_2", 95, 60, 25, 45, m_hot=12, cp_hot=3.6, cp_cold=4.18, area=80, f_given=0.92))
    assert hx["Heat duty Q"][0] == pytest.approx(1512) and hx["Overall U"][1] == "W/m2K" and hx["Correction factor F"][0] == 0.92 and "Cold flow" in hx
    assert set(val.hx_values(sv.solve_hx("counter", 100, 60, 20, 50))) == {"LMTD, counter-flow", "LMTD, parallel flow"}
    p = val.pipe_values(sv.solve_pipe(100, 100, 200, 998.2, 1.002e-3, 0.045, 8, 10, 0, 70))
    assert {"Velocity", "Friction pressure drop", "Total head required", "Hydraulic power", "Shaft power"} <= set(p)
    assert "Flow found" in val.pipe_values(sv.flow_from_head(5, 100, 200, 998.2, 1.002e-3, 0.045, 8))

def test_pdf_note_builds_for_empty_normal_and_odd_text():
    u = {"name": "Ali", "role": "student"}
    assert build_validation_pdf([], val.summarize([]), u)[:5] == b"%PDF-"
    rows = val.enrich([dict(created_at="2026-10-10T10:00:00", source="Çengel – p.640 η", module="Heat exchanger", problem="", quantity="LMTD", unit="K",
                            reference=99.7, app_value=99.67, notes="F ≥ 0.9 read from chart") for _ in range(30)])
    pdf = build_validation_pdf(rows, val.summarize(rows), {"name": "عبد", "role": "engineer"})
    assert pdf[:5] == b"%PDF-" and pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages") >= 2


def test_tiny_differences_never_show_as_negative_zero():
    assert val.fmt_diff(-0.001) == "0.00" and val.fmt_diff(0.004) == "0.00" and val.fmt_diff(-0.2) == "-0.20" and val.fmt_diff(1.234) == "+1.23" and val.fmt_diff(float("inf")) == "n/a"
