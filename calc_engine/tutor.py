"""Offline study assistant: concept library, practice problems and rule-based result explanations.

Everything here is computed by the PlantPulse calculation engine or written by hand (no AI model,
no internet). Answers to practice problems always come from the same functions the app uses.
"""
import math
import random

import pandas as pd

from . import heat_exchanger as hx
from . import pump_pipe as pp

# --------------------------------------------------------------------------- concept library
CONCEPTS = [
    {"id": "heat_duty", "topic": "Heat exchangers", "title": "Heat duty",
     "formula": r"Q = \dot m\, C_p\, \Delta T",
     "summary": "The rate at which heat moves from the hot fluid to the cold fluid. Calculate it separately on each side; the two answers should agree.",
     "plant": "Hot-side and cold-side duties should match within a few percent. A bigger gap points to a bad flow or temperature reading, or to heat loss to the surroundings.",
     "mistakes": ["Mixing kJ and J: with Cp in kJ/kg·K the answer comes out in kW.",
                  "Using the temperature change of the wrong stream.",
                  "Using volumetric flow without converting to mass flow (multiply by density)."],
     "check": {"q": "Water (Cp = 4.18 kJ/kg·K) flows at 2 kg/s and is heated from 20 °C to 50 °C. What is the heat duty?",
               "options": ["125.4 kW", "250.8 kW", "418 kW", "83.6 kW"], "answer": 1,
               "why": "Q = 2 × 4.18 × (50 − 20) = 250.8 kW."}},
    {"id": "lmtd", "topic": "Heat exchangers", "title": "Log mean temperature difference (LMTD)",
     "formula": r"LMTD = \dfrac{\Delta T_1 - \Delta T_2}{\ln(\Delta T_1/\Delta T_2)}",
     "summary": "The average driving force for heat transfer along the exchanger, because the temperature difference changes from one end to the other. ΔT₁ and ΔT₂ are the differences at the two ends.",
     "plant": "For the same terminal temperatures, counter-flow gives a larger LMTD than parallel flow, so it needs less heat transfer area.",
     "mistakes": ["Using the arithmetic mean of the two end differences (it overstates the driving force).",
                  "Pairing the wrong temperatures: in counter-flow ΔT₁ = T(hot in) − T(cold out).",
                  "Ignoring a temperature cross (a difference at or below zero): the formula is not valid then."],
     "check": {"q": "For the same four terminal temperatures, which arrangement gives the larger LMTD?",
               "options": ["Counter-flow", "Parallel flow", "They are always equal", "It depends only on the area"], "answer": 0,
               "why": "Counter-flow keeps the two streams further apart on average. (They are equal only in special cases, such as when one fluid stays at constant temperature.)"}},
    {"id": "u_value", "topic": "Heat exchangers", "title": "Overall heat transfer coefficient (U) and correction factor F",
     "formula": r"U = \dfrac{Q}{A\,F\,LMTD}",
     "summary": "How easily heat passes through the exchanger per square metre per degree. F corrects the LMTD for multi-pass arrangements; F = 1 for pure counter-flow or parallel flow.",
     "plant": "Compare today's U with the clean design U. A steady fall means resistance is building up on the heat transfer surfaces.",
     "mistakes": ["Forgetting F for shell-and-tube exchangers with more than one tube pass.",
                  "Using Q in kW with A in m² and expecting W/m²K: convert kW to W first."],
     "check": {"q": "Which arrangement always has F = 1?",
               "options": ["Pure counter-flow (and parallel flow, which uses its own LMTD)", "1 shell pass / 2 tube passes", "Cross-flow with mixing", "None of them"], "answer": 0,
               "why": "F is a correction applied to the pure-flow LMTD, so pure flow arrangements need none."}},
    {"id": "fouling", "topic": "Heat exchangers", "title": "Fouling resistance",
     "formula": r"R_f = \dfrac{1}{U_{fouled}} - \dfrac{1}{U_{clean}}",
     "summary": "Deposits (scale, biological growth, dirt) add a thermal resistance, so U falls with time. Rf measures how much resistance has been added.",
     "plant": "Scale on juice heaters in sugar mills is a classic example. Plants clean an exchanger when the lost duty costs more than the cleaning. PlantPulse's 10% and 25% limits are screening rules, not standards.",
     "mistakes": ["Giving Rf in the wrong units (it is m²·K/W).",
                  "Assuming every drop in U is fouling: a flow change or a faulty sensor can look similar, so check the trend."],
     "check": {"q": "U(clean) = 1000 W/m²K and U(fouled) = 800 W/m²K. What is Rf?",
               "options": ["0.00025 m²K/W", "0.0002 m²K/W", "0.0005 m²K/W", "0.25 m²K/W"], "answer": 0,
               "why": "Rf = 1/800 − 1/1000 = 0.00125 − 0.001 = 0.00025 m²K/W."}},
    {"id": "ntu", "topic": "Heat exchangers", "title": "Effectiveness and NTU (the digital twin method)",
     "formula": r"\varepsilon = \dfrac{Q}{Q_{max}},\qquad NTU = \dfrac{UA}{C_{min}}",
     "summary": "The effectiveness-NTU method predicts outlet temperatures when you only know the inlet temperatures and UA. PlantPulse's twin uses it to predict what the clean exchanger would deliver.",
     "plant": "If observed outlets are worse than the clean-exchanger prediction at the same flows, the gap is performance lost to fouling or another problem.",
     "mistakes": ["Using the larger capacity rate (m·Cp) as Cmin.",
                  "Expecting effectiveness to double when UA doubles: it rises with diminishing returns."],
     "check": {"q": "UA doubles with the same flows and inlet temperatures. What happens to effectiveness?",
               "options": ["It doubles", "It increases, but by less than double", "It decreases", "It stays the same"], "answer": 1,
               "why": "Effectiveness rises with NTU but flattens out, because the temperature difference shrinks as more heat is transferred."}},
    {"id": "reynolds", "topic": "Fluid flow and pumps", "title": "Reynolds number and flow regime",
     "formula": r"Re = \dfrac{\rho\, v\, D}{\mu}",
     "summary": "The ratio of inertial to viscous forces. It shows whether flow is laminar (Re below about 2,300) or turbulent (above about 4,000).",
     "plant": "Most water lines in plants are fully turbulent, so the friction factor depends mainly on pipe roughness.",
     "mistakes": ["Using the diameter in mm instead of m.", "Using viscosity in cP without converting to Pa·s (1 cP = 0.001 Pa·s)."],
     "check": {"q": "Water (ρ = 998 kg/m³, μ = 1.0×10⁻³ Pa·s) flows at 1 m/s in a 0.05 m pipe. Re is about:",
               "options": ["500", "5,000", "50,000", "500,000"], "answer": 2,
               "why": "Re = 998 × 1 × 0.05 / 0.001 ≈ 49,900, so about 50,000 (turbulent)."}},
    {"id": "friction", "topic": "Fluid flow and pumps", "title": "Friction loss (Darcy-Weisbach)",
     "formula": r"\Delta P = f\,\dfrac{L}{D}\,\dfrac{\rho v^2}{2}",
     "summary": "Pressure drop from pipe friction. The friction factor f comes from the Moody chart or an equation such as Swamee-Jain.",
     "plant": "In turbulent flow, friction loss grows roughly with the square of velocity: doubling the flow roughly quadruples the loss, so oversized flow rates are expensive to pump.",
     "mistakes": ["Using the Fanning friction factor (4 times smaller) in the Darcy equation.", "Forgetting fittings and valves (the ΣK terms)."],
     "check": {"q": "In fully turbulent flow with constant f, velocity doubles. The friction head loss becomes:",
               "options": ["2 times larger", "4 times larger", "8 times larger", "Unchanged"], "answer": 1,
               "why": "Loss is proportional to v², so doubling v gives 2² = 4 times the loss."}},
    {"id": "system_curve", "topic": "Fluid flow and pumps", "title": "System curve",
     "formula": r"H_{sys} = H_{static} + \left(f\dfrac{L}{D} + \Sigma K\right)\dfrac{v^2}{2g}",
     "summary": "The head the pipeline needs at each flow. Static head does not change with flow; friction head rises roughly with flow squared.",
     "plant": "Scaling, blockage or a partly closed valve make the system curve steeper.",
     "mistakes": ["Putting static head inside the friction term.", "Confusing static head (elevation and pressure difference) with pipe length."],
     "check": {"q": "Static head is 10 m and friction head is 6 m at 200 m³/h. At 400 m³/h (turbulent, constant f) the system head is:",
               "options": ["16 m", "22 m", "34 m", "46 m"], "answer": 2,
               "why": "Friction scales with Q²: 6 × 4 = 24 m. Adding static head: 10 + 24 = 34 m."}},
    {"id": "operating_point", "topic": "Fluid flow and pumps", "title": "Pump curve and operating point",
     "formula": r"H_{pump}(Q) = H_{sys}(Q)",
     "summary": "A centrifugal pump runs where its curve crosses the system curve. Change either curve and the operating point moves.",
     "plant": "Throttling a valve steepens the system curve: flow falls and head rises. Pump wear lowers the pump curve: flow and head both fall. PlantPulse's pump diagnosis uses exactly this logic.",
     "mistakes": ["Reading the pump curve at the design flow instead of the actual flow.", "Assuming low flow is always a pump fault: check the valve position first."],
     "check": {"q": "A discharge valve is partly closed. What happens to the system curve and the operating point?",
               "options": ["The system curve gets steeper; flow falls and head rises", "The system curve gets flatter; flow rises",
                           "The pump curve moves down; flow and head both fall", "Nothing changes"], "answer": 0,
               "why": "The valve adds resistance (extra K), so more head is needed for each flow. The crossing point moves up the pump curve to a lower flow."}},
    {"id": "pump_power", "topic": "Fluid flow and pumps", "title": "Pump power and efficiency",
     "formula": r"P_{hyd} = \rho g Q H,\qquad P_{shaft} = \dfrac{P_{hyd}}{\eta}",
     "summary": "The power the fluid receives, and the larger power the shaft must supply because the pump is not 100% efficient.",
     "plant": "Pumps are among the largest electricity users in a plant. A small efficiency loss or extra throttling costs money every hour.",
     "mistakes": ["Using flow in m³/h directly: divide by 3600 to get m³/s.", "Forgetting motor losses when comparing with the electricity meter."],
     "check": {"q": "What is the hydraulic power for 0.05 m³/s of water (ρ = 1000 kg/m³) at 20 m head?",
               "options": ["0.98 kW", "9.8 kW", "98 kW", "19.6 kW"], "answer": 1,
               "why": "P = 1000 × 9.81 × 0.05 × 20 = 9,810 W ≈ 9.8 kW."}},
]


