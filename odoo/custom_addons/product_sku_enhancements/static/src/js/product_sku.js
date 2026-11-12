/** @odoo-module **/
/**
 * product_sku_enhancements — product_sku.js
 *
 * Patches WebsiteSale (Odoo 19 Interaction pattern) to update the displayed
 * SKU / Internal Reference whenever the customer selects a different product
 * variant on the product detail page.
 *
 * The server already injects `default_code` into the combination_info dict via
 * the product.template._get_combination_info() model override.
 * This JS patch reads that value on every variant change and syncs the #product_sku
 * container rendered by the QWeb template (website_templates.xml).
 */

import { patch } from '@web/core/utils/patch';
import { WebsiteSale } from '@website_sale/interactions/website_sale';

patch(WebsiteSale.prototype, {

    /**
     * Override _onChangeCombination to sync the SKU display whenever the
     * customer selects a different product variant.
     *
     * @param {Event}   ev          - change event that triggered the combination fetch
     * @param {Element} parent      - closest .js_product element
     * @param {Object}  combination - combination_info dict returned by the server
     */
    _onChangeCombination(ev, parent, combination) {
        // Always call the parent handler first (price, stock, images, etc.)
        super._onChangeCombination(...arguments);
        this._updateSkuDisplay(parent, combination);
    },

    /**
     * Sync the #product_sku element content with the variant's default_code.
     *
     * Shows the container when a SKU is available and hides it when the
     * variant has no Internal Reference assigned.
     *
     * @param {Element} parent      - .js_product container element
     * @param {Object}  combination - combination_info dict from server
     */
    _updateSkuDisplay(parent, combination) {
        const skuContainer = parent.querySelector('#product_sku');
        const skuSpan = parent.querySelector('#product_sku .js_sku');
        if (!skuContainer || !skuSpan) {
            return;
        }
        const skuVal = (combination && combination.default_code) ? combination.default_code : '';
        skuSpan.textContent = skuVal;
        skuContainer.classList.toggle('d-none', !skuVal);
    },
});
