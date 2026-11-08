"""Animated, fully labelled flow diagrams (self-contained HTML + SVG, animated with SMIL and CSS).

Particles move along the real flow paths. Colour shows temperature (heat exchanger) or pressure
(pipeline). Everything is generated from numbers only, so the HTML is safe to embed.
"""
import math

HOT0, HOT1, COLD0, COLD1 = "#D64550", "#F28C28", "#2563EB", "#F2B705"
NAVY, GREY, BLUE = "#0B2545", "#6B7280", "#2F6DA8"
SPEED = 120.0   # pixels per second at 1x


def _len(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _d(pts):
    return "M" + " L".join(f"{x:g},{y:g}" for x, y in pts)


def _stream(pts, c0, c1, speed=SPEED, gap=46, r=5, switch=None):
    """Particles travelling along a polyline. Fill changes c0 -> c1 smoothly, or at `switch` (0-1) abruptly."""
    length = _len(pts)
    dur = length / speed
    n = max(3, round(length / gap))
    d = _d(pts)
    if switch is None:
        fill = f'<animate data-dur="{dur:.3f}" attributeName="fill" values="{c0};{c1}" dur="{dur:.3f}s" begin="__B__s" repeatCount="indefinite"/>'
    else:
        fill = (f'<animate data-dur="{dur:.3f}" attributeName="fill" values="{c0};{c1}" keyTimes="0;{switch:.4f}" calcMode="discrete" '
                f'dur="{dur:.3f}s" begin="__B__s" repeatCount="indefinite"/>')
    out = []
    for i in range(n):
        b = f"{-(i * dur / n):.3f}"
        out.append(f'<circle r="{r}" fill="{c0}" stroke="white" stroke-width="1">'
                   f'<animateMotion data-dur="{dur:.3f}" dur="{dur:.3f}s" begin="{b}s" repeatCount="indefinite" path="{d}"/>'
                   f'{fill.replace("__B__", b)}</circle>')
    return "".join(out)


def _tx(x, y, text, color=NAVY, size=12, anchor="middle", bold=False):
    w = ' font-weight="bold"' if bold else ""
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="Arial, sans-serif" font-size="{size}" text-anchor="{anchor}"{w}>{text}</text>'


def _leader(x1, y1, x2, y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{GREY}" stroke-width="1" stroke-dasharray="3 2"/>'


def _tube(pts):
    d = _d(pts)
    return (f'<path d="{d}" fill="none" stroke="#94A3B8" stroke-width="12" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<path d="{d}" fill="none" stroke="white" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>')


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;font-family:Arial,sans-serif;background:#fff;color:#0B2545}
.bar{display:flex;flex-wrap:wrap;gap:14px;align-items:center;padding:6px 10px;font-size:13px}
button,select{font-size:13px;padding:4px 10px;border:1px solid #CBD5E1;border-radius:6px;background:#F4F7FA;color:#0B2545;cursor:pointer}
.sw{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:5px;vertical-align:-1px}
svg{width:100%;height:auto;display:block}
.hotflow{animation:dash 1.2s linear infinite}
@keyframes dash{to{stroke-dashoffset:-24}}
.paused .hotflow{animation-play-state:paused}
.note{padding:2px 12px 8px;font-size:12px;color:#6B7280}
</style></head><body>
<div class="bar"><button id="pp">Pause</button><span>Speed <select id="sp"><option value="0.5">0.5x</option><option value="1" selected>1x</option><option value="2">2x</option></select></span>__LEGEND__</div>
__SVG__
<div class="note">__NOTE__</div>
<script>(function(){var svg=document.getElementById('anim'),btn=document.getElementById('pp'),sel=document.getElementById('sp'),paused=false;
btn.onclick=function(){paused=!paused;if(paused){svg.pauseAnimations();document.body.classList.add('paused');}else{svg.unpauseAnimations();document.body.classList.remove('paused');}btn.textContent=paused?'Play':'Pause';};
sel.onchange=function(){var f=parseFloat(sel.value);document.querySelectorAll('[data-dur]').forEach(function(e){e.setAttribute('dur',(parseFloat(e.getAttribute('data-dur'))/f).toFixed(3)+'s');});};})();</script>
</body></html>"""


def _page(svg, legend, note):
    return PAGE.replace("__LEGEND__", legend).replace("__SVG__", svg).replace("__NOTE__", note)


HX_HEIGHT, PIPE_HEIGHT = 470, 470


# ---------------------------------------------------------------------------- heat exchanger
def animated_hx_html(arrangement, th_in, th_out, tc_in, tc_out, hot_in_tubes=False):
    """Shell-and-tube flow diagram. By default the hot fluid is on the shell side; hot_in_tubes swaps the two fluids."""
    two = arrangement in ("shell_1_2", "shell_2_4")
    counter = arrangement == "counter"
    hot = {"name": "Hot", "t_in": th_in, "t_out": th_out, "c0": HOT0, "c1": HOT1, "tint": "#FDF0EE"}
    cold = {"name": "Cold", "t_in": tc_in, "t_out": tc_out, "c0": COLD0, "c1": COLD1, "tint": "#EAF2FE"}
    sh, tb = (cold, hot) if hot_in_tubes else (hot, cold)
    s = ['<svg id="anim" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 330" width="800" height="330">',
         '<rect width="800" height="330" fill="white"/>',
         f'<rect x="170" y="100" width="460" height="140" rx="12" fill="{sh["tint"]}" stroke="{NAVY}" stroke-width="3"/>']
    head_r = 700 if two else 680
    s += [f'<rect x="120" y="100" width="50" height="140" fill="#E5E7EB" stroke="{NAVY}" stroke-width="2"/>',
          f'<rect x="630" y="100" width="{head_r - 630}" height="140" fill="#E5E7EB" stroke="{NAVY}" stroke-width="2"/>']
    # shell-side stream
    if two:
        shell_paths = [[(230, 40), (230, 112), (285, 160), (310, 230), (355, 205), (420, 115), (470, 112), (520, 165), (570, 230), (570, 290)]]
        s += [f'<line x1="310" y1="100" x2="310" y2="215" stroke="{NAVY}" stroke-width="5"/>',
              f'<line x1="470" y1="240" x2="470" y2="125" stroke="{NAVY}" stroke-width="5"/>']
    else:
        shell_paths = [[(230, 40), (230, 115), (570, 115), (570, 290)], [(230, 40), (230, 225), (570, 225), (570, 290)]]
    for p in shell_paths:
        s.append(f'<path class="hotflow" d="{_d(p)}" fill="none" stroke="{sh["c0"]}" stroke-opacity=".22" stroke-width="12" stroke-linejoin="round" stroke-dasharray="14 10"/>')
    for p in shell_paths:
        s.append(_stream(p, sh["c0"], sh["c1"]))
    # tube-side stream
    if two:
        p1 = [(40, 145), (660, 145), (690, 157)]
        p2 = [(690, 183), (660, 195), (40, 195)]
        s += [_tube(p1), _tube(p2), f'<line x1="120" y1="170" x2="170" y2="170" stroke="{NAVY}" stroke-width="4"/>']
        tube_paths = [[(40, 145), (660, 145), (690, 157), (690, 183), (660, 195), (40, 195)]]
        s += [f'<rect x="40" y="139" width="80" height="12" fill="#E5E7EB" stroke="{NAVY}" stroke-width="1"/>',
              f'<rect x="40" y="189" width="80" height="12" fill="#E5E7EB" stroke="{NAVY}" stroke-width="1"/>']
    else:
        for y in (130, 160, 190):
            s.append(_tube([(125, y), (675, y)]))
        xs = [(760, 40), (675, 125)] if counter else [(40, 760), (125, 675)]
        tube_paths = [[(xs[0][0], 160), (xs[0][1], 160)]] + [[(xs[1][0], y), (xs[1][1], y)] for y in (130, 190)]
        s += [f'<rect x="40" y="154" width="80" height="12" fill="#E5E7EB" stroke="{NAVY}" stroke-width="1"/>',
              f'<rect x="680" y="154" width="80" height="12" fill="#E5E7EB" stroke="{NAVY}" stroke-width="1"/>']
    for p in tube_paths:
        s.append(_stream(p, tb["c0"], tb["c1"], r=5))
    # tube sheets, nozzles
    s += [f'<rect x="166" y="100" width="8" height="140" fill="{NAVY}"/>', f'<rect x="626" y="100" width="8" height="140" fill="{NAVY}"/>',
          f'<rect x="224" y="30" width="12" height="46" fill="#E5E7EB" stroke="{NAVY}" stroke-width="1"/>',
          f'<rect x="217" y="72" width="26" height="28" fill="#E5E7EB" stroke="{NAVY}" stroke-width="2"/>',
          f'<rect x="564" y="240" width="12" height="60" fill="#E5E7EB" stroke="{NAVY}" stroke-width="1"/>',
          f'<rect x="557" y="240" width="26" height="28" fill="#E5E7EB" stroke="{NAVY}" stroke-width="2"/>']
    # labels
    s += [_tx(230, 22, f"{sh['name']} in {sh['t_in']:g} °C", sh["c0"], 13, "middle", True),
          _tx(570, 318, f"{sh['name']} out {sh['t_out']:g} °C", sh["c1"], 13, "middle", True),
          _tx(262, 56, "Shell inlet nozzle", GREY, 11, "start"), _tx(602, 285, "Shell outlet nozzle", GREY, 11, "start"),
          _tx(145, 93, "Channel head", GREY, 11), _tx(172, 258, "Tube sheet", GREY, 11), _tx(632, 258, "Tube sheet", GREY, 11, "start"),
          _leader(172, 242, 172, 250), _leader(630, 242, 640, 250),
          _tx(380, 262, f"Shell ({sh['name'].lower()} fluid)", sh["c0"], 12, "middle", True)]
    if two:
        caption = ("2-4 exchanger: two of these 1-2 shells in series (one is drawn). The cold fluid passes shell 1 then shell 2; the hot fluid passes shell 2 then shell 1."
                   if arrangement == "shell_2_4" else
                   f"{tb['name']} fluid in the tubes: pass 1 left to right, U-turn in the return head, pass 2 right to left")
        s += [_tx(665, 93, "Return head", GREY, 11), _tx(310, 94, "Baffle", GREY, 11), _tx(470, 256, "Baffle", GREY, 11),
              _tx(390, 172, "Tube bundle", BLUE, 12, "middle", True),
              _tx(10, 133, f"{tb['name']} in {tb['t_in']:g} °C", tb["c0"], 13, "start", True),
              _tx(10, 220, f"{tb['name']} out {tb['t_out']:g} °C", tb["c1"], 13, "start", True),
              _tx(10, 322, caption, GREY, 11, "start")]
    else:
        s.append(_tx(655, 93, "Channel head", GREY, 11))
        s.append(_tx(400, 214, f"Tube bundle ({tb['name'].lower()} fluid)", BLUE, 12, "middle", True))
        if counter:
            s += [_tx(760, 146, f"{tb['name']} in {tb['t_in']:g} °C", tb["c0"], 13, "end", True), _tx(10, 146, f"{tb['name']} out {tb['t_out']:g} °C", tb["c1"], 13, "start", True),
                  _tx(10, 322, f"Counter-flow: the {sh['name'].lower()} fluid moves left to right, the {tb['name'].lower()} fluid moves right to left", GREY, 11, "start")]
        else:
            s += [_tx(10, 146, f"{tb['name']} in {tb['t_in']:g} °C", tb["c0"], 13, "start", True), _tx(760, 146, f"{tb['name']} out {tb['t_out']:g} °C", tb["c1"], 13, "end", True),
                  _tx(10, 322, "Parallel flow: both fluids move left to right", GREY, 11, "start")]
    s.append("</svg>")
    legend = (f'<span><span class="sw" style="background:{HOT0}"></span>Hot fluid (red = hot, orange = cooler)</span>'
              f'<span><span class="sw" style="background:{COLD0}"></span>Cold fluid (blue = cold, gold = warmer)</span>')
    note = "Dots show the direction of flow; their colour shows the temperature changing as heat moves from the hot fluid to the cold fluid. Schematic, not to scale."
    return _page("".join(s), legend, note)


# ---------------------------------------------------------------------------- pipeline and pump
def animated_pipe_html(q_m3h, v, d_mm, length_m, sum_k, static_m, head_m=None, shaft_kw=None, re=None, has_pump=True, static_label="Static head", equiv_len_d=0.0):
    pipe = [(140, 280), (250, 280), (310, 280), (420, 280), (420, 95), (660, 95)]
    total = _len(pipe)
    tp = _len(pipe[:3]) / total              # fraction of the path at which the fluid passes the pump
    speed = max(60.0, min(180.0, 50.0 + 30.0 * v))
    lo, hi = "#60A5FA", "#1E3A8A"
    s = ['<svg id="anim" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 370" width="800" height="370">', '<rect width="800" height="370" fill="white"/>',
         f'<rect x="30" y="170" width="110" height="130" fill="white" stroke="{NAVY}" stroke-width="3"/>',
         '<rect x="33" y="200" width="104" height="97" fill="#BFDBFE"/>',
         f'<rect x="660" y="40" width="110" height="110" fill="white" stroke="{NAVY}" stroke-width="3"/>',
         '<rect x="663" y="70" width="104" height="77" fill="#BFDBFE"/>',
         f'<line x1="140" y1="200" x2="600" y2="200" stroke="{GREY}" stroke-width="1" stroke-dasharray="4 3"/>',
         f'<line x1="660" y1="70" x2="600" y2="70" stroke="{GREY}" stroke-width="1" stroke-dasharray="4 3"/>',
         _tube(pipe)]
    s.append(_stream(pipe, lo, hi if has_pump else lo, speed=speed, gap=40, r=4.5, switch=tp if has_pump else None) if has_pump
             else _stream(pipe, lo, lo, speed=speed, gap=40, r=4.5))
    if has_pump:
        s += [f'<circle cx="280" cy="280" r="30" fill="#E5E7EB" stroke="{NAVY}" stroke-width="3"/>',
              f'<g><line x1="262" y1="280" x2="298" y2="280" stroke="{NAVY}" stroke-width="4"/><line x1="280" y1="262" x2="280" y2="298" stroke="{NAVY}" stroke-width="4"/>'
              '<animateTransform attributeName="transform" type="rotate" from="0 280 280" to="360 280 280" dur="1.2s" repeatCount="indefinite"/></g>',
              f'<circle cx="280" cy="280" r="6" fill="{NAVY}"/>', _tx(280, 236, "Pump", NAVY, 13, "middle", True)]
    s += [f'<polygon points="408,178 420,190 408,202" fill="white" stroke="{NAVY}" stroke-width="2"/>',
          f'<polygon points="432,178 420,190 432,202" fill="white" stroke="{NAVY}" stroke-width="2"/>',
          _tx(442, 194, f"Valves and fittings (ΣK = {sum_k:g}" + (f", Le/D = {equiv_len_d:g}" if equiv_len_d else "") + ")", GREY, 11, "start")]
    s += [f'<line x1="590" y1="72" x2="590" y2="198" stroke="{NAVY}" stroke-width="2"/>',
          f'<polygon points="590,70 585,82 595,82" fill="{NAVY}"/><polygon points="590,200 585,188 595,188" fill="{NAVY}"/>',
          _tx(578, 140, f"{static_label} {static_m:g} m", NAVY, 12, "end", True),
          _tx(85, 322, "Suction tank", NAVY, 13, "middle", True), _tx(715, 170, "Discharge tank", NAVY, 13, "middle", True),
          _tx(500, 84, f"Pipe: D = {d_mm:g} mm, L = {length_m:g} m", NAVY, 12, "middle"),
          _tx(200, 268, "Suction pipe", GREY, 11)]
    info = f"Flow Q = {q_m3h:,.1f} m³/h   |   velocity v = {v:.2f} m/s" + (f"   |   Re = {re:,.0f}" if re else "")
    s.append(_tx(400, 348, info, NAVY, 13, "middle", True))
    if head_m is not None and shaft_kw is not None:
        s.append(_tx(400, 366, f"Total head required = {head_m:.2f} m   |   shaft power = {shaft_kw:.2f} kW", BLUE, 13, "middle", True))
    s.append("</svg>")
    legend = (f'<span><span class="sw" style="background:{lo}"></span>Low pressure (before the pump)</span>'
              f'<span><span class="sw" style="background:{hi}"></span>High pressure (after the pump)</span>')
    note = "Dots show the flow direction and move faster when the velocity is higher. The pump impeller turns; the dimension arrow marks the static head. Schematic, not to scale."
    return _page("".join(s), legend, note)


def show(html, height):
    """Embed an animation in the Streamlit page (st.iframe on new versions, components.html on older ones)."""
    import streamlit as st
    try:
        st.iframe(html, height=height)
    except Exception:
        import streamlit.components.v1 as components
        components.html(html, height=height)
