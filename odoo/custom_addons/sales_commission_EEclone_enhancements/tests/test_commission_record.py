from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..models.commission_record import SalesCommissionRecord


class TestSalesCommissionRecord(TransactionCase):

    def _create_plan(self):
        """Create a basic commission plan."""
        return self.env["sales.commission.plan"].create({
            "name": "Test Commission Plan",
            "commission_type": "achievement",
            "applies_on": "salesperson",
            "periodicity": "monthly",
        })

    def _create_target(self, plan):
        """Create a basic target period."""
        return self.env["sales.commission.target"].create({
            "plan_id": plan.id,
            "name": "January 2026",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "target_amount": 10000.0,
        })

    def _create_record(self, achieved=0.0):
        """Create a commission record."""
        user = self.env["res.users"].search([], limit=1)
        plan = self._create_plan()
        target = self._create_target(plan)

        return self.env["sales.commission.record"].create({
            "salesperson_id": user.id,
            "plan_id": plan.id,
            "target_id": target.id,
            "achieved": achieved,
        })

    # ---------------------------------------------------------
    # 1. _compute_achieved_rate
    # ---------------------------------------------------------

    def test_compute_achieved_rate(self):
        """Test calculation of achieved percentage."""

        record = self._create_record(achieved=5000.0)

        self.assertEqual(
            record.target_amount,
            10000.0,
        )

        self.assertEqual(
            record.achieved_rate,
            50.0,
        )

    # ---------------------------------------------------------
    # 2. _compute_commission
    # ---------------------------------------------------------

    def test_compute_commission(self):
        """Test commission calculation using commission levels."""

        user = self.env["res.users"].search([], limit=1)

        plan = self._create_plan()

        target = self._create_target(plan)

        # Create commission levels
        self.env["sales.commission"].create([
            {
                "plan_id": plan.id,
                "target_completion": 0,
                "commission": 0.0,
                "otc": 0.0,
            },
            {
                "plan_id": plan.id,
                "target_completion": 50,
                "commission": 1000.0,
                "otc": 0.0,
            },
            {
                "plan_id": plan.id,
                "target_completion": 100,
                "commission": 2000.0,
                "otc": 10.0,
            },
        ])

        record = self.env["sales.commission.record"].create({
            "salesperson_id": user.id,
            "plan_id": plan.id,
            "target_id": target.id,
            "achieved": 5000.0,
        })

        record._compute_commission()

        self.assertEqual(
            record.achieved_rate,
            50.0,
        )

        self.assertEqual(
            record.commission,
            1000.0,
        )

    # ---------------------------------------------------------
    # 3. create
    # ---------------------------------------------------------

    def test_create(self):
        """Test commission record creation."""

        user = self.env["res.users"].search([], limit=1)
        plan = self._create_plan()
        target = self._create_target(plan)

        with patch.object(
            SalesCommissionRecord,
            "_sync_report",
            return_value=None,
        ) as mock_sync:

            record = self.env["sales.commission.record"].create({
                "salesperson_id": user.id,
                "plan_id": plan.id,
                "target_id": target.id,
                "achieved": 1000.0,
            })

        self.assertTrue(record)
        self.assertEqual(record.achieved, 1000.0)

        mock_sync.assert_called()

    # ---------------------------------------------------------
    # 4. write
    # ---------------------------------------------------------

    def test_write(self):
        """Test updating a commission record."""

        record = self._create_record()

        with patch.object(
            SalesCommissionRecord,
            "_sync_report",
            return_value=None,
        ) as mock_sync:

            result = record.write({
                "achieved": 3000.0,
            })

        self.assertTrue(result)
        self.assertEqual(record.achieved, 3000.0)

        mock_sync.assert_called_once()

    # ---------------------------------------------------------
    # 5. _sync_report
    # ---------------------------------------------------------

    def test_sync_report(self):
        """Test synchronization with sales.commission.report."""

        user = self.env["res.users"].search([], limit=1)

        plan = self._create_plan()
        target = self._create_target(plan)

        record = self.env["sales.commission.record"].create({
            "salesperson_id": user.id,
            "plan_id": plan.id,
            "target_id": target.id,
            "achieved": 5000.0,
        })

        record._sync_report()

        report = self.env["sales.commission.report"].search([
            ("plan_id", "=", plan.id),
            ("salesperson_id", "=", user.id),
            ("period", "=", target.date_from),
        ], limit=1)

        self.assertTrue(
            report,
            "A commission report should be created.",
        )

        self.assertEqual(
            report.target_amount,
            record.target_amount,
        )

        self.assertEqual(
            report.achieved,
            record.achieved,
        )

        self.assertEqual(
            report.achieved_rate,
            record.achieved_rate,
        )

        self.assertEqual(
            report.commission,
            record.commission,
        )