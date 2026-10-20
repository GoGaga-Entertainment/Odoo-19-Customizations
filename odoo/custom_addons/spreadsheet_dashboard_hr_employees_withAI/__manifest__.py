# -*- coding: utf-8 -*-

{
    "name": "HR Employees Spreadsheet Dashboard with AI",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Employees",
    "summary": "Employee workforce analytics in Odoo Dashboards",
    "description": """
HR Employees Spreadsheet Dashboard
==================================

Adds an Employees dashboard below Recruitment in the shared HR dashboard
group. It provides workforce KPIs, certification and employment-type charts,
nationality and degree distribution tables, percentages, and HR filters.
    """,
    "author": "Arjun P S",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "hr",
        "spreadsheet_dashboard_hr_recruitment_withAI",
    ],
    "data": [
        "security/dashboard_security.xml",
        "security/ir.model.access.csv",
        "views/hr_employee_views.xml",
        "data/dashboards.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
