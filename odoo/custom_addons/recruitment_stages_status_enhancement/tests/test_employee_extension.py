# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError

from ..models.employee_extension import HrEmployee


class TestHrEmployee(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Employee = cls.env["hr.employee"]

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def _create_intern_employee(self):
        """Create a valid intern employee for conversion tests."""

        employee = self.Employee.create({
            "name": "John Employee",
            "is_intern_employee": True,
            "intern_source": "intern_recruitment",
        })

        return employee

    # ---------------------------------------------------------
    # Convert Intern To Employee
    # ---------------------------------------------------------

    def test_action_convert_intern_to_employee(self):
        employee = self._create_intern_employee()

        result = employee.action_convert_intern_to_employee()

        self.assertIsInstance(
            result,
            dict,
        )

        self.assertEqual(
            result["type"],
            "ir.actions.act_window",
        )

        self.assertEqual(
            result["name"],
            "Employee",
        )

        self.assertEqual(
            result["res_model"],
            "hr.employee",
        )

        self.assertEqual(
            result["res_id"],
            employee.id,
        )

        self.assertEqual(
            result["view_mode"],
            "form",
        )

        self.assertEqual(
            result["target"],
            "current",
        )

        self.assertFalse(
            employee.is_intern_employee
        )

    def test_action_convert_archived_intern(self):
        employee = self._create_intern_employee()

        employee.active = False

        with self.assertRaises(UserError):
            employee.action_convert_intern_to_employee()

    def test_action_convert_regular_employee(self):
        employee = self.Employee.create({
            "name": "Regular Employee",
            "is_intern_employee": False,
            "intern_source": "manual",
        })

        with self.assertRaises(UserError):
            employee.action_convert_intern_to_employee()

    def test_action_convert_blacklisted_intern(self):
        employee = self._create_intern_employee()

        # Only run this part if the blacklist field exists
        # in the installed hr.employee model.
        if "is_blacklisted_employee" not in employee._fields:
            self.skipTest(
                "is_blacklisted_employee field is not available."
            )

        employee.is_blacklisted_employee = True

        with self.assertRaises(UserError):
            employee.action_convert_intern_to_employee()