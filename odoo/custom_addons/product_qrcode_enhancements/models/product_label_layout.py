# -*- coding: utf-8 -*-
import base64
import io
import logging

from odoo import api, fields, models
from odoo.tools.misc import file_open

_logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None
    ImageDraw = None


class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'

    zpl_preview = fields.Image(
        'ZPL Preview',
        readonly=True,
        compute='_compute_zpl_preview',
    )

    @api.depends('print_format', 'zpl_template', 'product_ids', 'product_tmpl_ids')
    def _compute_zpl_preview(self):
        for wizard in self:
            placeholder_b64 = wizard._get_zpl_label_placeholder()
            if not wizard.print_format or 'zpl' not in wizard.print_format:
                wizard.zpl_preview = placeholder_b64
                continue

            product = False
            if wizard.product_ids:
                product = wizard.product_ids[0]
            elif wizard.product_tmpl_ids:
                product = wizard.product_tmpl_ids[0].product_variant_id or wizard.product_tmpl_ids[0]
            elif hasattr(wizard, 'move_ids') and wizard.move_ids:
                product = wizard.move_ids[0].product_id

            if not product or not getattr(product, 'qr_code_image', None) or not Image:
                wizard.zpl_preview = placeholder_b64
                continue

            try:
                # Load base placeholder image (456 x 253 px)
                with file_open('stock/static/img/zpl_label_placeholder.png', 'rb') as f:
                    base_img = Image.open(f).convert('RGBA')

                # Load variant QR code image
                qr_bytes = base64.b64decode(product.qr_code_image)
                qr_img = Image.open(io.BytesIO(qr_bytes)).convert('RGBA')
                # Resize QR code to fit cleanly in empty area: 100 x 100 px
                qr_img = qr_img.resize((100, 100), Image.Resampling.LANCZOS)

                # Paste in empty area to the right of barcode (X: 290, Y: 70)
                base_img.paste(qr_img, (290, 70), mask=qr_img)

                # Draw actual product name and variant over placeholder title area
                if ImageDraw:
                    draw = ImageDraw.Draw(base_img)
                    draw.rectangle([(25, 10), (430, 65)], fill=(255, 255, 255, 255))
                    name_text = product.name or ''
                    if len(name_text) > 32:
                        name_text = name_text[:29] + '...'
                    var_text = product._get_variant_attribute_values_str() if hasattr(product, '_get_variant_attribute_values_str') else ''
                    if var_text:
                        if len(var_text) > 36:
                            var_text = var_text[:33] + '...'
                        draw.text((35, 14), name_text, fill=(0, 0, 0, 255))
                        draw.text((35, 36), var_text, fill=(80, 80, 80, 255))
                    else:
                        draw.text((35, 22), name_text, fill=(0, 0, 0, 255))

                output = io.BytesIO()
                base_img.convert('RGB').save(output, format='PNG')
                wizard.zpl_preview = base64.b64encode(output.getvalue())
            except Exception as e:
                _logger.warning("Failed to render composite ZPL preview with QR: %s", e)
                wizard.zpl_preview = placeholder_b64
