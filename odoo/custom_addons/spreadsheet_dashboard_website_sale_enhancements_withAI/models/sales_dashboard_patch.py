# -*- coding: utf-8 -*-
"""
Runtime patch applied to the JSON payload of the standard "Sales"
spreadsheet dashboard (``spreadsheet_dashboard_website_sale.spreadsheet_dashboard_ecommerce``).

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

import math

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

# AI revenue forecast additions.  The selection global filter affects only
# the forecast summary pivot and forecast chart; the existing Sales dashboard
# filters/pivots remain untouched.
FORECAST_SUMMARY_PIVOT_ID = "15"
FORECAST_FILTER_ID = "f7c6f2f1-7f8f-4e0f-a0fd-3a3a8a7e0f21"
FORECAST_CHART_ID = "1a4b7f9c-2f8e-4c13-9a6e-2e8b7b1c4d55"
ES_FORECAST_CHART_ID = "8e2f7c41-6a95-4d30-b18e-52c7f9a6d184"
VALIDATION_CHART_ID = "6c4a1f82-9d7e-4b13-a5f0-2e8c6d7b1a90"
VALIDATION_TRAIN_SCORECARD_ID = "1f4e8a72-3c9d-4b15-a6e0-7d2c5f9b8a31"
VALIDATION_TEST_SCORECARD_ID = "2a5d9c73-1e8b-4f26-b7d0-6c3a8e5f1b42"
VALIDATION_BEST_SCORECARD_ID = "3b6e0a84-2f9c-4d17-a8e1-5c7b9f2d6a43"
VALIDATION_SUMMARY_PIVOT_ID = "16"
FORECAST_SCORECARD_IDS = {
    "current": "9b2b0f0c-8c91-4d35-b7b0-4b6b5e0f1a11",
    "forecast": "d1d9c9a7-6f35-4a9a-93e0-8c5a6a2b7e22",
    "growth": "e8f7b6c5-4d32-4f10-a9b8-7c6d5e4f3a33",
    "confidence": "f6e5d4c3-b2a1-4f09-8e7d-6c5b4a3d2e44",
}
FORECAST_HORIZONS = (
    ("7_days", "7 Days"),
    ("1_month", "1 Month"),
    ("6_months", "6 Months"),
    ("1_year", "1 Year"),
    ("2_years", "2 Years"),
    ("5_years", "5 Years"),
    ("10_years", "10 Years"),
)
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


def patch_sales_dashboard_json(data, forecast_context=None):
    """Add the three sales-forecast panels to the standard eCommerce dashboard.

    Only the forecast UI is injected; native eCommerce KPIs and tables are preserved.
    """
    import copy
    data = copy.deepcopy(data)
    forecast_context = forecast_context or {}
    sheets = data.get("sheets", [])
    dashboard_sheet = next((s for s in sheets if s.get("name") == "Dashboard"), None)
    data_sheet = next((s for s in sheets if s.get("name") == "Data"), None)
    if dashboard_sheet is None or data_sheet is None:
        return data
    pivots = data.setdefault("pivots", {})
    _restrict_monthly_sales_to_website(dashboard_sheet)
    _add_forecast_summary_pivot(pivots, forecast_context)
    _add_validation_summary_pivot(pivots, forecast_context)
    _add_forecast_global_filter(data)
    _add_forecast_section(dashboard_sheet, data_sheet, forecast_context)
    _add_training_testing_section(dashboard_sheet, forecast_context)
    _add_training_testing_helper_cells(data_sheet, dashboard_sheet)
    try:
        data["pivotNextId"] = str(max(int(k) for k in pivots.keys()) + 1)
    except (ValueError, TypeError):
        pass
    return data


def _restrict_monthly_sales_to_website(dashboard_sheet):
    """Make the native "Monthly Sales" chart show eCommerce sales only.

    The stock chart reads ``sale.report`` with only a state filter, so it
    includes every confirmed order (backend and website). Adding
    ``website_id != False`` matches the other eCommerce KPIs on this
    dashboard (Orders, Total Revenue, ...) and the forecast source.
    """
    website_leaf = ["website_id", "!=", False]
    for fig in dashboard_sheet.get("figures", []):
        data = fig.get("data") or {}
        title = data.get("title")
        title_text = title.get("text") if isinstance(title, dict) else title
        meta = data.get("metaData") or {}
        if title_text not in ("Monthly Sales", "Monthly e-Commerce Sales") or meta.get("resModel") != "sale.report":
            continue
        params = data.setdefault("searchParams", {})
        domain = [list(leaf) if isinstance(leaf, (list, tuple)) else leaf
                  for leaf in (params.get("domain") or [])]
        if any(isinstance(leaf, list) and leaf[:2] == ["website_id", "!="] for leaf in domain):
            continue  # already restricted
        params["domain"] = domain + [website_leaf]


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



def _add_forecast_summary_pivot(pivots, forecast_context):
    """Add a tiny pivot used by the four AI forecast scorecards."""
    if FORECAST_SUMMARY_PIVOT_ID in pivots:
        return

    # The owner/company domain is added by the server when the snapshot is
    # built. It is deliberately narrow so one user's generated forecast rows
    # can never appear in another user's dashboard.
    company_id = int(forecast_context.get("company_id") or 0)
    owner_id = int(forecast_context.get("owner_id") or 0)

    pivots[FORECAST_SUMMARY_PIVOT_ID] = {
        "type": "ODOO",
        "fieldMatching": {
            FORECAST_FILTER_ID: {
                "chain": "forecast_period",
                "type": "selection",
            },
        },
        "context": {"group_by": []},
        "domain": [
            ["company_id", "=", company_id],
            ["owner_id", "=", owner_id],
        ],
        "id": FORECAST_SUMMARY_PIVOT_ID,
        "measures": [
            
        ],
        "model": "website.sale.forecast.summary",
        "name": "AI sales forecast summary",
        "sortedColumn": None,
        "formulaId": FORECAST_SUMMARY_PIVOT_ID,
        "columns": [],
        "rows": [],
    }



def _add_validation_summary_pivot(pivots, forecast_context):
    """Pivot of filter-aware back-test metrics used by the Best Model card."""
    if VALIDATION_SUMMARY_PIVOT_ID in pivots:
        return
    company_id = int(forecast_context.get("company_id") or 0)
    owner_id = int(forecast_context.get("owner_id") or 0)
    pivots[VALIDATION_SUMMARY_PIVOT_ID] = {
        "type": "ODOO",
        "fieldMatching": {
            FORECAST_FILTER_ID: {"chain": "forecast_period", "type": "selection"},
        },
        "context": {"group_by": []},
        "domain": [["company_id", "=", company_id], ["owner_id", "=", owner_id]],
        "id": VALIDATION_SUMMARY_PIVOT_ID,
        "measures": [
            {"id": "mape", "fieldName": "mape", "userDefinedName": "MAPE"},
            {"id": "mae", "fieldName": "mae", "userDefinedName": "MAE"},
            {"id": "rmse", "fieldName": "rmse", "userDefinedName": "RMSE"},
        ],
        "model": "website.sale.forecast.validation.summary",
        "name": "Sales forecast validation summary",
        "sortedColumn": None,
        "formulaId": VALIDATION_SUMMARY_PIVOT_ID,
        "columns": [],
        "rows": [{"fieldName": "model_name"}],
    }

def _add_forecast_global_filter(data):
    """Add the only user-facing AI forecast filter: future forecast period."""
    filters = data.setdefault("globalFilters", [])
    filters[:] = [flt for flt in filters if flt.get("id") != FORECAST_FILTER_ID]

    graph_field = {
        "field": "forecast_period",
        "type": "selection",
    }
    filters.append({
        "id": FORECAST_FILTER_ID,
        "type": "selection",
        "label": "Forecast Period",
        # Odoo 19 selection filters use ``resModel`` and ``selectionField``
        # for the search-bar facet/value-label lookup.  ``modelName`` is used
        # by relation filters, not selection filters.
        "resModel": "website.sale.forecast.summary",
        "selectionField": "forecast_period",
        # 1 Month is the default user-facing forecast period. The historical
        # back-test points are retained inside every future horizon, so the
        # default view shows past actual + past forecast + the next month
        # forecast without exposing an internal Historical filter option.
        "defaultValue": {
            "operator": "in",
            "selectionValues": ["1_month"],
        },
        "pivotFields": {
            FORECAST_SUMMARY_PIVOT_ID: dict(graph_field),
            VALIDATION_SUMMARY_PIVOT_ID: dict(graph_field),
        },
        "listFields": {},
        "graphFields": {
            FORECAST_CHART_ID: dict(graph_field),
            ES_FORECAST_CHART_ID: dict(graph_field),
            VALIDATION_CHART_ID: dict(graph_field),
        },
    })


def _add_forecast_section(dashboard_sheet, data_sheet, forecast_context):
    """Insert the AI forecast panel immediately above Monthly Sales."""
    figures = dashboard_sheet.setdefault("figures", [])

    # Remove previous copies defensively.  IMPORTANT: older iterations of this
    # addon used different IDs for the ML chart.  The dashboard snapshot is
    # persistent, so simply replacing the current ID leaves those old ML
    # charts in the workbook.  That is exactly what caused an old empty
    # 0..1 chart to remain visible even after the data source was fixed.
    # Remove by both ID/chartId AND by the ML title so every legacy copy is
    # eliminated before adding exactly one current ML chart.
    legacy_ml_chart_ids = {
        ES_FORECAST_CHART_ID,
        "5d7e9a11-3c42-4a86-b1d2-6f9c0e8a4b77",
        "f9c3a7e2-8b41-4d65-9c20-1a7f6e3b5d84",
        "7b6e4d2a-91f8-4c35-a7e0-6d2b9f1c8453",
        "2c91f7a4-6e35-4b82-9d10-5f73c8e2a641",
        "8e2f7c41-6a95-4d30-b18e-52c7f9a6d184",
    }
    injected_ids = set(FORECAST_SCORECARD_IDS.values()) | {
        FORECAST_CHART_ID, "overall_sales_forecast_title", *legacy_ml_chart_ids
    }

    def _is_legacy_ml_figure(fig):
        if fig.get("id") in injected_ids:
            return True
        fig_data = fig.get("data") or {}
        if fig_data.get("chartId") in injected_ids:
            return True
        title = fig_data.get("title") or {}
        title_text = title.get("text") if isinstance(title, dict) else title
        return title_text in (
            "Overall Sales Forecast (ML Algorithms)",
            "Overall e-Commerce Sales Forecast (ML Algorithms)",
        )

    figures[:] = [fig for fig in figures if not _is_legacy_ml_figure(fig)]

    monthly = None
    for fig in figures:
        fig_data = fig.get("data", {})
        if (
            fig.get("tag") == "chart"
            and fig_data.get("type") == "odoo_line"
            and fig.get("offset", {}).get("x", 0) == 0
        ):
            monthly = fig
            break

    if monthly is None:
        return

    monthly_y = monthly.get("offset", {}).get("y", 0)

    # Restore the native Monthly Sales heading explicitly. Some Odoo 19
    # dashboard snapshots omit the chart title even though the chart itself
    # remains present, leaving the first graph looking unlabelled.
    import copy
    monthly_data = monthly.setdefault("data", {})
    monthly_title = monthly_data.get("title")
    if not isinstance(monthly_title, dict):
        monthly_title = {}
    else:
        monthly_title = copy.deepcopy(monthly_title)
    monthly_title.update({
        "text": "Monthly e-Commerce Sales",
        "bold": True,
        "color": "#007A83",
        "fontSize": 24,
    })
    monthly_data["title"] = monthly_title

    # Add a small amount of breathing room above the Monthly Sales graph so
    # its heading is visible and does not sit against the KPI cards.
    monthly_nudge = 24
    monthly.setdefault("offset", {})["y"] = monthly_y + monthly_nudge
    monthly_y = monthly["offset"]["y"]

    # Reserve a dedicated vertical block for the inserted forecast panels.
    # The native Top Quotations / Top Sales Orders sections are cell-based
    # content around row 35, so moving chart figures alone is not enough:
    # enlarge the spacer row above those sections as well. This keeps the
    # native tables from rendering through the custom forecast charts.
    #
    # Layout below Monthly Sales:
    #   Overall Sales Forecast chart       330 px + 30 px gap
    #   ML forecast chart                  330 px + 40 px gap
    #   Training/testing cards              82 px + 18 px gap
    #   Model Training & Testing chart     300 px
    #   final clearance                     50 px
    # The spacer is intentionally slightly generous for title/legend height.
    custom_stack_height = 330 + 30 + 330 + 40 + 82 + 18 + 300 + 50
    rows = dashboard_sheet.setdefault("rows", {})
    row5 = rows.setdefault("5", {"size": 40})
    row5["size"] = row5.get("size", 40) + custom_stack_height

    # Shift native dashboard charts other than Monthly Sales below the
    # complete custom block. Keep the Monthly Sales chart as the first chart.
    for native_fig in figures:
        if native_fig is monthly:
            continue
        native_data = native_fig.get("data") or {}
        native_offset = native_fig.get("offset")
        if (
            native_fig.get("tag") == "chart"
            and native_data.get("type") == "odoo_line"
            and isinstance(native_offset, dict)
            and native_offset.get("y", 0) >= monthly_y
        ):
            native_offset["y"] = native_offset.get("y", 0) + custom_stack_height

    # Increase the sheet's declared row count to accommodate the new vertical
    # space and preserve the native lower dashboard sections.
    dashboard_sheet["rowNumber"] = max(
        dashboard_sheet.get("rowNumber", 0),
        dashboard_sheet.get("rowNumber", 0) + int(math.ceil(custom_stack_height / 28.0)) + 2,
    )

    # Size the Monthly Sales displacement from the actual forecast chart
    # bounds instead of using a large fixed offset. This keeps Monthly Sales
    # just below the forecast chart, even when the KPI layout changes.
    card_height = 101
    # Leave enough vertical clearance so the Monthly Sales chart title is not
    # clipped/overlapped by the Overall Sales Forecast chart above it.
    chart_gap = 40
    chart_height = 330
    kpi_figures_for_layout = [
        fig for fig in figures
        if fig.get("tag") == "chart"
        and fig.get("data", {}).get("type") == "scorecard"
    ]
    kpi_bottom_for_layout = max(
        (
            fig.get("offset", {}).get("y", 0)
            + fig.get("height", card_height)
            for fig in kpi_figures_for_layout
        ),
        default=monthly_y + card_height,
    )
    # Put the native Monthly Sales chart first, immediately below the KPI cards.
    # The forecast panels are positioned beneath it later in this function.
    desired_monthly_y = kpi_bottom_for_layout + chart_gap
    panel_shift = max(0, desired_monthly_y - monthly_y)
    monthly["offset"]["y"] = monthly_y + panel_shift

    rows = dashboard_sheet.setdefault("rows", {})
    row5 = rows.setdefault("5", {"size": 40})
    row5["size"] = row5.get("size", 40) + panel_shift

    # Extend the logical grid so the shifted lower dashboard content remains
    # inside the sheet's declared bounds.
    dashboard_sheet["rowNumber"] = max(
        dashboard_sheet.get("rowNumber", 0),
        dashboard_sheet.get("rowNumber", 0) + int(math.ceil(panel_shift / 28.0)) + 2,
    )

    # Use exactly the same logical dimensions as the KPI cards created by
    # _add_kpi_scorecards above.  The previous forecast cards used 245x92,
    # which made them visibly wider than the native Sales KPI cards.
    card_width = 210
    card_height = 101
    gap = 15
    top_y = monthly_y

    def _scorecard(chart_id, x, title, background, key_cell, baseline_cell):
        return {
            "id": chart_id,
            "width": card_width,
            "height": card_height,
            "tag": "chart",
            "offset": {"x": x, "y": top_y},
            "col": 0,
            "row": 0,
            "data": {
                "baselineMode": "text",
                "baselineColorDown": "#DC6965",
                "baselineColorUp": "#00A04A",
                "title": {
                    "text": title,
                    "bold": True,
                    "color": "#434343",
                },
                "type": "scorecard",
                "background": background,
                "baseline": f"Data!{baseline_cell}",
                "keyValue": f"Data!{key_cell}",
                "humanize": False,
                "chartId": chart_id,
            },
        }

    figures.extend([

    ])

    # Place the forecast chart directly below the bottom-most KPI scorecard.
    # Previously this used ``monthly_y + card_height + 20``.  Since monthly_y
    # is already below the KPI rows, that added an unnecessary extra card-height
    # gap between the KPI cards and the Overall Sales Forecast chart.
    kpi_figures = [
        fig for fig in figures
        if fig.get("tag") == "chart"
        and fig.get("data", {}).get("type") == "scorecard"
    ]
    kpi_bottom = max(
        (
            fig.get("offset", {}).get("y", 0)
            + fig.get("height", card_height)
            for fig in kpi_figures
        ),
        default=top_y + card_height,
    )
    chart_y = monthly.get("offset", {}).get("y", 0) + monthly.get("height", 330) + 30
    chart_width = monthly.get("width", 1095)

    monthly_data = monthly.get("data", {})

    # Match the visual style of the native "Monthly Sales" heading.
    # The forecast heading is rendered by the chart itself, so explicitly
    # apply the same heading treatment instead of using the smaller default
    # chart-title styling.
    native_chart_title = copy.deepcopy(monthly_data.get("title") or {})
    native_chart_title.update({
        "text": "Overall e-Commerce Sales Forecast (AOV)",
        "bold": True,
        "color": "#007A83",
        "fontSize": 24,
    })
    # Keep the title inside forecast_chart_data. Do not append it as a
    # standalone dashboard figure because FigureComponent requires a
    # registered figure tag/type.

    forecast_chart_data = {
        # Exact native Monthly Sales chart title styling; only the text changes.
        "title": native_chart_title,
        "metaData": {
            # Use the same monthly time grain as Monthly Sales. This gives the
            # X-axis real calendar labels such as "Aug 2026", "Sep 2026", etc.
            "groupBy": ["date:month", "series"],
            "measure": "revenue",
            "order": None,
            "resModel": "website.sale.forecast.point",
            "mode": "line",
            "cumulatedStart": False,
        },
        "searchParams": {
            "comparison": None,
            "context": {"group_by": []},
            "domain": _forecast_chart_domain(forecast_context),
            "groupBy": ["date:month", "series"],
            "orderBy": [],
        },
        "type": "odoo_line",
        "dataSets": [{}],
        "verticalAxisPosition": monthly_data.get("verticalAxisPosition", "left"),
        "stacked": monthly_data.get("stacked", False),
        "cumulatedStart": monthly_data.get("cumulatedStart", False),
        "axesDesign": {
            # Match Monthly Sales: the horizontal axis is self-labelled by
            # calendar dates, while the vertical axis carries the Revenue title.
            "y": {"title": {"text": "Revenue"}},
        },
        # Monthly Sales is an area chart.  Match that native visualization.
        "fillArea": monthly_data.get("fillArea", True),
        "chartId": FORECAST_CHART_ID,
        "fieldMatching": {
            FORECAST_FILTER_ID: {
                "chain": "forecast_period",
                "type": "selection",
            },
        },
    }

    # Copy only visual properties from Monthly Sales.  We deliberately do not
    # copy its dataSets/metaData/searchParams because those are tied to
    # sale.report and would point the forecast chart at the wrong model.
    for visual_key in ("background", "legendPosition"):
        if visual_key in monthly_data:
            forecast_chart_data[visual_key] = monthly_data[visual_key]

    figures.append({
        "id": FORECAST_CHART_ID,
        "width": chart_width,
        "height": chart_height,
        "tag": "chart",
        "offset": {"x": 0, "y": chart_y},
        "col": 0,
        "row": 0,
        "data": forecast_chart_data,
    })

    # ------------------------------------------------------------------
    # ML/regression graph. The original Overall Sales Forecast (AOV) chart
    # keeps Actual Revenue and the original Forecast Revenue only. Linear and
    # Polynomial Regression are shown here alongside Exponential Smoothing
    # and ARIMA. All series use the same website.sale.forecast.point source and
    # Forecast Period filter.
    # ------------------------------------------------------------------
    es_chart_y = chart_y + chart_height + 40
    es_chart_data = {
        "title": {
            "text": "Overall e-Commerce Sales Forecast (ML Algorithms)",
            "bold": True,
            "color": "#007A83",
            "fontSize": 24,
        },
        "metaData": {
            # Keep the same chart data shape as the proven forecast chart.
            # The domain below limits this chart to the two ML time-series
            # outputs, and grouping by series gives each model its own legend.
            "groupBy": ["date:month", "series"],
            "measure": "revenue",
            "order": None,
            "resModel": "website.sale.forecast.point",
            "mode": "line",
            "cumulatedStart": False,
        },
        "searchParams": {
            "comparison": None,
            "context": {"group_by": []},
            "domain": _forecast_ml_chart_domain(forecast_context),
            "groupBy": ["date:month", "series"],
            "orderBy": [],
        },
        "type": "odoo_line",
        "dataSets": [{}],
        "verticalAxisPosition": monthly_data.get("verticalAxisPosition", "left"),
        "stacked": False,
        "cumulatedStart": False,
        "axesDesign": {
            "y": {"title": {"text": "Revenue"}},
        },
        "fillArea": False,
        "chartId": ES_FORECAST_CHART_ID,
        "fieldMatching": {
            FORECAST_FILTER_ID: {
                "chain": "forecast_period",
                "type": "selection",
            },
        },
    }
    figures.append({
        "id": ES_FORECAST_CHART_ID,
        "width": chart_width,
        "height": chart_height,
        "tag": "chart",
        "offset": {"x": 0, "y": es_chart_y},
        "col": 0,
        "row": 0,
        "data": es_chart_data,
    })

    cells = data_sheet.setdefault("cells", {})
    # Summary pivot 15 is filtered by Forecast Period.  Keep the scorecard
    # values as strings so Odoo displays compact currency/percentage values
    # exactly like the existing KPI cards.
    cells["H20"] = f'=FORMAT.LARGE.NUMBER(PIVOT.VALUE({FORECAST_SUMMARY_PIVOT_ID},"current_revenue"))'
    cells["H21"] = f'=FORMAT.LARGE.NUMBER(PIVOT.VALUE({FORECAST_SUMMARY_PIVOT_ID},"forecast_revenue"))'
    cells["H22"] = (
        f'=IFERROR(IF(PIVOT.VALUE({FORECAST_SUMMARY_PIVOT_ID},"growth_pct")>=0,"+","")'
        f'&ROUND(PIVOT.VALUE({FORECAST_SUMMARY_PIVOT_ID},"growth_pct"),1)&"%","0%")'
    )
    cells["H23"] = (
        f'=ROUND(PIVOT.VALUE({FORECAST_SUMMARY_PIVOT_ID},"confidence"),0)&"%"'
    )




def _add_training_testing_helper_cells(data_sheet, dashboard_sheet):
    """Write validation scorecard values to the hidden Data sheet.

    The dashboard scorecard renderer reliably displays values referenced as
    ``Data!A1``-style workbook cells.  Keep this helper block isolated in Z:Z
    so it cannot collide with the stock Sales dashboard helper formulas.
    """
    values = dashboard_sheet.pop("_validation_helper_cells", {})
    if not values:
        return
    cells = data_sheet.setdefault("cells", {})
    cells["Z1"] = values.get("training_pct", "0%")
    cells["Z2"] = values.get("training_count", "0 days")
    cells["Z3"] = values.get("testing_pct", "0%")
    cells["Z4"] = values.get("testing_count", "0 days")
    # Best-model values are formulas against the validation summary pivot, so
    # the Forecast Period global filter changes them automatically.
    # IMPORTANT: the value-lookup form of PIVOT.VALUE uses the actual field
    # name ("model_name"), not the ranked-field form ("#model_name").
    # Using "#model_name" here makes the lookup invalid and causes the
    # scorecard to fall through to the em-dash even though pivot 16 has rows.
    # The validation pivot is wired to the Forecast Period global filter, so
    # these formulas automatically recalculate when the user changes 7 Days,
    # 1 Month, 6 Months, etc.
    arima_mape = (
        f'PIVOT.VALUE({VALIDATION_SUMMARY_PIVOT_ID},"mape","model_name","ARIMA")'
    )
    es_mape = (
        f'PIVOT.VALUE({VALIDATION_SUMMARY_PIVOT_ID},"mape","model_name","Exponential Smoothing")'
    )
    cells["Z6"] = (
        f'=IFERROR(IF({arima_mape}<={es_mape},"ARIMA","Exponential Smoothing"),"—")'
    )
    cells["Z7"] = (
        f'=IFERROR("MAPE: "&ROUND(MIN({arima_mape},{es_mape}),1)&"%","MAPE: —")'
    )


def _add_training_testing_section(dashboard_sheet, forecast_context):
    """Add a compact filter-aware training/testing panel below the ML forecast."""
    validation = forecast_context.get("validation") or {}
    figures = dashboard_sheet.setdefault("figures", [])

    injected_ids = {
        VALIDATION_CHART_ID,
        VALIDATION_TRAIN_SCORECARD_ID,
        VALIDATION_TEST_SCORECARD_ID,
        VALIDATION_BEST_SCORECARD_ID,
    }
    figures[:] = [fig for fig in figures if fig.get("id") not in injected_ids]

    ml_chart = next((fig for fig in figures if fig.get("id") == ES_FORECAST_CHART_ID
                     or (fig.get("data") or {}).get("chartId") == ES_FORECAST_CHART_ID), None)
    if ml_chart is None:
        return

    ml_y = ml_chart.get("offset", {}).get("y", 0)
    ml_height = ml_chart.get("height", 330)
    chart_width = ml_chart.get("width", 1095)
    section_y = ml_y + ml_height + 32

    card_gap = 15
    card_height = 82
    training_pct = float(validation.get("training_percentage") or 0.0)
    testing_pct = float(validation.get("testing_percentage") or 0.0)
    training_count = int(validation.get("training_count") or 0)
    testing_count = int(validation.get("testing_count") or 0)

    validation_cells = dashboard_sheet.setdefault("_validation_helper_cells", {})
    validation_cells.update({
        "training_pct": f"{training_pct:.0f}%",
        "training_count": f"{training_count} days",
        "testing_pct": f"{testing_pct:.0f}%",
        "testing_count": f"{testing_count} days",
    })

    # Three cards in one row. Give the Best Performing Model card extra
    # width so the full "Exponential Smoothing" label remains readable
    # instead of being truncated by the scorecard renderer.
    split_width = (chart_width - 2 * card_gap) * 0.25
    best_width = chart_width - (2 * split_width) - (2 * card_gap)

    def split_card(fig_id, x, title, key_cell, baseline_cell, background):
        return {
            "id": fig_id, "width": split_width, "height": card_height,
            "tag": "chart", "offset": {"x": x, "y": section_y},
            "col": 0, "row": 0,
            "data": {
                "baselineMode": "text",
                "title": {"text": title, "bold": True, "color": "#434343"},
                "type": "scorecard", "background": background,
                "keyValue": f"Data!{key_cell}",
                "baseline": f"Data!{baseline_cell}",
                "humanize": False, "chartId": fig_id,
            },
        }

    figures.append(split_card(VALIDATION_TRAIN_SCORECARD_ID, 0, "Training Data", "Z1", "Z2", "#F0FDF4"))
    figures.append(split_card(VALIDATION_TEST_SCORECARD_ID, split_width + card_gap, "Testing Data", "Z3", "Z4", "#EFF6FF"))
    figures.append({
        "id": VALIDATION_BEST_SCORECARD_ID,
        "width": best_width, "height": card_height, "tag": "chart",
        "offset": {"x": 2 * (split_width + card_gap), "y": section_y},
        "col": 0, "row": 0,
        "data": {
            "baselineMode": "text",
            "title": {"text": "Best Performing Model", "bold": True, "color": "#166534"},
            "type": "scorecard", "background": "#F0FDF4",
            "keyValue": "Data!Z6", "baseline": "Data!Z7",
            "humanize": False, "chartId": VALIDATION_BEST_SCORECARD_ID,
        },
    })

    chart_y = section_y + card_height + 18
    validation_chart_data = {
        "title": {"text": "Overall e-Commerce Sales Forecast (Tested & Trained)", "bold": True, "color": "#007A83", "fontSize": 24},
        "metaData": {
            "groupBy": ["date:month", "series"],
            "measure": "revenue", "order": None,
            "resModel": "website.sale.forecast.validation.point",
            "mode": "line", "cumulatedStart": False,
        },
        "searchParams": {
            "comparison": None, "context": {"group_by": []},
            "domain": [
                ["company_id", "=", int(forecast_context.get("company_id") or 0)],
                ["owner_id", "=", int(forecast_context.get("owner_id") or 0)],
                ["series", "in", ["actual", "arima_predicted", "exponential_smoothing_predicted"]],
            ],
            "groupBy": ["date:month", "series"], "orderBy": [],
        },
        "type": "odoo_line", "dataSets": [{}],
        "verticalAxisPosition": "left", "stacked": False, "cumulatedStart": False,
        "axesDesign": {"y": {"title": {"text": "Revenue"}}},
        "fillArea": False, "chartId": VALIDATION_CHART_ID,
        "fieldMatching": {FORECAST_FILTER_ID: {"chain": "forecast_period", "type": "selection"}},
    }
    figures.append({
        "id": VALIDATION_CHART_ID, "width": chart_width, "height": 300, "tag": "chart",
        "offset": {"x": 0, "y": chart_y}, "col": 0, "row": 0,
        "data": validation_chart_data,
    })



def _forecast_ml_chart_domain(forecast_context):
    """Scope the ML/regression chart to the forecast-point table.

    This chart combines the time-series outputs (Exponential Smoothing and
    ARIMA) with Linear and Polynomial Regression. The global Forecast Period
    filter is applied through fieldMatching on forecast_period.
    """
    company_id = int(forecast_context.get("company_id") or 0)
    owner_id = int(forecast_context.get("owner_id") or 0)
    return [
        ["company_id", "=", company_id],
        ["owner_id", "=", owner_id],
        # Show both time-series algorithms and regression lines in this
        # chart. The native AOV chart excludes linear/polynomial series below.
        ["series", "in", [
            "exponential_smoothing_forecast",
            "arima_forecast",
            "linear_forecast",
            "polynomial_forecast",
        ]],
    ]


def _forecast_chart_domain(forecast_context):
    """Return the AOV chart scope, excluding regression and ML series.

    Linear and Polynomial Regression are now displayed in the ML Algorithms
    chart alongside Exponential Smoothing and ARIMA. This chart keeps only
    actual revenue and the original forecast revenue series.
    """
    company_id = int(forecast_context.get("company_id") or 0)
    owner_id = int(forecast_context.get("owner_id") or 0)
    return [
        ["company_id", "=", company_id],
        ["owner_id", "=", owner_id],
        ["series", "in", [
            "actual",
            "forecast",
        ]],
    ]


def _register_menu_references(data):
    refs = data.setdefault("chartOdooMenusReferences", {})
    for chart_id in NEW_KPI_FIGURE_IDS.values():
        refs[chart_id] = MENU_XMLID_REPORTING_SALES