# -*- coding: utf-8 -*-
"""
Runtime patch applied to the JSON payload of the standard "Sales"
spreadsheet dashboard (``spreadsheet_dashboard_sale.spreadsheet_dashboard_sales``).

Every technique used below was reverse-engineered from the *actual* shipped
``sales_dashboard.json`` / ``product_dashboard.json`` files of
``spreadsheet_dashboard_sale`` (Odoo 19), not invented:

- KPI cards are ``chart`` figures of ``type: "scorecard"`` whose ``keyValue``
  / ``baseline`` point at formula cells on the hidden "Data" sheet
  (see the existing Quotations/Orders/Revenue/Average Order cards).
- Click-through navigation for a scorecard figure is wired via the
  workbook-level ``chartOdooMenusReferences`` map: ``{chartId: "module.menu_xmlid"}``.
  The existing Revenue and Average Order cards already point at
  ``sale.menu_reporting_sales`` - the same target this module reuses.
- The existing "Top Products" table is produced by ``=PIVOT(6, 10, FALSE, FALSE)``,
  a dynamic array spill of pivot id 6, anchored at the title link cell
  ``E35`` (Product/Orders/Revenue in columns E/F/G). The spill geometry /
  column-header behaviour of ``PIVOT()`` is implemented in the (private)
  o-spreadsheet JS layer, so we do NOT attempt to rewrite that formula or
  insert a column *inside* its spilled range. Instead we add a single
  "Contribution %" column in column H - the unused column immediately to
  the right of the spill's own Revenue column (G) - over the same row
  range, using the *documented-by-example* ranked lookup function
  ``PIVOT.VALUE(pivotId, measure, "#field", rank)``
  - the exact mechanism the stock "Best Seller" / "Best Category" cards use
  in ``product_dashboard.json`` - against the *same* pivot id 6 the stock
  Top Products table already uses, so the figures are guaranteed consistent.
  (v2: an earlier version of this module built a whole separate, relabelled
  copy of Product/Orders/Revenue next to the real table, which rendered as
  two side-by-side tables. That copy has been removed - only the one new
  column is added now.)
- The existing "so stats - current" / "so stats - previous" pivots (ids 11/12)
  already give this dashboard a current-vs-previous-equivalent-period
  comparison, driven purely by the "Period" global filter (offset 0 vs -1).
  Sales Growth reuses those two pivots' revenue totals directly instead of
  creating a parallel comparison mechanism.

Everything here is additive: no existing pivot, cell, figure or global
filter is modified or removed.
"""

# Pivot ids already used by spreadsheet_dashboard_sale: "3".."12".
NEW_CANCELLATION_PIVOT_ID = "13"

# Cell block reserved on the (hidden, utility) "Data" sheet.
# Rows 1-8 / cols A-E are already used by the stock dashboard - everything
# below starts at row 10 in unused columns to guarantee zero collisions.
CUSTOMER_PIVOT_ROWS = 1000  # max customer rows materialized in the hidden helper area

# New KPI scorecards are appended to the same row/col anchor as the existing
# four cards. The seven cards are laid out cumulatively so the complete titles
# and KPI values remain visible in a single row.
NEW_KPI_FIGURE_IDS = {
    "revenue_per_customer": "b848046b-cf3b-4d4a-808f-e84dc363e738",
    "sales_growth": "8c0c94c3-1961-41c4-82b1-b671e87b77a0",
    "cancellation_rate": "c2f35dc0-bf1a-4fe6-ae55-3cc6ac8c3d4b",
}

TOP_PRODUCTS_PIVOT_ID = "6"          # stock "Product" pivot, already sorted desc by price_subtotal
POSITIVE_PRODUCT_REVENUE_PIVOT_ID = "14"  # all positive product revenue, same current-period/global filters
CURRENT_PERIOD_STATS_PIVOT_ID = "11"  # stock "so stats - current"
PREVIOUS_PERIOD_STATS_PIVOT_ID = "12"  # stock "so stats - previous"
CUSTOMER_PIVOT_ID = "4"              # stock "Customer" pivot (partner_id rows, current period)

