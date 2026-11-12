# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch
from odoo.tests.common import TransactionCase


class TestQrCodeLogic(TransactionCase):

    def test_01_qr_code_computation(self):
        """Test computing QR code image and fallback sequence (default_code -> barcode -> ID)."""
        product = self.env['product.product'].create({
            'name': 'QR Test Product',
            'default_code': 'SKU-QR-001',
        })
        self.assertEqual(product.qr_code_value, 'SKU-QR-001')
        self.assertTrue(product.qr_code_image)

        # Test barcode fallback when default_code is cleared
        product.default_code = False
        product.barcode = '1234567890123'
        product._compute_qr_code_image()
        self.assertEqual(product.qr_code_value, '1234567890123')
        self.assertTrue(product.qr_code_image)

        # Test ID fallback when default_code and barcode are cleared
        product.barcode = False
        product._compute_qr_code_image()
        self.assertEqual(product.qr_code_value, str(product.id))
        self.assertTrue(product.qr_code_image)

    def test_02_get_combination_info_qr_code(self):
        """Test that _get_combination_info provides variant's qr_code_image in combination dictionary."""
        template = self.env['product.template'].create({
            'name': 'QR Website Test Template',
            'default_code': 'TEMPL-QR-001',
        })
        website = self.env['website'].get_current_website()
        pricelist = website.pricelist_ids[:1] or self.env['product.pricelist'].search([], limit=1)
        mock_request = MagicMock()
        mock_request.website = website
        mock_request.pricelist = pricelist
        with patch('odoo.addons.website_sale.models.product_template.request', mock_request):
            comb_info = template._get_combination_info(product_id=template.product_variant_id.id)
            self.assertIn('qr_code_image', comb_info)
            self.assertTrue(comb_info['qr_code_image'])

    def test_03_label_layout_zpl_preview(self):
        """Test that product.label.layout computes zpl_preview."""
        product = self.env['product.product'].create({
            'name': 'ZPL QR Test Product',
            'default_code': 'ZPL-SKU-001',
        })
        wizard = self.env['product.label.layout'].create({
            'product_ids': [(6, 0, [product.id])],
            'print_format': 'zplxprice',
        })
        wizard._compute_zpl_preview()
        self.assertTrue(wizard.zpl_preview)

    def test_04_zpl_normal_label_rendering_without_variants(self):
        """Test that normal_zpl_label renders barcode, QR code, and price without variant line when product has no variants."""
        product = self.env['product.product'].create({
            'name': 'Simple Shirt',
            'default_code': 'ZPL-SKU-TEST',
            'barcode': '1234567890',
        })
        values = {
            'product': product,
            'barcode': product.barcode,
            'price_included': True,
            'price': '$ 99.00',
            'show_price_per_unit': False,
        }
        rendered = self.env['ir.qweb']._render('stock.normal_zpl_label', values)
        rendered_str = str(rendered)

        # Check Barcode command
        self.assertIn('^BCN,100,Y,N,N', rendered_str)
        self.assertIn('^FD1234567890^FS', rendered_str)
        # Check QR code command
        self.assertIn('^FO310,77^BQN,2,3^FDMA,ZPL-SKU-TEST^FS', rendered_str)
        # Check Price command
        self.assertIn('^FO300,200', rendered_str)
        self.assertIn('$ 99.00', rendered_str)
        # Check that actual product name is printed
        self.assertIn('^FDSimple Shirt^FS', rendered_str)
        self.assertNotIn('[ZPL-SKU-TEST] Simple Shirt', rendered_str)

    def test_05_zpl_label_with_variant_details(self):
        """Test that normal_zpl_label renders product name AND variant attributes separated by space (e.g. Shirt, Black Small)."""
        attr_color = self.env['product.attribute'].create({'name': 'Colour', 'sequence': 1})
        val_black = self.env['product.attribute.value'].create({
            'name': 'Black',
            'attribute_id': attr_color.id,
        })
        attr_size = self.env['product.attribute'].create({'name': 'Size', 'sequence': 2})
        val_small = self.env['product.attribute.value'].create({
            'name': 'Small',
            'attribute_id': attr_size.id,
        })

        template = self.env['product.template'].create({
            'name': 'Shirt',
            'attribute_line_ids': [
                (0, 0, {
                    'attribute_id': attr_color.id,
                    'value_ids': [(6, 0, [val_black.id])],
                }),
                (0, 0, {
                    'attribute_id': attr_size.id,
                    'value_ids': [(6, 0, [val_small.id])],
                }),
            ]
        })
        variant = template.product_variant_ids[0]
        variant.default_code = 'SHIRT-BLK-SM'
        variant.barcode = '9876543210'

        # Verify dynamic variant string format: "Black Small" (separated by single space)
        var_str = variant._get_variant_attribute_values_str()
        self.assertEqual(var_str, 'Black Small')

        values = {
            'product': variant,
            'barcode': variant.barcode,
            'price_included': True,
            'price': '$ 45.00',
            'show_price_per_unit': False,
        }
        rendered = self.env['ir.qweb']._render('stock.normal_zpl_label', values)
        rendered_str = str(rendered)

        # Check Product Name
        self.assertIn('^FDShirt^FS', rendered_str)
        # Check Variant details: "Black Small" (space separator)
        self.assertIn('^FDBlack Small^FS', rendered_str)
        # Check Barcode
        self.assertIn('^FD9876543210^FS', rendered_str)
        # Check QR code
        self.assertIn('^FO310,77^BQN,2,3^FDMA,SHIRT-BLK-SM^FS', rendered_str)
        # Check Price
        self.assertIn('^FO300,200', rendered_str)
        self.assertIn('$ 45.00', rendered_str)
