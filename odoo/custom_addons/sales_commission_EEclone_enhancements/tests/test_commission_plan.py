from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..models.commission_plan import SalesCommissionPlan


class TestSalesCommissionPlan(TransactionCase):

    def _create_plan(self, **values):
        """Helper method to create a basic commission plan."""
        vals = {
            "name": "Test Commission Plan",
            "commission_type": "achievement",
            "applies_on": "salesperson",
            "periodicity": "monthly",
        }
        vals.update(values)
        return self.env["sales.commission.plan"].create(vals)

    # ---------------------------------------------------------
    # 1. _onchange_generate_targets
    # ---------------------------------------------------------

    def test_onchange_generate_targets(self):
        """Test monthly target generation through onchange."""

        plan = self.env["sales.commission.plan"].new({
            "name": "Onchange Test Plan",
            "periodicity": "monthly",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
        })

        plan._onchange_generate_targets()

        self.assertEqual(
            len(plan.target_ids),
            3,
            "Three monthly targets should be generated.",
        )

        self.assertEqual(
            plan.target_ids[0].name,
            "January 2026",
        )

        self.assertEqual(
            plan.target_ids[1].name,
            "February 2026",
        )

        self.assertEqual(
            plan.target_ids[2].name,
            "March 2026",
        )

    # ---------------------------------------------------------
    # 2. _onchange_target_commission
    # ---------------------------------------------------------

    def test_onchange_target_commission(self):
        """Test automatic creation of commission levels."""

        plan = self.env["sales.commission.plan"].new({
            "name": "Commission Test Plan",
            "target_commission": 5000.0,
        })

        plan._onchange_target_commission()

        self.assertEqual(
            len(plan.commission_ids),
            3,
            "Three commission levels should be created.",
        )

        self.assertEqual(
            plan.commission_ids[0].target_completion,
            0,
        )

        self.assertEqual(
            plan.commission_ids[1].target_completion,
            50,
        )

        self.assertEqual(
            plan.commission_ids[2].target_completion,
            100,
        )

        self.assertEqual(
            plan.commission_ids[2].commission,
            5000.0,
        )

    # ---------------------------------------------------------
    # 3. action_approve
    # ---------------------------------------------------------

    def test_action_approve(self):
        """Test approving a commission plan."""

        plan = self._create_plan()

        with patch.object(
            SalesCommissionPlan,
            "_generate_commission_records",
            return_value=None,
        ) as mock_generate:

            result = plan.action_approve()

        self.assertEqual(
            plan.state,
            "approved",
        )

        self.assertTrue(result)

        # _generate_commission_records is called twice:
        # 1. Through write() when state becomes approved
        # 2. Directly inside action_approve()
        self.assertEqual(
            mock_generate.call_count,
            2,
        )

    # ---------------------------------------------------------
    # 4. _generate_commission_records
    # ---------------------------------------------------------

    def test_generate_commission_records(self):
        """Test creation of commission records."""

        user = self.env["res.users"].search([], limit=1)

        self.assertTrue(user)

        plan = self._create_plan()

        target = self.env["sales.commission.target"].create({
            "plan_id": plan.id,
            "name": "January 2026",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "target_amount": 10000.0,
        })

        self.env["sales.commission.salesperson"].create({
            "plan_id": plan.id,
            "user_id": user.id,
        })

        plan._generate_commission_records()

        record = self.env["sales.commission.record"].search([
            ("plan_id", "=", plan.id),
            ("salesperson_id", "=", user.id),
            ("target_id", "=", target.id),
        ], limit=1)

        self.assertTrue(
            record,
            "A commission record should be created.",
        )

        self.assertEqual(
            record.achieved,
            0.0,
        )

        self.assertEqual(
            record.state,
            "draft",
        )

    # ---------------------------------------------------------
    # 5. action_done
    # ---------------------------------------------------------

    def test_action_done(self):
        """Test changing a commission plan to Done."""

        plan = self._create_plan()

        plan.action_done()

        self.assertEqual(
            plan.state,
            "done",
        )

    # ---------------------------------------------------------
    # 6. action_reset_draft
    # ---------------------------------------------------------

    def test_action_reset_draft(self):
        """Test resetting a commission plan to Draft."""

        plan = self._create_plan(
            state="approved",
        )

        plan.action_reset_draft()

        self.assertEqual(
            plan.state,
            "draft",
        )

    # ---------------------------------------------------------
    # 7. action_add_multiple_salespersons
    # ---------------------------------------------------------

    def test_action_add_multiple_salespersons(self):
        """Test Add Multiple Salespersons action."""

        plan = self._create_plan()

        result = plan.action_add_multiple_salespersons()

        self.assertTrue(result)

    # ---------------------------------------------------------
    # 8. action_add_commission_level
    # ---------------------------------------------------------

    def test_action_add_commission_level(self):
        """Test adding a commission level."""

        plan = self._create_plan()

        result = plan.action_add_commission_level()

        self.assertTrue(result)

        level = self.env["sales.commission"].search([
            ("plan_id", "=", plan.id),
            ("target_completion", "=", 0),
        ], order="id desc", limit=1)

        self.assertTrue(
            level,
            "A commission level should be created.",
        )

        self.assertEqual(
            level.commission,
            0,
        )

        self.assertEqual(
            level.otc,
            0,
        )

    # ---------------------------------------------------------
    # 9. action_commission_table
    # ---------------------------------------------------------

    def test_action_commission_table(self):
        """Test commission table action."""

        plan = self._create_plan()

        result = plan.action_commission_table()

        self.assertTrue(result)

    # ---------------------------------------------------------
    # 10. _generate_targets
    # ---------------------------------------------------------

    def test_generate_targets(self):
        """Test backend monthly target generation."""

        plan = self._create_plan(
            start_date="2026-01-01",
            end_date="2026-03-31",
            periodicity="monthly",
        )

        # create() already generates targets,
        # so remove them before testing _generate_targets().
        plan.target_ids.unlink()

        plan._generate_targets()

        targets = self.env["sales.commission.target"].search([
            ("plan_id", "=", plan.id),
        ], order="date_from")

        self.assertEqual(
            len(targets),
            3,
            "Three monthly targets should be generated.",
        )

        self.assertEqual(
            targets[0].name,
            "January 2026",
        )

        self.assertEqual(
            targets[1].name,
            "February 2026",
        )

        self.assertEqual(
            targets[2].name,
            "March 2026",
        )

    # ---------------------------------------------------------
    # 11. create
    # ---------------------------------------------------------

    def test_create(self):
        """Test commission plan creation."""

        with patch.object(
            SalesCommissionPlan,
            "_generate_targets",
            return_value=None,
        ) as mock_generate:

            plan = self.env["sales.commission.plan"].create({
                "name": "Create Test Plan",
                "commission_type": "achievement",
                "applies_on": "salesperson",
                "periodicity": "monthly",
            })

        self.assertTrue(plan)

        self.assertEqual(
            plan.name,
            "Create Test Plan",
        )

        mock_generate.assert_called_once()

    # ---------------------------------------------------------
    # 12. write
    # ---------------------------------------------------------

    def test_write(self):
        """Test updating a commission plan."""

        plan = self._create_plan()

        with patch.object(
            SalesCommissionPlan,
            "_generate_commission_records",
            return_value=None,
        ) as mock_generate:

            result = plan.write({
                "state": "approved",
            })

        self.assertTrue(result)

        self.assertEqual(
            plan.state,
            "approved",
        )

        mock_generate.assert_called_once()

    # ---------------------------------------------------------
    # 13. _sync_commission_records
    # ---------------------------------------------------------

    def test_sync_commission_records(self):
        """Test synchronization of commission records."""

        user = self.env["res.users"].search([], limit=1)

        self.assertTrue(user)

        plan = self._create_plan()

        target = self.env["sales.commission.target"].create({
            "plan_id": plan.id,
            "name": "January 2026",
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "target_amount": 10000.0,
        })

        self.env["sales.commission.salesperson"].create({
            "plan_id": plan.id,
            "user_id": user.id,
        })

        plan._sync_commission_records()

        record = self.env["sales.commission.record"].search([
            ("plan_id", "=", plan.id),
            ("salesperson_id", "=", user.id),
            ("target_id", "=", target.id),
        ], limit=1)

        self.assertTrue(
            record,
            "A commission record should be created during synchronization.",
        )

        self.assertEqual(
            record.achieved,
            0.0,
        )

        self.assertEqual(
            record.commission,
            0.0,
        )

        self.assertEqual(
            record.state,
            "draft",
        )