/**
 * ecommerce_product_custom_discounts — back_in_stock_mixin.js
 *
 * Patches WebsiteSale to:
 *
 *  1. Render the "Back in Stock Message" (from combination_info.back_in_stock_message)
 *     into the `.availability_messages` div, below the default stock availability badge,
 *     whenever free_qty > 0 and the field is non-empty.
 *
 *  2. Keep the "(XX% OFF)" badge (rendered server-side in product_price)
 *     in sync during variant changes and on initial page load.
 */
import { patch } from '@web/core/utils/patch';
import { renderToFragment } from '@web/core/utils/render';
import { markup } from '@odoo/owl';
import { WebsiteSale } from '@website_sale/interactions/website_sale';

patch(WebsiteSale.prototype, {

    /**
     * On start, refresh the discount badge using DOM prices already rendered
     * server-side. This ensures the badge shows without needing a variant change.
     */
    start() {
        super.start(...arguments);
        this._refreshDiscountBadgeFromDOM();
    },

    /**
     * Override _onChangeCombination to also handle:
     *   - Back in Stock custom message rendering
     *   - Discount clarity badge synchronisation
     *
     * @param {Event} ev
     * @param {Element} parent
     * @param {Object} combination  - combination_info dict returned by server
     */
    _onChangeCombination(ev, parent, combination) {
        // Call the parent logic first (price update, stock UI, etc.)
        super._onChangeCombination(...arguments);

        this._updateBackInStockMessage(parent, combination);
        this._updateDiscountClarityBadge(parent, combination);
    },

    // ──────────────────────────────────────────────────────────────────
    // 1. Back In Stock Message
    // ──────────────────────────────────────────────────────────────────

    /**
     * Appends the custom "Back in Stock Message" to the .availability_messages
     * container when the product is in stock and the message is non-empty.
     * Removes any previously rendered instance first.
     *
     * @param {Element} parent   - .js_product container element
     * @param {Object}  combination - combination_info from server
     */
    _updateBackInStockMessage(parent, combination) {
        // Remove previous render
        parent.querySelectorAll('.o_custom_back_in_stock_rendered').forEach(el => el.remove());

        // Clear any previous timeout
        if (this._backInStockTimeout) {
            clearTimeout(this._backInStockTimeout);
            this._backInStockTimeout = null;
        }

        const availMsgEl = parent.querySelector('div.availability_messages');
        if (!availMsgEl) {
            return;
        }

        // Only show when:
        //  • product is a tracked storable
        //  • the Sales Manager has configured a message
        //  • trigger time is within the configured window
        if (
            !combination.is_storable ||
            !combination.back_in_stock_message ||
            !combination.back_in_stock_message.trim() ||
            !combination.back_in_stock_trigger_time
        ) {
            return;
        }

        // Calculate time difference
        const triggerTime = new Date(combination.back_in_stock_trigger_time + 'Z').getTime();
        const now = Date.now();
        const displayDurationMs = 5 * 60 * 1000; // 5 minutes
        const elapsedMs = now - triggerTime;

        if (elapsedMs > displayDurationMs) {
            return;
        }

        // Mark the HTML value as safe markup (field is Html type in Odoo)
        const combinationData = {
            ...combination,
            back_in_stock_message: markup(combination.back_in_stock_message),
        };

        // Render with our OWL template
        const fragment = renderToFragment(
            'ecommerce_product_custom_discounts.back_in_stock_message',
            combinationData
        );

        // Wrap in a container so we can target it for cleanup
        const wrapper = document.createElement('div');
        wrapper.classList.add('o_custom_back_in_stock_rendered');
        wrapper.style.transition = 'opacity 0.5s ease-out';
        wrapper.appendChild(fragment);

        availMsgEl.appendChild(wrapper);

        // Auto-hide after the remaining time
        const timeRemaining = displayDurationMs - elapsedMs;
        this._backInStockTimeout = setTimeout(() => {
            if (wrapper && wrapper.parentNode) {
                wrapper.style.opacity = '0';
                setTimeout(() => wrapper.remove(), 500);
            }
        }, timeRemaining);
    },

    // ──────────────────────────────────────────────────────────────────
    // 2. Discount Clarity Badge synchronisation
    // ──────────────────────────────────────────────────────────────────

    /**
     * On initial page load, Odoo renders prices server-side but the JS
     * variant change event never fires. This reads the rendered prices
     * directly from the DOM and injects/shows the badge immediately.
     */
    _refreshDiscountBadgeFromDOM() {
        document.querySelectorAll('.js_product').forEach(parent => {
            const listPriceSpan = parent.querySelector('.oe_default_price');
            const comparePriceSpan = parent.querySelector('.oe_compare_list_price');
            const currentPriceSpan = parent.querySelector('.oe_price');
            if (!currentPriceSpan) return;

            let originalPriceSpan = null;
            if (listPriceSpan && !listPriceSpan.classList.contains('d-none')) {
                originalPriceSpan = listPriceSpan;
            } else if (comparePriceSpan && !comparePriceSpan.classList.contains('d-none')) {
                originalPriceSpan = comparePriceSpan;
            }

            if (!originalPriceSpan) {
                // No discount active — ensure badge is hidden
                const existingBadge = parent.querySelector('.o_custom_discount_clarity');
                if (existingBadge) existingBadge.classList.add('d-none');
                return;
            }

            // Odoo renders monetary values using the monetary widget; we parse the number
            // by stripping currency symbols and thousands separators.
            const parseMonetary = (el) => {
                if (!el) return NaN;
                const raw = el.textContent.replace(/[^0-9.,\-]/g, '').replace(/,/g, '');
                return parseFloat(raw);
            };

            const origPrice = parseMonetary(originalPriceSpan);
            const currentPrice = parseMonetary(currentPriceSpan);

            if (!isNaN(origPrice) && !isNaN(currentPrice) && origPrice > currentPrice && origPrice > 0) {
                const discountPct = Math.round(((origPrice - currentPrice) / origPrice) * 100);
                if (discountPct > 0) {
                    this._renderOrUpdateBadge(parent, discountPct, originalPriceSpan);
                }
            } else {
                const existingBadge = parent.querySelector('.o_custom_discount_clarity');
                if (existingBadge) existingBadge.classList.add('d-none');
            }
        });
    },

    /**
     * Keeps the "(XX% OFF)" badge in sync when the customer switches variants.
     *
     * @param {Element} parent      - .js_product container element
     * @param {Object}  combination - combination_info from server
     */
    _updateDiscountClarityBadge(parent, combination) {
        const cpPrice = combination.price || 0;
        let cpBase = 0;
        let anchorSpan = null;

        if (combination.has_discounted_price && combination.list_price > cpPrice) {
            cpBase = combination.list_price;
            anchorSpan = parent.querySelector('.oe_default_price');
        } else if (combination.compare_list_price && combination.compare_list_price > cpPrice) {
            cpBase = combination.compare_list_price;
            anchorSpan = parent.querySelector('.oe_compare_list_price');
        }

        if (cpBase <= 0 || !anchorSpan) {
            const badge = parent.querySelector('.o_custom_discount_clarity');
            if (badge) badge.classList.add('d-none');
            return;
        }

        const discountPct = Math.round(((cpBase - cpPrice) / cpBase) * 100);
        if (discountPct > 0) {
            this._renderOrUpdateBadge(parent, discountPct, anchorSpan);
        } else {
            const badge = parent.querySelector('.o_custom_discount_clarity');
            if (badge) badge.classList.add('d-none');
        }
    },

    /**
     * Shared helper: show/update the badge in the given product container.
     * Creates the badge if it doesn't exist yet.
     *
     * @param {Element} parent      - .js_product container element
     * @param {number}  discountPct - integer percentage to display
     * @param {Element} anchorSpan   - the element to place the badge after
     */
    _renderOrUpdateBadge(parent, discountPct, anchorSpan) {
        let badge = parent.querySelector('.o_custom_discount_clarity');
        if (badge) {
            badge.textContent = `(${discountPct}% OFF)`;
            badge.classList.remove('d-none');
            if (anchorSpan && badge.previousElementSibling !== anchorSpan) {
                anchorSpan.insertAdjacentElement('afterend', badge);
            }
        } else {
            if (!anchorSpan) return;
            badge = document.createElement('span');
            badge.setAttribute('name', 'o_custom_discount_clarity');
            badge.className =
                'o_custom_discount_clarity badge text-bg-success ms-1 align-middle';
            badge.style.cssText =
                'font-size: 0.72rem; font-weight: 500; white-space: nowrap;';
            badge.textContent = `(${discountPct}% OFF)`;
            anchorSpan.insertAdjacentElement('afterend', badge);
        }
    },

    destroy() {
        super.destroy(...arguments);
        if (this._abandonedCartTimer) {
            clearTimeout(this._abandonedCartTimer);
        }
        if (this._backInStockTimeout) {
            clearTimeout(this._backInStockTimeout);
        }
    },
});
