# -*- coding: utf-8 -*-

from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestInternApplicant(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Applicant = cls.env["intern.applicant"]
        cls.Job = cls.env["intern.job"]
        cls.Stage = cls.env["intern.recruitment.stage"]
        cls.History = cls.env["intern.workflow.history"]
        cls.Employee = cls.env["hr.employee"]

        # ---------------------------------------------------------
        # Test Job
        # ---------------------------------------------------------
        cls.job = cls.Job.create({
            "name": "Intern Applicant Test Job",
            "open_positions": 2,
        })

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
            cls.initial_stage = cls.Stage.search(
                [
                    ("active", "=", True),
                    ("intern_workflow_category", "!=", "rejected"),
                ],
                order="sequence asc, id asc",
                limit=1,
            )

        if not cls.initial_stage:
            cls.initial_stage = cls.Stage.create({
                "name": "Test Initial Stage",
                "sequence": 10,
                "intern_initial_stage": True,
            })

        # ---------------------------------------------------------
        # Screening Stage
        # ---------------------------------------------------------
        cls.screening_stage = cls.Stage.search(
            [
                ("active", "=", True),
                ("intern_workflow_category", "=", "screening"),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

        if not cls.screening_stage:
            cls.screening_stage = cls.Stage.create({
                "name": "Test Screening",
                "sequence": 100,
                "intern_workflow_category": "screening",
            })

    # ---------------------------------------------------------
    # Test Data Helpers
    # ---------------------------------------------------------

    def _get_degree(self):
        """Return a real hr.employee.degree record."""
        degree = self.env["hr.employee.degree"].search(
            [],
            limit=1,
        )

        if not degree:
            degree = self.env["hr.employee.degree"].create({
                "name": "B.Tech",
            })

        return degree

    def _get_university(self):
        """Return a real hr.employee.university record."""
        university = self.env["hr.employee.university"].search(
            [],
            limit=1,
        )

        if not university:
            university = self.env["hr.employee.university"].create({
                "name": "Test University",
            })

        return university

    def _valid_applicant_vals(self):
        """Return valid values according to InternApplicant validation."""
        return {
            "intern_first_name": "John",
            "intern_last_name": "Doe",
            "email_from": "john.doe@example.com",
            "partner_phone": "9876543210",
            "pan_number": "ABCDE1234F",
            "availability": "2026-10-01",
            "job_id": self.job.id,
            "stage_id": self.initial_stage.id,
            "degree_id": self._get_degree().id,
            "university_id": self._get_university().id,
            "linkedin_profile": "https://www.linkedin.com/in/johndoe",
            "salary_expected": 10000,
        }

    def _create_test_applicant(self):
        """Create a persisted applicant for tests requiring a DB record."""
        return self.Applicant.create(
            self._valid_applicant_vals()
        )

    # ---------------------------------------------------------
    # Name Handling
    # ---------------------------------------------------------

    def test_compute_partner_name(self):
        applicant = self.Applicant.new({
            "intern_first_name": "John",
            "intern_middle_name": "Michael",
            "intern_last_name": "Doe",
        })

        applicant._compute_partner_name()

        self.assertEqual(
            applicant.partner_name,
            "John Michael Doe",
        )

    def test_get_intern_full_name(self):
        applicant = self.Applicant.new({
            "intern_first_name": "John",
            "intern_middle_name": "Michael",
            "intern_last_name": "Doe",
        })

        result = applicant._get_intern_full_name()

        self.assertEqual(
            result,
            "John Michael Doe",
        )

    def test_onchange_intern_name_parts(self):
        applicant = self.Applicant.new({
            "intern_first_name": "John",
            "intern_middle_name": "Michael",
            "intern_last_name": "Doe",
        })

        applicant._onchange_intern_name_parts()

        self.assertEqual(
            applicant.partner_name,
            "John Michael Doe",
        )

    # ---------------------------------------------------------
    # PAN
    # ---------------------------------------------------------

    def test_onchange_pan_number(self):
        applicant = self.Applicant.new({
            "pan_number": "abcde1234f",
        })

        applicant._onchange_pan_number()

        self.assertEqual(
            applicant.pan_number,
            "ABCDE1234F",
        )

    def test_normalize_pan_number(self):
        applicant = self.Applicant.new()

        result = applicant._normalize_pan_number(
            " abcde1234f "
        )

        self.assertEqual(
            result,
            "ABCDE1234F",
        )

    def test_validate_pan_format(self):
        applicant = self.Applicant.new()

        # Valid PAN does not return True.
        # The method simply completes without raising an exception.
        result = applicant._validate_pan_format(
            "ABCDE1234F"
        )

        self.assertIsNone(result)

        with self.assertRaises(ValidationError):
            applicant._validate_pan_format("INVALID")

    def test_get_blacklisted_employee_by_pan(self):
        applicant = self.Applicant.new()

        result = applicant._get_blacklisted_employee_by_pan(
            "ABCDE1234F"
        )

        self.assertFalse(result)

    def test_raise_blacklisted_pan_error(self):
        applicant = self.Applicant.new({
            "intern_first_name": "John",
            "intern_last_name": "Doe",
            "pan_number": "ABCDE1234F",
        })

        blacklisted_employee = SimpleNamespace(
            name="Blacklisted Employee",
            pan_number="ABCDE1234F",
            _fields={},
        )

        with self.assertRaises(ValidationError):
            applicant._raise_blacklisted_pan_error(
                blacklisted_employee
            )

    def test_check_blacklisted_pan_number(self):
        applicant = self.Applicant.new()

        result = applicant._check_blacklisted_pan_number(
            "ABCDE1234F"
        )

        self.assertIsNone(result)

    # ---------------------------------------------------------
    # Education
    # ---------------------------------------------------------

    def test_onchange_degree_id(self):
        degree = self._get_degree()

        applicant = self.Applicant.new({
            "degree_id": degree.id,
        })

        applicant._onchange_degree_id()

        self.assertEqual(
            applicant.type_id,
            degree.name,
        )

    def test_compute_university_location(self):
        university = self._get_university()

        applicant = self.Applicant.new({
            "university_id": university.id,
        })

        applicant._compute_university_location()

        city = university.city_id
        state = city.state_id if city else False
        country = (
            city.country_id
            if city
            else False
        )

        self.assertEqual(
            applicant.university_city_id,
            city,
        )
        self.assertEqual(
            applicant.university_state_id,
            state,
        )
        self.assertEqual(
            applicant.university_country_id,
            country,
        )

    # ---------------------------------------------------------
    # Resume Attachment
    # ---------------------------------------------------------

    def test_sync_resume_main_attachment(self):
        applicant = self.Applicant.new()

        result = applicant._sync_resume_main_attachment()

        self.assertIsNone(result)

    # ---------------------------------------------------------
    # Default Values
    # ---------------------------------------------------------

    def test_default_get(self):
        with patch.object(
            type(self.Stage),
            "get_default_intern_stage",
            return_value=self.initial_stage,
        ):
            result = self.Applicant.default_get(
                ["stage_id"]
            )

        self.assertEqual(
            result.get("stage_id"),
            self.initial_stage.id,
        )

    # ---------------------------------------------------------
    # Create / Write
    # ---------------------------------------------------------

    def test_create(self):
        vals = self._valid_applicant_vals()

        applicant = self.Applicant.create(vals)

        self.assertTrue(applicant.id)

        self.assertEqual(
            applicant.pan_number,
            "ABCDE1234F",
        )

        self.assertEqual(
            applicant.type_id,
            applicant.degree_id.name,
        )

    def test_write(self):
        applicant = self._create_test_applicant()

        result = applicant.write({
            "intern_first_name": "Jane",
        })

        self.assertTrue(result)

        self.assertEqual(
            applicant.intern_first_name,
            "Jane",
        )

    # ---------------------------------------------------------
    # Kanban Stage Expansion
    # ---------------------------------------------------------

    def test_read_group_stage_ids(self):
        result = self.Applicant._read_group_stage_ids(
            self.Stage.search([], limit=2),
            [],
        )

        self.assertIsNotNone(result)

        self.assertTrue(
            all(stage.active for stage in result)
        )

    # ---------------------------------------------------------
    # Workflow Buttons
    # ---------------------------------------------------------

    def test_compute_intern_workflow_buttons(self):
        applicant = self.Applicant.new({
            "active": False,
        })

        applicant._compute_intern_workflow_buttons()

        self.assertFalse(
            applicant.intern_can_approve
        )
        self.assertFalse(
            applicant.intern_can_send_back
        )
        self.assertFalse(
            applicant.intern_can_reject
        )
        self.assertFalse(
            applicant.intern_can_create_employee
        )

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def test_check_intern_application_validation(self):
        applicant = self._create_test_applicant()

        result = applicant._check_intern_application_validation()

        self.assertIsNone(result)

    def test_validate_intern_required_fields(self):
        applicant = self.Applicant.new({
            "active": False,
        })

        # Inactive applicants are skipped.
        result = applicant._validate_intern_required_fields()

        self.assertIsNone(result)

    # ---------------------------------------------------------
    # Contact
    # ---------------------------------------------------------

    def test_prepare_intern_contact_vals(self):
        applicant = self.Applicant.new({
            "intern_first_name": "John",
            "intern_last_name": "Doe",
            "email_from": "john.doe@example.com",
            "partner_phone": "9876543210",
        })

        result = applicant._prepare_intern_contact_vals()

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertEqual(
            result.get("name"),
            "John Doe",
        )

        self.assertEqual(
            result.get("email"),
            "john.doe@example.com",
        )

        self.assertEqual(
            result.get("phone"),
            "9876543210",
        )

    def test_create_or_update_intern_contact(self):
        applicant = self._create_test_applicant()

        contact = applicant._create_or_update_intern_contact()

        self.assertTrue(contact)

        self.assertEqual(
            contact.email,
            "john.doe@example.com",
        )

        self.assertEqual(
            contact.phone,
            "9876543210",
        )

        self.assertEqual(
            applicant.partner_id,
            contact,
        )

    # ---------------------------------------------------------
    # Workflow History
    # ---------------------------------------------------------

    def test_create_intern_workflow_history(self):
        applicant = self._create_test_applicant()

        # The applicant's create() already creates one history record.
        # Test the helper itself with a persisted applicant.
        before_count = self.History.search_count([
            ("applicant_id", "=", applicant.id),
        ])

        applicant._create_intern_workflow_history(
            old_stage=self.initial_stage,
            new_stage=self.screening_stage,
            action_type="approved",
        )

        after_count = self.History.search_count([
            ("applicant_id", "=", applicant.id),
        ])

        self.assertEqual(
            after_count,
            before_count + 1,
        )

    # ---------------------------------------------------------
    # Manager Access
    # ---------------------------------------------------------

    def test_check_intern_manager_access(self):
        applicant = self.Applicant.new()

        result = applicant._check_intern_manager_access()

        self.assertTrue(result)

    # ---------------------------------------------------------
    # Workflow Movement
    # ---------------------------------------------------------

    def test_move_to_intern_stage(self):
        applicant = self._create_test_applicant()

        result = applicant._move_to_intern_stage(
            self.screening_stage,
            action_type="approved",
        )

        self.assertIsNone(result)

        self.assertEqual(
            applicant.stage_id,
            self.screening_stage,
        )

    def test_action_intern_approve(self):
        applicant = self._create_test_applicant()

        next_stage = applicant.stage_id.get_next_intern_stage()

        if not next_stage:
            self.skipTest(
                "No next intern stage is configured."
            )

        with patch.object(
            type(applicant),
            "_check_intern_manager_access",
            return_value=True,
        ):
            result = applicant.action_intern_approve()

        self.assertTrue(result)

        self.assertEqual(
            applicant.stage_id,
            next_stage,
        )

    def test_action_intern_send_back(self):
        applicant = self._create_test_applicant()

        # Find a stage that actually permits send-back and
        # has a previous stage.
        send_back_stage = self.Stage.search(
            [
                ("active", "=", True),
                ("intern_allow_send_back", "=", True),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

        if not send_back_stage:
            self.skipTest(
                "No stage configured with send-back permission."
            )

        previous_stage = (
            send_back_stage.get_previous_intern_stage()
        )

        if not previous_stage:
            self.skipTest(
                "No previous stage configured for send-back stage."
            )

        applicant.with_context(
            allow_intern_stage_change=True
        ).write({
            "stage_id": send_back_stage.id,
        })

        with patch.object(
            type(applicant),
            "_check_intern_manager_access",
            return_value=True,
        ):
            result = applicant.action_intern_send_back()

        self.assertTrue(result)

        self.assertEqual(
            applicant.stage_id,
            previous_stage,
        )

    def test_action_intern_reject(self):
        applicant = self._create_test_applicant()

        rejected_stage = (
            self.Stage.get_rejected_intern_stage()
        )

        if not rejected_stage:
            self.skipTest(
                "No rejected intern stage is configured."
            )

        if not applicant.stage_id.intern_allow_reject:
            self.skipTest(
                "Current stage does not allow rejection."
            )

        with patch.object(
            type(applicant),
            "_check_intern_manager_access",
            return_value=True,
        ):
            result = applicant.action_intern_reject()

        self.assertTrue(result)

        self.assertEqual(
            applicant.stage_id,
            rejected_stage,
        )

    # ---------------------------------------------------------
    # Employee
    # ---------------------------------------------------------

    def test_prepare_employee_vals(self):
        applicant = self._create_test_applicant()

        contact = self.env["res.partner"].create({
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "9876543210",
        })

        result = applicant._prepare_employee_vals(
            contact
        )

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertEqual(
            result.get("name"),
            "John Doe",
        )

        self.assertEqual(
            result.get("intern_applicant_id"),
            applicant.id,
        )

        self.assertEqual(
            result.get("intern_job_id"),
            self.job.id,
        )

        self.assertEqual(
            result.get("is_intern_employee"),
            True,
        )

        self.assertEqual(
            result.get("intern_source"),
            "intern_recruitment",
        )

    def test_create_employee_from_applicant(self):
        applicant = self._create_test_applicant()

        # Employee creation is allowed only from a stage
        # configured as "Create Employee Stage".
        create_employee_stage = self.Stage.search(
            [
                ("active", "=", True),
                ("intern_create_employee_stage", "=", True),
            ],
            order="sequence asc, id asc",
            limit=1,
        )

        if not create_employee_stage:
            self.skipTest(
                "No Create Employee Stage is configured."
            )

        applicant.with_context(
            allow_intern_stage_change=True
        ).write({
            "stage_id": create_employee_stage.id,
        })

        with patch.object(
            type(applicant),
            "_check_intern_manager_access",
            return_value=True,
        ):
            result = applicant.create_employee_from_applicant()

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertEqual(
            result.get("res_model"),
            "hr.employee",
        )

        self.assertTrue(
            result.get("res_id")
        )

        self.assertEqual(
            applicant.employee_id.id,
            result.get("res_id"),
        )

        self.assertEqual(
            applicant.application_status,
            "hired",
        )