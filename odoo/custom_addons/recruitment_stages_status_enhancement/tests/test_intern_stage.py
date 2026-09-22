# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError

from ..models.intern_stage import InternRecruitmentStage


class TestInternRecruitmentStage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Stage = cls.env["intern.recruitment.stage"]

        # ---------------------------------------------------------
        # Initial Stage
        # ---------------------------------------------------------

        cls.initial_stage = cls.Stage.search(
            [
                ("active", "=", True),
                ("intern_initial_stage", "=", True),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

        if not cls.initial_stage:
            cls.initial_stage = cls.Stage.create({
                "name": "Test Initial Stage",
                "sequence": 900,
                "intern_workflow_category": "application",
                "intern_initial_stage": True,
                "intern_final_stage": False,
                "intern_rejected_stage": False,
            })

        # ---------------------------------------------------------
        # Rejected Stage
        # ---------------------------------------------------------

        cls.rejected_stage = cls.Stage.search(
            [
                ("active", "=", True),
                ("intern_rejected_stage", "=", True),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

        if not cls.rejected_stage:
            cls.rejected_stage = cls.Stage.create({
                "name": "Test Rejected Stage",
                "sequence": 999,
                "intern_workflow_category": "rejected",
                "intern_initial_stage": False,
                "intern_final_stage": False,
                "intern_rejected_stage": True,
            })

        # ---------------------------------------------------------
        # Normal Workflow Stage
        # ---------------------------------------------------------

        cls.normal_stage = cls.Stage.search(
            [
                ("active", "=", True),
                ("intern_initial_stage", "=", False),
                ("intern_rejected_stage", "=", False),
                ("intern_final_stage", "=", False),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

        if not cls.normal_stage:
            cls.normal_stage = cls.Stage.create({
                "name": "Test Screening Stage",
                "sequence": 950,
                "intern_workflow_category": "screening",
                "intern_initial_stage": False,
                "intern_final_stage": False,
                "intern_rejected_stage": False,
            })

        # ---------------------------------------------------------
        # Final Stage
        # ---------------------------------------------------------

        cls.final_stage = cls.Stage.search(
            [
                ("active", "=", True),
                ("intern_final_stage", "=", True),
                ("intern_rejected_stage", "=", False),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

        if not cls.final_stage:
            cls.final_stage = cls.Stage.create({
                "name": "Test Final Stage",
                "sequence": 998,
                "intern_workflow_category": "completed",
                "intern_initial_stage": False,
                "intern_final_stage": True,
                "intern_rejected_stage": False,
            })

    # ---------------------------------------------------------
    # CRUD
    # ---------------------------------------------------------

    def test_create(self):
        """
        Test that a normal intern workflow stage
        can be created successfully.
        """

        stage = self.Stage.create({
            "name": "Created Test Stage",
            "intern_workflow_category": "screening",
            "intern_initial_stage": False,
            "intern_final_stage": False,
            "intern_rejected_stage": False,
        })

        self.assertTrue(stage.id)

        self.assertEqual(
            stage.name,
            "Created Test Stage",
        )

        self.assertFalse(
            stage.intern_rejected_stage,
        )

        self.assertFalse(
            stage.intern_initial_stage,
        )

        self.assertFalse(
            stage.intern_final_stage,
        )

    def test_write(self):
        stage = self.Stage.create({
            "name": "Write Test Stage",
            "intern_workflow_category": "screening",
        })

        result = stage.write({
            "name": "Updated Test Stage",
        })

        self.assertTrue(result)

        self.assertEqual(
            stage.name,
            "Updated Test Stage",
        )

    # ---------------------------------------------------------
    # Constraints
    # ---------------------------------------------------------

    def test_check_single_initial_stage(self):
        stage = self.Stage.new({
            "intern_initial_stage": False,
        })

        result = stage._check_single_initial_stage()

        self.assertIsNone(result)

    def test_check_single_rejected_stage(self):
        stage = self.Stage.new({
            "intern_rejected_stage": False,
        })

        result = stage._check_single_rejected_stage()

        self.assertIsNone(result)

    def test_check_rejected_not_final(self):
        stage = self.Stage.new({
            "intern_rejected_stage": False,
            "intern_final_stage": False,
        })

        result = stage._check_rejected_not_final()

        self.assertIsNone(result)

    # ---------------------------------------------------------
    # Workflow Helpers
    # ---------------------------------------------------------

    def test_get_ordered_intern_workflow_stages(self):
        result = (
            self.initial_stage
            ._get_ordered_intern_workflow_stages()
        )

        self.assertTrue(result)

        self.assertNotIn(
            self.rejected_stage,
            result,
        )

    def test_get_default_intern_stage(self):
        result = self.Stage.get_default_intern_stage()

        self.assertTrue(result)

        self.assertTrue(
            result.active,
        )

        self.assertFalse(
            result.intern_rejected_stage,
        )

    def test_get_rejected_intern_stage(self):
        result = self.Stage.get_rejected_intern_stage()

        self.assertTrue(result)

        self.assertTrue(
            result.intern_rejected_stage,
        )

    def test_get_next_intern_stage(self):
        result = (
            self.initial_stage
            .get_next_intern_stage()
        )

        self.assertTrue(result)

        self.assertNotEqual(
            result,
            self.initial_stage,
        )

    def test_get_previous_intern_stage(self):
        result = (
            self.normal_stage
            .get_previous_intern_stage()
        )

        self.assertTrue(result)

    def test_get_next_intern_stage_from_final_stage(self):
        result = (
            self.final_stage
            .get_next_intern_stage()
        )

        self.assertFalse(result)

    def test_get_previous_intern_stage_from_first_stage(self):
        result = (
            self.initial_stage
            .get_previous_intern_stage()
        )

        self.assertFalse(result)

    def test_rejected_stage_has_no_next_or_previous(self):
        self.assertFalse(
            self.rejected_stage
            .get_next_intern_stage()
        )

        self.assertFalse(
            self.rejected_stage
            .get_previous_intern_stage()
        )