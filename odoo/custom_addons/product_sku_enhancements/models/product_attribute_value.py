# -*- coding: utf-8 -*-
"""
Extend product.attribute.value with an optional SKU Short Code.

The short code is used when constructing variant Internal References so that
each variant combination produces a compact, unique SKU segment.

Examples:
    Attribute Value "Navy Blue"  → sku_short_code = "NVY"
    Attribute Value "Extra Large" → sku_short_code = "XL"

If left empty the system will auto-derive a short code from the value name
at SKU-generation time (first 5 uppercase non-space chars).
"""

from odoo import fields, models


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    sku_short_code = fields.Char(
        string="SKU Short Code",
        size=10,
        help=(
            "Short alphabetic code used in the auto-generated Internal Reference "
            "(SKU) for product variants that use this attribute value.\n"
            "Example: 'NVY' for Navy, 'XL' for Extra Large.\n"
            "If left empty the system will derive one from the first characters "
            "of the value name."
        ),
    )

    # ------------------------------------------------------------------
    # Helper used by the SKU generation logic
    # ------------------------------------------------------------------

    def _get_sku_segment(self):
        """Return the SKU segment for this attribute value.

        Returns ``sku_short_code`` if set, otherwise derives a segment from the
        first 5 uppercase non-whitespace characters of ``name``.
        """
        self.ensure_one()
        if self.sku_short_code:
            return self.sku_short_code.strip().upper()
        # Derive: strip spaces, take first 5 chars, uppercase
        cleaned = ''.join(self.name.split())
        return cleaned[:5].upper()