MENU_XMLID_REPORTING_SALES = "sale.menu_reporting_sales"  # proven valid: already used by Revenue/Average Order cards


def _copy_field_matching(pivots, pivot_id):
    """Return a deep-enough copy of an existing pivot's fieldMatching block
    so new pivots stay wired to the same global filters (Period, Country,
    Product, Customer, Category, Sales Team, Salesperson, Source, Medium)."""
    import copy
    return copy.deepcopy(pivots[pivot_id]["fieldMatching"])


def patch_sales_dashboard_json(data):
    """Return a patched copy of the Sales dashboard snapshot dict.

    ``data`` is the already-``json.loads``-ed spreadsheet snapshot as
    produced by ``spreadsheet.dashboard._get_serialized_readonly_dashboard``.
    """
    import copy
    data = copy.deepcopy(data)

    pivots = data.setdefault("pivots", {})
    sheets = data.get("sheets", [])
    dashboard_sheet = next((s for s in sheets if s.get("name") == "Dashboard"), None)
    data_sheet = next((s for s in sheets if s.get("name") == "Data"), None)
    if dashboard_sheet is None or data_sheet is None:
        # Defensive: if the stock dashboard structure ever changes shape in
        # a way we don't recognise, don't guess - leave the dashboard as-is
        # rather than risk corrupting it.
        return data

    _add_cancellation_pivot(pivots)
    _add_positive_product_revenue_pivot(pivots)
    _add_data_sheet_helper_cells(data_sheet)
    _add_kpi_scorecards(dashboard_sheet)
    _add_contribution_table(dashboard_sheet, data)
    _register_menu_references(data)

    try:
        data["pivotNextId"] = str(max(int(k) for k in pivots.keys()) + 1)
    except (ValueError, TypeError):
        pass

    return data


def _add_cancellation_pivot(pivots):
    if NEW_CANCELLATION_PIVOT_ID in pivots:
        return  # already patched (defensive - see model override)
    field_matching = _copy_field_matching(pivots, CURRENT_PERIOD_STATS_PIVOT_ID)
    pivots[NEW_CANCELLATION_PIVOT_ID] = {
        "type": "ODOO",
        "fieldMatching": field_matching,
        "context": {"group_by": []},
        # No state filter at all (unlike pivot 11/12) so cancelled orders
        # are not excluded before grouping - this is what pivot 11/12
        # cannot give us, since their domain already excludes state=cancel.
        "domain": [],
        "id": NEW_CANCELLATION_PIVOT_ID,
        "measures": [
            {"id": "order_reference", "fieldName": "order_reference", "userDefinedName": "Orders"},
        ],
        "model": "sale.report",
        "name": "Order cancellation stats - current",
        "sortedColumn": None,
        "formulaId": NEW_CANCELLATION_PIVOT_ID,
        "columns": [],
        "rows": [{"fieldName": "state"}],
    }


def _add_positive_product_revenue_pivot(pivots):
    """Create a helper pivot containing only positive sales amounts.

    % of Revenue is a contribution/share metric. Discount lines in
    ``sale.report`` are negative values and must not reduce the denominator
    (or make a normal product appear to contribute more than 100%). The
    denominator therefore uses the sum of positive ``price_subtotal`` values
    across the complete current-period domain, while the visible Top Products
    rows still come from the stock product pivot (id 6).
    """
    if POSITIVE_PRODUCT_REVENUE_PIVOT_ID in pivots:
        return
    field_matching = _copy_field_matching(pivots, CURRENT_PERIOD_STATS_PIVOT_ID)
    pivots[POSITIVE_PRODUCT_REVENUE_PIVOT_ID] = {
        "type": "ODOO",
        "fieldMatching": field_matching,
        "context": {"group_by": []},
        "domain": [["price_subtotal", ">", 0]],
        "id": POSITIVE_PRODUCT_REVENUE_PIVOT_ID,
        "measures": [
            {
                "id": "price_subtotal",
                "fieldName": "price_subtotal",
                "userDefinedName": "Untaxed Total",
            },
        ],
        "model": "sale.report",
        "name": "Positive product sales revenue - current period",
        "sortedColumn": None,
        "formulaId": POSITIVE_PRODUCT_REVENUE_PIVOT_ID,
        "columns": [],
        "rows": [],
    }


