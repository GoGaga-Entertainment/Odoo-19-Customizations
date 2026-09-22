from odoo.tests.common import TransactionCase


class TestEventSaleReportCountry(TransactionCase):

    def test_select_clause(self):
        """Test that customer_country_id is added to the SQL SELECT clause."""

        report_model = self.env["event.sale.report"]

        result = report_model._select_clause()

        self.assertIn(
            "event_sale_customer_partner.country_id AS customer_country_id",
            result,
        )

    def test_from_clause(self):
        """Test that the customer country JOIN is added to the SQL FROM clause."""

        report_model = self.env["event.sale.report"]

        result = report_model._from_clause()

        self.assertIn(
            "LEFT JOIN res_partner AS event_sale_customer_partner "
            "ON event_sale_customer_partner.id = sale_order.partner_id",
            result,
        )