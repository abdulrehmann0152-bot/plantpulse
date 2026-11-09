"""The hot and cold temperature graph used by both heat exchanger pages.

Build the data with calc_engine.heat_exchanger.temperature_profile, then pass it here. The explanation printed under the graph
comes from profile_note, so the figure, the tests and the text always agree. Nothing typed by a user goes into the figure text.
"""
import plotly.graph_objects as go

from calc_engine import heat_exchanger as hx
from core import branding as b


def profile_figure(p):
    counter = p["flow"] == "counter"
    fig = go.Figure()
    fig.add_scatter(x=p["x"], y=p["hot"], name="Hot fluid", mode="lines", line=dict(color=b.RED, width=3))
    fig.add_scatter(x=p["x"], y=p["cold"], name="Cold fluid", mode="lines", line=dict(color=b.BLUE, width=3))

    left_cold, right_cold = ("Cold OUT", "Cold IN") if counter else ("Cold in", "Cold out")
    ends = (  # (x, y, text, anchor, shift up/down in pixels, colour)
        (0, p["hot"][0], f"Hot in {p['th_in']:g} °C", "left", 16, b.RED),
        (1, p["hot"][-1], f"Hot out {p['th_out']:g} °C", "right", 16, b.RED),
        (0, p["cold"][0], f"{left_cold} {p['cold'][0]:g} °C", "left", -16, b.BLUE),
        (1, p["cold"][-1], f"{right_cold} {p['cold'][-1]:g} °C", "right", -16, b.BLUE),
    )
    for x, y, text, anchor, dy, colour in ends:
        fig.add_annotation(x=x, y=y, text=f"<b>{text}</b>", showarrow=False, xanchor=anchor, yshift=dy, xshift=6 if anchor == "left" else -6, font=dict(size=12, color=colour))
    for x, d, name, anchor in ((0, p["d1"], "ΔT₁", "left"), (1, p["d2"], "ΔT₂", "right")):
        lo, hi = p["cold"][0 if x == 0 else -1], p["hot"][0 if x == 0 else -1]
        fig.add_shape(type="line", x0=x, x1=x, y0=lo, y1=hi, line=dict(color=b.GREY, width=1, dash="dot"))
        fig.add_annotation(x=x, y=(lo + hi) / 2, text=f"{name} = {d:g} K", showarrow=False, xanchor=anchor, xshift=8 if anchor == "left" else -8, font=dict(size=11, color=b.GREY))

    fig.add_annotation(xref="paper", yref="paper", x=0, y=-0.30, xanchor="left", yanchor="top", showarrow=False, align="left",
                       text="<br>".join(hx.profile_note(p).split("\n")), font=dict(size=12, color=b.NAVY), bgcolor=b.LIGHT, bordercolor=b.LINE, borderwidth=1, borderpad=8)
    fig.update_layout(
        xaxis=dict(title="Fraction of the heat duty transferred, measured from the hot-inlet end", range=[-0.02, 1.02],
                   tickmode="array", tickvals=[0, 0.25, 0.5, 0.75, 1], ticktext=["0<br>hot-inlet end", "0.25", "0.5", "0.75", "1<br>hot-outlet end"]),
        yaxis_title="Temperature (°C)", template="plotly_white", legend=dict(orientation="h", y=1.1), margin=dict(t=30, b=175), height=560)
    return fig
