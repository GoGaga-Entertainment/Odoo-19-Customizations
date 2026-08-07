# Part of custom addon - ecommerce_product_custom_discounts
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Abandoned Cart Recovery ─────────────────────────────────────────
    abandoned_cart_discount_enabled = fields.Boolean(
        string="Enable Abandoned Cart Recovery Discount",
        config_parameter='ecommerce_product_custom_discounts.abandoned_cart_discount_enabled',
    )
    abandoned_cart_strategy = fields.Selection(
        [('escalating', 'Escalating'), ('reverse', 'Diminishing')],
        string="Discount Strategy",
        config_parameter='ecommerce_product_custom_discounts.abandoned_cart_strategy',
        default='reverse',
    )
    abandoned_cart_delay_hours = fields.Integer(
        string="Abandonment Delay (hours)",
        config_parameter='ecommerce_product_custom_discounts.abandoned_cart_delay_hours',
        default=1,
    )
    abandoned_cart_discount_start = fields.Float(
        string="Starting Discount (%)",
        config_parameter='ecommerce_product_custom_discounts.abandoned_cart_discount_start',
        default=5.0,
    )
    abandoned_cart_discount_step = fields.Float(
        string="Incremental Step (%)",
        config_parameter='ecommerce_product_custom_discounts.abandoned_cart_discount_step',
        default=5.0,
    )
    abandoned_cart_discount_max = fields.Float(
        string="Max Total Discount (%)",
        config_parameter='ecommerce_product_custom_discounts.abandoned_cart_discount_max',
        default=20.0,
    )
    # Time period in hours the discount offer stays active before expiry
    abandoned_cart_discount_hours = fields.Integer(
        string="Offer Valid For (hours)",
        config_parameter='ecommerce_product_custom_discounts.abandoned_cart_discount_hours',
        default=24,
    )

    # ── Wishlist Special Day ────────────────────────────────────────────
    wishlist_special_day_enabled = fields.Boolean(
        string="Enable Wishlist Special Day Discount",
        config_parameter='ecommerce_product_custom_discounts.wishlist_special_day_enabled',
    )

    @api.constrains('abandoned_cart_discount_start', 'abandoned_cart_discount_step', 'abandoned_cart_discount_max', 'abandoned_cart_delay_hours', 'abandoned_cart_discount_enabled')
    def _check_abandoned_cart_discount(self):
        for record in self:
            if not record.abandoned_cart_discount_enabled:
                continue
            if record.abandoned_cart_discount_start > record.abandoned_cart_discount_max:
                raise ValidationError("Starting discount cannot be greater than Max Total Discount.")
            if record.abandoned_cart_discount_step <= 0:
                raise ValidationError("Incremental step must be greater than 0.")
            if record.abandoned_cart_delay_hours < 0:
                raise ValidationError("Abandonment delay cannot be negative.")
    # Stored via get_values/set_values because fields.Date can't use config_parameter directly
    wishlist_special_day_date = fields.Date(
        string="Special Day Date",
    )
    wishlist_special_day_discount = fields.Float(
        string="Discount on Special Day (%)",
        config_parameter='ecommerce_product_custom_discounts.wishlist_special_day_discount',
        default=15.0,
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        date_str = self.env['ir.config_parameter'].sudo().get_param(
            'ecommerce_product_custom_discounts.wishlist_special_day_date'
        )
        if date_str:
            try:
                res['wishlist_special_day_date'] = fields.Date.from_string(date_str)
            except Exception:
                res['wishlist_special_day_date'] = False
        else:
            res['wishlist_special_day_date'] = False

        delay_str = self.env['ir.config_parameter'].sudo().get_param('ecommerce_product_custom_discounts.abandoned_cart_delay_hours')
        if delay_str is not None and delay_str is not False:
            res['abandoned_cart_delay_hours'] = int(delay_str)
        else:
            res['abandoned_cart_delay_hours'] = 1

        return res

    def set_values(self):
        super().set_values()
        date_val = self.wishlist_special_day_date
        date_str = fields.Date.to_string(date_val) if date_val else ''
        self.env['ir.config_parameter'].sudo().set_param(
            'ecommerce_product_custom_discounts.wishlist_special_day_date', date_str
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'ecommerce_product_custom_discounts.abandoned_cart_delay_hours', str(self.abandoned_cart_delay_hours)
        )