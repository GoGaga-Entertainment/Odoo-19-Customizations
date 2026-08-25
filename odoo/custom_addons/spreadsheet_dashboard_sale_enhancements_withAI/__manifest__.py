# -*- coding: utf-8 -*-
{
    'name': "Spreadsheet Dashboard for Sale Enhancements with AI",
    'summary': "Adds Revenue per Customer, Sales Growth, Order Cancellation % "
               "and Product Sale Contribution % to the existing Sales Dashboard.",
    'description': """
Spreadsheet Dashboard for Sale Enhancements with AI
====================================================

Non-invasively extends the standard Sales spreadsheet dashboard shipped by
``spreadsheet_dashboard_sale`` with three new KPI scorecards and one new
column in the Top Products table. No core module is modified: everything is
injected at read-time via a Python ``_inherit`` of ``spreadsheet.dashboard``,
patching the JSON payload that is served to the browser for the "Sales"
dashboard only. The stored dashboard record and every other dashboard are
left completely untouched.

See the module README for full details of the formulas used and the data
sources they reuse.
""",
    'version': '19.0.1.2.0',
    'category': 'Productivity/Dashboard',
    'author': 'Abat Mathew Rajesh',
    'license': 'LGPL-3',
    'depends': [
        'spreadsheet_dashboard_sale',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
