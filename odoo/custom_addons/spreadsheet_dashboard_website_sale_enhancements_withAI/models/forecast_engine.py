# -*- coding: utf-8 -*-
"""Regression-based sales forecasting for the Odoo Sales dashboard.

Daily revenue is the target. The engine fits ordinary least-squares linear
regression (slope + intercept) and a degree-2 polynomial regression to the
available daily revenue history using the same scikit-learn approach as the
standalone daily regression script. Pearson R and in-sample R² diagnostics are
also calculated. Monthly forecast points are sums of predicted daily values in
each future calendar month. Install numpy, scipy, scikit-learn, and statsmodels in
the Odoo Python environment before using this module.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta

import numpy as np
import warnings
from scipy.stats import pearsonr
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.metrics import r2_score
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing

FORECAST_HORIZONS = (
    ("7_days", "7 Days"),
    ("1_month", "1 Month"),
    ("6_months", "6 Months"),
    ("1_year", "1 Year"),
    ("2_years", "2 Years"),
    ("5_years", "5 Years"),
    ("10_years", "10 Years"),
)

SERIES = (
    ("actual", "Actual Revenue"),
    ("forecast", "Forecasted Revenue"),
    ("linear_forecast", "Linear Regression"),
    ("polynomial_forecast", "Polynomial Regression"),
    ("exponential_smoothing_forecast", "Exponential Smoothing"),
    ("arima_forecast", "ARIMA"),
)
HISTORICAL_HORIZON = "historical"
HISTORICAL_HORIZON_LABEL = "Historical"
AVG_DAYS_PER_MONTH = 30.437
ARIMA_ORDER = (1, 1, 1)
ARIMA_MIN_OBSERVATIONS = 4

# ============================================================================
# 1. LINEAR REGRESSION AND POLYNOMIAL REGRESSION
# Linear and polynomial calculations share the existing fitted-model functions.
# ============================================================================

def floor_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def floor_month(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def add_months(value: datetime, months: int) -> datetime:
    index = value.year * 12 + value.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return value.replace(year=year, month=month, day=1)


def horizon_steps(key):
    if key == "7_days":
        return 7, "day"
    if key == "1_month":
        return 1, "month"
    if key == "6_months":
        return 6, "month"
    if key == "1_year":
        return 12, "month"
    if key == "2_years":
        return 24, "month"
    if key == "5_years":
        return 60, "month"
    if key == "10_years":
        return 120, "month"
    return 30, "day"


def fill_daily(history):
    """Fill calendar-day gaps between the first and last real history date."""
    if not history:
        return []
    values = {floor_day(date): float(value or 0.0) for date, value in history}
    first, last = min(values), max(values)
    result = []
    current = first
    while current <= last:
        result.append((current, values.get(current, 0.0)))
        current += timedelta(days=1)
    return result


def to_monthly(daily):
    buckets = {}
    for date, revenue in daily or []:
        month = floor_month(date)
        buckets[month] = buckets.get(month, 0.0) + float(revenue or 0.0)
    return sorted(buckets.items())


def _training_daily(daily, cutoff):
    """Return a continuous daily series from first history date through cutoff.

    Missing calendar dates are zero-revenue days. The target month is never
    included in a historical back-test window when cutoff is before that month.
    """
    cutoff = floor_day(cutoff)
    values = {floor_day(date): float(value or 0.0) for date, value in (daily or [])
              if date is not None and floor_day(date) <= cutoff}
    if not values:
        return []
    first = min(values)
    if cutoff < first:
        return []
    result = []
    current = first
    while current <= cutoff:
        result.append((current, values.get(current, 0.0)))
        current += timedelta(days=1)
    return result


def _fit_regression_models(training):
    """Fit scikit-learn linear and degree-2 polynomial models on daily revenue.

    X is elapsed calendar days since the first training date; y is daily revenue.
    This follows the standalone daily_regression_debug_with_future_forecast.py
    method: LinearRegression, PolynomialFeatures(degree=2), Pearson R, and R².
    """
    if not training:
        return {
            "first_date": None, "count": 0, "linear": (0.0, 0.0),
            "polynomial": (0.0, 0.0, 0.0), "time_scale": 1.0,
            "polynomial_fallback": True, "pearson_r": 0.0,
            "pearson_p_value": 1.0, "linear_r2": 0.0,
            "polynomial_r2": 0.0, "linear_estimator": None,
            "polynomial_estimator": None, "poly_transformer": None,
        }

    first_date = floor_day(training[0][0])
    xs = np.asarray(
        [(floor_day(date) - first_date).days for date, _ in training],
        dtype=float,
    ).reshape(-1, 1)
    ys = np.asarray([float(value or 0.0) for _, value in training], dtype=float)
    n = len(ys)

    linear_estimator = LinearRegression().fit(xs, ys)
    linear_fit = linear_estimator.predict(xs)
    linear_r2 = float(r2_score(ys, linear_fit)) if n >= 2 else 0.0

    # Pearson correlation is undefined for constant X or Y. Keep forecasting
    # operational and expose a neutral diagnostic value for those cases.
    if n >= 2 and np.std(xs.ravel()) > 0 and np.std(ys) > 0:
        pearson_r, pearson_p = pearsonr(xs.ravel(), ys)
        pearson_r, pearson_p = float(pearson_r), float(pearson_p)
    else:
        pearson_r, pearson_p = 0.0, 1.0

    poly_transformer = PolynomialFeatures(degree=2)
    polynomial_fallback = n < 3 or len(np.unique(xs)) < 3
    if not polynomial_fallback:
        xs_poly = poly_transformer.fit_transform(xs)
        polynomial_estimator = LinearRegression().fit(xs_poly, ys)
        polynomial_fit = polynomial_estimator.predict(xs_poly)
        polynomial_r2 = float(r2_score(ys, polynomial_fit))
        # Coefficients are ordered as x², x, constant for compatibility with
        # the existing Odoo debug payload.
        polynomial_coefficients = (
            float(polynomial_estimator.coef_[2]),
            float(polynomial_estimator.coef_[1]),
            float(polynomial_estimator.intercept_),
        )
    else:
        # With fewer than three distinct dates, use the linear fit as a safe
        # fallback instead of trying to fit an underdetermined quadratic.
        polynomial_estimator = linear_estimator
        polynomial_r2 = linear_r2
        polynomial_coefficients = (
            0.0, float(linear_estimator.coef_[0]),
            float(linear_estimator.intercept_),
        )

    return {
        "first_date": first_date,
        "count": n,
        "linear": (float(linear_estimator.coef_[0]), float(linear_estimator.intercept_)),
        "polynomial": polynomial_coefficients,
        "time_scale": 1.0,
        "polynomial_fallback": polynomial_fallback,
        "pearson_r": pearson_r,
        "pearson_p_value": pearson_p,
        "linear_r2": linear_r2,
        "polynomial_r2": polynomial_r2,
        "linear_estimator": linear_estimator,
        "polynomial_estimator": polynomial_estimator,
        "poly_transformer": poly_transformer,
    }


def _predict_day(model, date):
    """Return non-negative scikit-learn linear and quadratic predictions."""
    if not model.get("first_date"):
        return 0.0, 0.0
    x = float((floor_day(date) - model["first_date"]).days)
    x_input = np.asarray([[x]], dtype=float)
    linear_estimator = model.get("linear_estimator")
    polynomial_estimator = model.get("polynomial_estimator")
    transformer = model.get("poly_transformer")
    if linear_estimator is not None:
        linear_value = float(linear_estimator.predict(x_input)[0])
    else:
        slope, intercept = model["linear"]
        linear_value = slope * x + intercept
    if polynomial_estimator is not None and transformer is not None and not model.get("polynomial_fallback"):
        polynomial_value = float(
            polynomial_estimator.predict(transformer.transform(x_input))[0]
        )
    else:
        a, b, c = model["polynomial"]
        polynomial_value = a * x * x + b * x + c
    return max(0.0, linear_value), max(0.0, polynomial_value)


def _forecast_month_points(daily, future_dates, as_of=None):
    """Aggregate daily linear/quadratic predictions into calendar months."""
    if not future_dates:
        return [], [], {}
    cutoff = floor_day(as_of) if as_of is not None else max(date for date, _ in (daily or []))
    training = _training_daily(daily, cutoff)
    model = _fit_regression_models(training)
    linear_points, polynomial_points = [], []
    for month in future_dates:
        days = monthrange(month.year, month.month)[1]
        linear_total = polynomial_total = 0.0
        for offset in range(days):
            date = month + timedelta(days=offset)
            linear_value, polynomial_value = _predict_day(model, date)
            linear_total += linear_value
            polynomial_total += polynomial_value
        linear_points.append({"date": month, "revenue": linear_total})
        polynomial_points.append({"date": month, "revenue": polynomial_total})
    return linear_points, polynomial_points, model


def _cumulative_daily_rate(daily, end_date=None):
    """Return cumulative average revenue/day from the first historical
    month's first calendar day through end_date.

    The denominator is the number of calendar days in the complete historical
    calendar period, not the number of sales rows and not a fixed lookback
    window.
    """
    if not daily:
        return 0.0, 0, 0.0

    normalized = sorted(
        (floor_day(date), float(value or 0.0))
        for date, value in daily
    )
    # Start from the first calendar day of the first historical month.
    # This makes the denominator represent the complete calendar period
    # (for example, March 1 -> September 22), even when the first sale
    # happened after the first day of that month.
    first_date = floor_month(normalized[0][0])
    end_date = floor_day(end_date) if end_date is not None else normalized[-1][0]

    if end_date < first_date:
        return 0.0, 0, 0.0

    total_revenue = sum(value for date, value in normalized if date <= end_date)
    total_days = (end_date - first_date).days + 1
    daily_rate = total_revenue / total_days if total_days else 0.0
    return daily_rate, total_days, total_revenue


def _monthly_cumulative_daily_rate(monthly, as_of=None):
    """Calculate the forecast rate from the same monthly revenue series
    displayed by the forecast chart.

    The historical revenue is the sum of complete monthly actual values from
    the first historical month through the current month.  The denominator is
    the calendar-day span from the first historical month's day 1 through the
    calculation date.  This intentionally matches the manual/dashboard
    calculation: total historical monthly revenue / elapsed calendar days.
    """
    if not monthly:
        return 0.0, 0, 0.0

    normalized = sorted(
        (floor_month(date), float(value or 0.0))
        for date, value in monthly
    )
    first_month = normalized[0][0]
    end_date = floor_day(as_of) if as_of is not None else normalized[-1][0]

    # Use complete monthly actual values up to the calculation month.  This
    # keeps the forecast input identical to the monthly actual values shown
    # in the chart instead of allowing daily-row differences to change the
    # forecast rate.
    current_month = floor_month(end_date)
    total_revenue = sum(value for month, value in normalized if month <= current_month)
    total_days = (end_date - first_month).days + 1
    daily_rate = total_revenue / total_days if total_days else 0.0
    return daily_rate, total_days, total_revenue


def _monthly_forecast_points(daily, monthly, future_dates, as_of=None):
    linear_points, polynomial_points, model = _forecast_month_points(
        daily, future_dates, as_of=as_of
    )
    training = _training_daily(daily, as_of or max(date for date, _ in daily)) if daily else []
    total_revenue = sum(value for _, value in training)
    historical_days = len(training)
    daily_rate = total_revenue / historical_days if historical_days else 0.0
    return linear_points, polynomial_points, daily_rate, historical_days, total_revenue, model


def calculate_monthly_forecast(key, daily, monthly, daily_orders=None, monthly_orders=None, now=None):
    """Return the original cumulative-run-rate forecast plus regression comparisons."""
    now = now or datetime.now()
    steps, frequency = horizon_steps(key)
    assert frequency == "month"

    current_day = floor_day(now)
    current_month = floor_month(now)
    real_months = sorted((date, float(value or 0.0)) for date, value in (monthly or []))
    last_real_month = real_months[-1][0] if real_months else None
    next_month = add_months(current_month, 1)
    forecast_start = next_month if last_real_month is None else max(
        next_month, add_months(last_real_month, 1)
    )
    future_dates = [add_months(forecast_start, i) for i in range(steps)]

    # Original forecast: cumulative historical revenue / elapsed calendar days,
    # multiplied by the number of calendar days in each future month.
    daily_rate, historical_days, historical_revenue = _monthly_cumulative_daily_rate(
        monthly, current_day
    )
    forecast_points = [
        {"date": month, "revenue": max(0.0, daily_rate * monthrange(month.year, month.month)[1])}
        for month in future_dates
    ]

    # Regression forecasts are additional comparison series, not replacements
    # for the original Forecast Revenue series.
    linear_points, polynomial_points, _reg_rate, reg_days, reg_revenue, model = _monthly_forecast_points(
        daily, monthly, future_dates, as_of=current_day
    )
    actual_points = [
        {"date": date, "revenue": max(0.0, revenue)}
        for date, revenue in real_months[-36:]
        if revenue != 0.0
    ]

    forecast_revenue = sum(point["revenue"] for point in forecast_points)
    linear_forecast_revenue = sum(point["revenue"] for point in linear_points)
    polynomial_forecast_revenue = sum(point["revenue"] for point in polynomial_points)
    baseline = daily_rate * AVG_DAYS_PER_MONTH
    comparable_baseline = baseline * steps
    growth = (((forecast_revenue - comparable_baseline) / comparable_baseline * 100.0)
              if comparable_baseline else 0.0)

    return {
        "current_revenue": max(0.0, comparable_baseline),
        "forecast_revenue": max(0.0, forecast_revenue),
        "linear_forecast_revenue": max(0.0, linear_forecast_revenue),
        "polynomial_forecast_revenue": max(0.0, polynomial_forecast_revenue),
        "growth_pct": growth,
        "confidence": 50.0,
        "actual_points": actual_points,
        "forecast_points": forecast_points,
        "linear_forecast_points": linear_points,
        "polynomial_forecast_points": polynomial_points,
        "debug": {
            "method": "cumulative_daily_run_rate_plus_linear_and_degree_2_polynomial_regression",
            "historical_revenue": historical_revenue,
            "historical_days": historical_days,
            "average_daily_revenue": daily_rate,
            "as_of": current_day,
            "future_original_forecast": forecast_points,
            "future_linear": linear_points,
            "future_polynomial": polynomial_points,
            "slope_per_day": model["linear"][0],
            "intercept": model["linear"][1],
            "pearson_r": model["pearson_r"],
            "pearson_p_value": model["pearson_p_value"],
            "linear_r2": model["linear_r2"],
            "polynomial_r2": model["polynomial_r2"],
            "polynomial_coefficients_scaled_time": model["polynomial"],
            "polynomial_time_scale_days": model["time_scale"],
            "polynomial_fallback_to_linear": model["polynomial_fallback"],
        },
    }


def calculate_historical_forecast(daily, monthly, now=None, max_months=36):
    """Build cumulative-run-rate and regression back-tests without target-month leakage."""
    now = now or datetime.now()
    current_month = floor_month(now)
    real_months = sorted((date, float(value or 0.0)) for date, value in (monthly or []))
    historical_months = [(date, value) for date, value in real_months if date < current_month][-max_months:]
    daily_sorted = sorted(daily or [], key=lambda item: item[0])
    if historical_months:
        target_months = list(historical_months)
        if target_months[-1][0] < current_month:
            target_months.append((current_month, 0.0))
    elif daily_sorted:
        target_months = [(current_month, 0.0)]
    else:
        target_months = []

    forecast_points, linear_forecast_points, polynomial_forecast_points, debug_windows = [], [], [], []
    for target_month, _actual_value in target_months:
        cutoff_day = target_month - timedelta(days=1)
        prior_months = [(date, value) for date, value in real_months if date < target_month]
        daily_rate, baseline_days, baseline_revenue = _monthly_cumulative_daily_rate(prior_months, cutoff_day)
        if baseline_days > 0:
            days = monthrange(target_month.year, target_month.month)[1]
            forecast_points.append({"date": target_month, "revenue": max(0.0, daily_rate * days)})

        training = _training_daily(daily_sorted, cutoff_day)
        if len(training) < 2:
            continue
        model = _fit_regression_models(training)
        days = monthrange(target_month.year, target_month.month)[1]
        linear_total = polynomial_total = 0.0
        for offset in range(days):
            linear_value, polynomial_value = _predict_day(model, target_month + timedelta(days=offset))
            linear_total += linear_value
            polynomial_total += polynomial_value
        linear_forecast_points.append({"date": target_month, "revenue": linear_total})
        polynomial_forecast_points.append({"date": target_month, "revenue": polynomial_total})
        debug_windows.append({
            "target_month": target_month,
            "baseline_historical_revenue": baseline_revenue,
            "baseline_historical_days": baseline_days,
            "baseline_average_daily_revenue": daily_rate,
            "training_days": model["count"],
            "slope_per_day": model["linear"][0],
            "intercept": model["linear"][1],
            "pearson_r": model["pearson_r"],
            "pearson_p_value": model["pearson_p_value"],
            "linear_r2": model["linear_r2"],
            "polynomial_r2": model["polynomial_r2"],
            "polynomial_coefficients_scaled_time": model["polynomial"],
            "polynomial_fallback_to_linear": model["polynomial_fallback"],
        })

    actual_points = [
        {"date": date, "revenue": max(0.0, revenue)}
        for date, revenue in real_months[-max_months:] if revenue != 0.0
    ]
    return {
        "current_revenue": 0.0,
        "forecast_revenue": 0.0,
        "linear_forecast_revenue": 0.0,
        "polynomial_forecast_revenue": 0.0,
        "growth_pct": 0.0,
        "confidence": 50.0,
        "actual_points": actual_points,
        "forecast_points": forecast_points,
        "linear_forecast_points": linear_forecast_points,
        "polynomial_forecast_points": polynomial_forecast_points,
        "debug": {
            "method": "historical_cumulative_daily_run_rate_plus_regression_backtest",
            "historical_forecast": forecast_points,
            "historical_linear_forecast": linear_forecast_points,
            "historical_polynomial_forecast": polynomial_forecast_points,
            "windows": debug_windows,
        },
    }


def calculate_daily_forecast(key, daily, now=None):
    now = now or datetime.now()
    steps, frequency = horizon_steps(key)
    assert frequency == "day"
    today = floor_day(now)
    daily_rate, historical_days, historical_revenue = _cumulative_daily_rate(daily, today)
    training = _training_daily(daily, today)
    model = _fit_regression_models(training)
    future_dates = [today + timedelta(days=i) for i in range(1, steps + 1)]
    forecast_points = [{"date": date, "revenue": max(0.0, daily_rate)} for date in future_dates]
    linear_forecast_points, polynomial_forecast_points = [], []
    for date in future_dates:
        linear_value, polynomial_value = _predict_day(model, date)
        linear_forecast_points.append({"date": date, "revenue": linear_value})
        polynomial_forecast_points.append({"date": date, "revenue": polynomial_value})
    actual_points = [
        {"date": date, "revenue": max(0.0, float(value or 0.0))}
        for date, value in list(daily or [])[-365:]
    ]
    total = sum(point["revenue"] for point in forecast_points)
    linear_total = sum(point["revenue"] for point in linear_forecast_points)
    polynomial_total = sum(point["revenue"] for point in polynomial_forecast_points)
    return {
        "current_revenue": total,
        "forecast_revenue": total,
        "linear_forecast_revenue": linear_total,
        "polynomial_forecast_revenue": polynomial_total,
        "growth_pct": 0.0,
        "confidence": 50.0,
        "actual_points": actual_points,
        "forecast_points": forecast_points,
        "linear_forecast_points": linear_forecast_points,
        "polynomial_forecast_points": polynomial_forecast_points,
        "debug": {
            "method": "cumulative_daily_run_rate_plus_linear_and_degree_2_polynomial_regression",
            "historical_revenue": historical_revenue,
            "historical_days": historical_days,
            "average_daily_revenue": daily_rate,
            "training_days": model.get("count", 0),
            "slope_per_day": model["linear"][0],
            "intercept": model["linear"][1],
            "pearson_r": model["pearson_r"],
            "pearson_p_value": model["pearson_p_value"],
            "linear_r2": model["linear_r2"],
            "polynomial_r2": model["polynomial_r2"],
            "polynomial_coefficients_scaled_time": model["polynomial"],
            "polynomial_time_scale_days": model["time_scale"],
            "polynomial_fallback_to_linear": model["polynomial_fallback"],
            "future_original_forecast": forecast_points,
            "future_linear": linear_forecast_points,
            "future_polynomial": polynomial_forecast_points,
        },
    }


# ============================================================================
# 3. EXPONENTIAL SMOOTHING
# ============================================================================

def _fit_exponential_smoothing(values):
    """Fit the dashboard's exponential-smoothing model robustly.

    The training series is daily sales with many zero-sales days and
    occasional large order spikes.  A manually fixed damped trend can
    collapse toward zero when the last part of the training series is quiet;
    that was the reason the validation chart showed an ES prediction of zero
    for almost the entire test period.

    Use the standard additive Holt/Exponential-Smoothing model with parameters
    estimated from the training data.  It remains an exponential-smoothing
    model, but lets statsmodels estimate the level/trend instead of forcing a
    damping configuration that can decay to zero.  If the optimized fit is
    unavailable, fall back to simple exponential smoothing so the dashboard
    never silently produces an all-zero ES series.
    """
    clean = [max(0.0, float(v or 0.0)) for v in values]
    if len(clean) < 2:
        return None

    values_array = np.asarray(clean, dtype=float)
    try:
        return ExponentialSmoothing(
            values_array,
            trend="add",
            damped_trend=False,
            seasonal=None,
            initialization_method="estimated",
        ).fit(
            optimized=True,
            remove_bias=False,
        )
    except (ValueError, RuntimeError, np.linalg.LinAlgError):
        try:
            return SimpleExpSmoothing(
                values_array,
                initialization_method="estimated",
            ).fit(optimized=True)
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            return None


def _fit_exponential_smoothing_future(values):
    """Fit the future-forecast-only ES model with a damped trend.

    This is intentionally separate from _fit_exponential_smoothing(), which
    is used by the Training & Testing back-test and must remain unchanged.
    A damped Holt trend prevents the Overall Sales Forecast from extending
    the learned trend as an indefinitely straight line.
    """
    clean = [max(0.0, float(v or 0.0)) for v in values]
    if len(clean) < 2:
        return None
    values_array = np.asarray(clean, dtype=float)
    try:
        return ExponentialSmoothing(
            values_array,
            trend="add",
            damped_trend=True,
            seasonal=None,
            initialization_method="estimated",
        ).fit(optimized=True, remove_bias=False)
    except (ValueError, RuntimeError, np.linalg.LinAlgError):
        try:
            return SimpleExpSmoothing(
                values_array,
                initialization_method="estimated",
            ).fit(optimized=True)
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            return None


def _normalized_monthly_series(monthly, current_month=None, max_months=36):
    """Return exactly one confirmed-revenue value per calendar month.

    ES must be fitted to monthly revenue, not to the individual order rows or
    to a daily zero-filled representation.  Aggregate duplicate month keys
    here so the model always receives the intended monthly sales series.
    """
    buckets = {}
    for date, value in (monthly or []):
        if date is None:
            continue
        month = floor_month(date)
        if current_month is not None and month >= current_month:
            continue
        buckets[month] = buckets.get(month, 0.0) + max(0.0, float(value or 0.0))
    return sorted(buckets.items())[-max_months:]


def calculate_exponential_smoothing_forecast(
    daily, monthly, key, now=None, max_historical_months=36
):
    """Return one-step historical ES forecasts plus future ES values.

    The historical series is back-tested month by month: each point is
    predicted using only months before that point. Future values are produced
    from the completed monthly history. For 7 Days, the daily history is used
    and seven daily predictions are returned.
    """
    now = now or datetime.now()
    current_day = floor_day(now)
    current_month = floor_month(current_day)
    real_months = _normalized_monthly_series(
        monthly, current_month=current_month, max_months=max_historical_months
    )

    # The ML chart is intentionally a SINGLE visible Exponential Smoothing
    # series.  For completed months, show the model's fitted/smoothed values
    # rather than the raw Revenue values.  This means March is also an
    # Exponential Smoothing value instead of an Actual Revenue value.  The
    # current month is forecast as the first future point (October in the
    # current dataset), so the 1 Month filter shows October rather than
    # skipping to November.

    if key == "7_days":
        daily_history = sorted(
            (floor_day(date), max(0.0, float(value or 0.0)))
            for date, value in (daily or [])
            if date is not None and floor_day(date) <= current_day
        )
        model = _fit_exponential_smoothing(
            [value for _, value in fill_daily(daily_history)]
        )
        steps = 7
        future_dates = [current_day + timedelta(days=i) for i in range(1, steps + 1)]
    else:
        steps, _frequency = horizon_steps(key)
        model = _fit_exponential_smoothing_future([value for _, value in real_months])
        # Keep the ES chart aligned with the existing Overall Sales Forecast
        # horizon semantics. The current month (October in the current data)
        # is the first forecast point, and longer selectable horizons then
        # extend by the full selected number of months. Thus 6 Months shows
        # October through April (7 plotted months including the current-month
        # forecast), matching the existing forecast chart's endpoint.
        # For 1 Month, preserve the requested October forecast as the first
        # point and add the one selected future month after it.
        future_count = steps + 1
        future_dates = [add_months(current_month, i) for i in range(future_count)]

    if model is None:
        return {
            "historical_forecast_points": [],
            "forecast_points": [],
        }

    if key == "7_days":
        # Keep the existing daily behaviour for the 7 Days filter.
        historical_forecast_points = []
        prediction_values = model.forecast(steps)
    else:
        # Use the fitted values from the Holt exponential-smoothing model for
        # every completed month.  This gives the ML chart a true ES series
        # from March onward instead of plotting raw revenue as if it were ES.
        fitted_values = list(model.fittedvalues)
        historical_forecast_points = [
            {"date": date, "revenue": max(0.0, float(value))}
            for (date, _actual), value in zip(real_months, fitted_values)
        ]
        prediction_values = model.forecast(future_count)

    future_forecast_points = [
        {"date": date, "revenue": max(0.0, float(value))}
        for date, value in zip(future_dates, prediction_values)
    ]
    return {
        "historical_forecast_points": historical_forecast_points,
        "forecast_points": future_forecast_points,
    }


# ============================================================================
# 4. ARIMA
# ============================================================================

def _safe_nonnegative(value):
    """Return a finite, non-negative revenue value for dashboard output."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(number):
        return 0.0
    return max(0.0, number)


