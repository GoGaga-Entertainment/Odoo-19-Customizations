# Part of custom addon - ecommerce_product_custom_discounts
from odoo import models, fields, api
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class ProductWishlist(models.Model):
    _inherit = 'product.wishlist'

    @api.model
    def get_wishlist_special_day_info(self):
        """
        Returns the special day config so the frontend JS can show
        a discount banner on the wishlist page if today matches.
        Also used by the cart controller to decide whether to apply discount.
        """
        get = self.env['ir.config_parameter'].sudo().get_param
        enabled = get('ecommerce_product_custom_discounts.wishlist_special_day_enabled', 'False') == 'True'
        special_date_str = get('ecommerce_product_custom_discounts.wishlist_special_day_date', '')
        discount = float(get('ecommerce_product_custom_discounts.wishlist_special_day_discount', '15') or '15')

        if not enabled or not special_date_str:
            return {'active': False}

        try:
            special_date = fields.Date.from_string(special_date_str)
        except Exception:
            return {'active': False}

        today = date.today()
        is_special_day = (today == special_date)

        return {
            'active': is_special_day,
            'discount_pct': discount,
            'special_date': special_date_str,
        }

    @api.model
    def get_current_partner_wishlist_product_ids(self):
        """
        Returns product.product IDs in the current user's wishlist.
        Used by the cart controller / JS to determine which cart lines
        qualify for the special day discount badge.
        """
        wishes = self.current()
        return wishes.mapped('product_id').ids