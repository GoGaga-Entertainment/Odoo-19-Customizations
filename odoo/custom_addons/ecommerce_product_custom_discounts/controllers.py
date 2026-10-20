# Part of custom addon - ecommerce_product_custom_discounts
from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.cart import Cart


class SaleStockCustomController(http.Controller):
    """
    Custom JSON endpoints for discount info banners (read-only, no state mutation).
    These are called by the frontend JS to decide whether to render banners.
    """


    @http.route(
        '/ecommerce_product_custom_discounts/cart_discount_info',
        type='jsonrpc',
        auth='public',
        website=True,
        csrf=False,
    )
    def cart_discount_info(self, **kwargs):
        """
        Returns the active abandoned cart recovery discount info for the
        current visitor's cart.  The session holds the sale_order_id so we
        do not need the frontend to pass an order ID.
        """
        order = request.cart
        if not order:
            return {'active': False}

        try:
            return order.sudo().get_cart_recovery_discount_info()
        except Exception:
            return {'active': False}


    @http.route(
        '/ecommerce_product_custom_discounts/wishlist_special_day_info',
        type='jsonrpc',
        auth='public',
        website=True,
        csrf=False,
    )
    def wishlist_special_day_info(self, **kwargs):
        """
        Returns the wishlist special day configuration so the frontend JS
        can display the banner and per-item badge on the correct date.
        """
        try:
            return request.env['product.wishlist'].sudo().get_wishlist_special_day_info()
        except Exception:
            return {'active': False}


    @http.route(
        '/ecommerce_product_custom_discounts/wishlist_product_ids',
        type='jsonrpc',
        auth='public',
        website=True,
        csrf=False,
    )
    def wishlist_product_ids(self, **kwargs):
        """
        Returns the list of product.product IDs in the current user's wishlist,
        used by the frontend JS to highlight cart lines with the special day badge.
        """
        try:
            return request.env['product.wishlist'].get_current_partner_wishlist_product_ids()
        except Exception:
            return []


class SaleStockCustomCart(Cart):
    """
    Extends the core Cart controller to inject discount logic on the cart page
    load — without any scheduled actions or automation rules.

    Strategy:
      • Abandoned Cart: on every `/shop/cart` GET, compute and write the current
        incremental discount step onto the order lines.
      • Wishlist Special Day: on every `/shop/cart` GET (if today is the special
        day), apply the configured discount % to any cart line whose product
        is in the customer's wishlist.
    """

    @http.route()
    def cart(self, id=None, access_token=None, revive_method='', **post):
        """Override to apply discount logic before rendering the cart page."""
        # Let the parent render first so the cart is fully set up in the session
        response = super().cart(
            id=id,
            access_token=access_token,
            revive_method=revive_method,
            **post,
        )

        # Apply discounts to the current cart (if one exists)
        # request.cart uses Odoo 19 style (replaces sale_get_order)
        try:
            order = request.cart
            if order and order.state == 'draft':
                if order.order_line:
                    # Cart has items: compute and apply best discount per line
                    order.sudo().action_apply_abandoned_cart_discount()
                    order.sudo()._apply_best_discounts_to_lines()
                else:
                    # Cart is empty: wipe any stale discount state left from previous items
                    order.sudo()._reset_abandoned_cart_discount()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                '[ecommerce_product_custom_discounts] Discount application failed: %s', e
            )
        return response