"""The pump curve against system curve graph for the Pump & Pipeline page.

Pump curve (solid inside the datasheet range, dotted where it is extrapolated), system curve, the datasheet points, the static head,
the shut-off head and the operating point with its drop lines and a plain-language note. All text is built from numbers, never from user text.
"""
import plotly.graph_objects as go

from core import branding as b
from core.plot_note import add_note


def operating_figure(coeffs, system_fn, pts, op, static, q_data_max, q_max, n=60):
    from calc_engine import pump_pipe as pp
    q_in = [i * q_data_max / n for i in range(n + 1)]
    q_ex = [q_data_max + i * (q_max - q_data_max) / n for i in range(n + 1)] if q_max > q_data_max else []
    q_sys = [i * q_max / (2 * n) for i in range(2 * n + 1)]
    m3h = lambda qs: [q * 3600 for q in qs]
    fig = go.Figure()
    fig.add_scatter(x=m3h(q_sys), y=[system_fn(q) for q in q_sys], name="System curve", mode="lines", line=dict(color=b.NAVY, width=3))
    fig.add_scatter(x=m3h(q_in), y=[pp.pump_head(coeffs, q) for q in q_in], name="Pump curve", mode="lines", line=dict(color=b.BLUE, width=3))
    if q_ex:
        fig.add_scatter(x=m3h(q_ex), y=[pp.pump_head(coeffs, q) for q in q_ex], name="Pump curve (extrapolated)", mode="lines", line=dict(color=b.BLUE, width=3, dash="dot"))
    fig.add_scatter(x=m3h([p[0] for p in pts]), y=[p[1] for p in pts], name="Datasheet points", mode="markers", marker=dict(symbol="diamond", size=11, color="white", line=dict(color=b.BLUE, width=2)),
                    hovertemplate="%{x:.1f} m³/h, %{y:.2f} m<extra>datasheet point</extra>")
    x_end = q_max * 3600
    fig.add_shape(type="line", x0=0, x1=x_end, y0=static, y1=static, line=dict(color=b.GREY, width=1.5, dash="dash"))
    fig.add_annotation(x=x_end, y=static, text=f"Static head {static:g} m (does not change with flow)", showarrow=False, xanchor="right", yanchor="bottom", font=dict(size=11, color=b.GREY))
    fig.add_annotation(x=0, y=coeffs[0], text=f"Shut-off head {coeffs[0]:.1f} m", showarrow=False, xanchor="left", yanchor="bottom", yshift=6, xshift=4, font=dict(size=11, color=b.BLUE))

    qx, hy = op["q"] * 3600, op["h"]
    for x0, x1, y0, y1 in ((0, qx, hy, hy), (qx, qx, 0, hy)):
        fig.add_shape(type="line", x0=x0, x1=x1, y0=y0, y1=y1, line=dict(color=b.RED, width=1, dash="dot"))
    fig.add_scatter(x=[qx], y=[hy], name="Operating point", mode="markers", marker=dict(color=b.RED, size=15, line=dict(color="white", width=2)))
    fig.add_annotation(x=qx, y=hy, text=f"<b>Operating point</b><br>Q = {qx:,.1f} m³/h<br>H = {hy:.2f} m", showarrow=True, arrowhead=2, arrowcolor=b.RED, ax=-100 if qx > 0.6 * x_end else 70, ay=-70,
                       align="left", bgcolor="white", bordercolor=b.RED, borderwidth=1, borderpad=5, font=dict(size=12, color=b.RED))
    if hy - static > 0.3:
        fig.add_shape(type="line", x0=qx, x1=qx, y0=static, y1=hy, line=dict(color=b.RED, width=3))
        fig.add_annotation(x=qx, y=(static + hy) / 2, text=f"friction + fittings<br>{hy - static:.2f} m", showarrow=False, xanchor="left", xshift=8, align="left", font=dict(size=11, color=b.RED))

    lines = ["How to read this graph:",
             "The pump runs where its curve (blue) crosses the system curve (navy): there the head the pump gives equals the head the pipeline needs.",
             f"At that point it delivers {qx:,.1f} m³/h at {hy:.2f} m. Of this head, {static:g} m is static lift and {hy - static:.2f} m is lost to friction and fittings.",
             "Diamonds are your datasheet points; the pump curve is a quadratic through them."]
    lines.append("The operating point lies on the DOTTED, extrapolated part of the curve, beyond your last datasheet point, so it is only indicative."
                 if op["extrapolated"] else "The dotted part of the pump curve (if shown) is extrapolated beyond your last datasheet point and is less reliable.")
    top = max(coeffs[0], system_fn(q_max), hy) * 1.12
    fig.update_layout(xaxis=dict(title="Flow rate, Q (m³/h)", range=[0, x_end * 1.02]), yaxis=dict(title="Head, H (m)", range=[0, top]), template="plotly_white",
                      legend=dict(orientation="h", y=1.0, yanchor="bottom"))
    add_note(fig, lines, plot_height=400, margin_t=85)                      # room above the plot for a legend that wraps on a phone
    return fig