def concepts_for(topic=None):
    return [c for c in CONCEPTS if topic in (None, "All", c["topic"])]


# --------------------------------------------------------------------------- practice problems
PROBLEM_TYPES = {"hx_lmtd": "Heat exchanger: LMTD", "hx_u": "Heat exchanger: duty and U value",
                 "foul_rf": "Fouling resistance", "pipe_dp": "Pipe pressure drop", "pump_power": "Pump power"}


def _temps(rng):
    while True:
        th_in = rng.choice(range(90, 151, 5)); th_out = th_in - rng.choice(range(20, 51, 5))
        tc_in = rng.choice(range(15, 36, 5)); tc_out = tc_in + rng.choice(range(15, 41, 5))
        d1, d2 = th_in - tc_out, th_out - tc_in
        if d1 > 5 and d2 > 5 and d1 != d2 and th_out - tc_out > 5:
            return th_in, th_out, tc_in, tc_out


def _ans(key, label, unit, value, tol=0.02):
    return {"key": key, "label": label, "unit": unit, "value": value, "tol": tol}


def make_problem(kind, seed):
    """Deterministic practice problem: same (kind, seed) always gives the same problem."""
    rng = random.Random(f"{kind}-{seed}")
    if kind == "hx_lmtd":
        thi, tho, tci, tco = _temps(rng)
        lc, lp = hx.lmtd(thi, tho, tci, tco, "counter"), hx.lmtd(thi, tho, tci, tco, "parallel")
        return {"kind": kind, "title": PROBLEM_TYPES[kind],
                "prompt": f"A hot stream cools from **{thi} °C to {tho} °C** while a cold stream heats from **{tci} °C to {tco} °C**. "
                          "Calculate the LMTD for counter-flow and for parallel flow.",
                "answers": [_ans("counter", "LMTD, counter-flow", "K", lc), _ans("parallel", "LMTD, parallel flow", "K", lp)],
                "steps": [f"Counter-flow: ΔT₁ = {thi} − {tco} = {thi - tco} K, ΔT₂ = {tho} − {tci} = {tho - tci} K → LMTD = ({thi - tco} − {tho - tci}) / ln({thi - tco}/{tho - tci}) = {lc:.2f} K",
                          f"Parallel flow: ΔT₁ = {thi} − {tci} = {thi - tci} K, ΔT₂ = {tho} − {tco} = {tho - tco} K → LMTD = {lp:.2f} K",
                          "Counter-flow gives the larger LMTD for the same terminal temperatures."]}
    if kind == "hx_u":
        thi, tho, tci, tco = _temps(rng)
        m, area = rng.choice([1.0, 1.5, 2.0, 2.5, 3.0]), rng.choice([8, 10, 12, 15, 20])
        q = m * 4.18 * (thi - tho); lm = hx.lmtd(thi, tho, tci, tco, "counter"); u = q * 1000 / (area * lm)
        return {"kind": kind, "title": PROBLEM_TYPES[kind],
                "prompt": f"Hot water (Cp = 4.18 kJ/kg·K) flows at **{m} kg/s** and cools from **{thi} °C to {tho} °C**. The cold stream goes from "
                          f"**{tci} °C to {tco} °C**. The exchanger is counter-flow with **{area} m²** of area. Find the heat duty, the LMTD and U.",
                "answers": [_ans("q", "Heat duty", "kW", q), _ans("lmtd", "LMTD", "K", lm), _ans("u", "Overall U", "W/m²K", u)],
                "steps": [f"Q = m·Cp·ΔT = {m} × 4.18 × {thi - tho} = {q:.1f} kW",
                          f"LMTD (counter-flow) = {lm:.2f} K",
                          f"U = Q / (A·LMTD) = {q * 1000:,.0f} / ({area} × {lm:.2f}) = {u:,.1f} W/m²K"]}
    if kind == "foul_rf":
        uc, loss = rng.choice([800, 1000, 1200, 1500]), rng.choice([10, 15, 20, 25, 30, 35])
        uf = round(uc * (1 - loss / 100)); rf = hx.fouling_resistance(uf, uc); pct = (1 - uf / uc) * 100
        return {"kind": kind, "title": PROBLEM_TYPES[kind],
                "prompt": f"A heat exchanger had a clean U of **{uc} W/m²K**. Today it measures **{uf} W/m²K**. Find the fouling resistance and the percentage loss in U.",
                "answers": [_ans("rf", "Fouling resistance Rf", "m²K/W", rf), _ans("pct", "Loss in U", "%", pct)],
                "steps": [f"Rf = 1/{uf} − 1/{uc} = {1 / uf:.6f} − {1 / uc:.6f} = {rf:.6f} m²K/W", f"Loss = (1 − {uf}/{uc}) × 100 = {pct:.1f} %"]}
    if kind == "pipe_dp":
        t, d_mm, length, v = rng.choice([20, 30, 40]), rng.choice([50, 80, 100, 150]), rng.choice([50, 100, 200]), rng.choice([1.0, 1.5, 2.0, 2.5])
        d = d_mm / 1000.0; q_m3h = round(v * math.pi * d * d / 4 * 3600, 1)
        rho, mu = pp.water_properties(t)
        r = pp.pipe_losses(q_m3h / 3600, d, length, 0.045e-3, 0.0, rho, mu)
        return {"kind": kind, "title": PROBLEM_TYPES[kind],
                "prompt": f"Water at **{t} °C** (ρ = {rho:.1f} kg/m³, μ = {mu * 1000:.3f} mPa·s) flows at **{q_m3h} m³/h** through a commercial steel pipe "
                          f"(roughness 0.045 mm), **{d_mm} mm** inside diameter and **{length} m** long. Find Re, the friction factor (Swamee-Jain) and the friction pressure drop.",
                "answers": [_ans("re", "Reynolds number", "-", r["re"], 0.02), _ans("f", "Friction factor f", "-", r["f"], 0.05),
                            _ans("dp", "Friction pressure drop", "kPa", r["dp"] / 1000, 0.05)],
                "steps": [f"v = Q/A = {q_m3h / 3600:.5f} / {math.pi * d * d / 4:.5f} = {r['v']:.3f} m/s",
                          f"Re = ρvD/μ = {rho:.1f} × {r['v']:.3f} × {d:.3f} / {mu:.6f} = {r['re']:,.0f}",
                          f"f (Swamee-Jain) = {r['f']:.4f}   (Moody chart readings within about 5% are fine)",
                          f"ΔP = f (L/D) ρv²/2 = {r['f']:.4f} × ({length}/{d:.3f}) × {rho:.1f} × {r['v']:.3f}² / 2 = {r['dp'] / 1000:.2f} kPa"]}
    if kind == "pump_power":
        q, h, eta = rng.choice([100, 150, 200, 250, 300]), rng.choice([15, 20, 25, 30, 40]), rng.choice([60, 65, 70, 75, 80])
        hyd = 1000 * 9.81 * (q / 3600) * h / 1000; sh = hyd / (eta / 100)
        return {"kind": kind, "title": PROBLEM_TYPES[kind],
                "prompt": f"A pump delivers **{q} m³/h** of water against a head of **{h} m** with an overall efficiency of **{eta}%**. "
                          "Take ρ = 1000 kg/m³ and g = 9.81 m/s². Find the hydraulic power and the shaft power.",
                "answers": [_ans("hyd", "Hydraulic power", "kW", hyd), _ans("shaft", "Shaft power", "kW", sh)],
                "steps": [f"Q = {q}/3600 = {q / 3600:.5f} m³/s", f"P_hyd = ρgQH = 1000 × 9.81 × {q / 3600:.5f} × {h} = {hyd * 1000:,.0f} W = {hyd:.2f} kW",
                          f"P_shaft = P_hyd / η = {hyd:.2f} / {eta / 100:.2f} = {sh:.2f} kW"]}
    raise ValueError(f"Unknown problem type: {kind}")


