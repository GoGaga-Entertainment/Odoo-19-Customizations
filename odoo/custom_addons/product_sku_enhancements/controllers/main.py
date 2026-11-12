# -*- coding: utf-8 -*-
"""
Controllers for product_sku_enhancements.

Note: SKU injection into combination_info is handled at the model layer by
overriding ``product.template._get_combination_info`` in models/product_template.py.

The website_sale variant controller (website_sale/controllers/variant.py) calls
``product_template._get_combination_info()`` which then automatically includes
``default_code`` via our model-level override.  No controller override is needed.
"""
