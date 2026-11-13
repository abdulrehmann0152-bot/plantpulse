"""A note under a Plotly graph that cannot be clipped.

Plotly does not wrap annotation text and clips anything outside the figure, so the note is wrapped to a width that fits a phone
and the bottom margin is sized from the number of lines. Text only; never put text typed by a user in a note.
"""
import textwrap

from core import branding as b

WRAP_CHARS = 58          # about 330 px at an 11 px font: fits a phone screen as well as a desktop
FONT_PX = 11


def wrap_lines(paragraphs, width=WRAP_CHARS):
    out = []
    for para in paragraphs:
        out += textwrap.wrap(para, width=width) or [""]
    return out


def add_note(fig, paragraphs, plot_height=380, margin_t=30, axis_px=85):
    """Add the note below the plot and set the figure height and margins so that all of it is visible. Returns the wrapped lines."""
    lines = wrap_lines(paragraphs)
    note_h = round(len(lines) * FONT_PX * 1.45 + 24)
    margin_b = axis_px + note_h + 10
    fig.add_annotation(xref="paper", yref="paper", x=0, y=-axis_px / plot_height, xanchor="left", yanchor="top", showarrow=False, align="left",
                       text="<br>".join(lines), font=dict(size=FONT_PX, color=b.NAVY), bgcolor=b.LIGHT, bordercolor=b.LINE, borderwidth=1, borderpad=8)
    fig.update_layout(height=margin_t + plot_height + margin_b, margin=dict(t=margin_t, b=margin_b))
    return lines