def check_answer(problem, key, value):
    """Return (is_correct, relative_error) for one answer of a practice problem."""
    a = next(x for x in problem["answers"] if x["key"] == key)
    err = abs(value - a["value"]) / abs(a["value"])
    return err <= a["tol"], err


# --------------------------------------------------------------------------- explain my result
def _day(ts):
    return pd.Timestamp(ts).strftime("%d %b %Y")


def explain_hx(res, params, warn=10.0, crit=25.0):
    ok = res[res["error"] == ""]
    if len(ok) < 3:
        return ["Not enough valid readings yet. Load or upload at least 3 readings to get an explanation."]
    first, last = ok["u_loss_pct"].head(3).mean(), ok["u_loss_pct"].tail(3).mean()
    now = ok.iloc[-1]
    days = max(1.0, (ok["timestamp"].iloc[-1] - ok["timestamp"].iloc[0]).total_seconds() / 86400)
    out = [f"**What the numbers say.** U is now about {now['u']:,.0f} W/m²K, which is {now['u_loss_pct']:.1f}% below the clean design value of "
           f"{params['u_clean']:g} W/m²K. The fouling resistance is {now['rf']:.6f} m²K/W."]
    smooth = ok["u_loss_pct"].rolling(3, min_periods=3).mean().dropna()
    change5 = (smooth - smooth.shift(4)).abs()            # biggest change over any 5 readings
    total = abs(last - first)
    sudden = len(smooth) >= 8 and total >= 5 and change5.max() > 0.6 * total
    if total < 5:
        out.append("**Trend.** U has stayed close to its starting value, so there is no sign of fouling in this period.")
    elif sudden:
        when = ok["timestamp"].loc[change5.idxmax() - 2]
        out.append(f"**Trend.** Most of the change happened within a few readings around {_day(when)}. Fouling is usually gradual, so a sudden step points to "
                   "a change in flow or operation, a faulty sensor, or a cleaning event. Check what happened on that date.")
    else:
        out.append(f"**Trend.** U has declined gradually, by about {(last - first) / days * 30:.1f} percentage points per 30 days. A slow, steady decline "
                   "is the typical signature of fouling building up on the surfaces.")
    out.append(f"**Digital twin.** At the same flows and inlet temperatures, a clean exchanger would transfer about {now['q_expected_kw']:,.0f} kW. "
               f"Today's duty is {now['q_kw']:,.0f} kW, so about {now['q_expected_kw'] - now['q_kw']:,.0f} kW ({now['shortfall_pct']:.1f}%) is being lost.")
    if ok["mismatch_pct"].tail(5).mean() > 5:
        out.append("**Data quality.** Hot-side and cold-side duties disagree by more than 5% in recent readings, so check the flow meters and thermometers before trusting the U value.")
    if now["u_loss_pct"] > crit:
        out.append(f"**What to do.** The loss is beyond your {crit:g}% alarm level. Plan cleaning or inspection, then confirm U recovers afterwards.")
    elif now["u_loss_pct"] > warn:
        out.append(f"**What to do.** The loss is beyond your {warn:g}% warning level. Keep monitoring and plan cleaning before it reaches {crit:g}%.")
    else:
        out.append("**What to do.** Performance is within limits. Keep logging readings so a future change shows up early.")
    return out


