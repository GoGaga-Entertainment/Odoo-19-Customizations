/**
 * ecommerce_product_custom_discounts — abandoned_cart_discount.js
 *
 * Patches WebsiteSale to fetch the current recovery discount info
 * and render a countdown banner on the cart page.
 *
 * The actual discount has already been written to order lines server-side
 * (by the Cart controller override). This JS only handles the UI banner
 * and countdown timer.
 */
import { patch } from '@web/core/utils/patch';
import { WebsiteSale } from '@website_sale/interactions/website_sale';

patch(WebsiteSale.prototype, {
    start() {
        super.start(...arguments);
        this._initAbandonedCartBanner();
    },

    async _initAbandonedCartBanner() {
        // Only run on the cart page
        if (!window.location.pathname.includes('/shop/cart')) {
            return;
        }

        // Find a suitable anchor in the cart page
        const cartSummary = document.querySelector(
            '.o_cart_summary, .js_cart_summary, #cart_total, .oe_website_sale .cart_total, ' +
            '[name="website_sale_cart_lines"], .o_wsale_cart_lines, #cart_products, #shop_cart'
        );
        if (!cartSummary) {
            return;
        }

        let info;
        try {
            const resp = await fetch('/ecommerce_product_custom_discounts/cart_discount_info', {
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
            console.warn('[abandoned_cart_discount] fetch failed', e);
            return;
        }

        if (!info || !info.active) return;

        // Remove any existing banner (prevent duplicates on SPA navigation)
        document.querySelectorAll('.o_custom_abandoned_cart_banner').forEach(el => el.remove());

        // Build the banner HTML
        const discountPct = Math.round(info.discount_pct);
        const maxDiscount = Math.round(info.max_discount);

        const wrapper = document.createElement('div');
        wrapper.classList.add('o_custom_abandoned_cart_banner');
        wrapper.innerHTML = `
            <div class="alert mb-3 d-flex align-items-center gap-3"
                 style="background: linear-gradient(135deg,#fff8e1 0%,#fffde7 100%);
                        border: 1.5px solid #ffe082;
                        border-radius: 8px;">
                <i class="fa fa-tag fa-lg flex-shrink-0" style="color:#f57f17;" aria-hidden="true"></i>
                <div>
                    <strong style="color:#e65100;font-size:0.95rem;">
                        🎉 Special offer: ${discountPct}% off your cart!
                    </strong>
                    <div style="color:#6d4c41;font-size:0.82rem;margin-top:2px;">
                        Complete your purchase before this offer expires — up to
                        ${maxDiscount}% discount available.
                        &nbsp;Expires in: <strong class="o_cart_banner_timer">--:--:--</strong>
                    </div>
                </div>
            </div>`;

        cartSummary.insertAdjacentElement('beforebegin', wrapper);
        this._startAbandonedCartCountdown(wrapper, info.expiry);
    },

    _startAbandonedCartCountdown(wrapper, expiryIso) {
        const timerEl = wrapper.querySelector('.o_cart_banner_timer');
        if (!timerEl || !expiryIso) return;

        // Ensure the expiry string is parsed as UTC
        const expiryStr = expiryIso.endsWith('Z') ? expiryIso : expiryIso + 'Z';
        const expiry = new Date(expiryStr).getTime();

        const tick = () => {
            const remaining = expiry - Date.now();
            if (remaining <= 0) {
                wrapper.remove();
                return;
            }
            const h = Math.floor(remaining / 3600000);
            const m = Math.floor((remaining % 3600000) / 60000);
            const s = Math.floor((remaining % 60000) / 1000);
            timerEl.textContent =
                `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
            this._abandonedCartTimer = setTimeout(tick, 1000);
        };
        tick();
    },

    destroy() {
        super.destroy(...arguments);
        if (this._abandonedCartTimer) {
            clearTimeout(this._abandonedCartTimer);
        }
    }
});