eCommerce Forecast Graphs — Log Fix (Odoo 19)
================================================

What this fixes
---------------
- The forecast refresh no longer lets a missing validation SQL table abort the
  main forecast refresh. Validation persistence is isolated in a database
  savepoint, so the AOV and ML forecast rows can still be refreshed.
- The addon version is bumped to 19.0.1.1.0.
- Explicit administrator read ACLs are included for the forecast chart models.
- A normal module upgrade is still required so Odoo creates missing SQL tables
  and loads the ACL records.

IMPORTANT: Apply the module upgrade
-----------------------------------
Use the same Python environment and database shown in your Odoo log. On Windows,
run this command from Command Prompt (adjust paths only if your installation
differs):

C:\Users\alwin\Odoo-19-Customizations\odoo\odoo19\Scripts\python.exe C:\Users\alwin\Odoo-19-Customizations\odoo\odoo-bin -d odoo19pdt -u spreadsheet_dashboard_website_sale_enhancements_withAI --stop-after-init

After it exits successfully, start Odoo normally and hard-refresh the browser
(Ctrl+Shift+R). Confirm that the command says the addon upgrade completed.

The current log already confirms eCommerce sales history is being loaded
(6 daily buckets, revenue 2,074,863.97). The failure is the missing
website_sale_forecast_validation_point table during refresh, plus missing
read ACLs. The module upgrade is required to create/load these structures.
