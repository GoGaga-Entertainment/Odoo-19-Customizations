# -*- coding: utf-8 -*-
import json
import logging

from odoo import models

from .sales_dashboard_patch import patch_sales_dashboard_json

_logger = logging.getLogger(__name__)

TARGET_DASHBOARD_XMLID = "spreadsheet_dashboard_sale.spreadsheet_dashboard_sales"


class SpreadsheetDashboard(models.Model):
    """Extends the standard Odoo Sales spreadsheet dashboard.

    The forecast helper records are refreshed before the dashboard snapshot is
    patched.  The Forecast Period global filter is client-side and selects one
    of the already-generated horizons; changing it therefore updates the
    chart/KPIs without rebuilding the dashboard or changing the native Sales
    filters.
    """
    _inherit = "spreadsheet.dashboard"

    def _get_serialized_readonly_dashboard(self):
        result = super()._get_serialized_readonly_dashboard()

        target = self.env.ref(TARGET_DASHBOARD_XMLID, raise_if_not_found=False)
        if not target or self.id != target.id:
            return result

        forecast_context = {
            "company_id": self.env.company.id,
            "owner_id": self.env.user.id,
        }

        # Refresh all forecast horizons.  This is intentionally best-effort:
        # a forecast failure must never remove the native Sales dashboard.
        try:
            validation_context = self.env["sale.forecast.point"].refresh_for_dashboard()
            forecast_context["validation"] = validation_context or {}
        except Exception:
            _logger.exception(
                "spreadsheet_dashboard_sale_enhancements_withAI: forecast "
                "refresh failed; serving the dashboard with existing forecast rows."
            )
            forecast_context["validation"] = {}

        try:
            payload = json.loads(result)
            payload["snapshot"] = patch_sales_dashboard_json(
                payload["snapshot"], forecast_context=forecast_context
            )
            return json.dumps(payload)
        except Exception:
            _logger.exception(
                "spreadsheet_dashboard_sale_enhancements_withAI: failed to "
                "patch the Sales dashboard JSON, serving the stock dashboard instead."
            )
            return result
