# Part of custom addon - ecommerce_product_custom_discounts
from odoo import models, fields
from odoo.tools.translate import html_translate


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ── Back In Stock Message ───────────────────────────────────────────
    back_in_stock_message = fields.Html(
        string="Back in Stock Message",
        help=(
            "Message shown on the website product page for 5 minutes after "
            "stock transitions from 0 to a positive quantity. "
            "Visible only for storable products."
        ),
        sanitize=True,
        translate=html_translate,
    )

    # Timestamp set automatically by stock_quant override when stock goes 0 → positive
    back_in_stock_trigger_time = fields.Datetime(
        string="Back In Stock Trigger Time",
        copy=False,
        readonly=True,
    )

    def _get_additionnal_combination_info(
        self, product_or_template, quantity, uom, date, website
    ):
        """
        Extend combination_info to expose back-in-stock fields to the website JS.
        Note: method name has a deliberate double-n typo matching Odoo core.
        """
        res = super()._get_additionnal_combination_info(
            product_or_template, quantity, uom, date, website
        )

        # Expose back-in-stock message
        res['back_in_stock_message'] = self.back_in_stock_message or ''

        # Expose trigger time as a naive ISO string (UTC); JS appends 'Z' to parse correctly
        trigger = self.back_in_stock_trigger_time
        res['back_in_stock_trigger_time'] = (
            trigger.strftime('%Y-%m-%dT%H:%M:%S') if trigger else ''
        )

        return res