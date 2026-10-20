# -*- coding: utf-8 -*-
"""ORM layer for the Events AI forecast.

All maths lives in ``event_forecast_engine`` (plain Python).  This file only
loads confirmed event sales into ``(datetime, value)`` series, calls the engine
for every Forecast Period and stores the result in helper models that the
dashboard charts read (like the Sales enhancement module).
"""
import logging
from datetime import datetime, timedelta

from odoo import api, fields, models

from . import event_forecast_engine as engine

_logger = logging.getLogger(__name__)

# Event-specific series labels.  The Sales AI module's tooltip script decorates
# any tooltip containing the exact text "Actual Revenue" with whole-company
# Sales data (AOV, mode product, frequency).  Using "Actual Event Revenue"
# keeps that Sales-only data off the Events charts.
EVENT_SERIES = (
    ("actual", "Actual Event Revenue"),
    ("forecast", "Forecasted Event Revenue"),
    ("linear_forecast", "Linear Regression"),
    ("polynomial_forecast", "Polynomial Regression"),
    ("exponential_smoothing_forecast", "Exponential Smoothing"),
    ("arima_forecast", "ARIMA"),
)
FORECAST_HORIZONS = engine.FORECAST_HORIZONS
FORECAST_HORIZONS_WITH_HISTORY = (
    (engine.HISTORICAL_HORIZON, engine.HISTORICAL_HORIZON_LABEL),
) + FORECAST_HORIZONS

HORIZON_TEST_DAYS = {
    "7_days": 7, "1_month": 30, "6_months": 180, "1_year": 365,
    "2_years": 730, "5_years": 1825, "10_years": 3650,
}
# Rebuild the helper rows at most this often unless event sales changed.
REFRESH_TTL_MINUTES = 10


