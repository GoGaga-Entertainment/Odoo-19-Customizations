# -*- coding: utf-8 -*-

import json

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestHrRecruitmentDashboard(TransactionCase):
    def test_dashboard_is_published_in_hr_group(self):
        dashboard = self.env.ref(
            "spreadsheet_dashboard_hr_recruitment_withAI.dashboard_hr_recruitment"
        )
        self.assertTrue(dashboard.is_published)
        self.assertEqual(dashboard.name, "Recruitment")
        self.assertEqual(dashboard.dashboard_group_id.name, "HR")

    def test_dashboard_group_grants_both_recruitment_accesses(self):
        group = self.env.ref(
            "spreadsheet_dashboard_hr_recruitment_withAI."
            "group_hr_recruitment_dashboard"
        )
        self.assertIn(
            self.env.ref("hr_recruitment.group_hr_recruitment_interviewer"),
            group.implied_ids,
        )

    def test_dashboard_has_aligned_employee_and_intern_sections(self):
        dashboard = self.env.ref(
            "spreadsheet_dashboard_hr_recruitment_withAI.dashboard_hr_recruitment"
        )
        document = json.loads(dashboard.spreadsheet_data)
        sheet = next(
            sheet for sheet in document["sheets"] if sheet["name"] == "Dashboard"
        )
        scorecards = [
            figure
            for figure in sheet["figures"]
            if figure["data"]["type"] == "scorecard"
        ]
        charts = {
            figure["data"]["title"]["text"]: figure
            for figure in sheet["figures"]
            if figure["data"]["type"] != "scorecard"
        }

        self.assertEqual(sheet["cells"]["A1"], "Employees")
        self.assertEqual(sheet["cells"]["A40"], "Interns")
        self.assertEqual(sheet["styles"]["A1"], 8)
        self.assertEqual(sheet["styles"]["A40"], 8)

        self.assertEqual(
            [card["data"]["title"]["text"] for card in scorecards],
            [
                "All-time Job Applicants",
                "Active Job Vacancies",
                "Active Job Applicants",
                "All-time Internship Applicants",
                "Active Internship Roles",
                "Active Internship Applicants",
            ],
        )
        self.assertEqual(
            [card["offset"] for card in scorecards[:3]],
            [
                {"x": 0, "y": 50},
                {"x": 330, "y": 50},
                {"x": 660, "y": 50},
            ],
        )
        self.assertEqual(
            [card["offset"] for card in scorecards[3:]],
            [
                {"x": 0, "y": 1100},
                {"x": 330, "y": 1100},
                {"x": 660, "y": 1100},
            ],
        )

        self.assertEqual(sheet["cells"]["F11"], "Job Applicants by University")
        self.assertEqual(
            sheet["cells"]["F50"],
            "Internship Applicants by University",
        )
        self.assertEqual(sheet["cells"]["H12"], "% of Total")
        self.assertEqual(sheet["cells"]["H51"], "% of Total")
        self.assertIn("Data!$B$1", sheet["cells"]["H13"])
        self.assertIn("Data!$B$2", sheet["cells"]["H52"])

        self.assertEqual(
            charts["Job Applicants by Role"]["offset"],
            {"x": 0, "y": 245},
        )
        self.assertEqual(
            charts["Internship Applicants by Role"]["offset"],
            {"x": 0, "y": 1225},
        )
        self.assertEqual(
            charts["Job Applications by Month"]["offset"],
            {"x": 0, "y": 660},
        )
        self.assertEqual(charts["Job Applications by Month"]["width"], 990)
        self.assertEqual(
            charts["Internship Applications by Month"]["offset"],
            {"x": 0, "y": 1640},
        )
        self.assertEqual(
            charts["Internship Applications by Month"]["width"],
            990,
        )
        self.assertEqual(
            charts["Interns By Stages"]["offset"],
            {"x": 0, "y": 2055},
        )
        self.assertEqual(charts["Interns By Stages"]["width"], 990)
        self.assertEqual(
            charts["Interns By Stages"]["data"]["metaData"]["groupBy"],
            ["stage_id"],
        )
        self.assertEqual(
            charts["Interns By Stages"]["data"]["searchParams"]["domain"],
            [
                [
                    "stage_id.intern_workflow_category",
                    "in",
                    ["selection", "onboarding", "active", "completed"],
                ]
            ],
        )

        self.assertEqual(
            [dashboard_filter["label"] for dashboard_filter in document["globalFilters"]],
            [
                "Job Role",
                "Job University",
                "Internship Role",
                "Internship University",
            ],
        )

    def test_scorecards_reuse_existing_job_kanban_menus(self):
        dashboard = self.env.ref(
            "spreadsheet_dashboard_hr_recruitment_withAI.dashboard_hr_recruitment"
        )
        document = json.loads(dashboard.spreadsheet_data)
        self.assertEqual(
            document["chartOdooMenusReferences"],
            {
                "kpi-active-job-vacancies": (
                    "hr_recruitment.menu_hr_job_position"
                ),
                "kpi-active-job-applicants": (
                    "hr_recruitment.menu_hr_job_position"
                ),
                "kpi-active-internship-roles": (
                    "recruitment_stages_status_enhancement."
                    "menu_intern_job_positions_list"
                ),
                "kpi-active-intern-applicants": (
                    "recruitment_stages_status_enhancement."
                    "menu_intern_job_positions_list"
                ),
            },
        )

        job_menu = self.env.ref("hr_recruitment.menu_hr_job_position")
        intern_menu = self.env.ref(
            "recruitment_stages_status_enhancement.menu_intern_job_positions_list"
        )
        self.assertEqual(job_menu.action.res_model, "hr.job")
        self.assertEqual(intern_menu.action.res_model, "intern.job")
        self.assertEqual(
            self.env.ref("hr_recruitment.view_hr_job_kanban").model,
            "hr.job",
        )
        self.assertEqual(
            self.env.ref(
                "recruitment_stages_status_enhancement.view_intern_job_kanban"
            ).model,
            "intern.job",
        )
        self.assertIn(
            self.env.ref(
                "recruitment_stages_status_enhancement."
                "group_intern_recruitment_user"
            ),
            group.implied_ids,
        )
