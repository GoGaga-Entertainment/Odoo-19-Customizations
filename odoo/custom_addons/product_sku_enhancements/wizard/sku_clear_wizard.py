# -*- coding: utf-8 -*-
"""
Wizard to safely clear generated SKU / Internal Reference values.

Safety features:
- Requires user confirmation.
- Explains which products/variants are affected.
- Clears ONLY default_code and is_sku_generated.
- Preserves products, variants, barcodes, QR codes, and sequence settings.
- Skips manually assigned SKUs unless explicitly requested by the user.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SkuClearWizard(models.TransientModel):
    _name = 'sku.clear.wizard'
    _description = 'Clear Generated SKUs Wizard'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string="Product Template",
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string="Product Variant",
        readonly=True,
    )
    product_variant_ids = fields.Many2many(
        'product.product',
        string="Targeted Variants",
        compute='_compute_variants',
        readonly=True,
    )
    generated_sku_count = fields.Integer(
        string="Auto-Generated SKUs",
        compute='_compute_variants',
        readonly=True,
        help="Number of variants with auto-generated SKUs that will be cleared.",
    )
    manual_sku_count = fields.Integer(
        string="Manually Assigned SKUs",
        compute='_compute_variants',
        readonly=True,
        help="Number of variants with manually assigned SKUs that will be preserved by default.",
    )
    clear_manual_skus = fields.Boolean(
        string="Also clear manually assigned Internal References",
        default=False,
        help="If unchecked, only SKUs created by the auto-generation system will be cleared. "
             "Manually assigned references will be safely kept.",
    )

    @api.depends('product_tmpl_id', 'product_id')
    def _compute_variants(self):
        for wizard in self:
            if wizard.product_id:
                variants = wizard.product_id
            elif wizard.product_tmpl_id:
                variants = wizard.product_tmpl_id.product_variant_ids
            else:
                variants = self.env['product.product']
            wizard.product_variant_ids = variants
            variants_with_code = variants.filtered(lambda v: bool(v.default_code))
            wizard.generated_sku_count = len(variants_with_code.filtered(lambda v: v.is_sku_generated))
            wizard.manual_sku_count = len(variants_with_code.filtered(lambda v: not v.is_sku_generated))

    def action_confirm_clear(self):
        """Safely clear default_code on targeted variants without deleting products, barcodes, or QR codes."""
        self.ensure_one()
        variants = self.product_variant_ids.filtered(lambda v: bool(v.default_code))
        if not self.clear_manual_skus:
            # By default, only clear auto-generated SKUs
            variants = variants.filtered(lambda v: v.is_sku_generated)

        cleared_count = len(variants)
        if cleared_count:
            # Safely reset default_code and is_sku_generated flag only
            variants.write({
                'default_code': False,
                'is_sku_generated': False,
            })
            message = _(
                "Internal References cleared. SKUs for %d variants cleared successfully.",
                cleared_count,
            )
            msg_type = 'success'
        else:
            message = _("Internal References cleared. SKUs for 0 variants cleared successfully.")
            msg_type = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(""),
                'message': message,
                'type': msg_type,
                'sticky': False,
            },
        }