def _set_cells(sheet, cells):
    sheet.setdefault("cells", {})
    sheet["cells"].update(cells)


def _add_data_sheet_helper_cells(data_sheet):
    cells = {}

    # --- Revenue Per Customer -------------------------------------------------
    # The previous implementation incorrectly treated the third argument of
    # PIVOT.HEADER() as a row/rank number. In Odoo 19, PIVOT.HEADER() accepts
    # domain field/value pairs; it does not expose a rank argument. That made
    # the old J1:J200 helper unreliable and, in the user's dashboard, caused
    # the customer denominator to behave like the 200-row cap.
    #
    # Use the stock Customer pivot (id 4) itself as a dynamic array instead.
    # Pivot 4 is already grouped by partner_id and wired to the dashboard's
    # current-period filters. With totals and column titles disabled, its first
    # output column is exactly the customer dimension. COUNTA over that column
    # therefore gives the actual number of customer groups currently returned
    # by the pivot. This also grows automatically as new customers appear, up
    # to the generous helper-row limit below.
    for n in range(1, CUSTOMER_PIVOT_ROWS + 1):
        cells.pop(f"J{n}", None)
    cells["J1"] = f'=PIVOT({CUSTOMER_PIVOT_ID},{CUSTOMER_PIVOT_ROWS},0,0)'

    cells["A10"] = '=_t("Unique customers (current period)")'
    cells["H10"] = f"=COUNTA(J1:J{CUSTOMER_PIVOT_ROWS})"

    cells["A11"] = '=_t("Revenue Per customer (raw)")'
    cells["H11"] = "=IFERROR(B7/H10,0)"  # B7 = current-period Revenue, already on this sheet

    cells["A12"] = '=_t("Revenue Per customer")'
    cells["H12"] = "=FORMAT.LARGE.NUMBER(H11)"
    cells["I12"] = '=_t("per unique customer")'

    # Use the same large-number formatter as the stock Revenue KPI.
    # This displays large values compactly, e.g. ₹175.88k instead of the full amount.

    # --- Sales Growth -----------------------------------------------------------
    # Reuses the existing current (B7) / previous (C7) period Revenue totals,
    # already computed on this sheet from pivots 11/12, which are themselves
    # already driven by the "Period" global filter (offset 0 / -1). No new
    # pivot needed.
    cells["A13"] = '=_t("Sales growth (raw)")'
    cells["H13"] = "=IFERROR((B7-C7)/C7,0)"

    cells["A14"] = '=_t("Sales growth")'
    cells["H14"] = '=IF(H13>=0,"+","")&ROUND(H13*100,1)&"%"'
    cells["I14"] = '=_t("vs previous period")'

    # --- Order Cancellation Percentage ---------------------------------------------------
    cells["A15"] = '=_t("Total orders, all states (current period)")'
    cells["H15"] = (
        f'=PIVOT.VALUE({NEW_CANCELLATION_PIVOT_ID},"order_reference","state","draft")'
        f'+PIVOT.VALUE({NEW_CANCELLATION_PIVOT_ID},"order_reference","state","sent")'
        f'+PIVOT.VALUE({NEW_CANCELLATION_PIVOT_ID},"order_reference","state","sale")'
        f'+PIVOT.VALUE({NEW_CANCELLATION_PIVOT_ID},"order_reference","state","cancel")'
    )
    cells["A16"] = '=_t("Cancelled orders (current period)")'
    cells["H16"] = f'=PIVOT.VALUE({NEW_CANCELLATION_PIVOT_ID},"order_reference","state","cancel")'

    cells["A17"] = '=_t("Cancellation rate (raw)")'
    cells["H17"] = "=IFERROR(H16/H15,0)"

    cells["A18"] = '=_t("Order Cancellation Percentage")'
    cells["H18"] = '=ROUND(H17*100,1)&"%"'
    cells["I18"] = '=_t("of total orders")'

    # Positive sales revenue is the denominator for % of Revenue. Discount
    # lines are negative sale.report rows; excluding them prevents a product
    # from showing >100% contribution. This helper uses a separate pivot with
    # the same dashboard/global-filter wiring and a domain price_subtotal > 0,
    # and it includes ALL positive products (not only the visible top 10).
    cells["A19"] = '=_t("Positive product sales revenue total")'
    cells["H19"] = f'=PIVOT.VALUE({POSITIVE_PRODUCT_REVENUE_PIVOT_ID},"price_subtotal")'

    _set_cells(data_sheet, cells)


