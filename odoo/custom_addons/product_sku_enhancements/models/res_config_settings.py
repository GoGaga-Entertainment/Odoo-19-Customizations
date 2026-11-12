# -*- coding: utf-8 -*-
"""
SKU configuration settings extension for res.config.settings.

Provides Fallback SKU Sequence configuration under Inventory -> Configuration -> Settings.
Global prefix and suffix are centrally managed through User Settings -> Sequences (ir.sequence).
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_PARAM_SEQ_ID = 'product_sku.sequence_id'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    sku_sequence_id = fields.Many2one(
        comodel_name='ir.sequence',
        string="Fallback SKU Sequence",
        config_parameter=_PARAM_SEQ_ID,
        domain="[('active', '=', True)]",
        help=(
            "Fallback sequence used ONLY when a product or variant does not have an "
            "SKU Product Code Template with an SKU Infix assigned."
        ),
    )

    @api.constrains('sku_sequence_id')
    def _check_sku_sequence_id(self):
        for rec in self:
            if rec.sku_sequence_id:
                if not rec.sku_sequence_id.active:
                    raise ValidationError(_("The selected Fallback SKU Sequence must be active."))
                if rec.sku_sequence_id.code == 'product.sku.global':
                    raise ValidationError(_(
                        "The Global Product SKU Configuration sequence cannot be used as the Fallback sequence."
                    ))
                if rec.sku_sequence_id.number_increment <= 0:
                    raise ValidationError(_(
                        "The Fallback SKU Sequence must have an increment greater than 0."
                    ))
