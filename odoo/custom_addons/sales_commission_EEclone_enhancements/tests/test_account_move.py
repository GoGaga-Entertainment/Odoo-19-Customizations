from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..models.account_move import AccountMove


class TestAccountMove(TransactionCase):

    def test_post_customer_invoice_creates_commission_achievement(self):
        """Test that posting a customer invoice updates commission data."""

        # Find a salesperson
        user = self.env["res.users"].search([], limit=1)
        self.assertTrue(user, "A test user is required.")

        # Find a customer
        partner = self.env["res.partner"].search([], limit=1)
        self.assertTrue(partner, "A test partner is required.")

        # Find an accounting journal
        journal = self.env["account.journal"].search(
            [("type", "=", "sale")],
            limit=1,
        )
        self.assertTrue(journal, "A sales journal is required.")

        # Create a draft customer invoice
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "journal_id": journal.id,
            "invoice_user_id": user.id,
            "invoice_date": "2026-01-15",
        })

        # Add an invoice line so the invoice has an amount
        account = self.env["account.account"].search(
            [("account_type", "=", "income")],
            limit=1,
        )

        if account:
            self.env["account.move.line"].create({
                "move_id": invoice.id,
                "name": "Test Product",
                "quantity": 1,
                "price_unit": 1000.0,
                "account_id": account.id,
            })

        # --------------------------------------------------
        # Mock the commission-related searches/creation
        # --------------------------------------------------

        assignment_model = self.env["sales.commission.salesperson"]
        target_model = self.env["sales.commission.target"]
        record_model = self.env["sales.commission.record"]
        achievement_model = self.env[
            "sales.commission.achievement.line"
        ]

        assignment = assignment_model.new({
            "user_id": user.id,
        })

        target = target_model.new({
            "name": "Test Target",
            "plan_id": assignment.plan_id.id,
            "target_amount": 10000.0,
        })

        commission_record = record_model.new({
            "achieved": 0.0,
        })

        with patch.object(
            type(assignment_model),
            "search",
            return_value=assignment,
        ), patch.object(
            type(target_model),
            "search",
            return_value=target,
        ), patch.object(
            type(record_model),
            "search",
            return_value=commission_record,
        ), patch.object(
            type(achievement_model),
            "create",
            return_value=True,
        ):

            # Call the method being tested
            invoice._post()

        # Basic verification
        self.assertEqual(invoice.move_type, "out_invoice")