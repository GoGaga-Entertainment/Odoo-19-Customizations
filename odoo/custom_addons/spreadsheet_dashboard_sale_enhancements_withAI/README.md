# Spreadsheet Dashboard for Sale Enhancement with AI

Technical name: `spreadsheet_dashboard_sale_enhancements_withAI`

Adds four data points to the existing, stock **Sales** spreadsheet
dashboard shipped by `spreadsheet_dashboard_sale` — without touching that
module, or any other Odoo core/addon file, on disk.

The `withAI` in the name is intentional and forward-looking only. This
version does **not** add any chatbot/LLM functionality — see "Scope" below.

## What it does

Adds to the **Sales** dashboard (the "Sales" entry under Dashboards, the one
with the Quotations / Orders / Revenue / Average Order cards):

1. **Revenue per Customer** — a 5th KPI card.
2. **Sales Growth** — a 6th KPI card, current vs. previous equivalent period.
3. **Order Cancellation %** — a 7th KPI card.
4. **%** (Contribution) — one new column added directly next to the existing
   Top Products table's Revenue column, showing each of the top 10
   products' share of total revenue, colored red for negative and green
   for positive contributions. (v2: this used to be a whole separate,
   relabelled copy of the Product/Orders/Revenue table next to the real
   one, which rendered as two side-by-side tables — that duplicate has
   been removed; now it's just the one extra column on the real table.
   v2.3: the column is clickable — see records for that product — just
   like the Product/Orders/Revenue columns next to it. v2.4: renamed
   header from "Contribution %" to "%", and fixed the coloring — see
   below.)

All four are formulas, not snapshots — they respond live to the dashboard's
"Period" filter and to every other global filter (Country, Product,
Customer, Category, Sales Team, Salesperson, Source, Medium) exactly like
the stock KPI cards do, because they're built from the same pivot
infrastructure.

The 3 new KPI cards are clickable and navigate to **Sales → Reporting →
Sales**, the same target the stock Revenue and Average Order cards use.

The Contribution % column is clickable too, and behaves like the stock
Product/Orders/Revenue columns: clicking a value opens "See records" for
that product on the current dashboard filters. This relies on an Odoo
client-side rule (`SEE_RECORDS_PIVOT_VISIBLE` in
`spreadsheet/static/src/pivot/pivot_actions.js`) that only makes a cell
clickable when its formula contains **exactly one** `PIVOT.*` function
call. Earlier versions of this column also called `PIVOT.HEADER(...)` in
the same formula (to detect "no product at this rank") alongside
`PIVOT.VALUE(...)`, which put two pivot calls in one cell and silently
disabled the click - the column looked identical but never opened
anything. It now guards against empty ranks by checking the stock
Revenue cell (`G{row}`) already present in the same row instead, which
keeps the cell down to a single `PIVOT.VALUE(...)` call.

