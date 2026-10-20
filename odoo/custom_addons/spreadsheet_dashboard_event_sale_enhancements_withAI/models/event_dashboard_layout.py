# -*- coding: utf-8 -*-
"""Layout helpers shared by the Events dashboard patches (no Odoo import).

The Events dashboard mixes absolutely positioned figures (charts/cards, placed
by pixel offset) with cell based tables.  To insert a block of figures above
the existing content we (1) grow the empty row just above the first heading,
which moves every cell below it, and (2) add the same amount to the offset of
every figure that sits at or below that heading.
"""
import re

DEFAULT_ROW_HEIGHT = 23
HEADING_TOLERANCE = 30


def find_sheet(data, name):
    return next((s for s in data.get("sheets", []) if s.get("name") == name), None)


def row_top(sheet, index):
    rows = sheet.get("rows") or {}
    return sum((rows.get(str(i)) or {}).get("size", DEFAULT_ROW_HEIGHT) for i in range(index))


def first_content_row(sheet):
    """0-based index of the first row that holds a cell (the first heading)."""
    found = []
    for ref in (sheet.get("cells") or {}):
        m = re.match(r"^[A-Z]+(\d+)$", ref)
        if m:
            found.append(int(m.group(1)) - 1)
    return min(found) if found else None


def kpi_bottom(sheet):
    cards = [f for f in sheet.get("figures", []) if (f.get("data") or {}).get("type") == "scorecard"]
    return max([(f.get("offset") or {}).get("y", 0) + f.get("height", 0) for f in cards] or [0])


def reserve_space(sheet, height):
    """Open ``height`` px at the current top of the first heading.

    Returns the y where the new block should start (the heading's old top), or
    None when the layout is not recognised (caller then skips its block).
    """
    first_row = first_content_row(sheet)
    if not first_row:
        return None
    heading_y = row_top(sheet, first_row)
    rows = sheet.setdefault("rows", {})
    spacer = rows.setdefault(str(first_row - 1), {"size": DEFAULT_ROW_HEIGHT})
    spacer["size"] = spacer.get("size", DEFAULT_ROW_HEIGHT) + height
    for fig in sheet.get("figures", []):
        off = fig.get("offset") or {}
        if off.get("y", 0) >= heading_y - HEADING_TOLERANCE:
            off["y"] = off.get("y", 0) + height
    return heading_y
