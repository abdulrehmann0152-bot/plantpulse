"""A number box with a unit dropdown. Returns the value converted to the engine unit (or None if left empty)."""
import streamlit as st

from core import units


def unit_input(label, cat, default, key, *, optional=False, min_value=None, step=None, container=None, show_si=True,
               placeholder="empty = unknown", help=None, disabled=False):
    """Type the number as the problem gives it, then pick its unit. The unit dropdown has key f'{key}_u'."""
    box = container if container is not None else st
    names = units.unit_names(cat)
    c_val, c_unit = box.columns([3, 2])
    unit = c_unit.selectbox("Unit", names, key=f"{key}_u", label_visibility="hidden", disabled=disabled)
    x = c_val.number_input(label, min_value=min_value, value=None if optional else float(default), step=step, format="%g",
                           placeholder=placeholder if optional else None, key=key, help=help, disabled=disabled)
    if x is None:
        return None
    si = units.to_si(cat, unit, x)
    if show_si and unit != names[0]:
        box.caption(f"= {si:.6g} {names[0]}")
    return si