The column is also colored: negative contributions render in red
(`#DC6965`) and positive ones in green (`#00A04A`) - the same two colors
this module already uses for the KPI cards' up/down baseline. This
needed a real fix, not just adding a coloring rule: the cell used to end
in `&"%"` (string concatenation), which makes the cell's evaluated value
text, not a number - and o-spreadsheet's conditional formatting
(`CellIsRule`, `isLessThan` / `isGreaterThan`) requires a real number to
ever fire (`typeof value !== "number" -> false`, unconditionally, in
o-spreadsheet's `criterion_registry.ts`). No coloring rule, however
written, could ever have applied to a text cell. The cell now holds the
raw numeric ratio and gets a `"0.00%"` number format instead, which is
what actually makes it a number the color rules can evaluate.

Nothing else on the dashboard is changed. The Product dashboard (the
second dashboard shipped by `spreadsheet_dashboard_sale`) is untouched.

## How it works (architecture)

`spreadsheet_dashboard_sale` ships the dashboard as a single JSON blob
(`spreadsheet_binary_data`) on a `spreadsheet.dashboard` record — there is
no XML view or field to inherit for its internal cells/pivots/KPI cards, so
ordinary `_inherit`-a-view XML inheritance doesn't apply here. Instead this
module does the following, which *is* a standard, non-invasive Odoo
extension technique:

- `models/spreadsheet_dashboard.py` adds `_inherit = "spreadsheet.dashboard"`
  and overrides `_get_serialized_readonly_dashboard()` — the exact method
  Odoo's own `/spreadsheet/dashboard/data/<dashboard>` controller
  (`spreadsheet_dashboard/controllers/dashboards_controllers.py`) calls to
  produce the JSON sent to the browser.
- The override calls `super()` first (so the stock behaviour always runs
  unchanged), then — **only when the record being served is the stock
  "Sales" dashboard** (`spreadsheet_dashboard_sale.spreadsheet_dashboard_sales`)
  — patches the in-memory JSON before returning it.
- Every other dashboard record, including the Product dashboard, is
  returned completely untouched.
- Nothing is written back to the database. This is deliberate: the stock
  `dashboards.xml` record has no `noupdate="1"`, so a future upgrade of
  `spreadsheet_dashboard_sale` would silently reset any change persisted to
  the record. Patching at read-time instead means this module survives
  upgrades of the base module without any migration logic.
- If the patch logic ever raises for any reason, the override catches it,
  logs it, and falls back to serving the untouched stock dashboard rather
  than breaking the page.

`models/sales_dashboard_patch.py` contains the actual JSON patch, built
**only** from formula patterns already proven in the real, shipped
`sales_dashboard.json` / `product_dashboard.json` files (inspected directly
— see "What was inspected" below), namely:

- `PIVOT.VALUE(pivotId, measure, "field", "value")` — used by the stock
  Quotations/Orders/Revenue/Average Order cards.
- `PIVOT.HEADER(pivotId, "#field", rank)` / `PIVOT.VALUE(pivotId, measure,
  "#field", rank)` — the ranked-lookup form, used by the stock "Best
  Seller" / "Best Category" cards in the Product dashboard.
- The `[Label](odoo://view/{...})` cell-link syntax used throughout the
  Sales dashboard for section headers (e.g. "Top Products").
- The `chartOdooMenusReferences: {chartId: "module.menu_xmlid"}`
  workbook-level map that wires a scorecard figure to a click-through menu
  — this is exactly how the stock Revenue/Average Order/Quotations/Orders
  cards navigate today.
- `IFERROR`, `FORMAT.LARGE.NUMBER`, `_t()`, `COUNTA`, `ROUND` — all used
  as-is in the stock file.

No new pivot measure, no new global filter, and no change to any existing
pivot, cell, or figure was made. Two additions only: one new pivot
(id `13`, "Order cancellation stats - current" — needed because the stock
pivots 11/12 explicitly *exclude* `state = cancel` from their domain, so
they cannot be reused to count cancellations), and new cells/figures placed
in previously-unused rows/columns of the Dashboard and Data sheets.

## Formulas

- **Revenue per Customer** = `Data!B7 (current-period Revenue) / distinct customer count`.
  Customer count comes from the stock "Customer" pivot (id 4) rendered as a
  hidden dynamic pivot in the Data sheet. Totals and column titles are
  disabled, and the populated partner dimension cells are counted, so the
  denominator reflects the actual current-period customer groups.
- **Sales Growth** = `(Data!B7 − Data!C7) / Data!C7 × 100`, where `B7`/`C7`
  are the stock current/previous period Revenue totals already computed by
  pivots 11/12 (offset 0 / −1 on the "Period" global filter). Division by
  zero is guarded with `IFERROR(...,0)`, shown as `0%`.
- **Order Cancellation %** = `cancelled orders / total orders (all states) × 100`
  for the current period, using the new pivot 13 grouped by `state` with no
  state filter in its domain. Both counts use the `order_reference`
  measure — the same field the stock "Orders" KPI uses, which counts
  distinct orders rather than `sale.report` lines, avoiding the
  line-level double-counting the spec calls out. Division by zero guarded
  with `IFERROR(...,0)`.
- **Product Sale Contribution %** = `product revenue / pivot-6 total product
  revenue × 100`, for each of the top 10 products from the same pivot (id 6)
  the stock Top Products table already uses. The denominator is stored in
  `Data!H19` from `PIVOT.VALUE(6,"price_subtotal")`, so numerator and
  denominator use the exact same pivot domain and measure. Each visible
  contribution cell still contains only one `PIVOT.VALUE()` call, preserving
  Odoo's pivot drill-down behaviour.

## Models used

Only the stock `sale.report` model (via the existing pivots) and the stock
`spreadsheet.dashboard` model (inherited, no new fields). No new Odoo
model, no new database field, no new SQL view was created.

## Dependencies

- `spreadsheet_dashboard_sale` (which in turn depends on
  `spreadsheet_dashboard` and `sale`) — declared as the sole `depends` entry,
  since it already pulls in everything this module needs.

## Core files NOT modified

Nothing under `spreadsheet_dashboard/`, `spreadsheet_dashboard_sale/`, or
`sale/` is touched, on disk or otherwise. This module only adds one new
Python model override (`_inherit`) that runs at read-time.

## Installation

1. Copy the `spreadsheet_dashboard_sale_enhancements_withAI/` folder into
   your custom addons path.
2. Apps → Update Apps List.
3. Search "Spreadsheet Dashboard for Sale Enhancement with AI" → Install.
4. Open Dashboards → Sales. The 3 new KPI cards and the new "Top Products —
   Sale Contribution %" table should appear.

## Uninstall

Apps → search the module → Uninstall. Because this module makes no schema
changes and writes nothing to the database, uninstalling it simply removes
the read-time override — the stock Sales dashboard reverts to exactly its
original shipped appearance.

## Known limitations / what could not be runtime-tested

This module was built by inspecting the actual `spreadsheet_dashboard` and
`spreadsheet_dashboard_sale` addon source (manifests, model, controller,
and the real `sales_dashboard.json` / `product_dashboard.json` payloads)
that were provided, and validated with static checks (Python
`py_compile`, running the patch function against the real dashboard JSON
and confirming valid, collision-free JSON output). No live Odoo 19 instance
was available to actually open the patched dashboard in a browser, so the
following could **not** be runtime-verified and are worth checking first:

- **Large customer-volume helper limit.** The customer count uses a dynamic
  `PIVOT(4, 1000, 0, 0)` helper in the hidden Data sheet. The 1000-row limit
  is deliberately generous for the dashboard. If a selected period can
  contain more than 1000 unique customers, increase `CUSTOMER_PIVOT_ROWS` in
  `models/sales_dashboard_patch.py`.
- **Visual/layout only:** the exact pixel spacing of the 3 new KPI cards
  (x-offsets 895/1118/1341, continuing the stock cards' spacing pattern)
  were chosen by inspection of the stock layout, not rendered and visually
  checked in a running instance.
- **Contribution % column placement.** The column is placed at `H36:H46` of
  the Dashboard sheet: this module's own notes record that the stock Top
  Products title link is at `E35`, so the table's columns are E (Product) /
  F (Orders) / G (Revenue), and H is the first unused column right after
  Revenue. An earlier version of this file mistakenly assumed A/B/C and
  used column D, which rendered just *before* the real table instead of
  after it — check this looks right after installing; if your instance's
  table uses different columns, update `TOP_PRODUCTS_CONTRIB_COL` in
  `_add_contribution_table()` (`models/sales_dashboard_patch.py`).
- **KPI cards, all 7 in one row.** All 7 KPI cards, including the 4 stock
  ones, are resized so they all fit in a single row within the width
  already proven to render. Quotations/Orders/Revenue and the 3 new cards
  are 148px/134px respectively (short values), and Average Order is
  widened to 190px so its full, unabbreviated currency value (e.g.
  "₹27,300.00" - unlike Revenue, it isn't passed through
  FORMAT.LARGE.NUMBER) isn't clipped to "₹27,...". Total row width is
  unchanged from the previous uniform-148px layout, so it still fits.
  The 4 stock cards are found by title ("Quotations", "Orders", "Revenue",
  "Average Order") and resized in place — if your instance's stock card
  titles differ (e.g. a different Odoo version/localisation), this module
  can't confidently find and resize them, and falls back to a 2-row layout
  for the 3 new cards instead of guessing. If the single row still doesn't
  fit your screen, adjust `NEW_WIDTH` / `AVERAGE_ORDER_WIDTH` /
  `NEW_CARD_WIDTH` / `GAP` in `_add_kpi_scorecards()`
  (`models/sales_dashboard_patch.py`).
- **`baselineMode: "text"`** was used for all 3 new cards (the same
  mechanism the stock "Best Seller"/"Best Category" cards use) rather than
  the `"percentage"` mode the stock Revenue/Average Order cards use, because
  `"percentage"` mode computes its own comparison between `keyValue` and
  `baseline` from two raw numbers — not applicable here where the KPI
  itself already *is* a percentage or a per-unit figure. This means the 3
  new cards show a `+`/`−` sign (Sales Growth) as their positive/negative
  indicator rather than the stock cards' colour-coded arrow — reproducing
  that arrow for a headline percentage was not something we could verify
  is supported without access to the o-spreadsheet front-end source, so we
  did not guess at it.
- Install was validated statically (manifest structure, Python syntax,
  JSON structural validity of the patched payload) but not by actually
  running `odoo-bin -i` against a live 19.0 database.


## v1.2 Product Sale % correction

Product Sale % is calculated as each positive product revenue divided by the total positive `sale.report.price_subtotal` for the same dashboard/global-filter domain. Negative discount rows are excluded from the denominator and display 0% in the contribution column. This prevents discount lines from making a normal product exceed 100%, while the denominator includes all positive products rather than only the visible top-10 rows.

## Overall Sales Forecast

This version includes the **Overall Sales Forecast** panel above Monthly Sales.

### Forecast Period filter

The dashboard adds an independent **Forecast Period** selection filter with:

- 7 Days
- 1 Month (default)
- 6 Months
- 1 Year
- 2 Years
- 5 Years
- 10 Years

The filter is matched to the forecast chart and forecast summary only; the
standard Sales dashboard date/customer/product/salesperson filters are not
mutated by this feature.

### Forecast calculation

The Overall Sales Forecast preserves the original cumulative daily run-rate forecast and adds linear and degree-2 polynomial regression comparison forecasts using confirmed `sale.order` revenue aggregated to daily totals.

The separate **Overall Sales Forecast (ML Algorithm)** chart now contains **two time-series models side by side**:

- **Exponential Smoothing:** Holt exponential smoothing with an additive, damped trend and estimated initial state. Monthly horizons are fitted to one confirmed-revenue value per completed calendar month. The current month is excluded from training and is then shown as the first future forecast point.
- **ARIMA:** ARIMA with a preferred `(1, 1, 1)` order. If that order does not converge for the available history, nearby valid `(0, 1, 1)`, `(1, 1, 0)`, and `(0, 1, 0)` models are tried and the lowest-AIC converged model is selected. This keeps the dashboard operational for short or strongly trending histories.

For monthly horizons, both ML models use completed monthly revenue. For the **7 Days** horizon, both models use continuous daily history and return seven daily forecasts. The current month is the first plotted future point for the monthly ML chart so its endpoint remains aligned with the existing forecast chart; therefore the 1 Month filter displays the current month plus one selected future month, 6 Months displays the current month plus six selected future months, and so on.

The ML chart contains only the **Exponential Smoothing** and **ARIMA** series. The Forecast Period filter controls both series together. The original Forecast Revenue KPI and the native Overall Sales Forecast calculations remain unchanged.

The scientific dependencies used by the forecast engine are listed in `requirements.txt`: NumPy, SciPy, scikit-learn, and statsmodels 0.14.6. Negative or non-finite ML predictions are clipped to zero before they are written to the dashboard.

A developer diagnostic helper is available from an Odoo shell:

```python
env["sale.forecast.point"].get_forecast_debug("1_month")
env["sale.forecast.point"].get_forecast_debug("6_months")
```

The Odoo module itself does not declare scientific packages through Odoo's
external dependency manifest. Install the packages from `requirements.txt` in
the same Python environment used by the Odoo server before upgrading the module.

### Forecast chart default / filter behavior

The Overall Sales Forecast now opens in a historical/back-test view. The chart shows actual revenue for completed months together with a historical forecast for those months. Each historical forecast uses only revenue from dates before the month being forecast, so the target month's actual revenue is not used in its own forecast.

The future forecast horizons (7 Days, 1 Month, 6 Months, 1 Year, 2 Years, 5 Years, and 10 Years) are not displayed in the default Historical view. Selecting a Forecast Period switches the chart to that future horizon, while retaining the historical actual series.

## Model training and testing

The dashboard also performs a chronological 80/20 hold-out validation on the
continuous daily confirmed-sales history. The first 80% is used for training
and the final 20% is held out as unseen test data. Both the existing ARIMA
and Exponential Smoothing implementations are evaluated on the same test
window. The dashboard shows Actual Sales plus both model predictions in a
compact Training & Testing chart and reports MAE, RMSE, and MAPE. MAPE ignores
zero-actual days because percentage error is undefined there; MAE and RMSE
include all test days. The best model is ranked by MAPE, with RMSE as the tie
breaker.

The validation dataset is stored in `sale.forecast.validation.point` and is
refreshed together with the existing forecast points. It does not change the
Forecast Period selector or the existing forecast calculations.

## Chart "Group by" selector follows the Forecast Period filter (v19.0.5.3.3)

The small selector next to each forecast chart is filtered by the header
**Forecast Period** filter (implemented in `static/src/js/forecast_axis_filter.js`
by patching `OdooChartFeaturePlugin.getAvailableChartGranularities`):

| Forecast Period            | Selector options          |
|----------------------------|---------------------------|
| 7 Days                     | Days, Months              |
| 1 Month, 6 Months          | Months, Quarters          |
| 1 / 2 / 5 / 10 Years       | Months, Quarters, Years   |
| nothing selected           | all options               |

After updating the files run `odoo-bin -u spreadsheet_dashboard_sale_enhancements_withAI`
and open the dashboard with `?debug=assets` once so the JS bundle is rebuilt.

v19.0.5.3.3 fix: removed `import { Chart } from "chart.js"` (not an Odoo ES module, it made the whole file fail to load) and added support for the newer `definition.dataSource.metaData` chart shape. The selector now applies to every chart.
Also moved the Forecast Period chart-regrouping hook from GlobalFiltersCoreViewPlugin.handle (not called in newer Odoo) to OdooChartFeaturePlugin, which works on both.
