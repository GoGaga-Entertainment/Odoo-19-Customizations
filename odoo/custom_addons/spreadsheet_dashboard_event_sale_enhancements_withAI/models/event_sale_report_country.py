# -*- coding: utf-8 -*-
from odoo import fields, models


class EventSaleReportCountry(models.Model):
    """Expose the event customer's country as a direct report field.

    The stock ``event.sale.report`` already contains the customer through
    ``sale_order_partner_id``.  The dashboard geo chart is much more reliable
    when its country dimension is a direct Many2one to ``res.country`` rather
    than a nested relation (sale_order_partner_id.country_id).
    """

    _inherit = "event.sale.report"

    customer_country_id = fields.Many2one(
        "res.country",
        string="Customer Country",
        readonly=True,
    )

    def _select_clause(self, *select):
        return super()._select_clause(
            *select,
            "event_sale_customer_partner.country_id AS customer_country_id",
        )

    def _from_clause(self, *join):
        return super()._from_clause(
            *join,
            "LEFT JOIN res_partner AS event_sale_customer_partner ON event_sale_customer_partner.id = sale_order.partner_id",
        )