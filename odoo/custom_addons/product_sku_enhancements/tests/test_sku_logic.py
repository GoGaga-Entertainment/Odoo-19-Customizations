# -*- coding: utf-8 -*-
from datetime import datetime
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestSkuLogic(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Configure Centralized Global SKU Sequence
        cls.seq_global = cls.env['ir.sequence'].search([('code', '=', 'product.sku.global')], limit=1)
        if not cls.seq_global:
            cls.seq_global = cls.env['ir.sequence'].create({
                'name': 'Product SKU Global Values',
                'code': 'product.sku.global',
                'implementation': 'standard',
                'prefix': 'GOGAGA-IN-',
                'suffix': '-%(year)s',
                'padding': 0,
                'number_next': 1,
                'number_increment': 1,
                'active': True,
            })
        else:
            cls.seq_global.write({
                'name': 'Product SKU Global Values',
                'prefix': 'GOGAGA-IN-',
                'suffix': '-%(year)s',
                'active': True,
                'number_next': 1,
            })

        # Create SKU Product Codes using direct sku_infix
        cls.tmpl_mens = cls.env['product.sku.template'].create({
            'name': "Men's Cotton T-Shirt",
            'sku_infix': 'URB-FUNNY-MEN-CTSH-PLAIN-',
            'active': True,
        })
        cls.tmpl_womens = cls.env['product.sku.template'].create({
            'name': "Women's Cotton T-Shirt",
            'sku_infix': 'URB-FUNNY-WOMEN-CTSH-PLAIN-',
            'active': True,
        })

        # Configure Fallback SKU Sequence
        cls.seq_fallback = cls.env['ir.sequence'].create({
            'name': 'Test Configured Fallback Sequence',
            'code': 'product.sku.test.fallback',
            'implementation': 'standard',
            'prefix': 'FALLBACK-',
            'padding': 3,
            'suffix': '-%(year)s',
            'number_next': 1,
            'number_increment': 1,
            'active': True,
        })
        cls.env['ir.config_parameter'].sudo().set_param('product_sku.sequence_id', cls.seq_fallback.id)

        # Attributes: Color & Size
        cls.attr_color = cls.env['product.attribute'].create({'name': 'Colour', 'sequence': 1})
        cls.val_navy = cls.env['product.attribute.value'].create({
            'name': 'Navy Blue',
            'sku_short_code': 'NVY',
            'attribute_id': cls.attr_color.id,
        })
        cls.val_red = cls.env['product.attribute.value'].create({
            'name': 'Red',
            'sku_short_code': 'RED',
            'attribute_id': cls.attr_color.id,
        })
        cls.val_green = cls.env['product.attribute.value'].create({
            'name': 'Green',
            'sku_short_code': 'GRN',
            'attribute_id': cls.attr_color.id,
        })

        cls.attr_size = cls.env['product.attribute'].create({'name': 'Size', 'sequence': 2})
        cls.val_xl = cls.env['product.attribute.value'].create({
            'name': 'Extra Large',
            'sku_short_code': 'XL',
            'attribute_id': cls.attr_size.id,
        })

    def test_01_sku_infix_creation_and_validation(self):
        """Test SKU Infix creation, validation and backwards compatibility."""
        with self.assertRaises(ValidationError):
            self.env['product.sku.template'].create({
                'name': '',
                'sku_infix': 'URB-FUNNY-',
            })
        with self.assertRaises(ValidationError):
            self.env['product.sku.template'].create({
                'name': 'Test Shirt',
                'sku_infix': '   ',
            })

        # Direct creation with sku_infix
        tmpl = self.env['product.sku.template'].create({
            'name': 'Formal Shirt',
            'sku_infix': 'URB-FORMAL-MEN-CTSH-PLAIN-',
        })
        self.assertEqual(tmpl.clean_infix(), 'URB-FORMAL-MEN-CTSH-PLAIN')

        # Backwards compatibility: creation with legacy prefix and suffix
        legacy_tmpl = self.env['product.sku.template'].create({
            'name': 'Legacy Shirt',
            'prefix': 'URB-LEGACY',
            'suffix': '-MEN',
        })
        self.assertEqual(legacy_tmpl.clean_infix(), 'URB-LEGACY-MEN')

    def test_02_sku_generation_structure_and_no_sequence_consumption(self):
        """Test exact standard SKU structure when Active = ON:
        GLOBAL PREFIX + PRODUCT-SPECIFIC SKU INFIX + PRODUCT VARIANT CODE + GLOBAL SUFFIX
        Example: GOGAGA-IN-URB-FUNNY-MEN-CTSH-PLAIN-NVY-XL-2026

        Also verifies that sequence number_next is NOT consumed or incremented.
        """
        initial_number_next = self.seq_global.number_next

        product = self.env['product.template'].create({
            'name': "Men's Cotton T-Shirt",
            'sku_template_id': self.tmpl_mens.id,
            'attribute_line_ids': [
                (0, 0, {
                    'attribute_id': self.attr_color.id,
                    'value_ids': [(6, 0, [self.val_navy.id, self.val_red.id])],
                }),
                (0, 0, {
                    'attribute_id': self.attr_size.id,
                    'value_ids': [(6, 0, [self.val_xl.id])],
                }),
            ]
        })
        self.assertEqual(len(product.product_variant_ids), 2)

        # Generate SKUs - Scenario A (first time: 2 SKUs)
        res_a = product.action_generate_all_skus()
        self.assertIn("Internal References generated. 2 SKUs generated successfully.", res_a['params']['message'])

        v_navy_xl = product.product_variant_ids.filtered(
            lambda v: self.val_navy in v.product_template_attribute_value_ids.product_attribute_value_id
        )
        v_red_xl = product.product_variant_ids.filtered(
            lambda v: self.val_red in v.product_template_attribute_value_ids.product_attribute_value_id
        )

        current_year = str(datetime.now().year)
        self.assertEqual(v_navy_xl.default_code, f'GOGAGA-IN-URB-FUNNY-MEN-CTSH-PLAIN-NVY-XL-{current_year}')
        self.assertEqual(v_red_xl.default_code, f'GOGAGA-IN-URB-FUNNY-MEN-CTSH-PLAIN-RED-XL-{current_year}')

        # Verify global sequence counter was NOT incremented
        self.assertEqual(self.seq_global.number_next, initial_number_next)

    def test_03_scenario_b_and_c_notifications(self):
        """Test Scenario B (already exist) and Scenario C (partial generation)."""
        product = self.env['product.template'].create({
            'name': "Women's Cotton T-Shirt",
            'sku_template_id': self.tmpl_womens.id,
            'attribute_line_ids': [
                (0, 0, {
                    'attribute_id': self.attr_color.id,
                    'value_ids': [(6, 0, [self.val_navy.id, self.val_red.id])],
                }),
                (0, 0, {
                    'attribute_id': self.attr_size.id,
                    'value_ids': [(6, 0, [self.val_xl.id])],
                }),
            ]
        })
        # First-time generation
        product.action_generate_all_skus()

        # Scenario B: SKUs already exist, click Generate All SKUs again
        res_b = product.action_generate_all_skus()
        self.assertEqual(res_b['params']['message'], "Internal References generated")

        # Scenario C: Partial generation (clear 1 variant, regenerate)
        v1 = product.product_variant_ids[0]
        v1.write({'default_code': False, 'is_sku_generated': False})
        res_c = product.action_generate_all_skus()
        self.assertIn("Internal References generated. 1 SKUs generated successfully.", res_c['params']['message'])

    def test_04_scenario_d_clear_generated_skus(self):
        """Test Scenario D: bulk Clear Generated SKUs wizard dynamic counts."""
        product = self.env['product.template'].create({
            'name': "Clearable Shirt",
            'sku_template_id': self.tmpl_mens.id,
            'attribute_line_ids': [
                (0, 0, {
                    'attribute_id': self.attr_color.id,
                    'value_ids': [(6, 0, [self.val_navy.id, self.val_red.id])],
                }),
            ]
        })
        product.action_generate_all_skus()
        self.assertEqual(len(product.product_variant_ids.filtered(lambda v: bool(v.default_code))), 2)

        # Clear 2 variants
        wizard = self.env['sku.clear.wizard'].create({
            'product_tmpl_id': product.id,
            'clear_manual_skus': False,
        })
        res_d = wizard.action_confirm_clear()
        self.assertIn("Internal References cleared. SKUs for 2 variants cleared successfully.", res_d['params']['message'])
        self.assertEqual(len(product.product_variant_ids.filtered(lambda v: bool(v.default_code))), 0)

        # Clear when 0 variants have SKUs
        wizard_zero = self.env['sku.clear.wizard'].create({
            'product_tmpl_id': product.id,
            'clear_manual_skus': False,
        })
        res_zero = wizard_zero.action_confirm_clear()
        self.assertIn("Internal References cleared. SKUs for 0 variants cleared successfully.", res_zero['params']['message'])

    def test_05_fallback_when_sku_product_code_active_off(self):
        """Test that when SKU Product Code Active = OFF:
        1. Inactive product SKU infix is NOT used.
        2. Fallback sequence selected in Settings is automatically used.
        3. Prefix, sequence number, padding, and suffix from fallback sequence are applied.
        4. Sequence number increments correctly across multiple variants.
        """
        self.seq_fallback.write({
            'prefix': 'FALLBACK-',
            'padding': 3,
            'suffix': '-%(year)s',
            'number_next': 1,
            'number_increment': 1,
            'active': True,
        })
        self.env['ir.config_parameter'].sudo().set_param('product_sku.sequence_id', self.seq_fallback.id)

        tmpl_inactive = self.env['product.sku.template'].create({
            'name': "Inactive Infix Code",
            'sku_infix': 'DO-NOT-USE-INFIX-',
            'active': False,
        })
        product = self.env['product.template'].create({
            'name': "Fallback Test Product",
            'sku_template_id': tmpl_inactive.id,
            'attribute_line_ids': [
                (0, 0, {
                    'attribute_id': self.attr_color.id,
                    'value_ids': [(6, 0, [self.val_navy.id, self.val_red.id, self.val_green.id])],
                }),
            ]
        })
        self.assertEqual(len(product.product_variant_ids), 3)

        res = product.action_generate_all_skus()
        self.assertIn("Internal References generated. 3 SKUs generated successfully.", res['params']['message'])

        current_year = str(datetime.now().year)
        skus = product.product_variant_ids.mapped('default_code')

        # Check sequential numbering and padding: FALLBACK-001-2026, FALLBACK-002-2026, FALLBACK-003-2026
        expected_skus = [
            f'FALLBACK-001-{current_year}',
            f'FALLBACK-002-{current_year}',
            f'FALLBACK-003-{current_year}',
        ]
        self.assertEqual(sorted(skus), sorted(expected_skus))

        # Check that inactive infix was NOT combined
        for sku in skus:
            self.assertNotIn('DO-NOT-USE-INFIX', sku)
            self.assertNotIn('GOGAGA-IN', sku)

    def test_06_fallback_sequence_validation_missing_or_inactive(self):
        """Test validation when Fallback SKU Sequence is missing or inactive."""
        tmpl_inactive = self.env['product.sku.template'].create({
            'name': "Inactive Code For Error Test",
            'sku_infix': 'INACTIVE-',
            'active': False,
        })
        product = self.env['product.template'].create({
            'name': "Product For Fallback Validation",
            'sku_template_id': tmpl_inactive.id,
        })

        IrParam = self.env['ir.config_parameter'].sudo()

        # Case 1: Parameter is cleared / missing
        IrParam.set_param('product_sku.sequence_id', False)
        with self.assertRaises(UserError) as cm_missing:
            product.action_generate_all_skus()
        self.assertIn("No active Fallback SKU Sequence is configured", str(cm_missing.exception))

        # Case 2: Configured sequence is archived / inactive
        self.seq_fallback.active = False
        IrParam.set_param('product_sku.sequence_id', self.seq_fallback.id)
        with self.assertRaises(UserError) as cm_inactive:
            product.action_generate_all_skus()
        self.assertIn("No active Fallback SKU Sequence is configured", str(cm_inactive.exception))

        # Restore
        self.seq_fallback.active = True

    def test_07_mixed_bulk_generation_standard_and_fallback(self):
        """Test standard and fallback SKUs generated together in a single bulk operation."""
        self.seq_fallback.write({
            'prefix': 'FALLBACK-',
            'padding': 3,
            'suffix': '-%(year)s',
            'number_next': 10,
            'active': True,
        })
        self.env['ir.config_parameter'].sudo().set_param('product_sku.sequence_id', self.seq_fallback.id)

        # Product 1: Active = ON (2 variants)
        p1 = self.env['product.template'].create({
            'name': "Active SKU Shirt",
            'sku_template_id': self.tmpl_mens.id,
            'attribute_line_ids': [
                (0, 0, {
                    'attribute_id': self.attr_color.id,
                    'value_ids': [(6, 0, [self.val_navy.id, self.val_red.id])],
                }),
            ]
        })
        # Product 2: Active = OFF (3 variants)
        tmpl_off = self.env['product.sku.template'].create({
            'name': "Inactive Code Mixed",
            'sku_infix': 'INACTIVE-MIXED-',
            'active': False,
        })
        p2 = self.env['product.template'].create({
            'name': "Inactive SKU Shirt",
            'sku_template_id': tmpl_off.id,
            'attribute_line_ids': [
                (0, 0, {
                    'attribute_id': self.attr_color.id,
                    'value_ids': [(6, 0, [self.val_navy.id, self.val_red.id, self.val_green.id])],
                }),
            ]
        })

        # Bulk generate across both products (5 variants total)
        both_products = p1 + p2
        res = both_products.action_generate_all_skus()
        self.assertIn("Internal References generated. 5 SKUs generated successfully.", res['params']['message'])

        # Verify P1 variants have standard SKUs
        for v in p1.product_variant_ids:
            self.assertTrue(v.default_code.startswith('GOGAGA-IN-URB-FUNNY-MEN-CTSH-PLAIN-'))

        # Verify P2 variants have fallback SKUs with sequential numbers
        p2_skus = p2.product_variant_ids.mapped('default_code')
        current_year = str(datetime.now().year)
        self.assertIn(f'FALLBACK-010-{current_year}', p2_skus)
        self.assertIn(f'FALLBACK-011-{current_year}', p2_skus)
        self.assertIn(f'FALLBACK-012-{current_year}', p2_skus)

    def test_08_existing_skus_preserved_when_toggled_off(self):
        """Test that existing SKUs are not overwritten when SKU Product Code is switched to Active = OFF."""
        product = self.env['product.template'].create({
            'name': "Toggle Preservation Shirt",
            'sku_template_id': self.tmpl_mens.id,
        })
        product.action_generate_all_skus()
        original_sku = product.product_variant_ids[0].default_code
        self.assertTrue(original_sku.startswith('GOGAGA-IN-'))

        # Switch template to Active = OFF
        self.tmpl_mens.active = False
        product.invalidate_recordset()

        # Click Generate All SKUs again
        res = product.action_generate_all_skus()
        self.assertEqual(res['params']['message'], "Internal References generated")
        self.assertEqual(product.product_variant_ids[0].default_code, original_sku)

        # Restore
        self.tmpl_mens.active = True

    def test_09_preserve_manually_assigned_sku(self):
        """Test that an existing manually assigned Internal Reference is NOT overwritten."""
        product = self.env['product.template'].create({
            'name': "Custom Code Product",
            'sku_template_id': self.tmpl_mens.id,
        })
        variant = product.product_variant_ids[0]
        variant.default_code = 'MANUAL-REF-999'
        variant.is_sku_generated = False

        product.action_generate_all_skus()

        self.assertEqual(variant.default_code, 'MANUAL-REF-999')
        self.assertFalse(variant.is_sku_generated)

    def test_10_uniqueness_guarantee_on_duplicate_products(self):
        """Test that duplicate SKUs are never generated when two products have identical attributes."""
        p1 = self.env['product.template'].create({
            'name': "Shirt Batch 1",
            'sku_template_id': self.tmpl_mens.id,
        })
        p2 = self.env['product.template'].create({
            'name': "Shirt Batch 2",
            'sku_template_id': self.tmpl_mens.id,
        })
        p1.action_generate_all_skus()
        p2.action_generate_all_skus()

        sku1 = p1.product_variant_ids[0].default_code
        sku2 = p2.product_variant_ids[0].default_code

        self.assertNotEqual(sku1, sku2)
        self.assertTrue(sku2.startswith(sku1))
        self.assertTrue(sku2.endswith('-02'))

    def test_11_product_variant_views_do_not_contain_sku_template_id(self):
        """Verify that SKU Infix Template is removed from variant list and form views."""
        list_view = self.env.ref('product.product_product_tree_view')
        arch_list = self.env['product.product'].get_view(view_id=list_view.id, view_type='list')['arch']
        self.assertNotIn('name="sku_template_id"', arch_list)

        form_view = self.env.ref('product.product_normal_form_view')
        arch_form = self.env['product.product'].get_view(view_id=form_view.id, view_type='form')['arch']
        self.assertNotIn('name="sku_template_id"', arch_form)

    def test_12_product_template_views_ui_modifications(self):
        """Verify:
        1. SKU Template field label is 'SKU Infix Template'.
        2. Product List View does not contain 'SKU Infix Template' / 'SKU Product Code Template' or 'SKU Product Code' columns.
        3. Product Kanban View formats SKU with 'SKU : [SKU VALUE]'.
        """
        # 1. Field label on model and form
        fields_info = self.env['product.template'].fields_get(['sku_template_id'])
        self.assertEqual(fields_info['sku_template_id']['string'], "SKU Infix Template")

        form_view = self.env.ref('product.product_template_only_form_view')
        arch_form = self.env['product.template'].get_view(view_id=form_view.id, view_type='form')['arch']
        self.assertIn('string="SKU Infix Template"', arch_form)

        # 2. Columns removed from Product List View
        list_view = self.env.ref('product.product_template_tree_view')
        arch_list = self.env['product.template'].get_view(view_id=list_view.id, view_type='list')['arch']
        self.assertNotIn('name="sku_template_id"', arch_list)
        self.assertNotIn('string="SKU Product Code"', arch_list)
        # Verify Internal Reference (default_code) column is hidden in Product List View
        self.assertIn('name="default_code"', arch_list)
        self.assertIn('column_invisible="True"', arch_list)

        # Verify Internal Reference is retained on Product Variant List View
        variant_list_view = self.env.ref('product.product_product_tree_view')
        arch_var_list = self.env['product.product'].get_view(view_id=variant_list_view.id, view_type='list')['arch']
        self.assertIn('string="SKU / Internal Ref"', arch_var_list)

        # 3. Product Kanban spacing 'SKU :'
        kanban_view = self.env.ref('product.product_template_kanban_view')
        arch_kanban = self.env['product.template'].get_view(view_id=kanban_view.id, view_type='kanban')['arch']
        self.assertIn('<strong>SKU :</strong>', arch_kanban)
