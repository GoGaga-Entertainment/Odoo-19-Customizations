# eCommerce Dashboard Enhancements with AI (Odoo 19)

Extends the standard eCommerce spreadsheet dashboard with the existing AOV/regression forecast, ML forecast, and training/testing panels from the Sales dashboard addon. Forecast history is restricted to confirmed `sale.order` records with `website_id` set, so the forecast is based on eCommerce orders only. The existing eCommerce KPIs, customer acquisition KPI, and product revenue share are preserved.

Forecast panels appear directly below Monthly Sales: (1) Overall Sales Forecast (AOV), (2) Overall Sales Forecast (ML Algorithms), (3) training/testing scorecards and (4) training/testing chart. Models used: linear regression, polynomial regression, Exponential Smoothing, and ARIMA.

Dependencies: `spreadsheet_dashboard_website_sale`, `spreadsheet_dashboard`, `website_sale`; Python packages `numpy`, `scipy`, `scikit-learn`, `statsmodels` (use statsmodels 0.14.6 to match the validated Sales addon results).

Copy the addon folder into your custom addons path, restart Odoo, update the Apps list, and upgrade `Spreadsheet_dashboard_website_sale_enhancements_withAI`.


## Forecast chart data-source fix

The forecast loader first reads confirmed website orders from `sale.order`
(`website_id` set, state `sale` or `done`). If that returns no rows, it now
falls back to `sale.report` with the same website-only filter and confirmed
states, using the dashboard's untaxed `price_subtotal` basis. Order counts
from the fallback count distinct `order_id` values, not order lines. The server
log records which source was used and warns if no confirmed website sales exist.

After replacing the addon, restart Odoo and upgrade the module. If the charts
are still empty, inspect the Odoo log for `eCommerce forecast found no confirmed
website sales` or `sale.report fallback query failed`; the database may not have
any confirmed orders with `website_id` set.
