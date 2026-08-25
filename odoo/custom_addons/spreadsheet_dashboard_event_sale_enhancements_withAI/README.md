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
