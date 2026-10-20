# Part of custom addon - ecommerce_product_custom_discounts
from odoo import models, api, fields

import logging
_logger = logging.getLogger(__name__)

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def _update_available_quantity(self, product_id, location_id, quantity=False, reserved_quantity=False, lot_id=None, package_id=None, owner_id=None, in_date=None):
        """ Override to track when a product's stock changes from 0 to > 0.
        When this happens, set the back_in_stock_trigger_time to now. """

        # Only track actual inventory additions to internal locations
        # Also only trigger when quantity (not just reserved_quantity) is being increased
        if location_id.usage == 'internal' and quantity and quantity > 0:
            # Read the current on-hand qty directly from DB (bypass ORM cache)
            # to get a reliable pre-update value.
            self.env.cr.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM stock_quant
                WHERE product_id = %s
                  AND location_id IN (
                      SELECT id FROM stock_location
                      WHERE usage = 'internal'
                        AND active = true
                  )
                """,
                [product_id.id]
            )
            row = self.env.cr.fetchone()
            prev_qty = row[0] if row else 0.0

            # Call super to perform the actual stock quant update
            res = super()._update_available_quantity(
                product_id, location_id, quantity=quantity, reserved_quantity=reserved_quantity,
                lot_id=lot_id, package_id=package_id, owner_id=owner_id, in_date=in_date
            )

            # If stock went from 0 (or negative) to positive, set the trigger time on the template
            if prev_qty <= 0:
                new_qty = prev_qty + quantity
                if new_qty > 0:
                    product_id.product_tmpl_id.sudo().write({
                        'back_in_stock_trigger_time': fields.Datetime.now()
                    })
                    _logger.info(
                        '[ecommerce_product_custom_discounts] Back-in-stock triggered for product %s (template %s): '
                        'qty changed %.2f -> %.2f',
                        product_id.display_name,
                        product_id.product_tmpl_id.display_name,
                        prev_qty, new_qty,
                    )

            return res

        # For non-internal locations or reserved_quantity-only updates, just call super
        return super()._update_available_quantity(
            product_id, location_id, quantity=quantity, reserved_quantity=reserved_quantity,
            lot_id=lot_id, package_id=package_id, owner_id=owner_id, in_date=in_date
        )