class EventForecastValidationPoint(models.Model):
    _name = "event.forecast.validation.point"
    _description = "Event Forecast Training and Testing Point"
    _order = "date, series"

    date = fields.Date(required=True, index=True)
    revenue = fields.Float(required=True)
    series = fields.Selection([
        ("actual", "Actual Event Revenue"),
        ("arima_predicted", "ARIMA"),
        ("exponential_smoothing_predicted", "Exponential Smoothing"),
    ], required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    owner_id = fields.Many2one("res.users", required=True, index=True)
    forecast_period = fields.Selection(FORECAST_HORIZONS, required=True, index=True)


class EventForecastValidationSummary(models.Model):
    _name = "event.forecast.validation.summary"
    _description = "Event Forecast Training and Testing Summary"
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


class EventForecastPoint(models.Model):
    _name = "event.forecast.point"
    _description = "Event Sales Forecast Point"
    _order = "forecast_horizon, date, series"

    # Must stay a Date (not Datetime): see the note in the Sales module about
    # the odoo_line renderer zero-filling every day of a Datetime axis.
    date = fields.Date(required=True, index=True)
    revenue = fields.Float(required=True)
    series = fields.Selection(EVENT_SERIES, required=True, index=True)
    forecast_horizon = fields.Selection(FORECAST_HORIZONS_WITH_HISTORY, required=True, index=True)
    forecast_period = fields.Selection(FORECAST_HORIZONS, required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    owner_id = fields.Many2one("res.users", required=True, index=True)

    # ------------------------------------------------------------------
    # Source data: EVENT sales only, by SALE date (never by event date).
    # Primary   = confirmed sale.order.line rows that carry an event, bucketed
    #             by the sales-order date.
    # Fallback  = event.sale.report (sold) bucketed by its sale/registration
    #             date field (see _report_date_field).
    # ------------------------------------------------------------------
    @api.model
    def _report_date_field(self):
        """Date field of event.sale.report that reflects WHEN the sale happened.

        Falls back to the event start date only if the report has no sale-time
        date field at all (then months mean 'month of the event')."""
        report = self.env["event.sale.report"]
        for name in ("sale_order_date", "event_registration_create_date", "create_date"):
            field = report._fields.get(name)
            if field is not None and field.type in ("date", "datetime"):
                return name
        return "event_date_begin"

    @api.model
    def _history_from_report(self):
        report = self.env["event.sale.report"].sudo()
        date_field = self._report_date_field()
        rows = report._read_group(
            [("sale_status", "=", "sold")],
            ["%s:day" % date_field],
            ["sale_price_untaxed:sum", "__count"],
        )
        revenue, counts, monthly = [], [], {}
        for day, amount, count in rows:
            if not day:
                continue
            day_dt = datetime.combine(day, datetime.min.time()) if not isinstance(day, datetime) else day
            day_dt = engine.floor_day(day_dt)
            revenue.append((day_dt, float(amount or 0.0)))
            counts.append((day_dt, int(count or 0)))
            month = engine.floor_month(day_dt)
            monthly[month] = monthly.get(month, 0) + int(count or 0)
        return sorted(revenue), sorted(counts), sorted(monthly.items())

    @api.model
    def _history_from_order_lines(self, company):
        lines = self.env["sale.order.line"].sudo().search([
            ("company_id", "=", company.id),
            ("state", "=", "sale"),
            ("event_id", "!=", False),
        ], order="order_id")
        revenue, orders, monthly_orders, seen = {}, {}, {}, set()
        for line in lines:
            order = line.order_id
            if not order.date_order:
                continue
            day = engine.floor_day(fields.Datetime.to_datetime(order.date_order))
            revenue[day] = revenue.get(day, 0.0) + float(line.price_subtotal or 0.0)
            if order.id not in seen:
                seen.add(order.id)
                orders[day] = orders.get(day, 0) + 1
                month = engine.floor_month(day)
                monthly_orders[month] = monthly_orders.get(month, 0) + 1
        return sorted(revenue.items()), sorted(orders.items()), sorted(monthly_orders.items())

    @api.model
    def _load_history(self, company):
        """Return (daily revenue, daily counts, monthly counts, source label)."""
        try:
            with self.env.cr.savepoint():
                hist, counts, monthly = self._history_from_order_lines(company)
            if hist:
                return hist, counts, monthly, "sale.order.line (order date)"
        except Exception:
            _logger.exception("Event forecast: order-line history failed; trying event.sale.report")
        hist, counts, monthly = self._history_from_report()
        return hist, counts, monthly, "event.sale.report (%s)" % self._report_date_field()

    @api.model
    def get_tooltip_stats(self):
        """Per-day EVENT order statistics for the AOV chart tooltip.

        Same population and dates as the "Actual Event Revenue" series
        (confirmed sale order lines that carry an event, bucketed by the
        order date), so tooltip figures always agree with the plotted revenue.
        Returns ``{"days": {"YYYY-MM-DD": {revenue, orders, sumsq, tickets}}}``
        where ``orders`` counts sale orders, ``sumsq`` is the sum of squared
        order values (lets the browser combine days into months/quarters and
        compute the standard deviation exactly) and ``tickets`` maps each
        ticket type to the number of tickets sold.  Never raises.
        """
        try:
            lines = self.env["sale.order.line"].sudo().search([
                ("company_id", "=", self.env.company.id),
                ("state", "=", "sale"),
                ("event_id", "!=", False),
            ])
            has_ticket = "event_ticket_id" in self.env["sale.order.line"]._fields
            orders = {}   # order id -> [day, order value]
            tickets = {}  # day -> {ticket type: quantity}
            for line in lines:
                order = line.order_id
                if not order.date_order:
                    continue
                day = engine.floor_day(fields.Datetime.to_datetime(order.date_order))
                entry = orders.setdefault(order.id, [day, 0.0])
                entry[1] += float(line.price_subtotal or 0.0)
                name = (line.event_ticket_id.name if has_ticket and line.event_ticket_id
                        else self.env._("No ticket type"))
                per_day = tickets.setdefault(day, {})
                per_day[name] = per_day.get(name, 0.0) + float(line.product_uom_qty or 0.0)
            days = {}
            for day, value in orders.values():
                key = day.strftime("%Y-%m-%d")
                bucket = days.setdefault(key, {"revenue": 0.0, "orders": 0, "sumsq": 0.0, "tickets": {}})
                bucket["revenue"] += value
                bucket["orders"] += 1
                bucket["sumsq"] += value * value
            for day, per_day in tickets.items():
                key = day.strftime("%Y-%m-%d")
                if key in days:
                    days[key]["tickets"] = per_day
            return {"days": days}
        except Exception:
            _logger.exception("Event forecast: tooltip statistics failed")
            return {"days": {}}

    # ------------------------------------------------------------------
    def _vals(self, base, series, points, horizon=None, period=None):
        out = []
        for p in points or []:
            row = dict(base, date=p["date"], revenue=p["revenue"], series=series)
            if horizon:
                row.update(forecast_horizon=horizon, forecast_period=horizon)
            if period:
                row["forecast_period"] = period
            out.append(row)
        return out

    @api.model
    def refresh_for_dashboard(self, force=False):
        """Safe wrapper: never raises; returns a dict that always has the split
        info plus ``history_days``/``source`` or an ``error`` message."""
        try:
            with self.env.cr.savepoint():
                return self._refresh(force=force)
        except Exception as exc:
            _logger.exception("Event forecast refresh failed")
            return {"error": "%s: %s" % (type(exc).__name__, str(exc).splitlines()[0][:80] if str(exc) else "")}

    @api.model
    def _refresh(self, force=False):
        """Rebuild forecast helper rows for the current company/user.

        Returns the training/testing split info used by the scorecards.
        New rows are created before old ones are removed so concurrent dashboard
        reads never see an empty table.
        """
        Point = self.sudo()
        Summary = self.env["event.forecast.summary"].sudo()
        VPoint = self.env["event.forecast.validation.point"].sudo()
        VSummary = self.env["event.forecast.validation.summary"].sudo()
        company, owner = self.env.company, self.env.user
        base = {"company_id": company.id, "owner_id": owner.id}

        # Load first: the history decides both the cache signature and the data.
        history, daily_orders, monthly_orders, source = self._load_history(company)
        signature = "%s|%s|%.2f" % (source, len(history), sum(v for _d, v in history))
        latest = Summary.search(
            [("company_id", "=", company.id), ("owner_id", "=", owner.id)],
            order="generated_at desc", limit=1,
        )
        if (not force and latest and latest.source_signature == signature
                and latest.generated_at
                and fields.Datetime.now() - latest.generated_at
                < timedelta(minutes=REFRESH_TTL_MINUTES)):
            return {
                "training_percentage": latest.training_percentage,
                "testing_percentage": latest.testing_percentage,
                "training_count": latest.training_days,
                "testing_count": latest.testing_days,
                "history_days": latest.history_days,
                "history_months": latest.history_months,
                "source": latest.source,
            }

        now = fields.Datetime.now()
        now_dt = fields.Datetime.to_datetime(now)
        _logger.info("Event forecast: %s sale days (%.2f total) from %s",
                     len(history), sum(v for _d, v in history), source)
        daily = engine.fill_daily(history)
        monthly = engine.to_monthly(daily)
        dates = [d for d, _v in daily]
        as_of = max(engine.floor_day(max(dates)), engine.floor_day(now_dt)) if dates else engine.floor_day(now_dt)

        # ---- 80/20 back-test -------------------------------------------
        base_val = engine.calculate_training_testing(daily, train_ratio=0.80)
        vpoint_vals, vsummary_vals = [], []
        for key, _label in FORECAST_HORIZONS:
            available = list(base_val.get("testing_points") or [])
            n = HORIZON_TEST_DAYS.get(key, len(available))
            selected = available[-min(n, len(available)):] if available else []
            vpoint_vals += self._vals(base, "actual", base_val.get("actual_points"), period=key)
            for p in base_val.get("training_points") or []:
                for src, series in (("arima_fitted", "arima_predicted"),
                                    ("exponential_smoothing_fitted", "exponential_smoothing_predicted")):
                    if p.get(src) is not None:
                        vpoint_vals.append(dict(base, date=p["date"], revenue=p[src],
                                                series=series, forecast_period=key))
            for p in selected:
                for src, series in (("arima_predicted", "arima_predicted"),
                                    ("exponential_smoothing_predicted", "exponential_smoothing_predicted")):
                    if p.get(src) is not None:
                        vpoint_vals.append(dict(base, date=p["date"], revenue=p[src],
                                                series=series, forecast_period=key))
            # Visual-only continuation into the future (not used in metrics).
            for fn, series in ((engine.calculate_arima_forecast, "arima_predicted"),
                               (engine.calculate_exponential_smoothing_forecast,
                                "exponential_smoothing_predicted")):
                try:
                    fut = fn(daily, monthly, key, now=as_of)
                    vpoint_vals += self._vals(base, series, fut.get("forecast_points"), period=key)
                except Exception:
                    _logger.exception("Event forecast: %s future tail failed for %s", series, key)

            actual = [p["actual"] for p in selected]
            metrics = []
            for model_name, field in (("ARIMA", "arima_predicted"),
                                      ("Exponential Smoothing", "exponential_smoothing_predicted")):
                pred = [p.get(field) for p in selected]
                if actual and all(v is not None for v in pred):
                    metrics.append({"model": model_name, **engine._forecast_error_metrics(actual, pred)})
            metrics.sort(key=lambda m: (m["mape"], m["rmse"]))
            for rank, m in enumerate(metrics, start=1):
                vsummary_vals.append(dict(
                    base, forecast_period=key, model_name=m["model"], mae=m["mae"],
                    rmse=m["rmse"], mape=m["mape"], rank=rank,
                    training_count=int(base_val.get("training_count") or 0),
                    testing_count=len(selected),
                ))

        # ---- Future forecasts per horizon ------------------------------
        historical = engine.calculate_historical_forecast(daily, monthly, now=now_dt)
        point_vals, summary_vals = [], []
        for key, _label in FORECAST_HORIZONS:
            result = engine.calculate_horizon(
                key, daily, monthly, daily_orders, monthly_orders, now=as_of)
            if key == "7_days":
                actual_pts = result["actual_points"]
                cur = engine.floor_month(as_of)
                fc = [p for p in historical["forecast_points"] if engine.floor_month(p["date"]) < cur] + list(result["forecast_points"])
                lin = [p for p in historical["linear_forecast_points"] if engine.floor_month(p["date"]) < cur] + list(result["linear_forecast_points"])
                poly = [p for p in historical["polynomial_forecast_points"] if engine.floor_month(p["date"]) < cur] + list(result["polynomial_forecast_points"])
            else:
                actual_pts = historical["actual_points"]
                fc = historical["forecast_points"] + result["forecast_points"]
                lin = historical["linear_forecast_points"] + result["linear_forecast_points"]
                poly = historical["polynomial_forecast_points"] + result["polynomial_forecast_points"]
            point_vals += engine.point_values(key, company.id, owner.id, actual_pts, fc, poly, lin)

            for fn, series in ((engine.calculate_exponential_smoothing_forecast, "exponential_smoothing_forecast"),
                               (engine.calculate_arima_forecast, "arima_forecast")):
                try:
                    res = fn(daily, monthly, key, now=as_of)
                    pts = [] if key == "7_days" else list(res.get("historical_forecast_points") or [])
                    pts += list(res.get("forecast_points") or [])
                    point_vals += self._vals(base, series, pts, horizon=key)
                except Exception:
                    _logger.exception("Event forecast: %s failed for %s", series, key)

            summary_vals.append(dict(
                engine.summary_values(key, company.id, owner.id, now,
                                      result["current_revenue"], result["forecast_revenue"],
                                      result["growth_pct"], result["confidence"]),
                source_signature=signature, history_days=len(history), source=source,
                history_months=len({engine.floor_month(d) for d, _v in history}),
                training_percentage=float(base_val.get("training_percentage") or 0.0),
                testing_percentage=float(base_val.get("testing_percentage") or 0.0),
                training_days=int(base_val.get("training_count") or 0),
                testing_days=int(base_val.get("testing_count") or 0),
            ))

        domain = [("company_id", "=", company.id), ("owner_id", "=", owner.id)]
        old = (Point.search(domain), Summary.search(domain),
               VPoint.search(domain), VSummary.search(domain))
        if point_vals:
            Point.create(point_vals)
        if summary_vals:
            Summary.create(summary_vals)
        if vpoint_vals:
            VPoint.create(vpoint_vals)
        if vsummary_vals:
            VSummary.create(vsummary_vals)
        for recs in old:
            recs.unlink()
        return {
            "training_percentage": base_val.get("training_percentage") or 0.0,
            "testing_percentage": base_val.get("testing_percentage") or 0.0,
            "training_count": base_val.get("training_count") or 0,
            "testing_count": base_val.get("testing_count") or 0,
            "history_days": len(history),
            "history_months": len({engine.floor_month(d) for d, _v in history}),
            "source": source,
        }


class EventForecastSummary(models.Model):
    _name = "event.forecast.summary"
    _description = "Event Sales Forecast Summary"
    _order = "forecast_horizon"

    forecast_horizon = fields.Selection(FORECAST_HORIZONS_WITH_HISTORY, required=True, index=True)
    forecast_period = fields.Selection(FORECAST_HORIZONS, required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    owner_id = fields.Many2one("res.users", required=True, index=True)
    generated_at = fields.Datetime(required=True, index=True)
    current_revenue = fields.Float()
    forecast_revenue = fields.Float()
    growth_pct = fields.Float()
    confidence = fields.Float()
    source_signature = fields.Char()
    training_percentage = fields.Float()
    testing_percentage = fields.Float()
    training_days = fields.Integer()
    testing_days = fields.Integer()
    history_days = fields.Integer()
    history_months = fields.Integer()
    source = fields.Char()