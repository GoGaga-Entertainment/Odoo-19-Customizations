from odoo.tests.common import TransactionCase

from ..models.dashboard_final_fixes import (
    SpreadsheetDashboardFinalFixes,
    DATE_FILTER_ID,
    VENUE_FILTER_ID,
    TEMPLATE_FILTER_ID,
    TAGS_FILTER_ID,
    ORGANIZER_FILTER_ID,
    COUNTRY_FILTER_ID,
    EVENT_REPORT_MODEL,
    TOP_COUNTRIES_FIGURE_ID,
    TOP_COUNTRIES_CHART_ID,
    TOP_COUNTRIES_PIVOT_NAME,
)


class TestDashboardFinalFixes(TransactionCase):

    def test_find_sheet(self):
        data = {
            "sheets": [
                {
                    "name": "Dashboard",
                    "id": "dashboard_sheet",
                },
                {
                    "name": "Data",
                    "id": "data_sheet",
                },
            ]
        }

        result = SpreadsheetDashboardFinalFixes._find_sheet(
            data,
            "Dashboard"
        )

        self.assertEqual(
            result["name"],
            "Dashboard"
        )
        self.assertEqual(
            result["id"],
            "dashboard_sheet"
        )

    def test_find_top_countries(self):
        dashboard = {
            "figures": [
                {
                    "tag": "chart",
                    "data": {
                        "title": {
                            "text": "Revenue"
                        }
                    }
                },
                {
                    "tag": "carousel",
                    "data": {
                        "title": {
                            "text": "Top Countries"
                        }
                    }
                },
            ]
        }

        result = SpreadsheetDashboardFinalFixes._find_top_countries(
            dashboard
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result["data"]["title"]["text"],
            "Top Countries"
        )

    def test_ensure_country_filter(self):
        data = {
            "globalFilters": []
        }

        result = SpreadsheetDashboardFinalFixes._ensure_country_filter(
            data
        )

        self.assertEqual(
            result,
            COUNTRY_FILTER_ID
        )

        self.assertEqual(
            len(data["globalFilters"]),
            1
        )

        country_filter = data["globalFilters"][0]

        self.assertEqual(
            country_filter["id"],
            COUNTRY_FILTER_ID
        )
        self.assertEqual(
            country_filter["type"],
            "relation"
        )
        self.assertEqual(
            country_filter["label"],
            "Country"
        )
        self.assertEqual(
            country_filter["modelName"],
            "res.country"
        )

    def test_top_country_field_matching(self):
        dashboard = self.env["spreadsheet.dashboard"]

        data = {
            "globalFilters": []
        }

        result = dashboard._top_country_field_matching(
            data
        )

        self.assertIn(
            DATE_FILTER_ID,
            result
        )
        self.assertIn(
            VENUE_FILTER_ID,
            result
        )
        self.assertIn(
            TEMPLATE_FILTER_ID,
            result
        )
        self.assertIn(
            TAGS_FILTER_ID,
            result
        )
        self.assertIn(
            ORGANIZER_FILTER_ID,
            result
        )
        self.assertIn(
            COUNTRY_FILTER_ID,
            result
        )

        self.assertEqual(
            result[DATE_FILTER_ID]["chain"],
            "event_date_begin"
        )
        self.assertEqual(
            result[DATE_FILTER_ID]["type"],
            "date"
        )

        self.assertEqual(
            result[COUNTRY_FILTER_ID]["chain"],
            "country_id"
        )
        self.assertEqual(
            result[COUNTRY_FILTER_ID]["type"],
            "many2one"
        )

    def test_get_top_country_pivot_id(self):
        data = {
            "pivots": {
                "20": {
                    "model": EVENT_REPORT_MODEL,
                    "name": TOP_COUNTRIES_PIVOT_NAME,
                    "rows": [
                        {
                            "fieldName": "country_id"
                        }
                    ]
                }
            }
        }

        result = SpreadsheetDashboardFinalFixes._get_top_country_pivot_id(
            data
        )

        self.assertEqual(
            result,
            "20"
        )

    def test_ensure_top_country_pivot(self):
        dashboard = self.env["spreadsheet.dashboard"]

        data = {
            "pivots": {
                "20": {
                    "model": EVENT_REPORT_MODEL,
                    "name": TOP_COUNTRIES_PIVOT_NAME,
                    "rows": [
                        {
                            "fieldName": "country_id"
                        }
                    ]
                }
            }
        }

        result = dashboard._ensure_top_country_pivot(
            data
        )

        self.assertEqual(
            result,
            "20"
        )

        self.assertEqual(
            len(data["pivots"]),
            1
        )

    def test_fix_top_countries_carousel(self):
        dashboard = self.env["spreadsheet.dashboard"]

        data = {
            "pivots": {
                "20": {
                    "model": EVENT_REPORT_MODEL,
                    "name": TOP_COUNTRIES_PIVOT_NAME,
                    "rows": [
                        {
                            "fieldName": "country_id"
                        }
                    ]
                }
            },
            "globalFilters": [],
        }

        dashboard_data = {
            "name": "Dashboard",
            "figures": [
                {
                    "tag": "carousel",
                    "data": {
                        "title": {
                            "text": "Top Countries"
                        }
                    }
                }
            ]
        }

        dashboard._fix_top_countries_carousel(
            data,
            dashboard_data
        )

        carousel = dashboard_data["figures"][0]

        self.assertEqual(
            carousel["width"],
            475
        )
        self.assertEqual(
            carousel["height"],
            345
        )

        self.assertEqual(
            carousel["offset"],
            {
                "x": 0,
                "y": 300
            }
        )

        chart_definitions = (
            carousel["data"]["chartDefinitions"]
        )

        self.assertIn(
            TOP_COUNTRIES_CHART_ID,
            chart_definitions
        )

        chart = chart_definitions[
            TOP_COUNTRIES_CHART_ID
        ]

        self.assertEqual(
            chart["metaData"]["resModel"],
            EVENT_REPORT_MODEL
        )
        self.assertEqual(
            chart["metaData"]["groupBy"],
            ["country_id"]
        )
        self.assertEqual(
            chart["metaData"]["measure"],
            "sale_price_untaxed"
        )

        self.assertIn(
            "A14",
            dashboard_data["cells"]
        )
        self.assertEqual(
            dashboard_data["cells"]["A14"],
            '=_t("Country")'
        )

        self.assertEqual(
            dashboard_data["cells"]["B14"],
            '=_t("Revenue")'
        )

        self.assertIn(
            "A15",
            dashboard_data["cells"]
        )
        self.assertIn(
            "B15",
            dashboard_data["cells"]
        )

    def test_fix_kpi_positions(self):
        dashboard = self.env["spreadsheet.dashboard"]

        dashboard_data = {
            "figures": [
                {
                    "tag": "chart",
                    "data": {
                        "type": "scorecard",
                        "title": {
                            "text": "Events"
                        }
                    }
                },
                {
                    "tag": "chart",
                    "data": {
                        "type": "scorecard",
                        "title": {
                            "text": "Revenue"
                        }
                    }
                },
                {
                    "tag": "chart",
                    "data": {
                        "type": "scorecard",
                        "title": {
                            "text": "Attendees"
                        }
                    }
                },
            ]
        }

        dashboard._fix_kpi_positions(
            dashboard_data
        )

        events_card = dashboard_data["figures"][0]
        revenue_card = dashboard_data["figures"][1]
        attendees_card = dashboard_data["figures"][2]

        self.assertEqual(
            events_card["width"],
            280
        )
        self.assertEqual(
            events_card["height"],
            105
        )
        self.assertEqual(
            events_card["offset"],
            {
                "x": 0,
                "y": 9
            }
        )

        self.assertEqual(
            revenue_card["offset"],
            {
                "x": 290,
                "y": 9
            }
        )

        self.assertEqual(
            attendees_card["offset"],
            {
                "x": 580,
                "y": 9
            }
        )

    def test_fix_event_status(self):
        dashboard = self.env["spreadsheet.dashboard"]

        data = {}

        dashboard_data = {
            "figures": [
                {
                    "tag": "chart",
                    "data": {
                        "metaData": {
                            "resModel": "event.event",
                            "groupBy": [
                                "dashboard_status"
                            ]
                        }
                    }
                }
            ]
        }

        dashboard._fix_event_status(
            data,
            dashboard_data
        )

        status_chart = dashboard_data["figures"][0]

        self.assertEqual(
            status_chart["data"]["metaData"]["resModel"],
            "event.event"
        )

        self.assertEqual(
            status_chart["data"]["metaData"]["groupBy"],
            ["dashboard_status"]
        )

        self.assertEqual(
            status_chart["data"]["metaData"]["measure"],
            "__count"
        )

        self.assertEqual(
            status_chart["data"]["title"],
            {
                "text": ""
            }
        )

        self.assertEqual(
            dashboard_data["cells"]["D13"],
            '=_t("Events Status")'
        )

        self.assertEqual(
            dashboard_data["styles"]["D13"],
            1
        )

        self.assertEqual(
            dashboard_data["borders"]["D13:E13"],
            1
        )

        self.assertEqual(
            status_chart["width"],
            475
        )

        self.assertEqual(
            status_chart["height"],
            345
        )

        self.assertEqual(
            status_chart["offset"],
            {
                "x": 525,
                "y": 340
            }
        )

        self.assertEqual(
            status_chart["row"],
            0
        )

        self.assertEqual(
            status_chart["col"],
            0
        )

    def test_apply_final_dashboard_fixes(self):
        dashboard = self.env["spreadsheet.dashboard"]

        snapshot = {
            "sheets": [
                {
                    "name": "Dashboard",
                    "figures": [
                        {
                            "tag": "chart",
                            "data": {
                                "type": "scorecard",
                                "title": {
                                    "text": "Events"
                                }
                            }
                        },
                        {
                            "tag": "chart",
                            "data": {
                                "type": "scorecard",
                                "title": {
                                    "text": "Revenue"
                                }
                            }
                        },
                        {
                            "tag": "carousel",
                            "data": {
                                "title": {
                                    "text": "Top Countries"
                                }
                            }
                        },
                        {
                            "tag": "chart",
                            "data": {
                                "metaData": {
                                    "resModel": "event.event",
                                    "groupBy": [
                                        "dashboard_status"
                                    ]
                                }
                            }
                        },
                    ]
                }
            ],
            "pivots": {
                "20": {
                    "model": EVENT_REPORT_MODEL,
                    "name": TOP_COUNTRIES_PIVOT_NAME,
                    "rows": [
                        {
                            "fieldName": "country_id"
                        }
                    ]
                }
            },
            "globalFilters": [],
        }

        result = dashboard._apply_final_dashboard_fixes(
            snapshot
        )

        self.assertIs(
            result,
            snapshot
        )

        dashboard_data = snapshot["sheets"][0]

        self.assertIn(
            "cells",
            dashboard_data
        )

        self.assertIn(
            "D13",
            dashboard_data["cells"]
        )

        self.assertEqual(
            dashboard_data["cells"]["D13"],
            '=_t("Events Status")'
        )

        self.assertIn(
            "styles",
            dashboard_data
        )

        self.assertIn(
            "borders",
            dashboard_data
        )

        self.assertIn(
            "A14",
            dashboard_data["cells"]
        )

        self.assertEqual(
            dashboard_data["cells"]["A14"],
            '=_t("Country")'
        )

        self.assertIn(
            "B14",
            dashboard_data["cells"]
        )

        self.assertEqual(
            dashboard_data["cells"]["B14"],
            '=_t("Revenue")'
        )