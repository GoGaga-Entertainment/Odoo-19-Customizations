# -*- coding: utf-8 -*-
"""Pure-Python (no Odoo import) JSON patch that adds the AI forecast block to
the Events dashboard.  It runs on the in-memory payload only, so uninstalling
the module restores the stock dashboard immediately."""
from . import event_dashboard_layout as layout

FORECAST_FILTER_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a10"
FORECAST_CHART_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a11"
ML_CHART_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a12"
VALIDATION_CHART_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a13"
TRAIN_CARD_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a14"
TEST_CARD_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a15"
BEST_CARD_ID = "c3a91e5b-7d24-4f68-9b0a-5e1d8c2f7a16"
INJECTED_IDS = {
    FORECAST_CHART_ID, ML_CHART_ID, VALIDATION_CHART_ID,
    TRAIN_CARD_ID, TEST_CARD_ID, BEST_CARD_ID,
}
MIN_HISTORY_MONTHS = 3
TITLE_COLOR = "#007A83"


def _next_pivot_id(pivots):
    ids = [int(k) for k in pivots if str(k).isdigit()]
    return str(max(ids or [0]) + 1)


def _summary_pivot(pivot_id, model, name, ctx, measures=None, rows=None):
    return {
        "type": "ODOO",
        "fieldMatching": {FORECAST_FILTER_ID: {"chain": "forecast_period", "type": "selection"}},
        "context": {"group_by": []},
        "domain": [["company_id", "=", ctx["company_id"]], ["owner_id", "=", ctx["owner_id"]]],
        "id": pivot_id, "measures": measures or [], "model": model, "name": name,
        "sortedColumn": None, "formulaId": pivot_id, "columns": [], "rows": rows or [],
    }


def _scope(ctx, extra=None):
    domain = [["company_id", "=", ctx["company_id"]], ["owner_id", "=", ctx["owner_id"]]]
    return domain + (extra or [])


def _line_chart(chart_id, title, model, domain, fill, group_by=None):
    group_by = group_by or ["date:month", "series"]
    return {
        "title": {"text": title, "bold": True, "color": TITLE_COLOR, "fontSize": 24},
        "metaData": {"groupBy": group_by, "measure": "revenue", "order": None,
                     "resModel": model, "mode": "line", "cumulatedStart": False},
        "searchParams": {"comparison": None, "context": {"group_by": []},
                         "domain": domain, "groupBy": group_by, "orderBy": []},
        "type": "odoo_line", "dataSets": [{}], "verticalAxisPosition": "left",
        "stacked": False, "cumulatedStart": False, "fillArea": fill,
        "axesDesign": {"y": {"title": {"text": "Revenue"}}},
        "chartId": chart_id,
        "fieldMatching": {FORECAST_FILTER_ID: {"chain": "forecast_period", "type": "selection"}},
    }


def _figure(fig_id, x, y, w, h, data):
    return {"id": fig_id, "width": w, "height": h, "tag": "chart",
            "offset": {"x": x, "y": y}, "col": 0, "row": 0, "data": data}