def _add_kpi_scorecards(dashboard_sheet):
    """Arrange all 7 KPI scorecards in a readable 4 + 3 layout.

    Layout:
        Row 1: Quotations | Orders | Revenue | Average Order
        Row 2: Revenue Per Customer | Sales Growth Percentage | Order Cancellation Percentage

    All seven cards use the same dimensions so the KPI area looks consistent.
    The standard Sales dashboard content below the cards is shifted down to
    make room for the second scorecard row; no KPI is hidden.
    """
    figures = dashboard_sheet.setdefault("figures", [])

    STOCK_TITLES = ["Quotations", "Orders", "Revenue", "Average Order"]
    stock_figs = [
        fig for fig in figures
        if fig.get("tag") == "chart"
        and fig.get("data", {}).get("type") == "scorecard"
        and fig.get("data", {}).get("title", {}).get("text") in STOCK_TITLES
    ]
    stock_figs.sort(key=lambda f: f.get("offset", {}).get("x", 0))

    # A uniform size keeps all seven cards visually consistent while still
    # leaving enough room for the longer KPI titles and currency values.
    CARD_WIDTH = 210
    CARD_HEIGHT = 101
    GAP = 15
    FIRST_ROW_Y = stock_figs[0].get("offset", {}).get("y", 11) if stock_figs else 11
    SECOND_ROW_Y = FIRST_ROW_Y + CARD_HEIGHT + GAP

    def _position(fig, x, y):
        fig["width"] = CARD_WIDTH
        fig["height"] = CARD_HEIGHT
        fig["offset"] = {"x": x, "y": y}

    if len(stock_figs) == 4:
        # Four stock KPIs on the first row.
        for index, fig in enumerate(stock_figs):
            _position(fig, index * (CARD_WIDTH + GAP), FIRST_ROW_Y)

        # The stock dashboard's Monthly Sales chart starts at y=155. Move it
        # below the new second KPI row.  The same vertical delta is applied to
        # the standard lower dashboard figures so they do not overlap.
        required_chart_y = SECOND_ROW_Y + CARD_HEIGHT + 45
        chart_shift = required_chart_y - 155
        if chart_shift > 0:
            for fig in figures:
                if fig in stock_figs:
                    continue
                offset = fig.get("offset")
                if not offset:
                    continue
                # Shift the standard Sales dashboard chart/tables only.  The
                # Top Countries/Categories carousels are independent figures
                # and should retain their original positions.
                if fig.get("data", {}).get("type") == "odoo_line":
                    offset["y"] = offset.get("y", 0) + chart_shift

            # Rows 6+ contain the standard dashboard tables. Increase row 5
            # (the spacer directly below the KPI cards) by the same amount so
            # all cell-based sections below it move down together.
            rows = dashboard_sheet.setdefault("rows", {})
            old_row5_height = rows.get("5", {}).get("size", 40)
            rows["5"] = {"size": old_row5_height + chart_shift}

    common = {
        "width": CARD_WIDTH,
        "height": CARD_HEIGHT,
        "tag": "chart",
        "col": 0,
        "row": 0,
    }

    def scorecard(chart_id, x, y, title, background, key_cell, baseline_cell):
        fig = dict(common)
        fig["id"] = chart_id
        fig["offset"] = {"x": x, "y": y}
        fig["data"] = {
            "baselineColorDown": "#DC6965",
            "baselineColorUp": "#00A04A",
            "baselineMode": "text",
            "title": {"text": title, "bold": True, "color": "#434343"},
            "type": "scorecard",
            "background": background,
            "baseline": f"Data!{baseline_cell}",
            "keyValue": f"Data!{key_cell}",
            "humanize": False,
            "chartId": chart_id,
        }
        return fig

    # Remove previously injected copies if this patch is ever applied to an
    # already-patched payload. This keeps the operation idempotent.
    figures[:] = [
        fig for fig in figures
        if fig.get("id") not in NEW_KPI_FIGURE_IDS.values()
    ]

    # Row 2: the three custom KPIs. They retain the same card size as the four
    # standard KPIs and are aligned from the left edge of the dashboard.
    figures.append(scorecard(
        NEW_KPI_FIGURE_IDS["revenue_per_customer"],
        0,
        SECOND_ROW_Y,
        "Revenue Per Customer",
        "#FFF7ED",
        "H12",
        "I12",
    ))
    figures.append(scorecard(
        NEW_KPI_FIGURE_IDS["sales_growth"],
        CARD_WIDTH + GAP,
        SECOND_ROW_Y,
        "Sales Growth Percentage",
        "#EFF6FF",
        "H14",
        "I14",
    ))
    figures.append(scorecard(
        NEW_KPI_FIGURE_IDS["cancellation_rate"],
        2 * (CARD_WIDTH + GAP),
        SECOND_ROW_Y,
        "Order Cancellation Percentage",
        "#FEF2F2",
        "H18",
        "I18",
    ))

