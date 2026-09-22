from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSalesCommission(TransactionCase):

    def _create_plan(self):
        """Create a commission plan for the commission level."""
        return self.env["sales.commission.plan"].create({
            "name": "Test Commission Plan",
            "commission_type": "achievement",
            "applies_on": "salesperson",
            "periodicity": "monthly",
        })

    def test_check_values(self):
        """Test that commission values cannot be negative."""

        plan = self._create_plan()

        # Negative target completion
        with self.assertRaises(ValidationError):
            self.env["sales.commission"].create({
                "plan_id": plan.id,
                "target_completion": -10.0,
                "commission": 100.0,
                "otc": 5.0,
            })

        # Negative commission
        with self.assertRaises(ValidationError):
            self.env["sales.commission"].create({
                "plan_id": plan.id,
                "target_completion": 50.0,
                "commission": -100.0,
                "otc": 5.0,
            })

        # Negative OTC
        with self.assertRaises(ValidationError):
            self.env["sales.commission"].create({
                "plan_id": plan.id,
                "target_completion": 50.0,
                "commission": 100.0,
                "otc": -5.0,
            })