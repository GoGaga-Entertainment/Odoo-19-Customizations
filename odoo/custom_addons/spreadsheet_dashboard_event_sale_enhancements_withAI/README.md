# Spreadsheet Dashboard for Event Sale Enhancements with AI

Technical name: `spreadsheet_dashboard_event_sale_enhancements_withAI`

This module enhances the standard Odoo 19 Events spreadsheet dashboard while
keeping the dashboard record itself unchanged during normal operation.

## Included functionality

- Customer Acquisition KPI.
- Average Registration KPI.
- Average Revenue KPI.
- Events Status enhancement with Archived status.
- Top Countries geo map.
- Top Venues, Top Templates, Top Tags and Top Organisers layout.
- Existing Events dashboard filters remain connected to the added KPIs/charts.
- Existing dashboard functionality is preserved.

## Important architecture change

The previous version called a model method from `data/dashboard_patch.xml` and
then used `dashboard.write()` to permanently save the modified spreadsheet JSON
into `spreadsheet.dashboard.spreadsheet_binary_data`.

That is why uninstalling the module did not remove the visual changes.

This corrected version works like the Sales enhancement module:

1. Odoo's standard Events dashboard is loaded normally.
2. `_get_serialized_readonly_dashboard()` calls `super()`.
3. The custom code patches only the JSON payload returned to the browser.
4. Nothing is written to `spreadsheet.dashboard` during normal dashboard use.
5. Uninstall therefore removes the read-time patch and the standard dashboard
   is shown again.

## Existing installations of the old version

The old version may already have permanently modified the dashboard record.
The new module therefore contains a one-time `post_init_hook` that restores the
stock Odoo Events dashboard JSON when the corrected module is installed.

It also contains an `uninstall_hook` that restores the stock Events dashboard
when the corrected module is uninstalled.

The stock dashboard source is read from:

`spreadsheet_dashboard_event_sale/data/files/events_dashboard.json`

No custom dashboard JSON is stored by this module.

## Files

- `models/dashboard_patch.py` — read-time dashboard patch and all dashboard
  enhancements.
- `models/customer_acquisition.py` — reporting SQL view for acquisition.
- `models/event_sale_report_country.py` — customer country field for the
  Events sales report.
- `__init__.py` — install/uninstall cleanup hooks.
- `security/ir.model.access.csv` — access to the acquisition reporting view.

There is intentionally no XML function that writes a modified dashboard
payload.

## Install / uninstall behavior

Install:
- Standard dashboard is restored first.
- Custom enhancements are displayed dynamically.

While installed:
- Standard database dashboard JSON remains untouched by the enhancement
  logic.

Uninstall:
- The cleanup hook restores the stock Events dashboard.
- Custom fields/models are removed by Odoo as part of module uninstall.
- The Events dashboard returns to the standard Odoo version.

## Final integrated customization layer

This ZIP is a single replacement addon. It keeps the existing Events dashboard
enhancements and integrates the final dashboard fixes in the same module folder.
There is no second customization addon to install.

Included final fixes:
- Three KPI cards on the second row.
- Customer Acquisitions.
- Average Registrations Per Event.
- Average Revenue Per Event.
- Sales-style Top Countries Map / Top 10 carousel.
- Top 10 country values backed by the Events sales pivot.
- Archived Event Status shown after Ended.

## AI forecast section (v19.0.1.11.0)

Mirrors the Sales "withAI" dashboard, applied to Events. Everything is added in
memory at read time (same architecture as above); stock addon files are not
modified and nothing is written to `spreadsheet.dashboard`.

New dashboard content, in this order: KPI cards -> Monthly Sales -> AI forecast block -> Top Countries / Events Status / tables (existing content is pushed down by `models/event_dashboard_layout.py`):
- **Monthly Event Sales** area chart (series label "Untaxed Total") (event sales only, `event.sale.report`, sold).
- **Forecast Period** filter (7 Days, 1 Month, 6 Months, 1/2/5/10 Years; default 1 Month).
- **Overall Event Sales Forecast** - actual vs forecast revenue.
- **Overall Event Sales Forecast (ML Algorithms)** - ARIMA, Exponential
  Smoothing, Linear Regression, Polynomial Regression.
- **Training Data / Testing Data / Best Performing Model** cards (80/20
  chronological back-test, MAPE based) and a **Trained & Tested** chart.
- Filter wiring: the **Forecast Period** filter drives ONLY the three forecast charts
  (AOV, ML Algorithms, Trained & Tested). **Monthly Sales** is wired ONLY to the dashboard
  **Date** filter, matched on the chart's own x-axis date field, so stock Odoo also drives its
  in-graph Days/Months/... choices and automatic default from the Date filter.
- Months/Quarters/Days chart granularity of the forecast charts follows the Forecast Period
  (`static/src/js/event_forecast_axis_filter.js`).

Data source: event sales only, bucketed by SALE date (not event date), so a
ticket sold in September for an October event counts in September.
Primary = confirmed `sale.order.line` rows that carry an event (order date).
Fallback = `event.sale.report` (sold) by its sale/registration date field.
Monthly Sales uses the same sale-date basis when the report exposes such a field.
Series are labelled "Actual Event Revenue" / "Forecast Event Revenue" so the Sales AI
module's tooltip script (which decorates tooltips containing "Actual Revenue" with
whole-company Sales data) never touches Events charts.
If the forecast cannot be built, the Best Performing Model card says why.

Verify the numbers (psql): monthly event revenue by order date
    SELECT to_char(date_trunc('month', so.date_order),'YYYY-MM') AS month,
           round(sum(sol.price_subtotal)) AS revenue, count(DISTINCT so.id) AS orders
      FROM sale_order_line sol JOIN sale_order so ON so.id = sol.order_id
     WHERE sol.event_id IS NOT NULL AND so.state = 'sale' GROUP BY 1 ORDER BY 1;
and what the chart stored:
    SELECT date, round(revenue) FROM event_forecast_point
     WHERE forecast_period = '1_month' AND series = 'actual' ORDER BY date;

Files added: `models/event_dashboard_layout.py`, `models/event_monthly_sales_patch.py`, `models/event_forecast_engine.py`, `models/event_forecast.py`,
`models/event_forecast_patch.py`, `models/event_forecast_dashboard.py`,
`static/src/js/event_forecast_axis_filter.js`, four read-only ACL lines.

Requirements (Odoo Python env): `pip install numpy scipy scikit-learn statsmodels`.
Forecast helper rows are rebuilt per user/company at most every 10 minutes, or
immediately when event sales change. A forecast failure never breaks the
dashboard (it is logged and the dashboard is served without the block).

Upgrade: `-u spreadsheet_dashboard_event_sale_enhancements_withAI`, then hard-refresh the browser.
