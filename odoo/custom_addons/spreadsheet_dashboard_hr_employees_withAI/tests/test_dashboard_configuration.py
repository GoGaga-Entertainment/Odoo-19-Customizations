# -*- coding: utf-8 -*-

import json

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestHrEmployeesDashboard(TransactionCase):
    def test_dashboard_uses_shared_hr_group(self):
        dashboard = self.env.ref(
            "spreadsheet_dashboard_hr_employees_withAI.dashboard_hr_employees"
        )
        hr_group = self.env.ref(
            "spreadsheet_dashboard_hr_recruitment_withAI.spreadsheet_dashboard_group_hr"
        )
        self.assertEqual(dashboard.name, "Employees")
        self.assertEqual(dashboard.dashboard_group_id, hr_group)
        self.assertEqual(dashboard.sequence, 20)
        self.assertTrue(dashboard.is_published)

    def test_dashboard_uses_existing_degree_field(self):
        field = self.env["hr.employee"]._fields["degree_id"]
        self.assertEqual(field.type, "many2one")
        self.assertEqual(field.comodel_name, "hr.employee.degree")
        self.assertNotIn("dashboard_degree_id", self.env["hr.employee"]._fields)

    def test_dashboard_json_has_requested_components(self):
        dashboard = self.env.ref(
            "spreadsheet_dashboard_hr_employees_withAI.dashboard_hr_employees"
        )
        document = json.loads(dashboard.spreadsheet_data)
        sheet = next(sheet for sheet in document["sheets"] if sheet["name"] == "Dashboard")
        scorecards = [
            figure
            for figure in sheet["figures"]
            if figure["data"]["type"] == "scorecard"
        ]
        charts = [
            figure
            for figure in sheet["figures"]
            if figure["data"]["type"] != "scorecard"
        ]
        self.assertEqual(len(scorecards), 8)
        self.assertEqual(len(charts), 4)
        self.assertEqual(len(document["globalFilters"]), 6)
        self.assertEqual(document["formats"]["3"], "0.0%")
        self.assertEqual(document["pivotNextId"], 13)
        self.assertEqual(
            [scorecard["data"]["title"]["text"] for scorecard in scorecards],
            [
                "All-time Employee Count",
                "Active Employees",
                "New Hires (90 Days)",
                "Blacklisted Employees",
                "All Intern Count",
                "Active Interns Count",
                "New Interns (90 Days)",
                "Blacklisted Interns",
            ],
        )
        self.assertEqual(
            document["pivots"]["1"]["domain"],
            [["is_intern_employee", "=", False]],
        )
        self.assertEqual(
            document["pivots"]["2"]["domain"],
            [["active", "=", True], ["is_intern_employee", "=", False]],
        )
        self.assertEqual(
            document["pivots"]["3"]["domain"],
            [
                ["is_blacklisted_employee", "=", True],
                ["is_intern_employee", "=", False],
            ],
        )
        self.assertFalse(document["pivots"]["3"]["context"]["active_test"])
        self.assertEqual(
            document["pivots"]["4"]["domain"],
            [
                ["active", "=", True],
                ["is_intern_employee", "=", False],
                ["newly_hired", "in", [True]],
            ],
        )
        self.assertEqual(
            document["pivots"]["5"]["domain"],
            [["is_intern_employee", "=", True]],
        )
        self.assertFalse(document["pivots"]["5"]["context"]["active_test"])
        self.assertEqual(
            document["pivots"]["6"]["domain"],
            [["active", "=", True], ["is_intern_employee", "=", True]],
        )
        self.assertEqual(
            document["pivots"]["11"]["domain"],
            [
                ["active", "=", True],
                ["is_intern_employee", "=", True],
                ["newly_hired", "in", [True]],
            ],
        )
        self.assertEqual(
            document["pivots"]["12"]["domain"],
            [
                ["is_blacklisted_employee", "=", True],
                ["is_intern_employee", "=", True],
            ],
        )
        self.assertFalse(document["pivots"]["12"]["context"]["active_test"])
        for pivot_id in ("7", "8"):
            self.assertIn(
                ["is_intern_employee", "=", False],
                document["pivots"][pivot_id]["domain"],
            )
        for pivot_id in ("9", "10"):
            self.assertEqual(
                document["pivots"][pivot_id]["domain"][0:2],
                [
                    ["active", "=", True],
                    ["is_intern_employee", "=", True],
                ],
            )
            self.assertEqual(
                document["pivots"][pivot_id]["measures"][0]["userDefinedName"],
                "Interns",
            )
        charts_by_title = {
            chart["data"]["title"]["text"]: chart
            for chart in charts
        }
        self.assertEqual(
            set(charts_by_title),
            {
                "Employees by Certification Level",
                "Employees by Employment Type",
                "Interns by Certification Level",
                "Interns by Internships",
            },
        )
        for title in (
            "Employees by Certification Level",
            "Employees by Employment Type",
        ):
            self.assertIn(
                ["is_intern_employee", "=", False],
                charts_by_title[title]["data"]["searchParams"]["domain"],
            )
        for title in (
            "Interns by Certification Level",
            "Interns by Internships",
        ):
            self.assertIn(
                ["is_intern_employee", "=", True],
                charts_by_title[title]["data"]["searchParams"]["domain"],
            )
        internship_chart = charts_by_title["Interns by Internships"]
        self.assertEqual(
            internship_chart["data"]["metaData"]["groupBy"],
            ["intern_job_id"],
        )
        self.assertIn(
            ["intern_job_id", "!=", False],
            internship_chart["data"]["searchParams"]["domain"],
        )
        self.assertNotIn(
            "88f7316b-7fc0-4c4a-a2f5-employee-job",
            internship_chart["data"]["fieldMatching"],
        )
        self.assertEqual(sheet["cells"]["A1"], "Employees")
        self.assertEqual(sheet["cells"]["A40"], "Interns")
        self.assertEqual(sheet["styles"]["A1"], 8)
        self.assertEqual(sheet["styles"]["A40"], 8)
        self.assertEqual(sheet["cells"]["A11"], "Employees by Nationality")
        self.assertEqual(sheet["cells"]["A26"], "Employees by Degree")
        self.assertEqual(sheet["cells"]["A50"], "Interns by Nationality")
        self.assertEqual(sheet["cells"]["A65"], "Interns by Degree")
        self.assertEqual(sheet["cells"]["A51"], "=PIVOT(9, 10, FALSE, FALSE)")
        self.assertEqual(sheet["cells"]["A66"], "=PIVOT(10, 10, FALSE, FALSE)")
        self.assertIn("Data!$B$6", sheet["cells"]["C52"])
        self.assertIn("Data!$B$6", sheet["cells"]["C67"])
        self.assertEqual(
            charts_by_title["Employees by Employment Type"]["offset"],
            {"x": 505, "y": 245},
        )
        self.assertEqual(
            charts_by_title["Employees by Certification Level"]["offset"],
            {"x": 505, "y": 660},
        )
        self.assertEqual(
            charts_by_title["Interns by Internships"]["offset"],
            {"x": 505, "y": 1295},
        )
        self.assertEqual(
            charts_by_title["Interns by Certification Level"]["offset"],
            {"x": 505, "y": 1710},
        )
        for scorecard in scorecards[4:]:
            self.assertEqual(scorecard["offset"]["y"], 1100)
        self.assertEqual(
            document["chartOdooMenusReferences"],
            {
                "kpi-active-employees": "hr.menu_hr_employee_payroll",
                "kpi-blacklisted-employees": (
                    "hr_customizations.menu_hr_blacklisted_employees"
                ),
                "kpi-active-interns": (
                    "hr_customizations.menu_hr_intern_employees"
                ),
                "kpi-blacklisted-interns": (
                    "hr_customizations.menu_hr_blacklisted_employees"
                ),
            },
        )

    def test_scorecard_drilldowns_reuse_existing_employee_menus(self):
        self.assertEqual(self.env.ref("hr.menu_hr_employee_payroll").name, "Employees")
        self.assertEqual(
            self.env.ref("hr_customizations.menu_hr_intern_employees").name,
            "Interns",
        )
        intern_action = self.env.ref("hr_customizations.action_hr_intern_employees")
        self.assertEqual(intern_action.name, "Interns")
        self.assertEqual(intern_action.res_model, "hr.employee")
        self.assertTrue(intern_action.view_mode.startswith("kanban"))
        employee_kanban = self.env.ref("hr.hr_kanban_view_employees")
        self.assertEqual(employee_kanban.model, "hr.employee")
        self.assertEqual(employee_kanban.type, "kanban")
        self.assertEqual(
            self.env.ref("hr_customizations.menu_hr_intern_employees").action,
            intern_action,
        )
        self.assertEqual(
            self.env.ref("hr_customizations.menu_hr_blacklisted_employees").name,
            "Blacklisted",
        )
        for obsolete_xml_id in (
            "menu_dashboard_employee_records",
            "menu_dashboard_active_employees",
            "menu_dashboard_blacklisted_employees",
            "menu_dashboard_active_interns",
            "menu_dashboard_blacklisted_interns",
            "action_dashboard_active_employees",
            "action_dashboard_blacklisted_employees",
            "action_dashboard_active_interns",
            "action_dashboard_blacklisted_interns",
        ):
            self.assertFalse(
                self.env.ref(
                    "spreadsheet_dashboard_hr_employees_withAI.%s"
                    % obsolete_xml_id,
                    raise_if_not_found=False,
                )
            )

    def test_internship_chart_uses_existing_intern_job_field(self):
        field = self.env["hr.employee"]._fields["intern_job_id"]
        self.assertEqual(field.type, "many2one")
        self.assertEqual(field.comodel_name, "intern.job")
