# Part of custom addon - ecommerce_product_custom_discounts
from odoo import models, fields, api
from datetime import timedelta, date
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ── Abandoned Cart tracking fields ──────────────────────────────────
    # Tracks how many incremental discount steps have been applied
    abandoned_cart_discount_step_count = fields.Integer(
        string="Abandoned Cart Discount Steps Applied",
        default=0,
        copy=False,
    )
    # Timestamp when the current discount offer expires
    abandoned_cart_offer_expiry = fields.Datetime(
        string="Abandoned Cart Offer Expiry",
        copy=False,
    )
    # The currently active recovery discount percentage on the order
    abandoned_cart_active_discount = fields.Float(
        string="Active Recovery Discount (%)",
        default=0.0,
        copy=False,
    )

    # ── Config helpers ──────────────────────────────────────────────────

    def _get_cart_recovery_config(self):
        """Fetch the global config params for abandoned cart discount."""
        get = self.env['ir.config_parameter'].sudo().get_param
        def safe_float(key, default):
            val = get(key)
            return float(val) if val is not False and val is not None and str(val).strip() != '' else float(default)
            
        def safe_int(key, default):
            val = get(key)
            return int(val) if val is not False and val is not None and str(val).strip() != '' else int(default)

        return {
            'enabled': get('ecommerce_product_custom_discounts.abandoned_cart_discount_enabled', 'False') == 'True',
            'start': safe_float('ecommerce_product_custom_discounts.abandoned_cart_discount_start', 5),
            'step': safe_float('ecommerce_product_custom_discounts.abandoned_cart_discount_step', 5),
            'max': safe_float('ecommerce_product_custom_discounts.abandoned_cart_discount_max', 20),
            'hours': safe_int('ecommerce_product_custom_discounts.abandoned_cart_discount_hours', 24),
            'strategy': get('ecommerce_product_custom_discounts.abandoned_cart_strategy', 'reverse'),
            'delay_hours': safe_int('ecommerce_product_custom_discounts.abandoned_cart_delay_hours', 1),
        }

    def _get_wishlist_special_day_config(self):
        """Fetch the global config params for wishlist special day discount."""
        get = self.env['ir.config_parameter'].sudo().get_param
        enabled = get('ecommerce_product_custom_discounts.wishlist_special_day_enabled', 'False') == 'True'
        special_date_str = get('ecommerce_product_custom_discounts.wishlist_special_day_date', '')
        discount = float(get('ecommerce_product_custom_discounts.wishlist_special_day_discount', '15') or '15')

        special_date = False
        if special_date_str:
            try:
                special_date = fields.Date.from_string(special_date_str)
            except Exception:
                special_date = False

        return {
            'enabled': enabled,
            'special_date': special_date,
            'discount': discount,
        }

    # ── Abandoned Cart Discount Logic ───────────────────────────────────

    def _recompute_cart(self):
        """Override to ensure our custom discounts persist when the core
        eCommerce logic recomputes taxes and prices during checkout."""
        res = super()._recompute_cart()
        if self.state == 'draft' and self.order_line:
            self.sudo().action_apply_abandoned_cart_discount()
            self.sudo()._apply_best_discounts_to_lines()
        elif self.state == 'draft':
            self.sudo()._reset_abandoned_cart_discount()
        return res

    def _reset_abandoned_cart_discount(self):
        """Clear all abandoned cart discount state from the order."""
        self.sudo().write({
            'abandoned_cart_offer_expiry': False,
            'abandoned_cart_active_discount': 0.0,
            'abandoned_cart_discount_step_count': 0,
        })
        for line in self.order_line:
            if line.discount > 0:
                line.sudo().write({'discount': 0.0})

    def action_apply_abandoned_cart_discount(self):
        """
        Called on cart page load to compute and apply the next incremental
        discount step to the abandoned cart. Respects the max cap and offer
        expiry window.
        """
        self.ensure_one()
        cfg = self._get_cart_recovery_config()

        # If feature is disabled OR cart has no lines → clear any stale discount and stop
        if not cfg['enabled'] or not self.order_line:
            if self.abandoned_cart_active_discount > 0 or self.abandoned_cart_offer_expiry:
                self._reset_abandoned_cart_discount()
            return

        now = fields.Datetime.now()
        cart_creation = self.create_date or now
        delay_hours = cfg.get('delay_hours', 1)

        # Check if abandonment delay has NOT yet passed → reset stale state
        if delay_hours > 0 and now < cart_creation + timedelta(hours=delay_hours):
            if self.abandoned_cart_active_discount > 0 or self.abandoned_cart_offer_expiry:
                self._reset_abandoned_cart_discount()
            return

        # If offer not yet started, set expiry starting from now (or delay end)
        if not self.abandoned_cart_offer_expiry:
            offer_start = max(now, cart_creation + timedelta(hours=delay_hours))
            expiry = offer_start + timedelta(hours=cfg['hours'])
            self.sudo().write({'abandoned_cart_offer_expiry': expiry})

        # Check if offer expired
        if self.abandoned_cart_offer_expiry and now > self.abandoned_cart_offer_expiry:
            self._reset_abandoned_cart_discount()
            return

        # Calculate discount based on strategy
        total_hours = cfg['hours']
        step = cfg['step'] if cfg['step'] > 0 else 1.0
        steps_count = int(abs(cfg['max'] - cfg['start']) / step)
        bracket_duration = total_hours / (steps_count + 1) if (steps_count >= 0 and total_hours > 0) else total_hours
        
        offer_start = self.abandoned_cart_offer_expiry - timedelta(hours=total_hours)
        elapsed_offer_hours = max(0.0, (now - offer_start).total_seconds() / 3600.0)
        current_bracket = min(int(elapsed_offer_hours / bracket_duration), steps_count) if bracket_duration > 0 else 0

        if cfg['strategy'] == 'escalating':
            current_discount = min(cfg['start'] + (current_bracket * step), cfg['max'])
        else: # reverse / diminishing
            current_discount = max(cfg['max'] - (current_bracket * step), cfg['start'])

        if current_discount != self.abandoned_cart_active_discount or not self.abandoned_cart_discount_step_count:
            self.sudo().write({
                'abandoned_cart_active_discount': current_discount,
                'abandoned_cart_discount_step_count': current_bracket + 1,
            })

    def _apply_best_discounts_to_lines(self):
        """Apply the highest discount between Abandoned Cart and Wishlist to each line."""
        self.ensure_one()
        ab_discount = self.abandoned_cart_active_discount or 0.0
        wishlist_ids, wl_discount = self._get_wishlist_discount_info()
        
        for line in self.order_line:
            if line.product_id and line.product_id.type != 'service':
                best_discount = ab_discount
                if line.product_id.id in wishlist_ids:
                    best_discount = max(ab_discount, wl_discount)
                if line.discount != best_discount:
                    line.sudo().write({'discount': best_discount})

    def get_cart_recovery_discount_info(self):
        """
        Returns a dict consumed by the website JS to display the offer banner.
        Called via our custom controller from the frontend on cart page load.
        """
        self.ensure_one()
        cfg = self._get_cart_recovery_config()
        now = fields.Datetime.now()
        active = (
            cfg['enabled']
            and self.abandoned_cart_active_discount > 0
            and self.abandoned_cart_offer_expiry
            and now <= self.abandoned_cart_offer_expiry
        )
        return {
            'active': active,
            'discount_pct': self.abandoned_cart_active_discount,
            'expiry': self.abandoned_cart_offer_expiry.isoformat() if self.abandoned_cart_offer_expiry else False,
            'max_discount': cfg['max'],
        }

    # ── Wishlist Special Day Discount Logic ─────────────────────────────

    def _get_wishlist_discount_info(self):
        """
        Returns (set_of_product_ids_in_wishlist, discount_pct) if the wishlist
        special day discount is active today. Otherwise returns (set(), 0.0).
        """
        cfg = self._get_wishlist_special_day_config()
        if not cfg['enabled'] or not cfg['special_date']:
            return set(), 0.0

        today = fields.Date.today()
        if today != cfg['special_date']:
            return set(), 0.0

        discount = cfg['discount']
        wishlist_product_ids = set()
        partner = self.partner_id
        is_real_user = bool(
            partner
            and partner.user_ids
            and any(not u._is_public() for u in partner.user_ids)
        )

        if is_real_user:
            domain = [('partner_id', '=', partner.id), ('active', '=', True)]
            if self.website_id:
                domain.append(('website_id', '=', self.website_id.id))
            wishes = self.env['product.wishlist'].sudo().search(domain)
            wishlist_product_ids = set(wishes.mapped('product_id').ids)
        else:
            try:
                from odoo.http import request as http_request
                session_ids = http_request.session.get('wishlist_ids', [])
                if session_ids:
                    wishes = self.env['product.wishlist'].sudo().search([
                        ('id', 'in', session_ids),
                        ('active', '=', True),
                    ])
                    wishlist_product_ids = set(wishes.mapped('product_id').ids)
            except Exception:
                pass

        return wishlist_product_ids, discount