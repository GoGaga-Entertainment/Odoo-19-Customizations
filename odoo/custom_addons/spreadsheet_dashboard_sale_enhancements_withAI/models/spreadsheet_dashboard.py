# -*- coding: utf-8 -*-
import json
import logging

from odoo import models

from .sales_dashboard_patch import patch_sales_dashboard_json

_logger = logging.getLogger(__name__)

# xmlid of the stock "Sales" dashboard record, defined in
# spreadsheet_dashboard_sale/data/dashboards.xml:
#   <record id="spreadsheet_dashboard_sales" model="spreadsheet.dashboard">
TARGET_DASHBOARD_XMLID = "spreadsheet_dashboard_sale.spreadsheet_dashboard_sales"


class SpreadsheetDashboard(models.Model):
    """Extends the stock dashboard model (defined in ``spreadsheet_dashboard``)
    to inject four additional KPIs into the standard "Sales" dashboard.

    This overrides ``_get_serialized_readonly_dashboard``, the single method
    the ``/spreadsheet/dashboard/data/<dashboard>`` controller
    (spreadsheet_dashboard/controllers/dashboards_controllers.py) calls to
    produce the JSON served to the browser. The patch is applied to the
    in-memory payload only, on every request, for the Sales dashboard record
    alone:

    - Nothing is written back to the database, so the change is immune to
      ``spreadsheet_dashboard_sale`` being upgraded/reinstalled later (its
      data file would otherwise reset any stored patch).
    - Every other dashboard record is returned completely untouched,
      including the "Product" dashboard also shipped by
      spreadsheet_dashboard_sale.
    - The "empty database" sample-dashboard code path in the base controller
      (``_dashboard_is_empty`` / ``sample_dashboard_file_path``) bypasses
      this method entirely, so the sample/preview dashboard shown before any
      real sale order exists is intentionally left as shipped.
    """
    _inherit = "spreadsheet.dashboard"

    def _get_serialized_readonly_dashboard(self):
        result = super()._get_serialized_readonly_dashboard()

        target = self.env.ref(TARGET_DASHBOARD_XMLID, raise_if_not_found=False)
        if not target or self.id != target.id:
            return result

        try:
            payload = json.loads(result)
            payload["snapshot"] = patch_sales_dashboard_json(payload["snapshot"])
            return json.dumps(payload)
        except Exception:
            # Never let a patching bug break the standard Sales dashboard -
            # fall back to the unmodified, stock payload.
            _logger.exception(
                "spreadsheet_dashboard_sale_enhancements_withAI: failed to "
                "patch the Sales dashboard JSON, serving the stock dashboard instead."
            )
            return result