def explain_pump(res, params):
    ok = res[res["error"] == ""]
    if len(ok) < 3:
        return ["Not enough valid readings yet. Load or upload at least 3 readings to get an explanation."]
    now = ok.iloc[-1]
    out = [f"**What the numbers say.** The latest reading is {now['flow_m3_h']:,.0f} m³/h at {now['head_m']:.1f} m head. The pump curve says {now['h_pump_expected']:.1f} m is expected "
           f"at this flow ({now['pump_dev_pct']:+.1f}%), and the system curve says {now['h_sys_expected']:.1f} m ({now['sys_dev_pct']:+.1f}%)."]
    if now["status"] == "healthy":
        out.append("**Diagnosis.** Both deviations are inside ±5%, so the reading fits the pump curve and the pipeline model. No fault is indicated.")
    elif now["status"] == "pump_degraded":
        out.append("**Diagnosis.** The point sits on the pipeline's system curve but below the pump curve. The pipeline behaves as modelled, so the pump is delivering less head than it should: "
                   "look for impeller or wear-ring wear, internal leakage, low speed or a suction problem.")
    elif now["status"] == "system_resistance":
        out.append("**Diagnosis.** The point sits on the pump curve but above the system curve. The pump is fine, but the pipeline needs more head than modelled: look for a partly closed valve, "
                   "a blocked strainer or scaling in the line.")
    else:
        out.append("**Diagnosis.** The reading does not fit a single clear cause. Re-check the instruments and the entered equipment data first.")
    bad = ok[ok["status"] != "healthy"]
    if not bad.empty and now["status"] != "healthy":
        out.append(f"**Trend.** The first off-curve reading was on {_day(bad['timestamp'].iloc[0])}; {len(bad)} of {len(ok)} readings are outside the ±5% band.")
    out.append("**What to do.** Use the What-if tab on the Pump page to test valve positions, and compare the result with the datasheet curve after any maintenance.")
    return out
