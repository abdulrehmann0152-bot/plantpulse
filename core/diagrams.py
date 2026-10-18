"""Simple SVG schematics that show how the fluids flow through each exchanger arrangement."""
import math

NAVY, TEAL, RED, GREY = "#0B2545", "#13A89E", "#D64550", "#6B7280"


def _arrow(x1, y1, x2, y2, color):
    """Line with a drawn arrowhead (no SVG markers, so it renders the same everywhere)."""
    L = math.hypot(x2 - x1, y2 - y1) or 1.0
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    bx, by = x2 - ux * 11, y2 - uy * 11
    px, py = -uy * 6, ux * 6
    return (f'<line x1="{x1}" y1="{y1}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{color}" stroke-width="3"/>'
            f'<polygon points="{x2},{y2} {bx + px:.1f},{by + py:.1f} {bx - px:.1f},{by - py:.1f}" fill="{color}"/>')


def _t(x, y, text, color=NAVY, size=13, anchor="middle", bold=False):
    weight = ' font-weight="bold"' if bold else ""
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="Arial, sans-serif" font-size="{size}" text-anchor="{anchor}"{weight}>{text}</text>'


def schematic_svg(arrangement, th_in, th_out, tc_in, tc_out):
    """Return an SVG string. Hot fluid (red) is on the shell side, cold fluid (teal) in the tubes."""
    s = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 300" width="760" height="300">',
         '<rect width="760" height="300" fill="white"/>',
         f'<rect x="150" y="90" width="460" height="130" rx="14" fill="#F4F7FA" stroke="{NAVY}" stroke-width="3"/>',
         f'<rect x="190" y="62" width="26" height="28" fill="#F4F7FA" stroke="{NAVY}" stroke-width="2"/>',
         f'<rect x="544" y="220" width="26" height="28" fill="#F4F7FA" stroke="{NAVY}" stroke-width="2"/>',
         _arrow(203, 24, 203, 62, RED), _arrow(557, 248, 557, 284, RED),
         _t(203, 16, f"Hot in {th_in:g} °C", RED, 13, "middle", True), _t(557, 298, f"Hot out {th_out:g} °C", RED, 13, "middle", True)]
    if arrangement == "shell_1_2":
        s += [f'<line x1="300" y1="90" x2="300" y2="185" stroke="{NAVY}" stroke-width="3"/>',
              f'<line x1="440" y1="220" x2="440" y2="125" stroke="{NAVY}" stroke-width="3"/>',
              f'<path d="M150,140 L585,140 Q615,140 615,160 Q615,180 585,180 L150,180" fill="none" stroke="{TEAL}" stroke-width="4"/>',
              _arrow(14, 140, 148, 140, TEAL), _arrow(148, 180, 14, 180, TEAL),
              _t(10, 128, f"Cold in {tc_in:g} °C", TEAL, 13, "start", True), _t(10, 202, f"Cold out {tc_out:g} °C", TEAL, 13, "start", True),
              _t(380, 112, "Shell side: hot fluid zig-zags across the tubes around the baffles", GREY, 12),
              _t(380, 208, "Tube side: pass 1 goes left to right, the U-bend returns it as pass 2", TEAL, 12)]
    else:
        s += [f'<line x1="150" y1="{y}" x2="610" y2="{y}" stroke="{TEAL}" stroke-width="4"/>' for y in (130, 160, 190)]
        if arrangement == "counter":
            s += [_arrow(750, 160, 612, 160, TEAL), _arrow(148, 160, 14, 160, TEAL),
                  _t(750, 148, f"Cold in {tc_in:g} °C", TEAL, 13, "end", True), _t(10, 148, f"Cold out {tc_out:g} °C", TEAL, 13, "start", True),
                  _t(380, 112, "Hot flows left to right, cold flows right to left (opposite directions)", GREY, 12)]
        else:
            s += [_arrow(14, 160, 148, 160, TEAL), _arrow(612, 160, 750, 160, TEAL),
                  _t(10, 148, f"Cold in {tc_in:g} °C", TEAL, 13, "start", True), _t(750, 148, f"Cold out {tc_out:g} °C", TEAL, 13, "end", True),
                  _t(380, 112, "Hot and cold both flow left to right (same direction)", GREY, 12)]
        s.append(_t(380, 212, "Cold fluid in the tubes", TEAL, 12))
    s.append('</svg>')
    return "".join(s)
