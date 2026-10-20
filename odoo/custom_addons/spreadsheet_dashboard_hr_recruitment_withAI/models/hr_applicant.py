# -*- coding: utf-8 -*-

from odoo import fields, models


class HrApplicant(models.Model):
    _inherit = "hr.applicant"

    dashboard_university_id = fields.Many2one(
        comodel_name="hr.employee.university",
        string="University",
        tracking=True,
        ondelete="restrict",
        help="University used by the HR Recruitment spreadsheet dashboard.",
    )
