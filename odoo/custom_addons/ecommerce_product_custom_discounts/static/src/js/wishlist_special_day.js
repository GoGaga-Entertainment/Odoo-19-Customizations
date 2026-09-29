/**
 * ecommerce_product_custom_discounts — wishlist_special_day.js
 *
 * Patches WebsiteSale to fetch special-day config and render:
 *  1. A banner on the /shop/wishlist page
 *  2. Per-item discount badges on the wishlist page
 *  3. A banner on the /shop/cart page (when today is special day and user has
 *     wishlist items in their cart, the discount is already applied server-side)
 *
 * The actual line.discount is written server-side in the Cart controller.
 * This JS only handles the visual layer.
 */
import { patch } from '@web/core/utils/patch';
import { WebsiteSale } from '@website_sale/interactions/website_sale';

patch(WebsiteSale.prototype, {
    start() {
        super.start(...arguments);
        this._initWishlistSpecialDay();
        this._initWishlistCartBanner();
    },

    // ── Wishlist Page: banner + per-item badge ───────────────────────────

    async _initWishlistSpecialDay() {
        if (!window.location.pathname.includes('/shop/wishlist')) {
            return;
        }

        let info;
        try {
            const resp = await fetch('/ecommerce_product_custom_discounts/wishlist_special_day_info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
            });
            const data = await resp.json();
            info = data.result;
        } catch (e) {
            console.warn('[wishlist_special_day] fetch failed', e);
            return;
        }

        if (!info || !info.active) return;

        const discountPct = Math.round(info.discount_pct);

        // ── Top-of-page banner ────────────────────────────────────────────
        const wishlistHeader = document.querySelector(
            'h1, .o_wsale_wishlist h1, #wrap h1, .wishlist-title'
        );

        const bannerHtml = `
            <div class="o_custom_wishlist_day_banner d-flex align-items-start gap-2 px-3 py-2 mb-3"
                 style="background: linear-gradient(135deg,#fce4ec 0%,#ffeeff 100%);
                        border: 1.5px solid #f48fb1;
                        border-radius: 8px;">
                <i class="fa fa-heart mt-1 flex-shrink-0" style="color:#c2185b;" aria-hidden="true"></i>
                <div>
                    <strong style="color:#880e4f;font-size:0.95rem;">
                        💝 Today is your special day! Enjoy ${discountPct}% off everything in your wishlist.
                    </strong>
                    <div style="color:#6d4c41;font-size:0.82rem;margin-top:2px;">
                        Add any wishlist item to your cart today — the discount is applied automatically at checkout.
                    </div>
                </div>
            </div>`;

        if (wishlistHeader) {
            wishlistHeader.insertAdjacentHTML('afterend', bannerHtml);
        } else {
            const mainContent = document.querySelector('#wrap .container, #wrap, main');
            if (mainContent) {
                mainContent.insertAdjacentHTML('afterbegin', bannerHtml);
            }
        }

        // ── Per-item price badge ──────────────────────────────────────────
        const priceSelectors = [
            '.o_wish_list .o_wish_price',
            '.o_wish_list td.text-end',
            '.o_wish_list .oe_currency_value',
            '[data-wish-id] .oe_currency_value',
            '[data-wish-id] .product_price',
            '.o_wsale_product_wishlist .oe_currency_value',
        ];

        let priceEls = [];
        for (const sel of priceSelectors) {
            priceEls = Array.from(document.querySelectorAll(sel));
            if (priceEls.length > 0) break;
        }

        if (priceEls.length === 0) {
            priceEls = Array.from(
                document.querySelectorAll('table .oe_currency_value, table .js_price')
            );
        }

        priceEls.forEach(priceEl => {
            if (!priceEl.querySelector('.o_wishlist_special_day_badge')) {
                const badge = document.createElement('span');
                badge.className =
                    'o_wishlist_special_day_badge badge text-bg-warning ms-2 align-middle';
                badge.style.cssText = 'font-size:0.7rem;font-weight:500;white-space:nowrap;';
                badge.textContent = `−${discountPct}% today`;
                priceEl.insertAdjacentElement('afterend', badge);
            }
        });
    },

    // ── Cart Page: banner for wishlist special day discount ──────────────

    async _initWishlistCartBanner() {
        if (!window.location.pathname.includes('/shop/cart')) {
            return;
        }

        let info;
        try {
            const resp = await fetch('/ecommerce_product_custom_discounts/wishlist_special_day_info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
            });
            const data = await resp.json();
            info = data.result;
        } catch (e) {
            return;
        }

        if (!info || !info.active) return;

        // Fetch the current user's wishlist product IDs to see if any apply
        let wishlistProductIds = [];
        try {
            const resp2 = await fetch('/ecommerce_product_custom_discounts/wishlist_product_ids', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
            });
            const data2 = await resp2.json();
            wishlistProductIds = data2.result || [];
        } catch (e) {
            return;
        }

        if (!wishlistProductIds.length) return;

        const discountPct = Math.round(info.discount_pct);
        const cartSummary = document.querySelector(
            '.o_cart_summary, .js_cart_summary, #cart_total, ' +
            '[name="website_sale_cart_lines"], .o_wsale_cart_lines, #cart_products, #shop_cart'
        );
        if (!cartSummary) return;

        // Remove duplicate banners
        document.querySelectorAll('.o_custom_wishlist_cart_banner').forEach(el => el.remove());

        const wrapper = document.createElement('div');
        wrapper.classList.add('o_custom_wishlist_cart_banner');
        wrapper.innerHTML = `
            <div class="alert mb-3 d-flex align-items-center gap-3"
                 style="background: linear-gradient(135deg,#fce4ec 0%,#ffeeff 100%);
                        border: 1.5px solid #f48fb1;
                        border-radius: 8px;">
                <i class="fa fa-heart fa-lg flex-shrink-0" style="color:#c2185b;" aria-hidden="true"></i>
                <div>
                    <strong style="color:#880e4f;font-size:0.95rem;">
                        💝 Wishlist Special Day — ${discountPct}% discount applied to your wishlist items!
                    </strong>
                    <div style="color:#6d4c41;font-size:0.82rem;margin-top:2px;">
                        Today only. Complete your purchase to redeem this exclusive offer.
                    </div>
                </div>
            </div>`;

        cartSummary.insertAdjacentElement('beforebegin', wrapper);
    },
});