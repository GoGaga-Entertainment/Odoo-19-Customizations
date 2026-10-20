# -*- coding: utf-8 -*-

{
    "name": "HR Recruitment Spreadsheet Dashboard with AI",
    "version": "19.0.6.0.0",
    "category": "Human Resources/Recruitment",
    "summary": "Recruitment and internship analytics in Odoo Dashboards",
    "description": """
HR Recruitment Spreadsheet Dashboard
====================================

Adds an HR dashboard group immediately after Finance and publishes a
Recruitment analytics dashboard containing applicant, internship, active
pipeline, and vacancy KPIs. Separate dashboard filters are provided for job
roles, job universities, internship roles, and internship universities.
    """,
    "author": "Arjun P S",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "hr_recruitment",
        "hr_customizations",
        "recruitment_stages_status_enhancement",
    ],
    "data": [
        "security/dashboard_security.xml",
        "views/hr_applicant_views.xml",
        "views/intern_applicant_views.xml",
        "data/dashboards.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
