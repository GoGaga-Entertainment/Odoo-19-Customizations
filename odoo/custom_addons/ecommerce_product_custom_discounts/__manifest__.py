{
    'name': 'Ecommerce Product Custom Discounts',
    'version': '19.0.1.0.0',
    'category': 'Website/eCommerce',
    'summary': 'Back in Stock Message, Abandoned Cart Recovery Discount, Wishlist Special Day Discount',
    'description': """
        Custom functionality for eCommerce website:
          1. Back in Stock message on product page when stock > 0
             (for both simple products and product variants).
          2. Configurable Abandoned Cart Recovery Discount (Escalating or Diminishing) with banner on cart page.
          3. Wishlist Special Day Discount — Configurable date & discount percentage
             for wishlist items when viewed in cart on that special day.
    """,
    'author': 'Custom',
    'depends': ['sale_stock', 'website_sale', 'website_sale_wishlist'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'ecommerce_product_custom_discounts/static/src/scss/custom_wishlist.scss',
            'ecommerce_product_custom_discounts/static/src/js/back_in_stock_mixin.js',
            'ecommerce_product_custom_discounts/static/src/js/abandoned_cart_discount.js',
            'ecommerce_product_custom_discounts/static/src/js/wishlist_special_day.js',
            'ecommerce_product_custom_discounts/static/src/xml/back_in_stock_message.xml',
            'ecommerce_product_custom_discounts/static/src/xml/abandoned_cart_banner.xml',
            'ecommerce_product_custom_discounts/static/src/xml/wishlist_day_banner.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}