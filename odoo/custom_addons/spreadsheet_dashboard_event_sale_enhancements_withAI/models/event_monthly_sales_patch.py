# -*- coding: utf-8 -*-
"""Adds a "Monthly Event Sales" area chart (event sales only) to the Events dashboard.

Pure JSON patch (no Odoo import), applied in memory at read time.  The chart
reads ``event.sale.report`` (sold event tickets, untaxed revenue) grouped by
month and follows the same dashboard filters as the Revenue KPI.
"""
import copy

from . import event_dashboard_layout as layout

MONTHLY_SALES_CHART_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7b01"
FORECAST_FILTER_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a10"
COUNTRY_FILTER_ID = "e6db018b-19ec-42c3-b29e-11b1e3910916"
REVENUE_PIVOT_NAME = "untaxed revenue - current"
CHART_WIDTH, CHART_HEIGHT = 1000, 345
GAP_ABOVE, GAP_BELOW = 24, 30


def _field_matching(data, date_field, date_type):
    """Reuse the filter wiring of the stock untaxed-revenue pivot, except that
    the Date filter is matched on the chart's own x-axis date field.

    Odoo links the in-graph Days/Months/... selector (and its automatic
    default) to the Date filter only when the filter's matched field IS the
    chart's group-by field.  The stock pivot matches ``event_date_begin``;
    Monthly Sales is grouped by the sale date, so the two must be aligned.
    Only the Date filter is touched; the Forecast Period filter is never added.
    """
    pivot = next((p for p in (data.get("pivots") or {}).values()
                  if p.get("name") == REVENUE_PIVOT_NAME), None)
    matching = copy.deepcopy((pivot or {}).get("fieldMatching") or {})
    for flt in data.get("globalFilters", []):
        if flt.get("type") == "date":
            matching[flt["id"]] = {"chain": date_field, "type": date_type, "offset": 0}
    matching.pop(FORECAST_FILTER_ID, None)
    if any(f.get("id") == COUNTRY_FILTER_ID for f in data.get("globalFilters", [])):
        matching[COUNTRY_FILTER_ID] = {"chain": "customer_country_id", "type": "many2one"}
    return matching


def add_monthly_sales(data, date_field="event_date_begin", date_type="date"):
    """Insert Monthly Sales directly under the KPI cards (first block)."""
    dash = layout.find_sheet(data, "Dashboard")
    if dash is None:
        return data
    figures = dash.setdefault("figures", [])
    figures[:] = [f for f in figures if f.get("id") != MONTHLY_SALES_CHART_ID]

    chart_y = layout.kpi_bottom(dash) + GAP_ABOVE
    first_row = layout.first_content_row(dash)
    if first_row:
        # Space needed so the old first heading ends up GAP_BELOW px under the chart.
        need = chart_y + CHART_HEIGHT + GAP_BELOW - layout.row_top(dash, first_row)
        if need > 0:
            layout.reserve_space(dash, need)

    chart = {
        "title": {"text": "Monthly Event Sales", "bold": True, "color": "#007A83", "fontSize": 24},
        "background": "#FFFFFF",
        "legendPosition": "none",
        "metaData": {
            "groupBy": ["%s:month" % date_field],
            "measure": "sale_price_untaxed",
            "order": None,
            "resModel": "event.sale.report",
            "mode": "line",
            "cumulatedStart": False,
        },
        "searchParams": {
            "comparison": None,
            "context": {"group_by": []},
            # Event sales only: tickets sold on confirmed sale orders.
            "domain": [["sale_status", "=", "sold"]],
            "groupBy": ["%s:month" % date_field],
            "orderBy": [],
        },
        "type": "odoo_line",
        "dataSets": [{"label": "Untaxed Total"}],
        "verticalAxisPosition": "left",
        "stacked": False,
        "cumulatedStart": False,
        "fillArea": True,
        "axesDesign": {"y": {"title": {"text": "Revenue"}}},
        "chartId": MONTHLY_SALES_CHART_ID,
        "fieldMatching": _field_matching(data, date_field, date_type),
    }
    figures.append({
        "id": MONTHLY_SALES_CHART_ID, "width": CHART_WIDTH, "height": CHART_HEIGHT,
        "tag": "chart", "offset": {"x": 0, "y": chart_y}, "col": 0, "row": 0, "data": chart,
    })
    return data
