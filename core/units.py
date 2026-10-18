"""Unit conversions. Every category converts to the unit PlantPulse's engine uses (the first unit listed).

to_si(value) = value * factor + offset. Only temperature needs an offset.
"""

UNITS = {
    "temp": {"°C": (1.0, 0.0), "K": (1.0, -273.15), "°F": (5.0 / 9.0, -160.0 / 9.0), "°R": (5.0 / 9.0, -273.15)},
    "mass_flow": {"kg/s": (1.0, 0.0), "kg/min": (1 / 60, 0.0), "kg/h": (1 / 3600, 0.0), "g/s": (0.001, 0.0), "t/h": (1000 / 3600, 0.0),
                  "lb/s": (0.45359237, 0.0), "lb/min": (0.45359237 / 60, 0.0), "lb/h": (0.45359237 / 3600, 0.0)},
    "vol_flow": {"m³/h": (1.0, 0.0), "m³/s": (3600.0, 0.0), "m³/min": (60.0, 0.0), "L/s": (3.6, 0.0), "L/min": (0.06, 0.0), "L/h": (0.001, 0.0),
                 "gpm (US)": (0.2271247, 0.0), "ft³/s": (101.94064, 0.0), "ft³/min": (1.699011, 0.0), "ft³/h": (0.02831685, 0.0),
                 "bbl/day": (0.006624471, 0.0)},
    "cp": {"kJ/kg·K": (1.0, 0.0), "J/kg·K": (0.001, 0.0), "kcal/kg·°C": (4.1868, 0.0), "BTU/lb·°F": (4.1868, 0.0)},
    "power": {"kW": (1.0, 0.0), "W": (0.001, 0.0), "MW": (1000.0, 0.0), "kJ/h": (1 / 3600, 0.0), "kcal/h": (0.001163, 0.0),
              "BTU/h": (0.00029307107, 0.0), "hp": (0.7456999, 0.0), "TR": (3.516853, 0.0)},
    "area": {"m²": (1.0, 0.0), "cm²": (1e-4, 0.0), "mm²": (1e-6, 0.0), "ft²": (0.09290304, 0.0), "in²": (6.4516e-4, 0.0)},
    "u_coeff": {"W/m²·K": (1.0, 0.0), "kW/m²·K": (1000.0, 0.0), "kcal/h·m²·°C": (1.163, 0.0), "BTU/h·ft²·°F": (5.678263, 0.0),
                "cal/s·cm²·°C": (41868.0, 0.0)},
    "length": {"m": (1.0, 0.0), "mm": (0.001, 0.0), "cm": (0.01, 0.0), "km": (1000.0, 0.0), "ft": (0.3048, 0.0), "in": (0.0254, 0.0),
               "yd": (0.9144, 0.0), "mile": (1609.344, 0.0)},
    "diameter": {"mm": (1.0, 0.0), "cm": (10.0, 0.0), "m": (1000.0, 0.0), "in": (25.4, 0.0), "ft": (304.8, 0.0)},
    "head": {"m": (1.0, 0.0), "ft": (0.3048, 0.0), "cm": (0.01, 0.0), "in": (0.0254, 0.0), "mm": (0.001, 0.0)},
    "pressure": {"kPa": (1.0, 0.0), "Pa": (0.001, 0.0), "MPa": (1000.0, 0.0), "bar": (100.0, 0.0), "mbar": (0.1, 0.0), "atm": (101.325, 0.0),
                 "psi": (6.894757, 0.0), "mmHg": (0.1333224, 0.0), "kgf/cm²": (98.0665, 0.0)},
    "velocity": {"m/s": (1.0, 0.0), "cm/s": (0.01, 0.0), "m/min": (1 / 60, 0.0), "km/h": (1 / 3.6, 0.0), "ft/s": (0.3048, 0.0),
                 "ft/min": (0.00508, 0.0), "mph": (0.44704, 0.0)},
    "density": {"kg/m³": (1.0, 0.0), "g/cm³": (1000.0, 0.0), "kg/L": (1000.0, 0.0), "lb/ft³": (16.018463, 0.0), "lb/gal (US)": (119.826427, 0.0)},
    "viscosity": {"mPa·s (cP)": (1.0, 0.0), "Pa·s": (1000.0, 0.0), "P (poise)": (100.0, 0.0), "lb/ft·s": (1488.1639, 0.0),
                  "lb/ft·h": (0.4133789, 0.0), "kg/m·h": (1 / 3.6, 0.0)},
    "roughness": {"mm": (1.0, 0.0), "µm": (0.001, 0.0), "m": (1000.0, 0.0), "in": (25.4, 0.0), "ft": (304.8, 0.0)},
}


def unit_names(cat):
    return list(UNITS[cat])


def si_unit(cat):
    """The unit the engine works in for this category."""
    return next(iter(UNITS[cat]))


def _fo(cat, unit):
    try:
        return UNITS[cat][unit]
    except KeyError:
        raise ValueError(f"Unknown unit '{unit}' for {cat}.")


def to_si(cat, unit, value):
    f, o = _fo(cat, unit)
    return value * f + o


def from_si(cat, unit, value):
    f, o = _fo(cat, unit)
    return (value - o) / f


def convert(cat, value, from_unit, to_unit):
    return from_si(cat, to_unit, to_si(cat, from_unit, value))


def to_si_series(cat, unit, series):
    """Same as to_si for a pandas Series (used for CSV files)."""
    f, o = _fo(cat, unit)
    return series * f + o
