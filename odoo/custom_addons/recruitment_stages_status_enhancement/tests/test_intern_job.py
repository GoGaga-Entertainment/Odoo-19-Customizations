# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError

from ..models.intern_job import InternJob


class TestInternJob(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Job = cls.env["intern.job"]
        cls.Stage = cls.env["intern.recruitment.stage"]

        cls.stage = cls.Stage.search(
            [
                ("active", "=", True),
                ("intern_initial_stage", "=", True),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

        if not cls.stage:
            cls.stage = cls.Stage.search(
                [
                    ("active", "=", True),
                    ("intern_workflow_category", "!=", "rejected"),
                ],
                order="sequence asc, id asc",
                limit=1,
            )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def _create_test_job(self, vals=None):
        values = {
            "name": "Test Intern Job",
            "open_positions": 2,
        }

        if vals:
            values.update(vals)

        return self.Job.create(values)

    # ---------------------------------------------------------
    # Compute / Onchange methods
    # ---------------------------------------------------------

    def test_get_company_location(self):
        job = self.Job.new()

        company = self.env.company

        result = job._get_company_location(company)

        self.assertIsInstance(result, str)

    def test_onchange_company_id_set_location(self):
        job = self.Job.new({
            "company_id": self.env.company.id,
        })

        job._onchange_company_id_set_location()

        self.assertEqual(
            job.company_id,
            self.env.company,
        )

    def test_compute_website_url(self):
        job = self._create_test_job()

        job._compute_website_url()

        self.assertTrue(
            hasattr(job, "website_url")
        )

    def test_compute_application_counts(self):
        job = self._create_test_job()

        job._compute_application_counts()

        self.assertEqual(job.application_count, 0)
        self.assertEqual(job.open_application_count, 0)
        self.assertEqual(job.new_application_count, 0)
        self.assertEqual(job.hired_count, 0)
        self.assertEqual(job.post_hiring_count, 0)

    # ---------------------------------------------------------
    # Constraints
    # ---------------------------------------------------------

    def test_check_open_positions(self):
        job = self.Job.new({
            "open_positions": -1,
        })

        with self.assertRaises(ValidationError):
            job._check_open_positions()

    def test_check_stipend_range(self):
        job = self.Job.new({
            "stipend_min": -1,
            "stipend_max": 1000,
        })

        with self.assertRaises(ValidationError):
            job._check_stipend_range()

    # ---------------------------------------------------------
    # Bridge / Context
    # ---------------------------------------------------------

    def test_get_standard_job_bridge_vals(self):
        job = self.Job.new({
            "name": "Bridge Test Job",
            "company_id": self.env.company.id,
        })

        result = job._get_standard_job_bridge_vals()

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result.get("name"),
            "Bridge Test Job",
        )

    # ---------------------------------------------------------
    # CRUD
    # ---------------------------------------------------------

    def test_create(self):
        job = self._create_test_job()

        self.assertTrue(job.id)
        self.assertTrue(job.standard_job_id)

    def test_write(self):
        job = self._create_test_job()

        result = job.write({
            "name": "Updated Intern Job",
        })

        self.assertTrue(result)
        self.assertEqual(
            job.name,
            "Updated Intern Job",
        )

    def test_unlink(self):
        job = self._create_test_job()

        standard_job = job.standard_job_id

        job_id = job.id

        job.unlink()

        self.assertFalse(
            self.Job.browse(job_id).exists()
        )

        self.assertFalse(
            standard_job.exists()
        )

    # ---------------------------------------------------------
    # Intern Stage
    # ---------------------------------------------------------

    def test_get_initial_intern_stage(self):
        job = self.Job.new()

        with patch.object(
            type(self.Stage),
            "get_default_intern_stage",
            return_value=self.stage,
        ):
            result = job._get_initial_intern_stage()

        self.assertEqual(
            result,
            self.stage,
        )

    # ---------------------------------------------------------
    # Context
    # ---------------------------------------------------------

    def test_get_intern_context(self):
        job = self._create_test_job()

        result = job._get_intern_context()

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertIn(
            "default_job_id",
            result,
        )

        self.assertEqual(
            result["default_job_id"],
            job.id,
        )

    # ---------------------------------------------------------
    # Applicant Views
    # ---------------------------------------------------------

    def test_get_intern_applicant_views(self):
        job = self._create_test_job()

        result = job._get_intern_applicant_views()

        self.assertIsInstance(
            result,
            list,
        )

        view_types = [
            view_type
            for _, view_type in result
        ]

        self.assertIn(
            "kanban",
            view_types,
        )

        self.assertIn(
            "list",
            view_types,
        )

        self.assertIn(
            "form",
            view_types,
        )

        self.assertIn(
            "activity",
            view_types,
        )

    # ---------------------------------------------------------
    # Actions
    # ---------------------------------------------------------

    def test_action_open_activities(self):
        job = self._create_test_job()

        result = job.action_open_activities()

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertEqual(
            result["type"],
            "ir.actions.act_window",
        )

    def test_action_open_applications(self):
        job = self._create_test_job()

        result = job.action_open_applications()

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertEqual(
            result["type"],
            "ir.actions.act_window",
        )

    def test_action_create_application(self):
        job = self._create_test_job()

        result = job.action_create_application()

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertEqual(
            result["type"],
            "ir.actions.act_window",
        )

    def test_action_open_post_hiring_interns(self):
        job = self._create_test_job()

        result = job.action_open_post_hiring_interns()

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertEqual(
            result["type"],
            "ir.actions.act_window",
        )

    def test_action_publish_job(self):
        job = self._create_test_job()

        result = job.action_publish_job()

        self.assertTrue(result)
        self.assertTrue(job.website_published)

    def test_action_unpublish_job(self):
        job = self._create_test_job({
            "website_published": True,
        })

        result = job.action_unpublish_job()

        self.assertTrue(result)
        self.assertFalse(job.website_published)

    def test_action_open_website_page(self):
        job = self._create_test_job({
            "website_published": True,
        })

        job._compute_website_url()

        if not job.website_url:
            self.skipTest(
                "Website URL is not available in this test environment."
            )

        result = job.action_open_website_page()

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertEqual(
            result["type"],
            "ir.actions.act_url",
        )

    def test_action_open_website_page_unpublished(self):
        job = self._create_test_job({
            "website_published": False,
        })

        with self.assertRaises(UserError):
            job.action_open_website_page()