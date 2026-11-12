# -*- coding: utf-8 -*-
"""
Generate and store dynamic QR Code binary image for Product Variant.

Value Priority:
1. default_code (SKU / Internal Reference)
2. barcode
3. product ID (str)
"""

import base64
import io
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

try:
    import qrcode
except ImportError:
    _logger.warning("The 'qrcode' Python library is not installed. QR code generation will fail until installed.")
    qrcode = None


class ProductProduct(models.Model):
    _inherit = 'product.product'

    qr_code_image = fields.Binary(
        string="QR Code Image",
        compute='_compute_qr_code_image',
        store=True,
        attachment=True,
        help="QR code containing the variant's Internal Reference (SKU), Barcode, or ID.",
    )

    qr_code_value = fields.Char(
        string="QR Code Encoded Value",
        compute='_compute_qr_code_image',
        store=True,
        help="The raw text value encoded in the QR code.",
    )

    @api.depends('default_code', 'barcode')
    def _compute_qr_code_image(self):
        for product in self:
            val = product.default_code or product.barcode or (str(product.id) if product.id else False)
            product.qr_code_value = val

            if not val or not qrcode:
                product.qr_code_image = False
                continue

            try:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=6,
                    border=2,
                )
                qr.add_data(val)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")

                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                product.qr_code_image = base64.b64encode(buffer.getvalue())
            except Exception as e:
                _logger.error("Failed to generate QR code for product ID %s: %s", product.id, e)
                product.qr_code_image = False

    def _get_variant_attribute_values_str(self):
        """Return formatted string of variant attribute values separated by a space (e.g. 'BLK XS').

        Excludes 'no_variant' attributes, orders by attribute line sequence and id,
        and returns an empty string if the product has no variant attributes.
        """
        self.ensure_one()
        ptavs = self.product_template_attribute_value_ids.filtered(
            lambda v: v.attribute_id.create_variant != 'no_variant'
        ).sorted(key=lambda v: (v.attribute_line_id.sequence, v.attribute_line_id.id, v.id))
        if not ptavs:
            return ''
        return ' '.join(ptav.name for ptav in ptavs if ptav.name)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    qr_code_image = fields.Binary(
        string="QR Code Image",
        compute='_compute_qr_code_image',
        help="QR code image for the primary variant.",
    )
    qr_code_value = fields.Char(
        string="QR Code Encoded Value",
        compute='_compute_qr_code_image',
        help="QR code value for the primary variant.",
    )

    @api.depends('product_variant_ids.qr_code_image', 'product_variant_ids.qr_code_value')
    def _compute_qr_code_image(self):
        for template in self:
            variant = template.product_variant_id
            template.qr_code_image = variant.qr_code_image if variant else False
            template.qr_code_value = variant.qr_code_value if variant else False

    def _get_variant_attribute_values_str(self):
        """Return formatted string of variant attribute values for this template's primary variant."""
        self.ensure_one()
        if self.product_variant_id:
            return self.product_variant_id._get_variant_attribute_values_str()
        return ''

    def _get_combination_info(
        self, combination=False, product_id=False, add_qty=1.0, uom_id=False, only_template=False,
    ):
        combination_info = super()._get_combination_info(
            combination=combination,
            product_id=product_id,
            add_qty=add_qty,
            uom_id=uom_id,
            only_template=only_template,
        )
        variant_id = combination_info.get('product_id')
        qr_img = False
        if variant_id:
            variant = self.env['product.product'].browse(variant_id)
            qr_img = variant.qr_code_image
        elif self.product_variant_id:
            qr_img = self.product_variant_id.qr_code_image
        else:
            qr_img = self.qr_code_image

        if qr_img:
            if isinstance(qr_img, bytes):
                combination_info['qr_code_image'] = qr_img.decode('utf-8')
            else:
                combination_info['qr_code_image'] = str(qr_img)
        else:
            combination_info['qr_code_image'] = False

        return combination_info


