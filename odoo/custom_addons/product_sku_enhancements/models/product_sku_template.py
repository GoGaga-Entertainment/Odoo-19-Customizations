# -*- coding: utf-8 -*-
"""
Model for managing product-specific SKU Infixes (SKU Product Codes).

Allows the Inventory Manager to configure product-specific middle codes
(e.g., SKU Infix: 'URB-FUNNY-MEN-CTSH-PLAIN-') independently of global sequence
settings.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductSkuTemplate(models.Model):
    _name = 'product.sku.template'
    _description = 'SKU Product Code'
    _order = 'name'

    name = fields.Char(
        string="Product Name",
        required=True,
        help="A meaningful name to identify the product associated with this SKU infix (e.g. Men's Cotton T-Shirt).",
    )
    sku_infix = fields.Char(
        string="SKU Infix",
        required=True,
        help="The product-specific middle code used when generating the final SKU.",
    )
    prefix = fields.Char(
        string="Internal SKU Product Code Prefix",
        required=False,
        help="Legacy prefix preserved for backwards compatibility and data preservation.",
    )
    suffix = fields.Char(
        string="Internal SKU Product Code Suffix",
        required=False,
        default="",
        help="Legacy suffix preserved for backwards compatibility and data preservation.",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="An option to enable or archive SKU infixes that should no longer be used.",
    )
    description = fields.Text(
        string="Notes / Description",
        help="Optional notes describing the product or SKU infix usage.",
    )

    product_count = fields.Integer(
        string="Products Using Code",
        compute='_compute_product_count',
        help="Number of product templates currently using this SKU infix.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Sync sku_infix to prefix if prefix is omitted
            if 'sku_infix' in vals and vals.get('sku_infix') and not vals.get('prefix'):
                vals['prefix'] = vals['sku_infix']
            # Sync legacy prefix/suffix to sku_infix if sku_infix is omitted
            elif 'prefix' in vals and vals.get('prefix') and not vals.get('sku_infix'):
                suffix = vals.get('suffix') or ''
                parts = [vals['prefix'].strip().strip('-')]
                if suffix and suffix.strip().strip('-'):
                    parts.append(suffix.strip().strip('-'))
                vals['sku_infix'] = '-'.join(parts)
        return super().create(vals_list)

    def write(self, vals):
        if 'sku_infix' in vals and vals.get('sku_infix') and not vals.get('prefix'):
            vals['prefix'] = vals['sku_infix']
        elif 'prefix' in vals and vals.get('prefix') and 'sku_infix' not in vals:
            suffix = vals.get('suffix') if 'suffix' in vals else (self.suffix or '')
            parts = [vals['prefix'].strip().strip('-')]
            if suffix and suffix.strip().strip('-'):
                parts.append(suffix.strip().strip('-'))
            vals['sku_infix'] = '-'.join(parts)
        return super().write(vals)

    def _compute_product_count(self):
        for rec in self:
            rec.product_count = self.env['product.template'].search_count([
                ('sku_template_id', '=', rec.id)
            ])

    @api.constrains('name', 'sku_infix', 'prefix')
    def _check_required_fields(self):
        for rec in self:
            if not rec.name or not rec.name.strip():
                raise ValidationError(_("Product Name is required and cannot be blank."))
            if not (rec.sku_infix and rec.sku_infix.strip()) and not (rec.prefix and rec.prefix.strip()):
                raise ValidationError(_("SKU Infix is required and cannot be blank."))

    def clean_prefix(self):
        """Return the trimmed prefix with outer whitespace removed."""
        self.ensure_one()
        return (self.prefix or self.sku_infix or '').strip()

    def clean_suffix(self):
        """Return the trimmed suffix with outer whitespace removed."""
        self.ensure_one()
        return (self.suffix or '').strip()

    def clean_infix(self):
        """Return the trimmed SKU Infix with outer whitespace and hyphens normalized."""
        self.ensure_one()
        if self.sku_infix and self.sku_infix.strip():
            return self.sku_infix.strip().strip('-')
        parts = []
        if self.prefix and self.prefix.strip():
            parts.append(self.prefix.strip().strip('-'))
        if self.suffix and self.suffix.strip():
            parts.append(self.suffix.strip().strip('-'))
        return '-'.join(parts)

    def action_view_products(self):
        """Open the list of products using this SKU infix."""
        self.ensure_one()
        return {
            'name': _("Products using %s", self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [('sku_template_id', '=', self.id)],
            'context': {'default_sku_template_id': self.id},
        }

    def action_open_global_settings(self):
        """Open Settings directly to configure Global Sequence Prefix and Suffix."""
        return {
            'type': 'ir.actions.act_window',
            'name': _("Settings"),
            'res_model': 'res.config.settings',
            'view_mode': 'form',
            'target': 'current',
            'context': {'module': 'stock'},
        }

