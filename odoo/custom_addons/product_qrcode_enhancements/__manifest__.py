# -*- coding: utf-8 -*-
{
    'name': 'Product QR Code Enhancements',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Products',
    'summary': 'Generates dynamic QR code images for product variants based on SKU, barcode, or ID. Includes QR codes on product label printouts and website.',
    'description': """
Product QR Code Enhancements
============================
* Computes dynamic QR code images for product variants using `default_code` (SKU), `barcode`, or product ID.
* Displays the QR code image field on product variant and template form views.
* Integrates QR code printing into product label reports and ZPL labels with price.
* Displays variant QR code on the website product detail page, dynamically updating with variant selection.
    """,
    'author': 'Custom',
    'depends': [
        'product',
        'stock',
        'barcodes',
        'website_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_product_views.xml',
        'views/website_templates.xml',
        'reports/product_label_qr.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'product_qrcode_enhancements/static/src/js/product_qrcode.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