def _fit_arima(values, order=ARIMA_ORDER):
    """Fit a robust ARIMA model while preferring the requested order.

    The default is ARIMA(1,1,1). With very short or strongly trending sales
    histories, statsmodels can fail to converge for that exact order. In that
    case we try nearby valid ARIMA(0,1,1), ARIMA(1,1,0), and ARIMA(0,1,0)
    alternatives and choose the lowest-AIC model among converged fits. This
    keeps the dashboard stable without replacing Exponential Smoothing or
    silently returning bad values.
    """
    clean = [_safe_nonnegative(value) for value in values]
    if len(clean) < ARIMA_MIN_OBSERVATIONS:
        return None

    candidates = []
    for candidate_order in (order, (0, 1, 1), (1, 1, 0), (0, 1, 0)):
        if candidate_order in [item[0] for item in candidates]:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ConvergenceWarning)
                warnings.simplefilter("ignore", UserWarning)
                model = ARIMA(
                    np.asarray(clean, dtype=float),
                    order=candidate_order,
                    trend=None,
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                ).fit()
            converged = bool(model.mle_retvals.get("converged", True))
            if converged and np.isfinite(model.aic):
                candidates.append((candidate_order, model))
        except (ValueError, np.linalg.LinAlgError, RuntimeError):
            continue

    if not candidates:
        return None

    _selected_order, selected_model = min(candidates, key=lambda item: item[1].aic)
    selected_model._dashboard_arima_order = _selected_order
    return selected_model


