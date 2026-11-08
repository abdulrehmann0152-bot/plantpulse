import ast, colorsys, glob, os, re, sys, tomllib
import xml.etree.ElementTree as ET
import pytest
from streamlit.testing.v1 import AppTest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core import branding as b

ROOT = os.path.dirname(os.path.dirname(__file__))
TAGLINE = "Learn it in class. Monitor it in the plant."                       # the user's tagline, written out here so a change in the code is caught
CODE = [os.path.join(ROOT, "app.py"), os.path.join(ROOT, "check_database.py")] + sorted(glob.glob(os.path.join(ROOT, "views", "*.py"))) + \
       sorted(glob.glob(os.path.join(ROOT, "core", "*.py"))) + sorted(glob.glob(os.path.join(ROOT, "calc_engine", "*.py")))
PRESENTATION = [p for p in CODE if os.path.basename(p) not in ("db.py",) and ("views" in p or "core" in p or p.endswith("app.py")) and "calc_engine" not in p]


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANTPULSE_DB", str(tmp_path / "d17.db"))


def _strings(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


# ====================================================================== 1. brand name
ALLOWED = [r"PLANTPULSE_[A-Z0-9_]+", r"setup_plantpulse\.bat", r"plantpulse\.db", r"@plantpulse\.invalid"]          # identifiers, file names and an internal test address


def test_the_brand_is_always_spelled_PlantPulse_in_code_strings():
    bad = []
    for path in CODE:
        if os.path.basename(path) == "db.py":                       # db.py is protected, and its only hit is 'plantpulse' in the list of passwords that are refused (never shown)
            continue
        for s in _strings(path):
            cleaned = s
            for allowed in ALLOWED:
                cleaned = re.sub(allowed, "", cleaned)
            bad += [(os.path.basename(path), m.group(0)) for m in re.finditer(r"(?i)plant[ _-]?pulse", cleaned) if m.group(0) != "PlantPulse"]
    assert bad == []

def _all_text(at):
    out = []
    for kind in ("markdown", "title", "header", "subheader", "caption", "text", "info", "warning", "error", "success"):
        out += [e.value for e in at.get(kind)]
    out += [t.label for t in at.tabs] + [e.label for e in at.expander] + [b_.label for b_ in at.button]
    return " ".join(str(x) for x in out)

def test_no_page_shows_a_wrong_spelling_of_the_name():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    seen = [_all_text(at)]
    at.button(key="do_guest").click().run()
    for page in sorted(glob.glob(os.path.join(ROOT, "views", "*.py"))):
        if os.path.basename(page) == "login.py":
            continue
        at.switch_page(f"views/{os.path.basename(page)}").run()
        assert not at.exception, page
        seen.append(_all_text(at))
    text = " ".join(seen)
    assert "PlantPulse" in text and not re.search(r"PLANTPULSE|Plantpulse|plantpulse|PlantPULSE|Plant Pulse|Plant-Pulse", text)

# ====================================================================== 2. tagline
def _visible(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()

def test_the_tagline_text_is_exactly_the_original_everywhere():
    assert b.TAGLINE == TAGLINE and b.BRAND == "PlantPulse"
    assert TAGLINE in _visible(b.HERO).replace(" .", ".").replace("class. Monitor", "class. Monitor")
    with open(os.path.join(ROOT, "core", "report.py"), encoding="utf-8") as f:
        assert f'"{TAGLINE}"' in f.read()                                                 # the PDF header keeps it too

def test_the_header_shows_the_name_and_tagline_with_a_clear_hierarchy():
    html = b.HERO.replace("{about}", "")
    assert re.sub(r"<[^>]+>", "", re.search(r'<p class="pp-brand">.*?</p>', html).group(0)) == "PlantPulse"               # the two-tone name still reads as one word
    assert re.sub(r"<[^>]+>", "", re.search(r'<p class="pp-tagline">.*?</p>', html).group(0)) == TAGLINE
    assert "<b>Monitor it in the plant.</b>" in html                                       # second sentence emphasised, text unchanged

def test_login_and_home_show_the_header():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    heroes = [m for m in at.markdown if 'class="pp-hero"' in m.value]
    assert len(heroes) == 1 and heroes[0].allow_html and TAGLINE in _visible(heroes[0].value) and b.DESCRIPTION in heroes[0].value
    at.button(key="do_guest").click().run()
    heroes = [m for m in at.markdown if 'class="pp-hero"' in m.value]
    assert len(heroes) == 1 and b.DESCRIPTION not in heroes[0].value                       # on Home the description is in the welcome sentence instead
    welcome = [m for m in at.markdown if m.value.startswith("Welcome,")]
    assert len(welcome) == 1 and b.DESCRIPTION in welcome[0].value and not welcome[0].allow_html

def test_home_keeps_every_module_link_in_two_labelled_groups():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.button(key="do_guest").click().run()
    assert not at.exception and [s.value for s in at.subheader] == ["Calculate and solve", "Learn, monitor and record"]
    labels = {p.label for p in at.get("page_link")}
    assert {"Heat Exchanger", "Pump & Pipeline", "HX Solver", "Pipe Solver", "Study Tutor", "Monitor", "Validation Log", "My Equipment"} <= labels

def test_user_text_never_goes_into_the_html_blocks():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    name = "<img src=x onerror=alert(1)>"
    at.text_input(key="reg_name").input(name); at.text_input(key="reg_email").input("x@plant.pk"); at.text_input(key="reg_pw").input("secret12")
    at.button(key="do_register").click().run()
    html_blocks = [m for m in at.markdown if m.allow_html]
    assert html_blocks and all(name not in m.value and "onerror" not in m.value for m in html_blocks)
    assert any(name in m.value and not m.allow_html for m in at.markdown)                  # the name appears only in the escaped welcome text

# ====================================================================== 3. colours and theme
def _hue_is_green(hex_color):
    r, g, bl = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, s, v = colorsys.rgb_to_hsv(r, g, bl)
    return 0.22 <= h <= 0.50 and s > 0.15 and v > 0.2                                       # hues from yellow-green to teal

def _luminance(hex_color):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, bl = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(bl)

def _contrast(a, c):
    la, lc = sorted((_luminance(a), _luminance(c)), reverse=True)
    return (la + 0.05) / (lc + 0.05)

def test_theme_uses_the_brand_palette_and_green_only_for_positive_status():
    with open(os.path.join(ROOT, ".streamlit", "config.toml"), "rb") as f:
        cfg = tomllib.load(f)
    t = cfg["theme"]
    assert (t["primaryColor"], t["backgroundColor"], t["secondaryBackgroundColor"]) == ("#0B2545", "#FFFFFF", "#F4F7FA")
    assert not _hue_is_green(t["primaryColor"]) and not _hue_is_green(t["linkColor"]) and t["greenColor"] == b.GREEN and _hue_is_green(t["greenColor"])
    assert _contrast(t["textColor"], t["backgroundColor"]) >= 7 and _contrast(t["linkColor"], t["backgroundColor"]) >= 4.5      # readable body text and links
    assert _contrast(b.GREEN, "#FFFFFF") >= 4.5 and _contrast(b.GREY, "#FFFFFF") >= 4.5 and _contrast(b.NAVY, b.LIGHT) >= 10
    assert cfg["browser"]["gatherUsageStats"] is False                                      # the earlier setting is kept

def test_the_only_green_in_the_code_is_the_status_green_and_teal_is_gone():
    greens, found = set(), set()
    for path in PRESENTATION:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        assert not re.search(r"(?i)13A89E|E8F7F5|2E9E5B|\bTEAL\b", src), path
        for hx in re.findall(r"#[0-9A-Fa-f]{6}\b", src):
            found.add(hx.upper())
            if _hue_is_green(hx):
                greens.add(hx.upper())
    assert greens == {b.GREEN}, greens
    assert b.BLUE in found and b.NAVY in found

def test_pdf_palette_matches_the_brand():
    from core import report, validation_report
    hexof = lambda rgb: "#%02X%02X%02X" % rgb
    assert hexof(report.NAVY) == b.NAVY and hexof(report.BLUE) == b.BLUE and hexof(report.GRN) == b.GREEN and hexof(report.LIGHT) == b.LIGHT and hexof(report.RED) == b.RED
    assert validation_report.BLUE is report.BLUE

def test_stylesheet_has_the_palette_a_responsive_rule_and_no_animation_or_outside_resources():
    css = b.CSS
    for token in (b.NAVY, b.BLUE, b.LIGHT, b.GREY, b.LINE, "@media (max-width: 640px)", ".pp-hero", ".pp-brand", ".pp-tagline", "h1", "h2", "h3", '[data-testid="stSidebar"]'):
        assert token in css, token
    assert not re.search(r"(?i)animation|@keyframes|transition|transform|@import|url\(|https?:|<script|javascript:", css)
    assert css.count("<style>") == 1 and css.count("</style>") == 1

def test_the_stylesheet_is_added_once_to_every_page_run():
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    assert sum("<style>" in m.value and ".pp-hero" in m.value for m in at.markdown) == 1
    at.button(key="do_guest").click().run()
    for page in ("heat_exchanger", "solver", "tutor", "monitor", "equipment"):
        at.switch_page(f"views/{page}.py").run()
        assert not at.exception and sum(".pp-hero" in m.value and "<style>" in m.value for m in at.markdown) == 1, page

# ====================================================================== 4. logo files
@pytest.mark.parametrize("name", ["logo.svg", "icon.svg"])
def test_logo_files_are_valid_small_and_safe(name):
    path = os.path.join(ROOT, "assets", name)
    assert os.path.getsize(path) < 5000
    root = ET.parse(path).getroot()
    text = ET.tostring(root, encoding="unicode")
    assert root.tag.endswith("svg") and not re.search(r"(?i)<script|href|onload|onclick|javascript:|<image|<foreignObject", text)
    assert root.get("{http://www.w3.org/2000/svg}x") is None and root.get("aria-label") == "PlantPulse"
    if name == "logo.svg":
        assert "".join(t.text or "" for t in root.iter() if t.tag.endswith("tspan")) == "PlantPulse"

def test_the_app_runs_with_the_logo_and_without_it(monkeypatch, tmp_path):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    assert not at.exception
    monkeypatch.setattr(b, "ASSETS", tmp_path)                                              # missing files must not break the page
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    assert not at.exception and at.markdown
