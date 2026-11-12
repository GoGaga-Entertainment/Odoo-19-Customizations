# -*- coding: utf-8 -*-
{
    'name': 'Product SKU Enhancements',
    'version': '19.0.2.0.0',
    'category': 'Inventory/Configuration',
    'summary': 'Configurable SKU/Internal Reference generation with Global sequence prefix/suffix, '
               'reusable SKU Product Code Templates, variant short codes, and safe SKU clearing.',
    'description': """
Product SKU Enhancements
========================
* Global SKU sequence prefix & suffix (supports %YEAR, %MONTH, %DAY).
* Reusable SKU Product Code Templates (Prefix, Suffix) managed under Inventory → Configuration → SKU Product Codes.
* Assign SKU Product Code Templates directly on Product Templates.
* Final SKU combination formula:
    Global Prefix + Template Prefix + Variant Codes + Template Suffix + Global Suffix
* Guarantees unique Internal References across products/variants.
* Safe "Clear Generated SKUs" action with confirmation wizard to safely reset SKUs without affecting barcodes, QR codes, or product data.
* Preserves manually assigned Internal References by default.
* SKU displayed in Product List, Variant List, Kanban views, Website Product page, and Cart lines.
    """,
    'author': 'Custom',
    'depends': [
        'product',
        'website_sale',
        'base_setup',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sku_sequence.xml',
        'views/product_sku_template_views.xml',
        'views/sku_clear_wizard_views.xml',
        'views/product_attribute_value_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_template_views.xml',
        'views/product_product_views.xml',
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'product_sku_enhancements/static/src/js/product_sku.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