def add_forecast_sections(data, ctx):
    """Append the forecast block below the existing Events dashboard content.

    ``ctx`` = {"company_id", "owner_id", "validation": {...}}.  Returns data.
    """
    dash = layout.find_sheet(data, "Dashboard")
    helper = layout.find_sheet(data, "Data")
    if dash is None or helper is None:
        return data
    ctx = dict(ctx, company_id=int(ctx.get("company_id") or 0),
               owner_id=int(ctx.get("owner_id") or 0))
    validation = ctx.get("validation") or {}

    figures = dash.setdefault("figures", [])
    figures[:] = [f for f in figures
                  if f.get("id") not in INJECTED_IDS
                  and (f.get("data") or {}).get("chartId") not in INJECTED_IDS]

    # ---- pivots (numeric ids so PIVOT.VALUE(id, ...) parses) --------------
    pivots = data.setdefault("pivots", {})
    for key in [k for k, p in pivots.items() if p.get("name") in
                ("Event sales forecast summary", "Event forecast validation summary")]:
        del pivots[key]
    summary_id = _next_pivot_id(pivots)
    pivots[summary_id] = _summary_pivot(
        summary_id, "event.forecast.summary", "Event sales forecast summary", ctx)
    val_id = _next_pivot_id(pivots)
    pivots[val_id] = _summary_pivot(
        val_id, "event.forecast.validation.summary",
        "Event forecast validation summary", ctx,
        measures=[{"id": "mape", "fieldName": "mape", "userDefinedName": "MAPE"},
                  {"id": "mae", "fieldName": "mae", "userDefinedName": "MAE"},
                  {"id": "rmse", "fieldName": "rmse", "userDefinedName": "RMSE"}],
        rows=[{"fieldName": "model_name"}])
    data["pivotNextId"] = int(val_id) + 1

    # ---- global filter ----------------------------------------------------
    graph_field = {"field": "forecast_period", "type": "selection"}
    filters = data.setdefault("globalFilters", [])
    filters[:] = [f for f in filters if f.get("id") != FORECAST_FILTER_ID]
    filters.append({
        "id": FORECAST_FILTER_ID, "type": "selection", "label": "Forecast Period",
        "resModel": "event.forecast.summary", "selectionField": "forecast_period",
        "defaultValue": {"operator": "in", "selectionValues": ["1_month"]},
        "pivotFields": {summary_id: dict(graph_field), val_id: dict(graph_field)},
        "listFields": {},
        "graphFields": {FORECAST_CHART_ID: dict(graph_field), ML_CHART_ID: dict(graph_field),
                        VALIDATION_CHART_ID: dict(graph_field)},
    })

    # ---- layout: directly under Monthly Sales (above Top Countries) ------
    width = 1000  # same width as Monthly Sales / Events Status right edge
    chart_h, card_h, val_h = 330, 82, 300
    gap_charts, gap_cards, gap_below = 40, 32, 30
    block_h = chart_h + gap_charts + chart_h + gap_cards + card_h + 18 + val_h
    start_y = layout.reserve_space(dash, block_h + gap_below)
    if start_y is None:
        return data
    y1 = start_y
    y2 = y1 + chart_h + gap_charts
    y3 = y2 + chart_h + gap_cards
    y4 = y3 + card_h + 18

    figures.append(_figure(
        FORECAST_CHART_ID, 0, y1, width, chart_h,
        _line_chart(FORECAST_CHART_ID, "Overall Event Sales Forecast (AOV)", "event.forecast.point",
                    _scope(ctx, [["series", "in", ["actual", "forecast"]]]), True)))
    figures.append(_figure(
        ML_CHART_ID, 0, y2, width, chart_h,
        _line_chart(ML_CHART_ID, "Overall Event Sales Forecast (ML Algorithms)", "event.forecast.point",
                    _scope(ctx, [["series", "in", ["exponential_smoothing_forecast", "arima_forecast",
                                                    "linear_forecast", "polynomial_forecast"]]]), False)))

    # ---- training / testing cards (values live on the Data sheet, col Z) --
    cells = helper.setdefault("cells", {})
    cells["Z1"] = "%.0f%%" % float(validation.get("training_percentage") or 0.0)
    cells["Z2"] = "%d days" % int(validation.get("training_count") or 0)
    cells["Z3"] = "%.0f%%" % float(validation.get("testing_percentage") or 0.0)
    cells["Z4"] = "%d days" % int(validation.get("testing_count") or 0)
    arima = 'PIVOT.VALUE(%s,"mape","model_name","ARIMA")' % val_id
    es = 'PIVOT.VALUE(%s,"mape","model_name","Exponential Smoothing")' % val_id
    cells["Z6"] = '=IFERROR(IF(%s<=%s,"ARIMA","Exponential Smoothing"),"—")' % (arima, es)
    cells["Z7"] = '=IFERROR("MAPE: "&ROUND(MIN(%s,%s),1)&"%%","MAPE: —")' % (arima, es)
    # Make problems visible on the card instead of failing silently.
    if validation.get("error"):
        cells["Z6"] = "Forecast error"
        cells["Z7"] = validation["error"][:70]
    elif not int(validation.get("history_days") or 0):
        cells["Z6"] = "No data"
        cells["Z7"] = "No event sales found"
    elif int(validation.get("history_months") or 0) < MIN_HISTORY_MONTHS:
        # Too little history for the model ranking to mean anything.
        cells["Z6"] = "Not enough data"
        cells["Z7"] = "Needs %d+ months of sales" % MIN_HISTORY_MONTHS
    helper["rowNumber"] = max(helper.get("rowNumber", 0), 8)

    gap_x = 15
    small_w = (width - 2 * gap_x) * 0.25
    best_w = width - 2 * small_w - 2 * gap_x

    def card(fig_id, x, w, title, key, base, bg, color="#434343"):
        return _figure(fig_id, x, y3, w, card_h, {
            "baselineMode": "text", "title": {"text": title, "bold": True, "color": color},
            "type": "scorecard", "background": bg, "keyValue": "Data!" + key,
            "baseline": "Data!" + base, "humanize": False, "chartId": fig_id})

    figures.append(card(TRAIN_CARD_ID, 0, small_w, "Training Data", "Z1", "Z2", "#F0FDF4"))
    figures.append(card(TEST_CARD_ID, small_w + gap_x, small_w, "Testing Data", "Z3", "Z4", "#EFF6FF"))
    figures.append(card(BEST_CARD_ID, 2 * (small_w + gap_x), best_w, "Best Performing Model",
                        "Z6", "Z7", "#F0FDF4", "#166534"))

    figures.append(_figure(
        VALIDATION_CHART_ID, 0, y4, width, val_h,
        _line_chart(VALIDATION_CHART_ID, "Overall Event Sales Forecast (Trained & Tested)",
                    "event.forecast.validation.point",
                    _scope(ctx, [["series", "in", ["actual", "arima_predicted",
                                                    "exponential_smoothing_predicted"]]]), False)))

    return data
