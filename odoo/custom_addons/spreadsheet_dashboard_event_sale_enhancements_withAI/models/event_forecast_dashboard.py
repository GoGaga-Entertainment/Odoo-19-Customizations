# -*- coding: utf-8 -*-
import json
import logging

from odoo import models

from .event_forecast_patch import add_forecast_sections
from .event_monthly_sales_patch import add_monthly_sales

_logger = logging.getLogger(__name__)
# Order on the dashboard: KPIs -> Monthly Sales -> AI forecast block -> Top Countries ...
ENABLE_FORECAST = True
TARGET_XMLID = "spreadsheet_dashboard_event_sale.spreadsheet_dashboard_events"


class SpreadsheetDashboardEventForecast(models.Model):
    """Adds the AI forecast block on top of the already-patched Events
    dashboard.  Imported last in models/__init__.py so its ``super()`` returns
    the payload that the other Events enhancements have already modified."""
    _inherit = "spreadsheet.dashboard"

    def _get_serialized_readonly_dashboard(self):
        result = super()._get_serialized_readonly_dashboard()
        target = self.env.ref(TARGET_XMLID, raise_if_not_found=False)
        if not target or self.id != target.id:
            return result

        try:
            payload = json.loads(result)
            # Months are SALE months (same basis as the forecast), not event months.
            date_field = self.env["event.forecast.point"]._report_date_field()
            field = self.env["event.sale.report"]._fields.get(date_field)
            date_type = "datetime" if field is not None and field.type == "datetime" else "date"
            snapshot = add_monthly_sales(
                payload["snapshot"], date_field=date_field, date_type=date_type)
            if ENABLE_FORECAST:
                context = {"company_id": self.env.company.id,
                           "owner_id": self.env.user.id, "validation": {}}
                # refresh_for_dashboard never raises: it returns an "error" entry instead.
                context["validation"] = self.env["event.forecast.point"].refresh_for_dashboard() or {}
                snapshot = add_forecast_sections(snapshot, context)
            payload["snapshot"] = snapshot
            return json.dumps(payload)
        except Exception:
            _logger.exception("Events Monthly Sales patch failed; serving dashboard without it.")
            return result
