/** @odoo-module **/

import { patch } from '@web/core/utils/patch';
import { WebsiteSale } from '@website_sale/interactions/website_sale';

patch(WebsiteSale.prototype, {
    /**
     * Override _onChangeCombination to update the displayed QR Code
     * whenever the customer selects a different product variant.
     *
     * @override
     * @param {Event} ev
     * @param {Element} parent - Closest .js_product element
     * @param {Object} combination - combination_info dictionary from server
     */
    _onChangeCombination(ev, parent, combination) {
        super._onChangeCombination(...arguments);
        this._updateQrCodeDisplay(parent, combination);
    },

    /**
     * Dynamically updates or hides the QR code image element.
     *
     * @param {Element} parent
     * @param {Object} combination
     */
    _updateQrCodeDisplay(parent, combination) {
        const qrContainer = (parent && parent.querySelector('#product_qr_code'))
            || document.querySelector('#product_qr_code');
        if (!qrContainer) {
            return;
        }
        const qrImg = qrContainer.querySelector('.product_qr_code_img');
        const qrData = (combination && combination.qr_code_image) ? combination.qr_code_image : null;

        if (qrData && qrImg) {
            qrImg.src = 'data:image/png;base64,' + qrData;
            qrContainer.classList.remove('d-none');
        } else {
            qrContainer.classList.add('d-none');
            if (qrImg) {
                qrImg.src = '';
            }
        }
    },
});
