{
    'name': 'Spreadsheet_dashboard_website_sale_enhancements_withAI',
    'version': '1.0.0',
    'category': 'Productivity/Dashboard',
    'summary': 'Enhance the Odoo eCommerce spreadsheet dashboard with additional KPIs and product revenue share.',
    'description': '''
eCommerce Spreadsheet Dashboard Enhancements
============================================

Adds:
1. Average Order Value KPI.
2. Customer Acquisition KPI for logged-in website customers making their first confirmed website purchase.
3. % of Revenue column to the Top Products table.
4. eCommerce-only sales forecast panels (AOV/regression, ML forecast with linear,
   polynomial, Exponential Smoothing and ARIMA, and training/testing results).
''',
    'depends': [
        'spreadsheet_dashboard_website_sale',
        'spreadsheet_dashboard',
        'website_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/dashboards.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'external_dependencies': {'python': ['numpy', 'scipy', 'sklearn', 'statsmodels']},
    'assets': {'web.assets_backend': [
        'spreadsheet_dashboard_website_sale_enhancements_withAI/static/src/js/forecast_aov_tooltip.js',
        'spreadsheet_dashboard_website_sale_enhancements_withAI/static/src/js/forecast_axis_filter.js',
        'spreadsheet_dashboard_website_sale_enhancements_withAI/static/src/css/forecast_aov_tooltip.css',
    ]},
    'author': 'Custom',
}
