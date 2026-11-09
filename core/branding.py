"""PlantPulse look and feel: one palette, one stylesheet, one header. Presentation only: nothing here touches calculations or data.

The stylesheet and the header are fixed text written here. Never put text typed by a user into them.
"""
from pathlib import Path

import streamlit as st

BRAND = "PlantPulse"
TAGLINE = "Learn it in class. Monitor it in the plant."
DESCRIPTION = "A mini digital twin and problem solver for heat exchangers, pipes and pumps."

NAVY, BLUE, LIGHT, GREY, LINE = "#0B2545", "#2F6DA8", "#F4F7FA", "#6B7280", "#E3E8EF"
GREEN, AMBER, RED = "#2E7D4F", "#F5A623", "#D64550"            # status colours: green only for healthy / successful, amber for watch, red for alarm

ASSETS = Path(__file__).resolve().parent.parent / "assets"

CSS = f"""
<style>
:root {{ --pp-navy:{NAVY}; --pp-blue:{BLUE}; --pp-light:{LIGHT}; --pp-grey:{GREY}; --pp-line:{LINE}; }}

/* page rhythm */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px; }}

/* headings: navy, one scale on every page */
h1, h2, h3, h4 {{ color: var(--pp-navy); letter-spacing: -0.01em; }}
h1 {{ font-size: 2rem; font-weight: 800; line-height: 1.2; margin-bottom: 0.35rem; }}
h2 {{ font-size: 1.5rem; font-weight: 700; margin-top: 1.4rem; }}
h3 {{ font-size: 1.2rem; font-weight: 700; margin-top: 1.1rem; }}
h4 {{ font-size: 1.05rem; font-weight: 600; }}

/* secondary information: soft grey */
[data-testid="stCaptionContainer"] {{ color: var(--pp-grey); }}

/* sidebar */
[data-testid="stSidebar"] {{ background: var(--pp-light); border-right: 1px solid var(--pp-line); }}

/* cards, metrics, expanders */
[data-testid="stMetric"] {{ background: var(--pp-light); border: 1px solid var(--pp-line); border-radius: 10px; padding: 0.7rem 1rem; }}
[data-testid="stMetricLabel"] {{ color: var(--pp-grey); }}
[data-testid="stMetricValue"] {{ color: var(--pp-navy); font-weight: 700; }}

/* KPI cards: show the whole value and unit (Streamlit cuts long values with "..." by default). The value may wrap onto a second line instead. */
[data-testid="stMetricValue"], [data-testid="stMetricValue"] *, [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] *, [data-testid="stMetricDelta"], [data-testid="stMetricDelta"] * {{
  overflow: visible !important; text-overflow: clip !important; white-space: normal !important; overflow-wrap: anywhere; word-break: normal; max-width: 100%; }}
[data-testid="stMetricValue"] {{ font-size: clamp(1.25rem, 1.1rem + 0.9vw, 1.9rem); line-height: 1.2; }}
[data-testid="stMetricValue"] * {{ font-size: inherit; line-height: inherit; }}
[data-testid="stExpander"] {{ border: 1px solid var(--pp-line); border-radius: 10px; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 12px; }}
button[role="tab"] {{ font-weight: 600; }}

/* the PlantPulse header block */
.pp-hero {{ background: var(--pp-light); border: 1px solid var(--pp-line); border-left: 6px solid var(--pp-navy); border-radius: 12px; padding: 1.5rem 1.8rem; margin: 0 0 1.3rem; }}
.pp-brand {{ margin: 0; font-size: 2.6rem; font-weight: 800; line-height: 1.05; letter-spacing: -0.02em; color: var(--pp-navy); }}
.pp-brand span {{ color: var(--pp-blue); }}
.pp-tagline {{ margin: 0.6rem 0 0; font-size: 1.2rem; font-weight: 500; line-height: 1.4; letter-spacing: 0.01em; color: var(--pp-grey); }}
.pp-tagline b {{ color: var(--pp-navy); font-weight: 700; }}
.pp-about {{ margin: 0.7rem 0 0; font-size: 0.98rem; color: var(--pp-grey); }}

/* narrow screens */
@media (max-width: 640px) {{
  .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
  h1 {{ font-size: 1.6rem; }}
  h2 {{ font-size: 1.3rem; }}
  .pp-hero {{ padding: 1.1rem 1.1rem; }}
  .pp-brand {{ font-size: 2rem; }}
  .pp-tagline {{ font-size: 1.05rem; }}
}}
</style>
"""

HERO = (f'<div class="pp-hero"><p class="pp-brand">Plant<span>Pulse</span></p>'
        f'<p class="pp-tagline">Learn it in class. <b>Monitor it in the plant.</b></p>'
        f'{{about}}</div>')


def apply():
    """Add the stylesheet and the sidebar logo. Called once per page run from app.py, so every page gets the same look."""
    st.markdown(CSS, unsafe_allow_html=True)
    logo, icon = ASSETS / "logo.svg", ASSETS / "icon.svg"
    if logo.exists() and hasattr(st, "logo"):
        st.logo(str(logo), size="large", icon_image=str(icon) if icon.exists() else None)


def brand_header(show_about=False):
    """The PlantPulse name and the tagline, with a clear hierarchy. The tagline text is fixed."""
    about = f'<p class="pp-about">{DESCRIPTION}</p>' if show_about else ""
    st.markdown(HERO.replace("{about}", about), unsafe_allow_html=True)
