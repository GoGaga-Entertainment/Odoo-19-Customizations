# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase

from ..models.workflow_history import InternWorkflowHistory


class TestInternWorkflowHistory(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.History = cls.env["intern.workflow.history"]
        cls.Stage = cls.env["intern.recruitment.stage"]

        cls.old_stage = cls.Stage.search(
            [
                ("active", "=", True),
                ("intern_rejected_stage", "=", False),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

        cls.new_stage = cls.Stage.search(
            [
                ("active", "=", True),
                ("intern_rejected_stage", "=", False),
                ("id", "!=", cls.old_stage.id),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

    def test_compute_name(self):
        # Ensure the test has two usable stages.
        self.assertTrue(
            self.old_stage,
            "No active non-rejected stage is available.",
        )

        self.assertTrue(
            self.new_stage,
            "A second active non-rejected stage is required.",
        )

        applicant = self.env["intern.applicant"].new({
            "intern_first_name": "John",
            "intern_last_name": "Doe",
        })

        history = self.History.new({
            "applicant_id": applicant.id,
            "old_stage_id": self.old_stage.id,
            "new_stage_id": self.new_stage.id,
            "action_type": "approved",
        })

        history._compute_name()

        self.assertEqual(
            history.name,
            "John Doe: Moved to Next Stage (%s → %s)"
            % (
                self.old_stage.name,
                self.new_stage.name,
            ),
        )