def calculate_arima_forecast(
    daily, monthly, key, now=None, max_historical_months=36, order=ARIMA_ORDER
):
    """Return ARIMA fitted values plus future ARIMA predictions.

    Monthly horizons use one confirmed-revenue value per completed calendar
    month.  The current month is excluded from training, exactly like the
    existing Exponential Smoothing implementation.  The current month is then
    plotted as the first future point so the ARIMA curve stays aligned with the
    existing ML chart/filter semantics (1 Month => current month + one selected
    future month; 6 Months => current month + six selected future months).

    The 7 Days horizon uses a continuous daily history and returns seven daily
    ARIMA predictions.  ARIMA failures or insufficient history return an empty
    result rather than breaking the Sales dashboard.
    """
    now = now or datetime.now()
    current_day = floor_day(now)
    current_month = floor_month(current_day)
    real_months = _normalized_monthly_series(
        monthly, current_month=current_month, max_months=max_historical_months
    )

    if key == "7_days":
        daily_history = sorted(
            (floor_day(date), _safe_nonnegative(value))
            for date, value in (daily or [])
            if date is not None and floor_day(date) <= current_day
        )
        daily_series = fill_daily(daily_history)
        model = _fit_arima([value for _, value in daily_series], order=order)
        steps = 7
        future_dates = [
            current_day + timedelta(days=i) for i in range(1, steps + 1)
        ]
        if model is None:
            return {
                "historical_forecast_points": [],
                "forecast_points": [],
                "debug": {
                    "method": "ARIMA",
                    "order": getattr(model, "_dashboard_arima_order", order),
                    "training_points": len(daily_series),
                    "available": False,
                },
            }
        try:
            prediction_values = model.forecast(steps=steps)
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            return {
                "historical_forecast_points": [],
                "forecast_points": [],
                "debug": {
                    "method": "ARIMA",
                    "order": getattr(model, "_dashboard_arima_order", order),
                    "training_points": len(daily_series),
                    "available": False,
                },
            }
        future_forecast_points = [
            {"date": date, "revenue": _safe_nonnegative(value)}
            for date, value in zip(future_dates, prediction_values)
        ]
        return {
            "historical_forecast_points": [],
            "forecast_points": future_forecast_points,
            "debug": {
                "method": "ARIMA",
                "order": getattr(model, "_dashboard_arima_order", order),
                "training_points": len(daily_series),
                "available": True,
                "aic": float(model.aic) if np.isfinite(model.aic) else None,
            },
        }

    steps, _frequency = horizon_steps(key)
    values = [value for _, value in real_months]
    model = _fit_arima(values, order=order)
    future_count = steps + 1
    future_dates = [
        add_months(current_month, i) for i in range(future_count)
    ]

    if model is None:
        return {
            "historical_forecast_points": [],
            "forecast_points": [],
            "debug": {
                "method": "ARIMA",
                "order": getattr(model, "_dashboard_arima_order", order),
                "training_points": len(values),
                "available": False,
            },
        }

    try:
        fitted_values = list(model.fittedvalues)
        prediction_values = model.forecast(steps=future_count)
    except (ValueError, RuntimeError, np.linalg.LinAlgError):
        return {
            "historical_forecast_points": [],
            "forecast_points": [],
            "debug": {
                "method": "ARIMA",
                "order": getattr(model, "_dashboard_arima_order", order),
                "training_points": len(values),
                "available": False,
            },
        }

    # ARIMA(1,1,1) has an initialization value for its first fitted point that
    # can be zero even when the first month's actual revenue is non-zero. Do
    # not create a misleading drop to zero in the dashboard line; use the
    # first observed value only for that initialization point. All subsequent
    # historical values remain the model's fitted ARIMA values.
    historical_forecast_points = []
    for index, ((date, actual), fitted) in enumerate(zip(real_months, fitted_values)):
        revenue = _safe_nonnegative(fitted)
        if index == 0 and revenue == 0.0 and _safe_nonnegative(actual) > 0.0:
            revenue = _safe_nonnegative(actual)
        historical_forecast_points.append({
            "date": date,
            "revenue": revenue,
        })

    future_forecast_points = [
        {"date": date, "revenue": _safe_nonnegative(value)}
        for date, value in zip(future_dates, prediction_values)
    ]
    return {
        "historical_forecast_points": historical_forecast_points,
        "forecast_points": future_forecast_points,
        "debug": {
            "method": "ARIMA",
            "order": getattr(model, "_dashboard_arima_order", order),
            "training_points": len(values),
            "available": True,
            "aic": float(model.aic) if np.isfinite(model.aic) else None,
        },
    }


