"""Odoo ORM layer for sales revenue forecasting.

All the actual forecasting math (AOV-based monthly forecast, daily
trend/seasonality forecast, the zero-bridge-month fix, duration-matched
growth baseline, etc.) lives in ``forecast_engine.py`` as plain,
Odoo-independent Python. See that module's docstring for the full
explanation of the algorithm and the design decisions behind it.

This file's job is only to:
1. Load confirmed (``state == "sale"``) ``sale.order`` data into the plain
   ``(datetime, value)`` structures ``forecast_engine`` expects.
2. Call ``forecast_engine.calculate_horizon`` for each supported horizon.
3. Persist the results into ``sale.forecast.point`` / ``sale.forecast.summary``
   (read by the dashboard chart and KPI cards -- see
   ``models/sales_dashboard_patch.py``).
4. Expose a developer-facing debug helper (``get_forecast_debug``) that
   surfaces the full computation trail for one horizon, for verification
   against the live dashboard.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import math
import logging

from odoo import api, fields, models

from . import forecast_engine as engine

_logger = logging.getLogger(__name__)

FORECAST_HORIZONS = engine.FORECAST_HORIZONS
FORECAST_HORIZONS_WITH_HISTORY = ((engine.HISTORICAL_HORIZON, engine.HISTORICAL_HORIZON_LABEL),) + FORECAST_HORIZONS
SERIES = engine.SERIES


class SaleForecastValidationPoint(models.Model):
    _name = "sale.forecast.validation.point"
    _description = "Sales Forecast Training and Testing Point"
    _order = "date, series"

    date = fields.Date(required=True, index=True)
    revenue = fields.Float(required=True)
    series = fields.Selection([
        ("actual", "Actual Sales"),
        ("training_actual", "Training Actual Sales"),
        ("testing_actual", "Testing Actual Sales"),
        ("arima_predicted", "ARIMA"),
        ("exponential_smoothing_predicted", "Exponential Smoothing"),
    ], required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    owner_id = fields.Many2one("res.users", required=True, index=True)
    forecast_period = fields.Selection(FORECAST_HORIZONS, required=True, index=True, default="1_month")


class SaleForecastValidationSummary(models.Model):
    _name = "sale.forecast.validation.summary"
    _description = "Sales Forecast Training and Testing Summary"
    _order = "forecast_period, rank, model_name"

    forecast_period = fields.Selection(FORECAST_HORIZONS, required=True, index=True)
    model_name = fields.Selection([
        ("ARIMA", "ARIMA"),
        ("Exponential Smoothing", "Exponential Smoothing"),
    ], required=True, index=True)
    mae = fields.Float()
    rmse = fields.Float()
    mape = fields.Float()
    rank = fields.Integer()
    training_count = fields.Integer()
    testing_count = fields.Integer()
    company_id = fields.Many2one("res.company", required=True, index=True)
    owner_id = fields.Many2one("res.users", required=True, index=True)



class SaleForecastPoint(models.Model):
    _name = "sale.forecast.point"
    _description = "Sales Revenue Forecast Point"
    _order = "forecast_horizon, date, series"

    # IMPORTANT: this must stay a Date field, not Datetime.
    #
    # The "Overall Sales Forecast" chart is an odoo_line chart built directly
    # from this model (see _add_forecast_section / forecast_chart_data in
    # sales_dashboard_patch.py), grouped by "date:month". The KPI cards read
    # the same underlying data through a pivot (PIVOT.VALUE), which
    # aggregates server-side via read_group and buckets a Datetime field by
    # month correctly. The client-side graph renderer behind an odoo_line
    # chart does not: for a Datetime field it fills every day between the
    # first and last point with a zero-value tick (to keep the line smooth
    # at day resolution), which produced a sawtooth that spiked on each real
    # monthly point and dropped back to 0 on every day in between, even
    # though every value going in was already correct.
    #
    # All values written to this field are already day/month-floored
    # datetime objects (see engine.floor_day/floor_month/add_months).
    # Odoo's Date field setter truncates a datetime to its date portion on
    # write, so no other code in this file needs to change.
    date = fields.Date(required=True, index=True)
    revenue = fields.Float(required=True)
    series = fields.Selection(SERIES, required=True, index=True)
    forecast_horizon = fields.Selection(FORECAST_HORIZONS_WITH_HISTORY, required=True, index=True)
    # User-facing forecast selector. Unlike forecast_horizon, this intentionally
    # excludes the internal Historical bucket so the search-bar filter only
    # offers actual forecast periods.
    forecast_period = fields.Selection(FORECAST_HORIZONS, required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    owner_id = fields.Many2one("res.users", required=True, index=True)

    @api.model
    def _forecast_as_of(self, daily, fallback=None):
        """Return the business-data cut-off date used by future forecasts.

        The cut-off is the *later* of the latest confirmed sales date and
        today's date (the fallback/server clock).

        Using today's date (rather than stopping at the last confirmed
        order) matters whenever there have been quiet days with zero
        confirmed sales: those days still elapsed and must still count in
        the historical-days denominator, or the daily run rate is
        overstated. For example, if the last confirmed order is 16 Sep 2026
        but today is 22 Sep 2026, the historical period is still
        Mar 1 -> Sep 22 (206 calendar days), not Mar 1 -> Sep 16 (200 days).

        Using the last confirmed order date (rather than stopping at today)
        still matters on the other side: if the Odoo server clock is behind
        the period represented by the imported/confirmed sales data, the
        cut-off must not be earlier than that data.
        """
        today = engine.floor_day(fallback or fields.Datetime.to_datetime(fields.Datetime.now()))
        dates = [date for date, value in (daily or []) if date is not None]
        if dates:
            return max(engine.floor_day(max(dates)), today)
        return today

    @api.model
    def refresh_for_dashboard(self):
        Point = self.sudo()
        Summary = self.env["sale.forecast.summary"].sudo()
        company = self.env.company
        owner = self.env.user
        now = fields.Datetime.now()
        now_dt = fields.Datetime.to_datetime(now)

        history = self._load_daily_history(company)
        daily = engine.fill_daily(history)
        monthly = engine.to_monthly(daily)
        # Future forecast calculations use the latest confirmed sales date as
        # the data cut-off.  Do not use the server clock here.
        forecast_as_of = self._forecast_as_of(daily, fallback=now_dt)
        # Log the exact input used for the 1 Month forecast so the live Odoo
        # server can be verified against the dashboard values.
        if monthly:
            one_month_check = engine.calculate_monthly_forecast(
                "1_month", daily, monthly, now=forecast_as_of
            )
            _logger.info(
                "Sales forecast 1 Month calculation: start_month=%s, as_of=%s, "
                "historical_revenue=%.2f, historical_days=%s, average_daily=%.10f, "
                "first_future=%s, first_future_revenue=%.2f",
                monthly[0][0].date(),
                forecast_as_of.date(),
                one_month_check["debug"].get("historical_revenue", 0.0),
                one_month_check["debug"].get("historical_days", 0),
                one_month_check["debug"].get("average_daily_revenue", 0.0),
                (one_month_check.get("forecast_points") or [{}])[0].get("date"),
                (one_month_check.get("forecast_points") or [{}])[0].get("revenue", 0.0),
            )
        daily_orders = self._load_daily_orders(company)
        monthly_orders = self._load_monthly_orders(company)

        # Compact chronological 80/20 back-test for the dashboard.
        # The split itself remains fixed at 80/20, while the selected Forecast
        # Period controls how much of the held-out test window is evaluated.
        # This makes the Best Model result respond to the Forecast Period
        # filter without inventing six months of test data when only ~39
        # historical test days are available.
        base_validation = engine.calculate_training_testing(daily, train_ratio=0.80)
        validation_result = base_validation
        validation_point_vals = []
        validation_summary_vals = []

        horizon_test_days = {
            "7_days": 7,
            "1_month": 30,
            "6_months": 180,
            "1_year": 365,
            "2_years": 730,
            "5_years": 1825,
            "10_years": 3650,
        }

        for period_key, _period_label in FORECAST_HORIZONS:
            available_test = list(base_validation.get("testing_points") or [])
            requested_days = horizon_test_days.get(period_key, len(available_test))
            # Use the most recent portion of the held-out test window. If the
            # requested horizon is longer than the available test history,
            # use every available test observation rather than fabricating
            # data or leaking future observations into training.
            selected_test = available_test[-min(requested_days, len(available_test)):] if available_test else []

            # Plot one continuous Actual Sales series for the complete
            # historical period. Training/testing are still separated
            # internally for evaluation, but the dashboard does not need two
            # duplicate actual-sales lines.
            for point in base_validation.get("actual_points") or []:
                validation_point_vals.append({
                    "date": point["date"],
                    "revenue": point["revenue"],
                    "series": "actual",
                    "forecast_period": period_key,
                    "company_id": company.id,
                    "owner_id": owner.id,
                })

            # Plot the complete training history plus in-sample fitted
            # values. Fitted values are visual diagnostics only; the accuracy
            # metrics below use the unseen test window only.
            for point in base_validation.get("training_points") or []:
                if point.get("arima_fitted") is not None:
                    validation_point_vals.append({
                        "date": point["date"],
                        "revenue": point["arima_fitted"],
                        "series": "arima_predicted",
                        "forecast_period": period_key,
                        "company_id": company.id,
                        "owner_id": owner.id,
                    })
                if point.get("exponential_smoothing_fitted") is not None:
                    validation_point_vals.append({
                        "date": point["date"],
                        "revenue": point["exponential_smoothing_fitted"],
                        "series": "exponential_smoothing_predicted",
                        "forecast_period": period_key,
                        "company_id": company.id,
                        "owner_id": owner.id,
                    })

            for point in selected_test:
                if point.get("arima_predicted") is not None:
                    validation_point_vals.append({
                        "date": point["date"],
                        "revenue": point["arima_predicted"],
                        "series": "arima_predicted",
                        "forecast_period": period_key,
                        "company_id": company.id,
                        "owner_id": owner.id,
                    })
                if point.get("exponential_smoothing_predicted") is not None:
                    validation_point_vals.append({
                        "date": point["date"],
                        "revenue": point["exponential_smoothing_predicted"],
                        "series": "exponential_smoothing_predicted",
                        "forecast_period": period_key,
                        "company_id": company.id,
                        "owner_id": owner.id,
                    })

            # Add the same future forecast tail used by the main ML forecast
            # chart.  The testing section therefore remains fully historical
            # through the last actual sale, but when a Forecast Period is
            # selected it continues into the corresponding future horizon.
            #
            # IMPORTANT: these future points are visualization only.  They are
            # NOT included in MAE/RMSE/MAPE.  Accuracy is still calculated
            # strictly on the unseen held-out test observations above.
            try:
                arima_future = engine.calculate_arima_forecast(
                    daily, monthly, period_key, now=forecast_as_of
                )
                for point in arima_future.get("forecast_points") or []:
                    validation_point_vals.append({
                        "date": point["date"],
                        "revenue": point["revenue"],
                        "series": "arima_predicted",
                        "forecast_period": period_key,
                        "company_id": company.id,
                        "owner_id": owner.id,
                    })
            except Exception:
                _logger.exception(
                    "ARIMA future forecast could not be added to validation chart for %s",
                    period_key,
                )

            try:
                es_future = engine.calculate_exponential_smoothing_forecast(
                    daily, monthly, period_key, now=forecast_as_of
                )
                for point in es_future.get("forecast_points") or []:
                    validation_point_vals.append({
                        "date": point["date"],
                        "revenue": point["revenue"],
                        "series": "exponential_smoothing_predicted",
                        "forecast_period": period_key,
                        "company_id": company.id,
                        "owner_id": owner.id,
                    })
            except Exception:
                _logger.exception(
                    "Exponential Smoothing future forecast could not be added to validation chart for %s",
                    period_key,
                )

            # Recalculate testing metrics for this filter-specific evaluation
            # window.  The model fits are still based only on the same 80%
            # training history, so there is no test-data leakage.
            actual = [point["actual"] for point in selected_test]
            arima_pred = [point.get("arima_predicted") for point in selected_test]
            es_pred = [point.get("exponential_smoothing_predicted") for point in selected_test]
            period_metrics = []
            if actual and all(value is not None for value in arima_pred):
                period_metrics.append({
                    "model": "ARIMA",
                    **engine._forecast_error_metrics(actual, arima_pred),
                })
            if actual and all(value is not None for value in es_pred):
                period_metrics.append({
                    "model": "Exponential Smoothing",
                    **engine._forecast_error_metrics(actual, es_pred),
                })
            period_metrics.sort(key=lambda item: (item["mape"], item["rmse"]))
            for rank, item in enumerate(period_metrics, start=1):
                validation_summary_vals.append({
                    "forecast_period": period_key,
                    "model_name": item["model"],
                    "mae": item["mae"],
                    "rmse": item["rmse"],
                    "mape": item["mape"],
                    "rank": rank,
                    "training_count": int(base_validation.get("training_count") or 0),
                    "testing_count": len(selected_test),
                    "company_id": company.id,
                    "owner_id": owner.id,
                })

        ValidationPoint = self.env["sale.forecast.validation.point"].sudo()
        ValidationSummary = self.env["sale.forecast.validation.summary"].sudo()
        old_validation_points = ValidationPoint.search([
            ("company_id", "=", company.id),
            ("owner_id", "=", owner.id),
        ])
        old_validation_summaries = ValidationSummary.search([
            ("company_id", "=", company.id),
            ("owner_id", "=", owner.id),
        ])
        # Replace the previous validation snapshot before inserting the new
        # one.  Do NOT create first and then unlink the search result: that
        # search also sees the rows we just created and would immediately
        # delete the entire validation dataset.  That was the reason the
        # Training/Testing chart showed zero ES values and the Best Model card
        # showed an em-dash.
        if old_validation_points:
            old_validation_points.unlink()
        if old_validation_summaries:
            old_validation_summaries.unlink()
        if validation_point_vals:
            ValidationPoint.create(validation_point_vals)
        if validation_summary_vals:
            ValidationSummary.create(validation_summary_vals)

        point_vals = []
        summary_vals = []

        # Always persist a separate historical/back-test series. This is the
        # default dashboard state and contains forecasts for historical months
        # plus the current month. The current month is calculated only from
        # data before it starts, so it is still a valid back-test point. It is
        # intentionally separate from the selectable
        # future horizons so the dashboard never shows future forecast values
        # until the user selects a Forecast Period.
        historical = engine.calculate_historical_forecast(
            daily, monthly, now=now_dt
        )

        # The standalone internal Historical horizon is no longer exposed to
        # the user-facing filter. Do not persist a second copy of these rows
        # under that horizon, otherwise the default 1 Month filter would see
        # duplicate historical points. Each selectable future horizon below
        # already receives the historical actual + back-test forecast series.
        for key, _label in FORECAST_HORIZONS:
            result = engine.calculate_horizon(
                key, daily, monthly, daily_orders, monthly_orders, now=forecast_as_of
            )

            # Every selectable future horizon must contain the same
            # historical/back-tested forecast series as the Historical
            # view.  The Forecast Period filter selects a horizon-specific
            # set of rows, so if we stored only the future points here, the
            # historical forecast disappeared as soon as the user selected
            # 7 Days / 1 Month / 6 Months / etc.
            #
            # Keep the historical actual + back-tested forecast points in
            # every horizon and append that horizon's future forecast. This
            # makes the chart continuous: past actual + past forecast +
            # future forecast. For the 7-day horizon, keep the actual sales
            # at daily resolution so the chart can switch to a daily X-axis
            # when the Forecast Period filter is set to 7 Days.
            if key == "7_days":
                horizon_actual_points = result["actual_points"]
            else:
                horizon_actual_points = historical["actual_points"]

            # IMPORTANT: for the 7-day horizon, the chart is displayed at
            # daily resolution. Including the historical/back-tested forecast
            # in the same monthly bucket causes Odoo to SUM them together
            # with the real 7-day future forecast.  That makes a correct
            # 7-day total (for example 1,113,631.20) appear as a much larger
            # monthly value (for example ~5,889k).
            #
            # Keep the historical forecast series for all longer horizons,
            # but for 7 Days the forecast series must contain ONLY the actual
            # seven future forecast points.  The summary/KPI already uses
            # result["forecast_revenue"], so this change affects only the
            # chart display and leaves the forecasting math untouched.
            if key == "7_days":
                # Keep historical back-test points before the current month and
                # use the selected horizon's daily future points for the current/future dates.
                current_month_start = engine.floor_month(forecast_as_of)
                past_historical_forecast = [
                    point for point in historical["forecast_points"]
                    if engine.floor_month(point["date"]) < current_month_start
                ]
                horizon_forecast_points = past_historical_forecast + list(result["forecast_points"])
                past_historical_linear = [
                    point for point in historical["linear_forecast_points"]
                    if engine.floor_month(point["date"]) < current_month_start
                ]
                horizon_linear_points = past_historical_linear + list(result["linear_forecast_points"])
                past_historical_polynomial = [
                    point for point in historical["polynomial_forecast_points"]
                    if engine.floor_month(point["date"]) < current_month_start
                ]
                horizon_polynomial_points = past_historical_polynomial + list(result["polynomial_forecast_points"])
            else:
                horizon_forecast_points = historical["forecast_points"] + result["forecast_points"]
                horizon_linear_points = historical["linear_forecast_points"] + result["linear_forecast_points"]
                horizon_polynomial_points = historical["polynomial_forecast_points"] + result["polynomial_forecast_points"]
            point_vals.extend(engine.point_values(
                key, company.id, owner.id,
                horizon_actual_points, horizon_forecast_points,
                horizon_polynomial_points, horizon_linear_points,
            ))

            # Completely separate ES dataset. The existing forecast point
            # model and all of its series/calculations remain untouched.
            try:
                es_result = engine.calculate_exponential_smoothing_forecast(
                    daily, monthly, key, now=forecast_as_of
                )
                # The ML chart is intentionally a SINGLE-SERIES chart:
                # Exponential Smoothing only.  Persist the historical
                # month-by-month ES back-test values together with the
                # selected horizon's future ES values so the graph shows the
                # complete ES curve rather than actual revenue or the other
                # forecast algorithms.
                #
                # For 7 Days the X-axis is daily, so keep only the daily
                # future ES values in that horizon.  Longer horizons are
                # monthly and include the historical ES back-test points.
                es_points = []
                if key != "7_days":
                    es_points.extend(es_result.get("historical_forecast_points") or [])
                es_points.extend(es_result.get("forecast_points") or [])
                for point in es_points:
                    point_vals.append({
                        "date": point["date"],
                        "revenue": point["revenue"],
                        "series": "exponential_smoothing_forecast",
                        "forecast_horizon": key,
                        "forecast_period": key,
                        "company_id": company.id,
                        "owner_id": owner.id,
                    })
                _logger.info(
                    "ES forecast %s: historical_points=%s future_points=%s first_future=%s first_future_revenue=%.2f",
                    key,
                    len(es_result.get("historical_forecast_points") or []),
                    len(es_result.get("forecast_points") or []),
                    (es_result.get("forecast_points") or [{}])[0].get("date"),
                    (es_result.get("forecast_points") or [{}])[0].get("revenue", 0.0),
                )
            except Exception:
                _logger.exception("ES forecast calculation failed for horizon %s", key)

            # Separate ARIMA dataset. Exponential Smoothing above is kept
            # unchanged; ARIMA is an additional time-series model using the
            # same confirmed sales history and the same Forecast Period filter.
            try:
                arima_result = engine.calculate_arima_forecast(
                    daily, monthly, key, now=forecast_as_of
                )
                arima_points = []
                if key != "7_days":
                    arima_points.extend(
                        arima_result.get("historical_forecast_points") or []
                    )
                arima_points.extend(arima_result.get("forecast_points") or [])
                for point in arima_points:
                    point_vals.append({
                        "date": point["date"],
                        "revenue": point["revenue"],
                        "series": "arima_forecast",
                        "forecast_horizon": key,
                        "forecast_period": key,
                        "company_id": company.id,
                        "owner_id": owner.id,
                    })
                _logger.info(
                    "ARIMA forecast %s: historical_points=%s future_points=%s first_future=%s first_future_revenue=%.2f available=%s",
                    key,
                    len(arima_result.get("historical_forecast_points") or []),
                    len(arima_result.get("forecast_points") or []),
                    (arima_result.get("forecast_points") or [{}])[0].get("date"),
                    (arima_result.get("forecast_points") or [{}])[0].get("revenue", 0.0),
                    arima_result.get("debug", {}).get("available", False),
                )
            except Exception:
                _logger.exception("ARIMA forecast calculation failed for horizon %s", key)

            summary_vals.append(engine.summary_values(
                key,
                company.id,
                owner.id,
                now,
                result["current_revenue"],
                result["forecast_revenue"],
                result["growth_pct"],
                result["confidence"],
            ))

        # IMPORTANT: create the new rows *before* deleting the old ones, and
        # capture the old IDs first.
        #
        # This method is called every time the Sales dashboard JSON is
        # served (see spreadsheet_dashboard.py), while the browser is
        # simultaneously (re)evaluating PIVOT.VALUE() formulas and the
        # forecast chart against this same table. The previous
        # unlink()-then-create() ordering left a window, however short,
        # where a concurrent read would find zero rows for this
        # company/owner and briefly render 0 / +0% before the new rows
        # landed - this is what caused the Forecast Revenue KPI to flicker
        # 0 -> 25,495k -> 23,495k -> 0 across a couple of seconds with no
        # filter change. Creating first means a concurrent read always sees
        # either the complete old set or the complete new set, never empty.
        old_points = Point.search([
            ("company_id", "=", company.id),
            ("owner_id", "=", owner.id),
        ])
        old_summaries = Summary.search([
            ("company_id", "=", company.id),
            ("owner_id", "=", owner.id),
        ])
        if point_vals:
            Point.create(point_vals)
        if summary_vals:
            Summary.create(summary_vals)

        old_points.unlink()
        old_summaries.unlink()
        return validation_result

    @api.model
    def get_monthly_aov_tooltip_data(self):
        """Return monthly tooltip data for the forecast chart hover.

        AOV is calculated from the same confirmed ``sale.order`` records used
        by the forecast chart: monthly revenue divided by the number of
        confirmed sales orders in that month.

        Alongside AOV, this also returns the "mode" product per month -- the
        product that appears on the most confirmed ``sale.order.line`` rows
        that month -- and that count ("mode frequency"). Frequency is a
        count of order LINES (i.e. how many separate sales included that
        product), not total quantity/units sold. Ties are broken by keeping
        the first product encountered, so the result is deterministic for a
        given data set.

        The result is intentionally a small JSON-friendly mapping used only
        by the frontend tooltip; it does not create another chart or series.
        """
        company = self.env.company
        SaleOrder = self.env["sale.order"].sudo()
        domain = [
            ("company_id", "=", company.id),
            ("state", "=", "sale"),
        ]
        revenue_by_month = {}
        orders_by_month = {}
        # month_key -> individual confirmed order totals used for
        # the per-month standard deviation shown in the tooltip.
        order_amounts_by_month = {}
        # month_key -> {product_id: line_count}
        product_line_counts_by_month = {}
        # month_key -> {product_id: product_display_name}
        product_names_by_month = {}
        for order in SaleOrder.search(domain, order="date_order asc"):
            if not order.date_order:
                continue
            month = engine.floor_month(fields.Datetime.to_datetime(order.date_order))
            key = month.strftime("%Y-%m")
            order_amount = float(order.amount_total or 0.0)
            revenue_by_month[key] = revenue_by_month.get(key, 0.0) + order_amount
            orders_by_month[key] = orders_by_month.get(key, 0) + 1
            order_amounts_by_month.setdefault(key, []).append(order_amount)

            line_counts = product_line_counts_by_month.setdefault(key, {})
            names = product_names_by_month.setdefault(key, {})
            for line in order.order_line:
                product = line.product_id
                if not product:
                    continue
                line_counts[product.id] = line_counts.get(product.id, 0) + 1
                if product.id not in names:
                    names[product.id] = product.display_name

        mode_product_by_month = {}
        mode_product_price_by_month = {}
        mode_frequency_by_month = {}
        for key, line_counts in product_line_counts_by_month.items():
            if not line_counts:
                continue
            top_product_id = max(
                line_counts,
                key=lambda product_id: line_counts[product_id],
            )
            mode_product_by_month[key] = product_names_by_month[key].get(top_product_id, "")
            top_product = self.env["product.product"].sudo().browse(top_product_id)
            mode_product_price_by_month[key] = float(top_product.lst_price or 0.0) if top_product.exists() else 0.0
            mode_frequency_by_month[key] = line_counts[top_product_id]

        # Standard deviation is calculated separately for each month from
        # the confirmed sales-order totals in that month. This makes the
        # tooltip value month-specific instead of repeating one global
        # standard deviation for every month. Population SD is used because
        # the calculation covers all confirmed orders available for that
        # month, rather than treating them as a sample.
        standard_deviation_by_month = {}
        for key, amounts in order_amounts_by_month.items():
            if not amounts:
                standard_deviation_by_month[key] = 0.0
                continue
            mean_order_amount = sum(amounts) / len(amounts)
            standard_deviation_by_month[key] = math.sqrt(
                sum(
                    (amount - mean_order_amount) ** 2
                    for amount in amounts
                ) / len(amounts)
            )

        return {
            "values": {
                key: (revenue_by_month[key] / orders_by_month[key])
                for key in revenue_by_month
                if orders_by_month.get(key)
            },
            "currency_symbol": company.currency_id.symbol or "",
            "mode_product": mode_product_by_month,
            "mode_product_price": mode_product_price_by_month,
            "mode_frequency": mode_frequency_by_month,
            "standard_deviation": standard_deviation_by_month,
        }

    @api.model
    def get_dashboard_forecast(self, horizon="1_month"):
        valid = dict(FORECAST_HORIZONS)
        if horizon not in valid:
            horizon = "1_month"

        company = self.env.company
        history = self._load_daily_history(company)
        daily = engine.fill_daily(history)
        monthly = engine.to_monthly(daily)
        now_dt = fields.Datetime.to_datetime(fields.Datetime.now())
        forecast_as_of = self._forecast_as_of(daily, fallback=now_dt)
        # Log the exact input used for the 1 Month forecast so the live Odoo
        # server can be verified against the dashboard values.
        if monthly:
            one_month_check = engine.calculate_monthly_forecast(
                "1_month", daily, monthly, now=forecast_as_of
            )
            _logger.info(
                "Sales forecast 1 Month calculation: start_month=%s, as_of=%s, "
                "historical_revenue=%.2f, historical_days=%s, average_daily=%.10f, "
                "first_future=%s, first_future_revenue=%.2f",
                monthly[0][0].date(),
                forecast_as_of.date(),
                one_month_check["debug"].get("historical_revenue", 0.0),
                one_month_check["debug"].get("historical_days", 0),
                one_month_check["debug"].get("average_daily_revenue", 0.0),
                (one_month_check.get("forecast_points") or [{}])[0].get("date"),
                (one_month_check.get("forecast_points") or [{}])[0].get("revenue", 0.0),
            )
        daily_orders = self._load_daily_orders(company)
        monthly_orders = self._load_monthly_orders(company)
        if horizon == engine.HISTORICAL_HORIZON:
            result = engine.calculate_historical_forecast(
                daily, monthly
            )
        else:
            result = engine.calculate_horizon(
                horizon, daily, monthly, daily_orders, monthly_orders, now=forecast_as_of
            )

        return {
            "horizon": horizon,
            "label": valid[horizon],
            "current_revenue": result["current_revenue"],
            "forecast_revenue": result["forecast_revenue"],
            "growth_pct": result["growth_pct"],
            "confidence": result["confidence"],
            "actual_points": result["actual_points"],
            "forecast_points": result["forecast_points"],
            "linear_forecast_points": result.get("linear_forecast_points", []),
            "polynomial_forecast_points": result.get("polynomial_forecast_points", []),
        }

    @api.model
    def get_forecast_debug(self, horizon="1_month"):
        """Developer-facing diagnostic helper.

        Returns (and logs) the full computation trail for one horizon:
        completed monthly revenue/order rows, monthly AOV rows, the
        weighted AOV/order baseline (or the daily run-rate baseline for
        sparse history), every future date with its forecast orders/AOV/
        revenue, and the total forecast revenue and growth. Use this from
        an Odoo shell or a server action to verify the dashboard's numbers:

            env["sale.forecast.point"].get_forecast_debug("1_month")
            env["sale.forecast.point"].get_forecast_debug("6_months")
        """
        valid = dict(FORECAST_HORIZONS)
        if horizon not in valid:
            horizon = "1_month"

        company = self.env.company
        history = self._load_daily_history(company)
        daily = engine.fill_daily(history)
        monthly = engine.to_monthly(daily)
        now_dt = fields.Datetime.to_datetime(fields.Datetime.now())
        forecast_as_of = self._forecast_as_of(daily, fallback=now_dt)
        # Log the exact input used for the 1 Month forecast so the live Odoo
        # server can be verified against the dashboard values.
        if monthly:
            one_month_check = engine.calculate_monthly_forecast(
                "1_month", daily, monthly, now=forecast_as_of
            )
            _logger.info(
                "Sales forecast 1 Month calculation: start_month=%s, as_of=%s, "
                "historical_revenue=%.2f, historical_days=%s, average_daily=%.10f, "
                "first_future=%s, first_future_revenue=%.2f",
                monthly[0][0].date(),
                forecast_as_of.date(),
                one_month_check["debug"].get("historical_revenue", 0.0),
                one_month_check["debug"].get("historical_days", 0),
                one_month_check["debug"].get("average_daily_revenue", 0.0),
                (one_month_check.get("forecast_points") or [{}])[0].get("date"),
                (one_month_check.get("forecast_points") or [{}])[0].get("revenue", 0.0),
            )
        daily_orders = self._load_daily_orders(company)
        monthly_orders = self._load_monthly_orders(company)
        result = engine.calculate_horizon(
            horizon, daily, monthly, daily_orders, monthly_orders, now=forecast_as_of
        )
        debug = result.get("debug", {})

        def _stringify(value):
            if isinstance(value, datetime):
                return value.date().isoformat()
            if isinstance(value, (list, tuple)):
                return [_stringify(v) for v in value]
            if isinstance(value, dict):
                return {k: _stringify(v) for k, v in value.items()}
            return value

        printable = _stringify(debug)
        _logger.info(
            "Sales forecast debug (%s):\n%s",
            horizon,
            json.dumps(printable, indent=2, default=str),
        )
        return printable

    @staticmethod
    def _point_values(horizon, company_id, owner_id, actual_points, forecast_points,
                      polynomial_forecast_points=None):
        # Kept for backward compatibility with any external caller; the
        # implementation now lives in forecast_engine.point_values.
        return engine.point_values(
            horizon, company_id, owner_id, actual_points, forecast_points,
            polynomial_forecast_points,
        )

    @api.model
    def _load_daily_history(self, company):
        """Load the same confirmed order revenue used by the forecast.

        ``amount_total`` is used because the dashboard KPI is overall sales
        revenue. Draft quotations and cancelled orders are excluded.
        """
        SaleOrder = self.env["sale.order"].sudo()
        # Use the complete confirmed sales history. The forecast engine
        # calculates the denominator dynamically from the first available
        # sales date through the calculation date; there is intentionally no
        # fixed 60-day (or 10-year) lookback window.
        domain = [
            ("company_id", "=", company.id),
            ("state", "=", "sale"),
        ]

        buckets = {}
        try:
            orders = SaleOrder.search(domain, order="date_order asc")
            for order in orders:
                if not order.date_order:
                    continue
                date_value = fields.Datetime.to_datetime(order.date_order)
                day = engine.floor_day(date_value)
                buckets[day] = buckets.get(day, 0.0) + float(
                    order.amount_total or 0.0
                )
        except Exception:
            _logger.exception("Sales forecast: sale.order history query failed")

        # Do not silently replace a valid sale.order result with sale.report.
        # This keeps the forecast source consistent with the visible Sales
        # Orders page and prevents double counting sale.report lines.
        return sorted(buckets.items(), key=lambda item: item[0])

    @api.model
    def _load_daily_orders(self, company):
        """Return confirmed order counts by day."""
        SaleOrder = self.env["sale.order"].sudo()
        domain = [
            ("company_id", "=", company.id),
            ("state", "=", "sale"),
        ]
        buckets = {}
        for order in SaleOrder.search(domain, order="date_order asc"):
            if not order.date_order:
                continue
            day = engine.floor_day(fields.Datetime.to_datetime(order.date_order))
            buckets[day] = buckets.get(day, 0) + 1
        return sorted(buckets.items(), key=lambda item: item[0])

    @api.model
    def _load_monthly_orders(self, company):
        """Return confirmed order counts by month for the AOV forecast."""
        SaleOrder = self.env["sale.order"].sudo()
        domain = [("company_id", "=", company.id), ("state", "=", "sale")]
        buckets = {}
        for order in SaleOrder.search(domain, order="date_order asc"):
            if not order.date_order:
                continue
            month = engine.floor_month(fields.Datetime.to_datetime(order.date_order))
            buckets[month] = buckets.get(month, 0) + 1
        return sorted(buckets.items(), key=lambda item: item[0])


class SaleForecastSummary(models.Model):
    _name = "sale.forecast.summary"
    _description = "Sales Revenue Forecast Summary"
    _order = "forecast_horizon"

    forecast_horizon = fields.Selection(FORECAST_HORIZONS_WITH_HISTORY, required=True, index=True)
    # User-facing selector: only future forecast periods are exposed.
    forecast_period = fields.Selection(FORECAST_HORIZONS, required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    owner_id = fields.Many2one("res.users", required=True, index=True)
    generated_at = fields.Datetime(required=True, index=True)
    current_revenue = fields.Float()
    forecast_revenue = fields.Float()
    growth_pct = fields.Float()
    confidence = fields.Float()