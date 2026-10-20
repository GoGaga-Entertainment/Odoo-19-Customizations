# -*- coding: utf-8 -*-
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "models"))
import forecast_engine as engine


def month(y, m, d=1):
    return datetime(y, m, d)


class ForecastEngineTests(unittest.TestCase):
    def rich_history(self):
        monthly = []
        daily = []
        for m, orders in zip(range(1, 9), [40, 42, 45, 44, 48, 50, 53, 55]):
            dt = month(2026, m)
            monthly.append((dt, orders * 500.0))
            daily.append((dt, orders * 500.0))
        return daily, monthly


    def test_future_rate_uses_all_history_through_present_not_fixed_60_days(self):
        daily = [
            (datetime(2026, 1, 1), 1000.0),
            (datetime(2026, 2, 1), 2000.0),
            (datetime(2026, 3, 1), 3000.0),
        ]
        # The calendar period is Jan 1 through Mar 31 = 90 days.
        # Total revenue = 6000, so the cumulative daily rate is 6000/90.
        rate, days, revenue = engine._cumulative_daily_rate(
            daily, datetime(2026, 3, 31)
        )
        self.assertEqual(days, 90)
        self.assertEqual(revenue, 6000.0)
        self.assertAlmostEqual(rate, 6000.0 / 90.0)


    def test_cumulative_rate_starts_at_first_historical_month(self):
        daily = [
            (datetime(2026, 3, 14), 1000.0),
            (datetime(2026, 4, 10), 2000.0),
            (datetime(2026, 9, 22), 2900.0),
        ]
        rate, days, revenue = engine._cumulative_daily_rate(
            daily, datetime(2026, 9, 22)
        )
        # March 1 through September 22 is 206 calendar days.
        self.assertEqual(days, 206)
        self.assertEqual(revenue, 5900.0)
        self.assertAlmostEqual(rate, 5900.0 / 206.0)

    def test_monthly_forecast_uses_linear_regression_and_returns_polynomial(self):
        daily = [
            (datetime(2026, 1, 1), 1000.0),
            (datetime(2026, 2, 1), 2000.0),
            (datetime(2026, 3, 1), 3000.0),
        ]
        monthly = [(date.replace(day=1), value) for date, value in daily]
        result = engine.calculate_monthly_forecast(
            "1_month", daily, monthly, now=month(2026, 3, 31)
        )
        self.assertEqual(len(result["forecast_points"]), 1)
        self.assertEqual(len(result["polynomial_forecast_points"]), 1)
        self.assertEqual(len(result["linear_forecast_points"]), 1)
        self.assertIn("linear_and_degree_2_polynomial_regression", result["debug"]["method"])
        self.assertIn("slope_per_day", result["debug"])
        self.assertIn("intercept", result["debug"])
        self.assertAlmostEqual(
            result["forecast_revenue"],
            sum(point["revenue"] for point in result["forecast_points"]),
        )

    def test_forecast_returns_nonnegative_linear_and_polynomial_points(self):
        daily = [
            (datetime(2026, 1, 1), 1000.0),
            (datetime(2026, 1, 2), 1200.0),
            (datetime(2026, 1, 3), 1400.0),
        ]
        monthly = [(month(2026, 1), 3600.0)]
        result = engine.calculate_monthly_forecast(
            "1_month", daily, monthly, now=month(2026, 1, 3)
        )
        self.assertTrue(all(p["revenue"] >= 0 for p in result["forecast_points"]))
        self.assertTrue(all(p["revenue"] >= 0 for p in result["polynomial_forecast_points"]))
        self.assertEqual(
            result["forecast_revenue"],
            sum(p["revenue"] for p in result["forecast_points"]),
        )

    def test_linear_regression_slope_intercept_and_future_prediction(self):
        training = [
            (datetime(2026, 1, 1), 10.0),
            (datetime(2026, 1, 2), 20.0),
            (datetime(2026, 1, 3), 30.0),
        ]
        model = engine._fit_regression_models(training)
        self.assertAlmostEqual(model["linear"][0], 10.0)
        self.assertAlmostEqual(model["linear"][1], 10.0)
        linear, _poly = engine._predict_day(model, datetime(2026, 1, 4))
        self.assertAlmostEqual(linear, 40.0)

    def test_horizon_lengths(self):
        daily, monthly = self.rich_history()
        now = month(2026, 9, 15)
        for key, expected in (("1_month", 1), ("6_months", 6), ("1_year", 12)):
            result = engine.calculate_monthly_forecast(
                key, daily, monthly, now=now
            )
            self.assertEqual(len(result["forecast_points"]), expected)

    def test_historical_forecast_includes_current_month_without_leakage(self):
        daily, monthly = self.rich_history()
        result = engine.calculate_historical_forecast(
            daily, monthly, now=month(2026, 9, 15)
        )
        self.assertTrue(result["forecast_points"])
        self.assertTrue(result["forecast_points"])
        self.assertEqual(result["forecast_points"][-1]["date"], month(2026, 9))
        self.assertFalse(any(p["date"] > month(2026, 9) for p in result["forecast_points"]))
        self.assertEqual(result["actual_points"][-1]["date"], month(2026, 8))

    def test_current_month_forecast_is_not_zero_when_prior_history_exists(self):
        daily = [
            (datetime(2026, 7, 1), 3000.0),
            (datetime(2026, 8, 1), 6000.0),
        ]
        monthly = [
            (month(2026, 7), 3000.0),
            (month(2026, 8), 6000.0),
        ]
        result = engine.calculate_historical_forecast(
            daily, monthly, now=month(2026, 9, 22)
        )
        september = next(
            p for p in result["forecast_points"]
            if p["date"] == month(2026, 9)
        )
        self.assertGreater(september["revenue"], 0.0)

    def test_historical_forecast_does_not_leak_target_month(self):
        # May's forecast must use only data before May, not May's actual value.
        daily = [
            (datetime(2026, 3, 1), 100.0),
            (datetime(2026, 4, 1), 200.0),
            (datetime(2026, 5, 1), 10000.0),
        ]
        monthly = [
            (month(2026, 3), 100.0),
            (month(2026, 4), 200.0),
            (month(2026, 5), 10000.0),
        ]
        result = engine.calculate_historical_forecast(
            daily, monthly, now=month(2026, 6, 1)
        )
        may = next(p for p in result["forecast_points"] if p["date"] == month(2026, 5))
        # The 10,000 May value is not part of the May forecast input.
        self.assertLess(may["revenue"], 10000.0)

    def test_no_zero_bridge_and_no_none_series(self):
        monthly = [(month(2026, 8), 24000.0)]
        daily = [(datetime(2026, 8, d), 24000.0 / 31) for d in range(1, 32)]
        result = engine.calculate_monthly_forecast(
            "1_month", daily, monthly, now=month(2026, 9, 11)
        )
        self.assertEqual(result["actual_points"][-1]["date"], month(2026, 8))
        self.assertEqual(result["forecast_points"][0]["date"], month(2026, 10))
        rows = engine.point_values(
            "1_month", 1, 1, result["actual_points"], result["forecast_points"]
        )
        self.assertTrue(all(r["series"] in ("actual", "forecast", "linear_forecast", "polynomial_forecast") for r in rows))
        self.assertTrue(all(r["series"] is not None for r in rows))


    def test_future_horizon_can_share_historical_forecast_series(self):
        # The dashboard stores the historical back-test points inside every
        # selectable future horizon so the Forecast Period filter never
        # removes the past forecast line.
        daily, monthly = self.rich_history()
        historical = engine.calculate_historical_forecast(
            daily, monthly, now=month(2026, 9, 15)
        )
        future = engine.calculate_monthly_forecast(
            "1_month", daily, monthly, now=month(2026, 9, 15)
        )
        rows = engine.point_values(
            "1_month", 1, 1,
            historical["actual_points"],
            historical["forecast_points"] + future["forecast_points"],
        )
        past_forecast_dates = {
            row["date"] for row in rows
            if row["series"] == "forecast" and row["date"] < month(2026, 9)
        }
        self.assertTrue(past_forecast_dates)
        self.assertEqual(
            max(past_forecast_dates),
            month(2026, 8),
        )
        current_forecast_dates = {
            row["date"] for row in rows
            if row["series"] == "forecast" and row["date"] == month(2026, 9)
        }
        self.assertTrue(current_forecast_dates)
        self.assertEqual(
            rows[-1]["date"],
            month(2026, 10),
        )

    def test_kpi_equals_forecast_sum(self):
        daily, monthly = self.rich_history()
        result = engine.calculate_monthly_forecast(
            "6_months", daily, monthly, now=month(2026, 9, 15)
        )
        self.assertAlmostEqual(
            result["forecast_revenue"],
            sum(p["revenue"] for p in result["forecast_points"]),
        )

    def test_exponential_smoothing_uses_es_values_and_forecasts_current_month(self):
        monthly = [
            (month(2026, 3), 1274648.38),
            (month(2026, 4), 6478458.13),
            (month(2026, 5), 5496245.83),
            (month(2026, 6), 6311888.04),
            (month(2026, 7), 3891666.81),
            (month(2026, 8), 5867671.87),
            (month(2026, 9), 3469246.18),
        ]
        result = engine.calculate_exponential_smoothing_forecast(
            monthly, monthly, "1_month", now=month(2026, 10, 6)
        )
        # The 1 Month filter must forecast October, not November.
        self.assertEqual(result["forecast_points"][0]["date"], month(2026, 10))
        # Verified forecast from the dashboard's optimized additive Holt model.
        self.assertAlmostEqual(
            result["forecast_points"][0]["revenue"],
            3953916.5899395384,
            places=2,
        )
        # Every completed month must contain the fitted/smoothed ES value,
        # never the raw Revenue value. These values come from the optimized
        # additive Holt calculation for the confirmed March-September series.
        expected_es = [
            2629478.5933418702,
            3455346.6741872556,
            6923449.77676565,
            7375898.840182832,
            7545945.3025128115,
            5418160.936054924,
            5577173.717727288,
        ]
        self.assertEqual(
            [p["date"] for p in result["historical_forecast_points"]],
            [m[0] for m in monthly],
        )
        for point, expected in zip(result["historical_forecast_points"], expected_es):
            self.assertAlmostEqual(point["revenue"], expected, places=2)
        self.assertNotEqual(
            result["historical_forecast_points"][0]["revenue"],
            monthly[0][1],
        )

    def test_exponential_smoothing_normalizes_duplicate_month_rows(self):
        # ES must receive one monthly revenue value per calendar month even if
        # the caller supplies duplicate month buckets.
        monthly = [
            (month(2026, 3), 1000.0),
            (month(2026, 3), 2000.0),
            (month(2026, 4), 4000.0),
        ]
        normalized = engine._normalized_monthly_series(
            monthly, current_month=month(2026, 5)
        )
        self.assertEqual(normalized, [
            (month(2026, 3), 3000.0),
            (month(2026, 4), 4000.0),
        ])

    def test_exponential_smoothing_horizon_lengths(self):
        monthly = [
            (month(2026, 3), 1274648.38),
            (month(2026, 4), 6478458.13),
            (month(2026, 5), 5496245.83),
            (month(2026, 6), 6311888.04),
            (month(2026, 7), 3891666.81),
            (month(2026, 8), 5867671.87),
            (month(2026, 9), 3469246.18),
        ]
        expected = {
            # The current month is included as the first forecast point so the
            # ES chart matches the existing Overall Sales Forecast endpoint.
            "1_month": 2, "6_months": 7, "1_year": 13,
            "2_years": 25, "5_years": 61, "10_years": 121,
        }
        for key, count in expected.items():
            result = engine.calculate_exponential_smoothing_forecast(
                monthly, monthly, key, now=month(2026, 10, 6)
            )
            self.assertEqual(len(result["forecast_points"]), count)

        # With 6 Months selected, October is the current-month forecast and
        # the six selected future months continue through April 2027.
        result = engine.calculate_exponential_smoothing_forecast(
            monthly, monthly, "6_months", now=month(2026, 10, 6)
        )
        self.assertEqual(result["forecast_points"][0]["date"], month(2026, 10))
        self.assertEqual(result["forecast_points"][-1]["date"], month(2027, 4))


    def test_training_testing_uses_chronological_80_20_split_and_scores_both_models(self):
        daily = [
            (datetime(2026, 1, 1) + timedelta(days=i), 1000.0 + i * 50.0)
            for i in range(30)
        ]
        result = engine.calculate_training_testing(daily, train_ratio=0.80)

        self.assertTrue(result["available"])
        self.assertEqual(result["training_count"], 24)
        self.assertEqual(result["testing_count"], 6)
        self.assertEqual(result["testing_start"], datetime(2026, 1, 25))
        self.assertEqual(result["testing_end"], datetime(2026, 1, 30))
        self.assertEqual(len(result["actual_points"]), 30)
        self.assertEqual(len(result["testing_points"]), 6)
        self.assertEqual(
            {item["model"] for item in result["metrics"]},
            {"ARIMA", "Exponential Smoothing"},
        )
        self.assertIn(result["best_model"], {"ARIMA", "Exponential Smoothing"})
        self.assertTrue(all(item["rank"] in (1, 2) for item in result["metrics"]))

    def test_arima_forecast_keeps_es_separate_and_returns_monthly_points(self):
        monthly = [
            (month(2026, 3), 1274648.38),
            (month(2026, 4), 6478458.13),
            (month(2026, 5), 5496245.83),
            (month(2026, 6), 6311888.04),
            (month(2026, 7), 3891666.81),
            (month(2026, 8), 5867671.87),
            (month(2026, 9), 3469246.18),
        ]
        result = engine.calculate_arima_forecast(
            monthly, monthly, "1_month", now=month(2026, 10, 6)
        )
        self.assertTrue(result["debug"]["available"])
        self.assertIn(result["debug"]["order"], ((1, 1, 1), (0, 1, 1), (1, 1, 0), (0, 1, 0)))
        self.assertEqual(len(result["historical_forecast_points"]), 7)
        self.assertEqual(len(result["forecast_points"]), 2)
        self.assertEqual(result["forecast_points"][0]["date"], month(2026, 10))
        self.assertEqual(result["forecast_points"][1]["date"], month(2026, 11))
        self.assertTrue(all(p["revenue"] >= 0 for p in result["forecast_points"]))


    def test_arima_horizon_lengths_match_ml_chart_filter(self):
        monthly = [
            (month(2026, 1), 2000.0),
            (month(2026, 2), 2500.0),
            (month(2026, 3), 3000.0),
            (month(2026, 4), 3500.0),
            (month(2026, 5), 4000.0),
            (month(2026, 6), 4500.0),
            (month(2026, 7), 5000.0),
            (month(2026, 8), 5500.0),
            (month(2026, 9), 6000.0),
        ]
        for key, expected in (("1_month", 2), ("6_months", 7), ("1_year", 13)):
            result = engine.calculate_arima_forecast(
                monthly, monthly, key, now=month(2026, 10, 6)
            )
            self.assertTrue(result["debug"]["available"])
            self.assertEqual(len(result["forecast_points"]), expected)


    def test_arima_seven_day_filter_returns_seven_daily_points(self):
        daily = [
            (datetime(2026, 9, 1) + timedelta(days=i), 1000.0 + i * 25.0)
            for i in range(45)
        ]
        result = engine.calculate_arima_forecast(
            daily, [], "7_days", now=datetime(2026, 10, 6)
        )
        self.assertTrue(result["debug"]["available"])
        self.assertEqual(len(result["historical_forecast_points"]), 0)
        self.assertEqual(len(result["forecast_points"]), 7)
        self.assertEqual(
            result["forecast_points"][0]["date"],
            datetime(2026, 10, 7),
        )


    def test_arima_insufficient_history_fails_safely(self):
        monthly = [
            (month(2026, 8), 1000.0),
            (month(2026, 9), 2000.0),
        ]
        result = engine.calculate_arima_forecast(
            monthly, monthly, "1_month", now=month(2026, 10, 6)
        )
        self.assertFalse(result["debug"]["available"])
        self.assertEqual(result["forecast_points"], [])



if __name__ == "__main__":
    unittest.main()