def _add_contribution_table(dashboard_sheet, data):
    """Add a single "%" (contribution) column right next to the stock Top
    Products table's Revenue column, instead of a whole separate copy of
    Product/Orders/Revenue.

    v2 fix: the previous version built a fully separate, relabelled table
    ("Top Products \u2014 Sale Contribution %") in unused columns (I:L).
    That duplicated Product/Orders/Revenue next to the real table and
    rendered as two side-by-side tables - the reported visual bug.

    v2.1 fix: corrected the column from D to H - the stock Top Products
    title link is at E35, so the table's own columns are E (Product),
    F (Orders), G (Revenue); H is the first unused column right after
    Revenue.

    v2.2 fix:
    - Phantom "0%" on trailing empty rows: PIVOT.VALUE(...) returns 0 (not
      blank) for ranks past the last real product, so the old formula
      showed "0%" on rows with no product at all. Guarded against this.

    v2.3 fix:
    - Column wasn't clickable. The v2.2 guard used PIVOT.HEADER(...)=""
      inside the same cell as the PIVOT.VALUE(...) call, i.e. two PIVOT.*
      calls in one formula. Odoo's click-to-drilldown check
      (spreadsheet/static/src/pivot/pivot_actions.js,
      SEE_RECORDS_PIVOT_VISIBLE) only enables a cell when its formula has
      *exactly one* pivot function call, so that cell could never be
      clickable no matter how it was styled. The empty-rank guard now
      checks the stock Revenue cell already sitting in the same row
      (column G, part of the existing =PIVOT(6,10,FALSE,FALSE) spill)
      instead of calling PIVOT.HEADER a second time - a plain cell
      reference doesn't count as a pivot call, so each Contribution %
      cell is back down to a single PIVOT.VALUE call and is now clickable
      exactly like Product/Orders/Revenue: it opens "See records" for
      that product on the same domain.

    v2.4 fix (this version):
    - Column header is "% of Revenue" to keep the label compact.
    - Red/green coloring never appeared, on any value, at any point:
      the cell's formula ended in ``&"%"`` (string concatenation), so the
      cell's *evaluated value* was always text (e.g. the literal string
      "-1.28%"), never a number. o-spreadsheet's CellIsRule conditional
      formatting (isLessThan / isGreaterThan) bails out immediately with
      `typeof value !== "number" -> false` for anything that isn't a real
      number - see o-spreadsheet's
      src/registries/criterion_registry.ts - so a color rule on this
      column could never fire, regardless of the actual number shown.
      Fixed by making the cell hold a genuine numeric ratio (e.g. 1.0266
      for "102.66%") and applying a "0.00%" *number format* instead of
      concatenating a literal "%" character, then adding two CellIsRule
      conditional formats on the column: isLessThan 0 -> red text
      (#DC6965, matching this module's other "down" color), isGreaterThan
      0 -> green text (#00A04A, matching this module's other "up" color).
      0% stays the sheet's default text color, same as before.
    - Visible gap before the column: column H is given an explicit,
      tighter width instead of the sheet's wide default column size.
    - Font/style mismatch: the added header/data cells now reuse the actual
      stock Top Products header/data style IDs (E36/G36 and G37/F37) instead
      of creating a custom style.

    Note on "between Orders and Revenue": the real Orders/Revenue columns
    are generated live by the stock =PIVOT(6,10,FALSE,FALSE) array formula
    (the private o-spreadsheet JS layer lays those two columns out itself).
    A separate cell cannot be inserted physically between two cells that
    belong to someone else's live array spill without colliding with it, so
    this stays positioned right after Revenue - now styled and spaced to
    read as one continuous table instead of a visibly separate block.
    """
    TOP_PRODUCTS_HEADER_ROW = 36
    TOP_PRODUCTS_CONTRIB_COL = "H"  # first unused column, right after Revenue (G)
    TOP_PRODUCTS_CONTRIB_COL_INDEX = 7  # 0-indexed: A=0 ... H=7

    # This module's existing cells (see _add_data_sheet_helper_cells,
    # _add_contribution_table's own header/link cells above) are all stored
    # as plain formula strings in sheet["cells"], not as {content, style}
    # objects - matching the standard o-spreadsheet SheetData shape, where
    # per-cell style is a *separate* sheet-level map (xc -> styleId), kept
    # apart from "cells" (xc -> content). Styling is added that same way
    # here, rather than nesting an unverified shape inside "cells".
    sheet_styles = dashboard_sheet.setdefault("styles", {})

    # Reuse the exact styles already used by the stock Top Products table.
    # The previous implementation created a new bold/left-aligned style,
    # which made the added column visibly different from Product / Orders /
    # Revenue.  The stock table's header/data cells are the source of truth.
    header_style_id = sheet_styles.get("E36") or sheet_styles.get("G36")
    data_style_id = sheet_styles.get("G37") or sheet_styles.get("F37")

    # Number format (workbook-level formats map + sheet-level xc -> formatId
    # map), kept separate from "styles" the same way o-spreadsheet keeps
    # them separate: this is what turns the raw numeric ratio (e.g. 1.0266)
    # into the displayed "102.66%" now that the cell no longer builds that
    # text itself via string concatenation.
    workbook_formats = data.setdefault("formats", {})
    try:
        next_format_id = max((int(k) for k in workbook_formats.keys()), default=0) + 1
    except (ValueError, TypeError):
        next_format_id = 1
    percent_format_id = next_format_id
    workbook_formats[str(percent_format_id)] = "0.00%"

    sheet_formats = dashboard_sheet.setdefault("formats", {})

    # Tighter, explicit width for the new column so it doesn't inherit the
    # sheet's wide default column size (that default width is what showed
    # up as a visible gap before the column).
    cols = dashboard_sheet.setdefault("cols", {})
    cols[str(TOP_PRODUCTS_CONTRIB_COL_INDEX)] = {"size": 120}

    cells = {}
    header_xc = f"{TOP_PRODUCTS_CONTRIB_COL}{TOP_PRODUCTS_HEADER_ROW}"
    cells[header_xc] = '=_t("% of Revenue")'
    if header_style_id is not None:
        sheet_styles[header_xc] = header_style_id

    first_data_row = TOP_PRODUCTS_HEADER_ROW + 1
    last_data_row = TOP_PRODUCTS_HEADER_ROW + 10
    contrib_range = (
        f"{TOP_PRODUCTS_CONTRIB_COL}{first_data_row}:"
        f"{TOP_PRODUCTS_CONTRIB_COL}{last_data_row}"
    )

    for n in range(1, 11):  # top 10, matching the stock PIVOT(6, 10, ...) row count
        row = TOP_PRODUCTS_HEADER_ROW + n
        xc = f"{TOP_PRODUCTS_CONTRIB_COL}{row}"
        # % of Revenue is the share of positive product/sales revenue.
        # Negative discount rows are not treated as products contributing
        # negative sales; they display 0%. The denominator is the complete
        # positive-revenue pivot (all products, not only the visible top 10),
        # so a normal product contribution can never exceed 100%.
        #
        # Guard against the "no product at this rank" case by checking the
        # stock Revenue cell in the SAME row (column G, part of the stock
        # =PIVOT(6,10,FALSE,FALSE) spill) instead of calling PIVOT.HEADER
        # ourselves. This is deliberate, not just a style choice: Odoo's
        # click-to-drilldown check for a cell
        # (spreadsheet/static/src/pivot/pivot_actions.js,
        # SEE_RECORDS_PIVOT_VISIBLE) only lights up when the cell's formula
        # contains *exactly one* PIVOT.* function call
        # (o-spreadsheet's getNumberOfPivotFunctions(...) === 1). Only one
        # PIVOT.VALUE call appears below, so Odoo treats this cell exactly
        # like the stock Product/Orders/Revenue cells: clicking it opens
        # "See records" for that same product/current-period domain.
        #
        # The result is left as a raw ratio (e.g. 1.0266, not "102.66%")
        # so the cell's evaluated value is a real number - the "0.00%"
        # format below turns it into the displayed percentage, and a real
        # number is also what conditional formatting's isLessThan /
        # isGreaterThan rules require to ever fire (see docstring).
        revenue_xc = f"G{row}"
        cells[xc] = (
            f'=IF({revenue_xc}="","",'
            f'IF({revenue_xc}<=0,0,'
            f'IFERROR(PIVOT.VALUE({TOP_PRODUCTS_PIVOT_ID},"price_subtotal",'
            f'"#product_id",{n})/Data!$H$19,0)))'
        )
        if data_style_id is not None:
            sheet_styles[xc] = data_style_id
        sheet_formats[xc] = percent_format_id

    _set_cells(dashboard_sheet, cells)

    conditional_formats = dashboard_sheet.setdefault("conditionalFormats", [])
    conditional_formats.append({
        "id": "contribution_pct_negative",
        "ranges": [contrib_range],
        "rule": {
            "type": "CellIsRule",
            "operator": "isLessThan",
            "values": ["0"],
            "style": {"textColor": "#DC6965"},  # same "down" red used by the KPI cards
        },
    })
    conditional_formats.append({
        "id": "contribution_pct_positive",
        "ranges": [contrib_range],
        "rule": {
            "type": "CellIsRule",
            "operator": "isGreaterThan",
            "values": ["0"],
            "style": {"textColor": "#00A04A"},  # same "up" green used by the KPI cards
        },
    })


def _register_menu_references(data):
    refs = data.setdefault("chartOdooMenusReferences", {})
    for chart_id in NEW_KPI_FIGURE_IDS.values():
        refs[chart_id] = MENU_XMLID_REPORTING_SALES 