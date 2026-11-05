"""Glossary of the terms PlantPulse uses. Pure data and a search function (no Streamlit)."""

CATEGORIES = ["Heat exchangers", "Fluid flow and pumps", "General"]


def _t(id_, term, category, definition, formula="", unit="", in_app="", see=(), aliases=()):
    return {"id": id_, "term": term, "category": category, "definition": definition, "formula": formula, "unit": unit,
            "in_app": in_app, "see_also": list(see), "aliases": list(aliases)}


HX, FL, GEN = CATEGORIES
GLOSSARY = [
    _t("lmtd", "LMTD (Log Mean Temperature Difference)", HX,
       "The average temperature difference that drives heat transfer in an exchanger. The hot and cold temperatures change along the exchanger, so the difference between them is different "
       "at the two ends (ΔT₁ and ΔT₂); the logarithmic mean gives the correct average.",
       r"LMTD=\dfrac{\Delta T_1-\Delta T_2}{\ln(\Delta T_1/\Delta T_2)}", "K (a temperature difference)", "Heat Exchanger Solver and Heat Exchanger pages",
       ("correction_factor", "counter_flow", "parallel_flow", "overall_u"), ("log mean temperature difference", "logarithmic mean temperature difference", "delta t lm")),
    _t("correction_factor", "Correction factor (F)", HX,
       "A number from 0 to 1 that corrects the counter-flow LMTD for exchangers whose flow is partly parallel, such as shell-and-tube exchangers with several tube passes. "
       "F = 1 for pure counter-flow. A very low F (below about 0.75) usually means the arrangement is a poor choice for those temperatures.",
       r"\Delta T_{lm,corr}=F\cdot LMTD_{counter}", "- (dimensionless)", "Heat Exchanger Solver (calculated from R and P, or entered)", ("lmtd", "shell_tube"), ("lmtd correction factor", "f factor")),
    _t("overall_u", "Overall heat transfer coefficient (U)", HX,
       "How much heat passes through each square metre of heat transfer surface for each degree of temperature difference. It combines the resistance of both fluid films, the tube wall "
       "and any fouling. A higher U means heat transfers more easily.",
       r"Q=U\,A\,\Delta T_{lm}", "W/m²·K", "Heat Exchanger Solver, Monitor, Equipment", ("fouling_factor", "lmtd", "heat_duty"), ("overall heat transfer coefficient", "u value", "u-value", "u")),
    _t("fouling_factor", "Fouling factor (fouling resistance, Rf)", HX,
       "The extra thermal resistance caused by deposits such as scale, dirt, corrosion products or biological growth on the heat transfer surface. It lowers U over time, "
       "which is why exchangers are cleaned.",
       r"R_f=\dfrac{1}{U_{fouled}}-\dfrac{1}{U_{clean}}", "m²·K/W", "Heat Exchanger pages and the Monitor (fouling trend and alerts)", ("overall_u", "digital_twin"), ("fouling", "fouling resistance", "rf")),
    _t("heat_duty", "Heat duty (Q)", HX,
       "The rate at which heat is transferred in the exchanger. The hot fluid gives up the same heat that the cold fluid takes up, if there is no heat loss.",
       r"Q=\dot m\,C_p\,\Delta T", "kW (kJ/s)", "Every heat exchanger page", ("specific_heat", "heat_balance", "capacity_rate"), ("duty", "heat load", "heat transfer rate")),
    _t("specific_heat", "Specific heat (Cp)", HX,
       "The heat needed to raise the temperature of 1 kg of a substance by 1 K. Liquid water is about 4.18 kJ/kg·K.",
       "", "kJ/kg·K", "Inputs of the heat exchanger pages", ("heat_duty", "capacity_rate"), ("cp", "heat capacity", "specific heat capacity")),
    _t("capacity_rate", "Heat capacity rate (C)", HX,
       "The mass flow of a stream multiplied by its specific heat. The stream with the smaller C changes temperature more for the same heat duty, and sets the maximum possible heat transfer.",
       r"C=\dot m\,C_p", "kW/K", "Effectiveness and NTU calculations behind the digital twin", ("effectiveness", "ntu", "specific_heat")),
    _t("effectiveness", "Effectiveness (ε)", HX,
       "The ratio of the heat actually transferred to the maximum heat that could be transferred with the same inlet temperatures and flows. It lies between 0 and 1.",
       r"\varepsilon=\dfrac{Q}{Q_{max}},\qquad Q_{max}=C_{min}(T_{h,in}-T_{c,in})", "-", "The digital twin of the heat exchanger (predicts the clean outlet temperatures)", ("ntu", "capacity_rate", "digital_twin")),
    _t("ntu", "NTU (Number of Transfer Units)", HX,
       "A dimensionless size of the exchanger: its UA divided by the smaller heat capacity rate. A larger NTU means a bigger exchanger for the same flows, and a higher effectiveness, with diminishing returns.",
       r"NTU=\dfrac{UA}{C_{min}}", "-", "The digital twin of the heat exchanger", ("effectiveness", "capacity_rate", "overall_u")),
    _t("counter_flow", "Counter-flow", HX,
       "An arrangement in which the two fluids move in opposite directions. For the same terminal temperatures it gives the largest LMTD, so it needs the least heat transfer area. "
       "The cold outlet can be hotter than the hot outlet.",
       "", "", "Heat Exchanger Solver (exchanger type 1-1 counter-flow)", ("parallel_flow", "lmtd"), ("countercurrent", "counter-current")),
    _t("parallel_flow", "Parallel flow (co-current)", HX,
       "An arrangement in which both fluids move in the same direction. The cold outlet can never be hotter than the hot outlet, and the LMTD is smaller than for counter-flow.",
       "", "", "Heat Exchanger Solver (exchanger type 1-1 parallel flow)", ("counter_flow", "lmtd"), ("co-current", "cocurrent", "concurrent")),
    _t("shell_tube", "Shell-and-tube heat exchanger", HX,
       "An exchanger with a bundle of tubes inside a cylindrical shell. One fluid flows through the tubes (tube side) and the other around them in the shell (shell side). "
       "The tubes may make several passes, written as shell passes and tube passes, for example 1-2 or 2-4; baffles in the shell direct the shell-side flow across the tubes.",
       "", "", "Heat Exchanger Solver and its animated diagram", ("correction_factor", "lmtd")),
    _t("heat_balance", "Heat balance (energy balance)", HX,
       "With no heat loss, the heat given by the hot fluid equals the heat taken by the cold fluid. Checking both sides is a quick test of the flow and temperature readings.",
       r"\dot m_hC_{p,h}(T_{h,in}-T_{h,out})=\dot m_cC_{p,c}(T_{c,out}-T_{c,in})", "kW", "The heat balance check (mismatch warning) on the heat exchanger pages", ("heat_duty",), ("energy balance", "mismatch")),
    _t("sieder_tate", "Sieder-Tate correction (wall viscosity)", HX,
       "A factor that corrects a fluid's film heat transfer coefficient for the viscosity change between the bulk of the fluid and the wall, where the fluid is hotter or cooler.",
       r"\phi=\left(\dfrac{\mu_{bulk}}{\mu_{wall}}\right)^{0.14}", "-", "Wall-viscosity correction in the Heat Exchanger Solver", ("overall_u", "viscosity"), ("viscosity correction", "wall viscosity")),
    _t("reynolds", "Reynolds number (Re)", FL,
       "The ratio of inertial to viscous forces in a flow. In a pipe the flow is laminar below about 2,300 and turbulent above about 4,000; in between it is unstable.",
       r"Re=\dfrac{\rho\,v\,D}{\mu}", "- (dimensionless)", "Pipe and Pump Solver, Pump & Pipeline", ("friction_factor", "darcy_weisbach", "viscosity")),
    _t("friction_factor", "Friction factor (Darcy, f)", FL,
       "A dimensionless number that tells how much friction a pipe wall causes. It depends on the Reynolds number and on the relative roughness of the pipe. "
       "It is 64/Re for laminar flow. The Fanning friction factor used in some books is one quarter of the Darcy factor.",
       r"f=\dfrac{64}{Re}\ \ (\text{laminar})", "-", "Pipe and Pump Solver (Swamee-Jain equation for turbulent flow)", ("reynolds", "darcy_weisbach"), ("darcy friction factor", "fanning")),
    _t("darcy_weisbach", "Darcy-Weisbach equation", FL,
       "The standard equation for the friction loss in a straight pipe. The loss grows with the pipe length and with the square of the velocity, and falls as the diameter increases. "
       "It works for any fluid and any flow regime once the friction factor is known.",
       r"h_f=f\,\dfrac{L}{D}\,\dfrac{v^2}{2g}\qquad \Delta P=f\,\dfrac{L}{D}\,\dfrac{\rho v^2}{2}", "m of liquid (head) or Pa (pressure)", "Pipe and Pump Solver, Pump & Pipeline",
       ("friction_factor", "reynolds", "head", "minor_losses"), ("darcy weisbach", "friction loss", "head loss")),
    _t("minor_losses", "Minor losses (K and Le/D)", FL,
       "The extra friction loss in fittings and valves. Textbooks give it either as a loss coefficient K for each fitting, or as an equivalent length of straight pipe written as a multiple of the diameter (Le/D).",
       r"h_K=\Sigma K\,\dfrac{v^2}{2g}\qquad h_{Le}=f\,\dfrac{L_e}{D}\,\dfrac{v^2}{2g}", "m of liquid", "Pipe and Pump Solver (toggle between ΣK and Le/D)", ("darcy_weisbach", "head"), ("fittings", "equivalent length", "k value")),
    _t("head", "Head", FL,
       "Energy per unit weight of liquid, written as the height of a column of that liquid, in metres. Pump head is the energy the pump adds. Because it is per unit weight, the same head applies "
       "to any liquid, while the pressure it produces depends on the density.",
       r"H=\dfrac{P}{\rho g}", "m of liquid", "All pump pages", ("static_head", "pump_curve", "system_curve"), ("pump head", "total head")),
    _t("static_head", "Static head", FL,
       "The height the liquid must be lifted: the difference between the discharge and suction liquid levels, plus any pressure difference between the two ends expressed as a head. "
       "It does not change with the flow.",
       "", "m of liquid", "Pipe and Pump Solver, Pump & Pipeline", ("head", "system_curve"), ("static lift", "elevation head")),
    _t("system_curve", "System curve", FL,
       "A graph of the head the pipeline needs at each flow: the static head plus the friction and fitting losses, which grow roughly with the square of the flow. "
       "A partly closed valve, a blockage or scale makes the curve steeper.",
       r"H_{sys}=H_{static}+\left(f\dfrac{L}{D}+\Sigma K\right)\dfrac{v^2}{2g}", "m", "Pump & Pipeline and Monitor", ("pump_curve", "operating_point", "static_head")),
    _t("pump_curve", "Pump curve", FL,
       "A graph from the pump maker showing the head the pump produces at each flow, measured on water. The head is highest at zero flow (shut-off head) and falls as the flow rises.",
       "", "m versus m³/h", "Pump & Pipeline, Monitor, Pipe and Pump Solver (viscosity correction)", ("system_curve", "operating_point", "bep")),
    _t("operating_point", "Operating point", FL,
       "The flow and head at which a pump actually runs: where the pump curve crosses the system curve. Throttling a valve or fouling the line moves it to a lower flow; pump wear lowers the pump curve.",
       r"H_{pump}(Q)=H_{sys}(Q)", "m³/h and m", "Pump & Pipeline, Pipe and Pump Solver", ("pump_curve", "system_curve", "bep")),
    _t("bep", "BEP (Best Efficiency Point)", FL,
       "The flow at which a pump is most efficient. Running far from it wastes energy and increases vibration and wear, so pumps are best selected so that the operating point lies close to the BEP.",
       "", "m³/h", "Pipe and Pump Solver (viscosity correction uses the BEP)", ("operating_point", "pump_curve", "hi_viscosity")),
    _t("hydraulic_power", "Hydraulic power and shaft power", FL,
       "Hydraulic power is the power the liquid receives from the pump. The shaft power the motor must deliver is larger, because the pump is not 100% efficient.",
       r"P_{hyd}=\rho\,g\,Q\,H\qquad P_{shaft}=\dfrac{P_{hyd}}{\eta}", "kW", "Pump & Pipeline, Pipe and Pump Solver", ("head", "bep"), ("pump power", "shaft power", "brake power")),
    _t("npsh", "NPSH (Net Positive Suction Head)", FL,
       "A measure of how far the pressure at the pump suction is above the point where the liquid would boil, expressed as a head of liquid. NPSH available (NPSHa) depends on the system: "
       "the pressure on the liquid, the liquid level, the suction losses and the vapor pressure. NPSH required (NPSHr) is set by the pump. NPSHa must exceed NPSHr, with a safety margin, "
       "or the pump cavitates.",
       r"NPSH_a=\dfrac{P_{abs}-P_v}{\rho g}+z-h_{f,s}", "m of liquid", "Pipe and Pump Solver, NPSH section (Cavitation Risk warning)", ("cavitation", "vapor_pressure", "absolute_pressure", "head"),
       ("npsha", "npshr", "net positive suction head", "npsh available", "npsh required")),
    _t("cavitation", "Cavitation", FL,
       "The formation and violent collapse of vapor bubbles inside a pump when the pressure at the impeller inlet falls below the vapor pressure of the liquid. "
       "It causes noise, vibration, a drop in head and flow, and damage to the impeller.",
       "", "", "NPSH section of the Pipe and Pump Solver", ("npsh", "vapor_pressure")),
    _t("vapor_pressure", "Vapor pressure", FL,
       "The pressure at which a liquid boils at a given temperature. It rises quickly with temperature, which is why hot liquids are harder to pump without cavitation. "
       "Use the absolute value in NPSH calculations.",
       "", "kPa absolute", "NPSH section (calculated for water from the temperature)", ("npsh", "cavitation", "absolute_pressure"), ("vapour pressure",)),
    _t("absolute_pressure", "Absolute and gauge pressure", FL,
       "Gauge pressure is measured relative to the atmosphere; absolute pressure is measured relative to a perfect vacuum. Calculations that involve vapor pressure, such as NPSH, need absolute pressure.",
       r"P_{abs}=P_{gauge}+P_{atm}", "kPa", "NPSH section (gauge or absolute choice)", ("npsh", "vapor_pressure"), ("gauge pressure", "atmospheric pressure")),
    _t("viscosity", "Viscosity (dynamic and kinematic)", FL,
       "A measure of a fluid's resistance to flow. Dynamic viscosity μ is usually given in cP (1 cP = 1 mPa·s; water is about 1 cP). Kinematic viscosity ν is the dynamic viscosity divided by the density, "
       "usually in cSt (1 cSt = 1 mm²/s).",
       r"\nu=\dfrac{\mu}{\rho}", "cP or mPa·s (dynamic), cSt (kinematic)", "Pipe and Pump Solver (other liquids)", ("reynolds", "hi_viscosity", "sieder_tate"), ("dynamic viscosity", "kinematic viscosity", "cp", "cst", "centipoise")),
    _t("hi_viscosity", "Hydraulic Institute viscosity correction", FL,
       "A standard method (ANSI/HI 9.6.7) that corrects a water pump curve for a viscous liquid. It uses a parameter B, which depends on the viscosity, head, flow and speed, to find factors that lower the flow, "
       "the head and above all the efficiency. It is not needed when B is 1 or below, and it is not defined for B of 40 or more.",
       r"B=\dfrac{16.5\,\nu^{0.5}\,H_{BEP}^{0.0625}}{Q_{BEP}^{0.375}\,N^{0.25}}", "-", "Pump curve section of the Pipe and Pump Solver", ("viscosity", "bep", "pump_curve")),
    _t("digital_twin", "Digital twin", GEN,
       "A model of a piece of equipment that predicts what it should be doing under the present conditions. Comparing the prediction with the measured readings shows when something has changed, "
       "for example fouling in an exchanger or wear in a pump.",
       "", "", "Monitor (expected versus observed charts and alerts)", ("fouling_factor", "effectiveness", "operating_point"), ("twin", "digital model")),
]


def get_term(term_id):
    return next((t for t in GLOSSARY if t["id"] == term_id), None)


def term_names(ids):
    return [get_term(i)["term"] for i in ids if get_term(i)]


def search(query="", category=None):
    """Terms matching the query (in the name, an alias or the definition), best matches first; with no query, A to Z."""
    q = (query or "").strip().lower()
    pool = [t for t in GLOSSARY if category in (None, "All", t["category"])]
    if not q:
        return sorted(pool, key=lambda t: t["term"].lower())
    scored = []
    for t in pool:
        names = [t["term"].lower()] + [a.lower() for a in t["aliases"]]
        if any(n == q for n in names):
            rank = 0
        elif any(n.startswith(q) for n in names):
            rank = 1
        elif any(q in n for n in names):
            rank = 2
        elif q in t["definition"].lower():
            rank = 3
        else:
            continue
        scored.append((rank, t["term"].lower(), t))
    return [t for _, _, t in sorted(scored, key=lambda s: (s[0], s[1]))]