# ============================================================================
# 5. TRAINING AND TESTING
# ============================================================================

def _forecast_error_metrics(actual, predicted):
    """Return MAE, RMSE and MAPE for a historical hold-out period.

    MAPE intentionally ignores zero-actual days because percentage error is
    undefined when actual revenue is zero.  MAE and RMSE still include those
    days, so quiet days are not silently removed from the main error measures.
    """
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if actual.size == 0:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0}

    errors = actual - predicted
    absolute = np.abs(errors)
    mae = float(np.mean(absolute))
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    non_zero = np.abs(actual) > 1e-12
    if np.any(non_zero):
        mape = float(np.mean(absolute[non_zero] / np.abs(actual[non_zero])) * 100.0)
    else:
        mape = 0.0
    return {"mae": mae, "rmse": rmse, "mape": mape}


def calculate_training_testing(daily, train_ratio=0.80, now=None):
    """Back-test ARIMA and Exponential Smoothing on chronological daily data.

    The last 20% of the continuous historical calendar is held out as unseen
    test data.  Both models are fitted only on the first 80%, then asked to
    forecast the complete hold-out window.  No future/test observations leak
    into either model fit.

    The returned payload is intentionally UI-friendly: it contains the full
    actual history for the chart, predicted values only for the test period,
    split metadata, model metrics, and the best model by MAPE (RMSE breaks a
    tie).  The function is independent of Odoo so it can be unit-tested with
    the same CSV-derived daily series used during development.
    """
    del now  # The validation window is based only on available historical data.
    continuous = fill_daily(sorted(daily or [], key=lambda item: item[0]))
    n = len(continuous)
    if n < 8:
        return {
            "available": False,
            "training_points": [],
            "testing_points": [],
            "metrics": [],
            "best_model": None,
            "training_count": n,
            "testing_count": 0,
            "training_percentage": 100.0,
            "testing_percentage": 0.0,
            "training_start": continuous[0][0] if continuous else None,
            "training_end": continuous[-1][0] if continuous else None,
            "testing_start": None,
            "testing_end": None,
        }

    ratio = min(max(float(train_ratio), 0.50), 0.95)
    split_index = int(n * ratio)
    split_index = min(max(split_index, 4), n - 1)
    training = continuous[:split_index]
    testing = continuous[split_index:]
    train_values = np.asarray([float(value or 0.0) for _, value in training], dtype=float)
    test_values = np.asarray([float(value or 0.0) for _, value in testing], dtype=float)

    # ARIMA: reuse the same robust candidate-selection logic as the dashboard
    # forecast. It prefers ARIMA(1,1,1) but falls back to nearby orders by AIC.
    arima_model = _fit_arima(train_values, order=ARIMA_ORDER)
    if arima_model is not None:
        try:
            arima_pred = np.maximum(
                0.0, np.asarray(arima_model.forecast(steps=len(testing)), dtype=float)
            )
            arima_available = True
            arima_order = getattr(arima_model, "_dashboard_arima_order", ARIMA_ORDER)
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            arima_pred = np.zeros(len(testing), dtype=float)
            arima_available = False
            arima_order = ARIMA_ORDER
    else:
        arima_pred = np.zeros(len(testing), dtype=float)
        arima_available = False
        arima_order = ARIMA_ORDER

    # Exponential Smoothing: use the same optimized additive Holt model as
    # the live dashboard forecast. This avoids the old fixed damped-trend
    # configuration collapsing the validation forecast toward zero.
    es_model = _fit_exponential_smoothing(train_values)
    if es_model is not None:
        try:
            es_pred = np.maximum(
                0.0, np.asarray(es_model.forecast(len(testing)), dtype=float)
            )
            es_available = True
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            es_pred = np.zeros(len(testing), dtype=float)
            es_available = False
    else:
        es_pred = np.zeros(len(testing), dtype=float)
        es_available = False

    metrics_by_name = []
    if arima_available:
        arima_metrics = _forecast_error_metrics(test_values, arima_pred)
        metrics_by_name.append({
            "model": "ARIMA",
            **arima_metrics,
            "order": tuple(arima_order),
            "available": True,
        })
    if es_available:
        es_metrics = _forecast_error_metrics(test_values, es_pred)
        metrics_by_name.append({
            "model": "Exponential Smoothing",
            **es_metrics,
            "order": None,
            "available": True,
        })

    ranked = sorted(
        metrics_by_name,
        key=lambda item: (item["mape"], item["rmse"]),
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank

    # In-sample fitted values are returned for the training period so the
    # dashboard can show the COMPLETE historical series instead of drawing
    # misleading zero-value model lines before the test window.  These fitted
    # values are for visualization only; MAE/RMSE/MAPE below are calculated
    # exclusively from the unseen testing period.
    arima_fitted = None
    if arima_available:
        try:
            arima_fitted = np.asarray(arima_model.fittedvalues, dtype=float)
        except (AttributeError, ValueError, TypeError):
            arima_fitted = None
        if arima_fitted is not None and len(arima_fitted) != len(training):
            arima_fitted = None

    es_fitted = None
    if es_available:
        try:
            es_fitted = np.asarray(es_model.fittedvalues, dtype=float)
        except (AttributeError, ValueError, TypeError):
            es_fitted = None
        if es_fitted is not None and len(es_fitted) != len(training):
            es_fitted = None

    training_points = []
    for index, (date, value) in enumerate(training):
        arima_value = None
        if arima_fitted is not None and np.isfinite(arima_fitted[index]):
            arima_value = _safe_nonnegative(arima_fitted[index])
        es_value = None
        if es_fitted is not None and np.isfinite(es_fitted[index]):
            es_value = _safe_nonnegative(es_fitted[index])
        training_points.append({
            "date": date,
            "revenue": _safe_nonnegative(value),
            "arima_fitted": arima_value,
            "exponential_smoothing_fitted": es_value,
        })

    test_points = []
    for index, (date, actual) in enumerate(testing):
        test_points.append({
            "date": date,
            "actual": _safe_nonnegative(actual),
            "arima_predicted": _safe_nonnegative(arima_pred[index]) if arima_available else None,
            "exponential_smoothing_predicted": _safe_nonnegative(es_pred[index]) if es_available else None,
        })

    return {
        "available": bool(metrics_by_name),
        "training_points": training_points,
        "actual_points": [
            {"date": date, "revenue": _safe_nonnegative(value)}
            for date, value in continuous
        ],
        "testing_points": test_points,
        "metrics": ranked,
        "best_model": ranked[0]["model"] if ranked else None,
        "training_count": len(training),
        "testing_count": len(testing),
        # Display the configured train/test split ratio (80% / 20%) rather
        # than percentages recalculated from whole-day counts. Because days
        # are indivisible, a 48-day series becomes 38 training days and 10
        # testing days (79.17% / 20.83%), even though the intended split is
        # 80% / 20%.
        "training_percentage": float(ratio * 100.0),
        "testing_percentage": float((1.0 - ratio) * 100.0),
        "training_start": training[0][0],
        "training_end": training[-1][0],
        "testing_start": testing[0][0],
        "testing_end": testing[-1][0],
        "arima_order": tuple(arima_order),
        "arima_available": arima_available,
        "exponential_smoothing_available": es_available,
    }


# ============================================================================
# Shared dashboard payload helpers
# ============================================================================

def calculate_horizon(key, daily, monthly, daily_orders=None, monthly_orders=None, now=None):
    _steps, frequency = horizon_steps(key)
    if frequency == "day":
        return calculate_daily_forecast(key, daily, now=now)
    return calculate_monthly_forecast(key, daily, monthly, now=now)


def summary_values(horizon, company_id, owner_id, generated_at,
                    current_revenue, forecast_revenue, growth_pct, confidence):
    """Build one ``sale.forecast.summary`` row for a future horizon.

    Mirrors ``point_values``: ``forecast_horizon`` is the internal storage
    bucket and ``forecast_period`` is the same value, since this is only
    ever called for the user-facing future horizons (never the internal
    ``historical`` bucket).
    """
    return {
        "forecast_horizon": horizon,
        "forecast_period": horizon,
        "company_id": company_id,
        "owner_id": owner_id,
        "generated_at": generated_at,
        "current_revenue": current_revenue,
        "forecast_revenue": forecast_revenue,
        "growth_pct": growth_pct,
        "confidence": confidence,
    }


def point_values(horizon, company_id, owner_id, actual_points, forecast_points,
                 polynomial_forecast_points=None, linear_forecast_points=None):
    """Build ORM rows for actual, original, linear, and polynomial forecast series."""
    rows = []
    for point in actual_points or []:
        rows.append({
            "date": point["date"], "revenue": point["revenue"], "series": "actual",
            "forecast_horizon": horizon, "forecast_period": horizon,
            "company_id": company_id, "owner_id": owner_id,
        })
    for point in forecast_points or []:
        rows.append({
            "date": point["date"], "revenue": point["revenue"], "series": "forecast",
            "forecast_horizon": horizon, "forecast_period": horizon,
            "company_id": company_id, "owner_id": owner_id,
        })
    for point in linear_forecast_points or []:
        rows.append({
            "date": point["date"], "revenue": point["revenue"], "series": "linear_forecast",
            "forecast_horizon": horizon, "forecast_period": horizon,
            "company_id": company_id, "owner_id": owner_id,
        })
    for point in polynomial_forecast_points or []:
        rows.append({
            "date": point["date"], "revenue": point["revenue"], "series": "polynomial_forecast",
            "forecast_horizon": horizon, "forecast_period": horizon,
            "company_id": company_id, "owner_id": owner_id,
        })
    return rows


