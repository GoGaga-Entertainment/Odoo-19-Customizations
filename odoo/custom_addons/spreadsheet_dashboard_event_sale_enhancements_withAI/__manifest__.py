# -*- coding: utf-8 -*-
{
    "name": "Spreadsheet Dashboard for Event Sale Enhancements withAI",
    "version": "19.0.1.8.0",
    "category": "Productivity/Dashboard",
    "summary": "Customer Acquisition, KPI Enhancements, Top Countries, and Events Status enhancements for the Events spreadsheet dashboard",
    "description": """
Enhances the existing Odoo Events spreadsheet dashboard without changing
any standard Odoo addon files.

Features included:
- Customer Acquisition KPI based on qualifying event sales.
- Average Registrations per Event KPI.
- Average Revenue per Event KPI.
- Events Status and Registration Status dashboard enhancements.
- Top Venues, Top Templates, Top Tags, and Top Organisers analysis.
- Top Countries analysis using the event customer's country.
- World map visualization for event sales by country.
- Top 10 Countries view for country-wise event sales analysis.
- Dashboard filters for date, venue, event template, tags, and organizer.
- Revenue and KPI display enhancements for improved dashboard readability.

All enhancements are implemented through the custom module and the
existing Odoo Events spreadsheet dashboard.

""",
    'author': 'Abat Mathew Rajesh',
    'license': 'LGPL-3',
    "depends": [
        "spreadsheet_dashboard_event_sale",
        "event_sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/event_sale_report_views.xml",
    ],
    "installable": True,
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "application": False,
    "license": "LGPL-3",
}