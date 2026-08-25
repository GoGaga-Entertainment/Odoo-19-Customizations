# -*- coding: utf-8 -*-
from odoo import fields, models


class EventCustomerAcquisition(models.Model):
    """
    Reporting view used by the Events spreadsheet dashboard.

    The view contains exactly one row for each partner whose first
    non-cancelled event registration is in the event registration history.
    Therefore acquisition_count is always 1 and the spreadsheet pivot can
    simply SUM(acquisition_count).
    """

    _name = "event.customer.acquisition"
    _description = "Event Customer Acquisition"
    _auto = False
    _rec_name = "partner_id"

    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        readonly=True,
    )

    first_event_date = fields.Datetime(
        string="First Event Registration",
        readonly=True,
    )

    event_id = fields.Many2one(
        "event.event",
        string="First Event",
        readonly=True,
    )

    acquisition_count = fields.Integer(
        string="Customer Acquisition",
        readonly=True,
        aggregator="sum",
    )

    def init(self):
        """
        Build the SQL reporting view.

        IMPORTANT:
        event.registration does NOT have an event_begin_date column.
        The event start date belongs to event.event.date_begin.

        For acquisition, the more useful date is the customer's first
        qualifying registration date (event_registration.create_date),
        because that is the date on which the customer was acquired through
        the event registration flow.  The linked event_id is the event of
        that first registration, so the existing dashboard Venue, Template,
        Tags and Organizer filters can still be applied.
        """
        self.env.cr.execute("""
            DROP VIEW IF EXISTS event_customer_acquisition CASCADE;

            CREATE VIEW event_customer_acquisition AS (
                SELECT
                    first_registration.id AS id,
                    first_registration.partner_id AS partner_id,
                    first_registration.create_date AS first_event_date,
                    first_registration.event_id AS event_id,
                    1 AS acquisition_count
                FROM (
                    SELECT DISTINCT ON (er.partner_id)
                        er.id,
                        er.partner_id,
                        er.event_id,
                        er.create_date
                    FROM event_registration er
                    WHERE
                        er.partner_id IS NOT NULL
                        AND er.event_id IS NOT NULL
                        AND er.state != 'cancel'
                    ORDER BY
                        er.partner_id,
                        er.create_date ASC,
                        er.id ASC
                ) AS first_registration
            )
        """)
