"""Structured templates and subfield models for Location and Price fields."""

import re
from typing import Any, Dict, List, Tuple


LOCATION_TEMPLATES = [
    {
        "name": "Beige Cart",
        "format": "Location: Beige Cart, drawer {drawer}",
        "subfields": [
            {"key": "drawer", "label": "drawer", "type": "number", "default": "7"},
        ],
    },
    {
        "name": "Black Cart",
        "format": "Location: Black Cart, drawer {drawer}",
        "subfields": [
            {"key": "drawer", "label": "drawer", "type": "number", "default": "1"},
        ],
    },
    {
        "name": "South Wall",
        "format": "Location: South Wall, row {row}, column {col}",
        "subfields": [
            {"key": "row", "label": "row", "type": "number", "default": "1"},
            {"key": "col", "label": "column", "type": "number", "default": "1"},
        ],
    },
    {
        "name": "North Wall",
        "format": "Location: North Wall, row {row}, column {col}",
        "subfields": [
            {"key": "row", "label": "row", "type": "number", "default": "1"},
            {"key": "col", "label": "column", "type": "number", "default": "1"},
        ],
    },
    {
        "name": "Toolbox",
        "format": "Location: Toolbox: {name}",
        "subfields": [
            {"key": "name", "label": "name", "type": "text", "default": "General"},
        ],
    },
]


PRICE_TEMPLATES = [
    {
        "name": "Single ($/ea)",
        "format": "MSRP: ${amount}",
        "subfields": [
            {"key": "amount", "label": "MSRP $", "type": "number", "default": "14.95"},
        ],
    },
    {
        "name": "Per Qty ($/units)",
        "format": "MSRP: ${amount}/{qty} {unit_name}",
        "subfields": [
            {"key": "amount", "label": "MSRP $", "type": "number", "default": "2.50"},
            {"key": "qty", "label": "qty", "type": "number", "default": "10"},
            {"key": "unit_name", "label": "unit", "type": "text", "default": "units"},
        ],
    },
]


def parse_location(loc_str: str) -> Tuple[int, Dict[str, str]]:
    """Extracts template index and subfield values from a location string."""
    s = (loc_str or "").strip()
    s_lower = s.lower()

    if "beige" in s_lower:
        idx = 0
        m = re.search(r"drawer\s*(\d+)", s_lower)
        drawer = m.group(1) if m else "7"
        return idx, {"drawer": drawer}

    if "black" in s_lower:
        idx = 1
        m = re.search(r"drawer\s*(\d+)", s_lower)
        drawer = m.group(1) if m else "1"
        return idx, {"drawer": drawer}

    if "south" in s_lower:
        idx = 2
        r_m = re.search(r"row\s*(\d+)", s_lower)
        c_m = re.search(r"col(?:umn)?\s*(\d+)", s_lower)
        return idx, {
            "row": r_m.group(1) if r_m else "1",
            "col": c_m.group(1) if c_m else "1",
        }

    if "north" in s_lower:
        idx = 3
        r_m = re.search(r"row\s*(\d+)", s_lower)
        c_m = re.search(r"col(?:umn)?\s*(\d+)", s_lower)
        return idx, {
            "row": r_m.group(1) if r_m else "1",
            "col": c_m.group(1) if c_m else "1",
        }

    if "toolbox" in s_lower:
        idx = 4
        m = re.search(r"toolbox\s*:\s*(.+)", s, re.IGNORECASE)
        name = m.group(1).strip() if m else "General"
        return idx, {"name": name}

    # Default to Beige Cart
    return 0, {"drawer": "7"}


def format_location(tmpl_idx: int, vals: Dict[str, str]) -> str:
    """Formats location string from template index and subfield values."""
    if not (0 <= tmpl_idx < len(LOCATION_TEMPLATES)):
        tmpl_idx = 0
    tmpl = LOCATION_TEMPLATES[tmpl_idx]
    clean_vals = {}
    for sf in tmpl["subfields"]:
        k = sf["key"]
        clean_vals[k] = vals.get(k, sf["default"])
    return tmpl["format"].format(**clean_vals)


def parse_price(price_str: str) -> Tuple[int, Dict[str, str]]:
    """Extracts template index and subfield values from a price string."""
    s = (price_str or "").strip()

    if "/" in s:
        # Per quantity format: e.g. MSRP: $2.50/10 pcs or $5/meter or $350/10 units
        tmpl_idx = 1
        parts = s.split("/", 1)
        m_amt = re.search(r"(\d+(?:\.\d+)?)", parts[0])
        amt = m_amt.group(1) if m_amt else "2.50"

        tail = parts[1].strip()
        m_tail = re.match(r"^(\d+)\s*(.*)$", tail)
        if m_tail:
            qty = m_tail.group(1)
            unit_name = m_tail.group(2).strip() or "units"
        else:
            qty = "1"
            unit_name = tail or "units"

        return tmpl_idx, {"amount": amt, "qty": qty, "unit_name": unit_name}

    # Single unit format: e.g. MSRP: $14.95 or $35.00
    tmpl_idx = 0
    m_amt = re.search(r"(\d+(?:\.\d+)?)", s)
    amt = m_amt.group(1) if m_amt else "14.95"
    return tmpl_idx, {"amount": amt}


def format_price(tmpl_idx: int, vals: Dict[str, str]) -> str:
    """Formats price string from template index and subfield values."""
    if not (0 <= tmpl_idx < len(PRICE_TEMPLATES)):
        tmpl_idx = 0
    if tmpl_idx == 0:
        amt = vals.get("amount", "14.95").strip()
        return f"MSRP: ${amt}"

    amt = vals.get("amount", "2.50").strip()
    qty = vals.get("qty", "10").strip()
    unit_name = vals.get("unit_name", "units").strip() or "units"

    if qty and qty != "1":
        return f"MSRP: ${amt}/{qty} {unit_name}"
    else:
        return f"MSRP: ${amt}/{unit_name}"
