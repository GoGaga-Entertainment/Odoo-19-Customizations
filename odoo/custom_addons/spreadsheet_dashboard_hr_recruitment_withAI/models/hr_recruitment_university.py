# -*- coding: utf-8 -*-

from odoo import fields, models


class HrRecruitmentUniversity(models.Model):
    _name = "hr.recruitment.university"
    _description = "Recruitment University"
    _order = "name"

    name = fields.Char(required=True, index="trigram")
    active = fields.Boolean(default=True)
    country_id = fields.Many2one("res.country", ondelete="restrict")
    website = fields.Char()
    notes = fields.Text()

