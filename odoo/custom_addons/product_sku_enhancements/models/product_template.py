# -*- coding: utf-8 -*-
"""
Template-level SKU generation hooks and template configuration for product.template.

Provides:
1. ``sku_template_id``: Many2one to product.sku.template.
2. ``action_generate_all_skus()``: Button action to generate SKUs for all variants.
3. ``action_clear_generated_skus()``: Button action to launch the safe Clear SKUs wizard.
4. Auto-generation helper when variants are created and a template is configured.
5. ``_get_combination_info`` override: injects ``default_code`` (SKU) into the combination
   info dict so the website product page always displays the correct variant SKU.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    sku_template_id = fields.Many2one(
        'product.sku.template',
        string="SKU Infix Template",
        ondelete='restrict',
        help="Select the SKU Infix Template to use for generating SKUs for this product. "
             "All variants of this product will use this template.",
    )

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def action_generate_all_skus(self):
        """Generate SKUs for all active variants of selected templates that lack one.

        Uses the assigned SKU Product Code if active, or the Fallback SKU Sequence
        if no template, inactive template (Active = OFF), or no SKU Infix is configured.
        """
        variants_without_sku = self.product_variant_ids.filtered(
            lambda v: not v.default_code
        )
        if not variants_without_sku:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _(""),
                    'message': _("Internal References generated"),
                    'type': 'info',
                    'sticky': False,
                },
            }
        return variants_without_sku.action_generate_sku()

    def action_clear_generated_skus(self):
        """Open the safe Clear Generated SKUs confirmation wizard."""
        self.ensure_one()
        return {
            'name': _("Clear Generated SKUs - %s", self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'sku.clear.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_tmpl_id': self.id,
            },
        }

    # ------------------------------------------------------------------
    # Helper for variant SKU generation
    # ------------------------------------------------------------------

    def _auto_generate_variant_skus(self, variants):
        """Generate SKUs for variants only if an active SKU Product Code is configured.

        Silently skips if no template is set or archived so that incorrectly formatted SKUs are never produced.
        """
        self.ensure_one()
        if not self.sku_template_id or not self.sku_template_id.active or not variants:
            return

        for variant in variants.filtered(lambda v: not v.default_code):
            try:
                new_sku = variant._build_sku()
                if new_sku:
                    variant.sudo().write({
                        'default_code': new_sku,
                        'is_sku_generated': True,
                    })
            except Exception:  # noqa: BLE001
                _logger.exception(
                    "product_sku_enhancements: Failed to auto-generate SKU "
                    "for variant %s (%d)",
                    variant.display_name,
                    variant.id,
                )

    # ------------------------------------------------------------------
    # Website combination info: inject SKU / default_code
    # ------------------------------------------------------------------

    def _get_combination_info(
        self, combination=False, product_id=False, add_qty=1.0, uom_id=False, only_template=False,
    ):
        """Extend combination info to include the variant's default_code (SKU).

        Called by the website_sale variant controller for both the initial page
        render and every variant-change JSON-RPC call.  Injecting here ensures
        the SKU is available in the QWeb template AND in the JS combination object
        so the frontend can update the displayed value without a page reload.
        """
        combination_info = super()._get_combination_info(
            combination=combination,
            product_id=product_id,
            add_qty=add_qty,
            uom_id=uom_id,
            only_template=only_template,
        )

        # Resolve the concrete variant for this combination
        variant_id = combination_info.get('product_id')
        if variant_id:
            variant = self.env['product.product'].browse(variant_id)
            combination_info['default_code'] = variant.default_code or ''
        else:
            combination_info['default_code'] = self.default_code or ''

        return combination_info
