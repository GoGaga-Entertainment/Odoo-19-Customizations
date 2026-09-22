from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..models.dashboard_patch import (
    SpreadsheetDashboard,
    EventEvent,
    EventSaleReportCountry,
    DATE_FILTER_ID,
    VENUE_FILTER_ID,
    TEMPLATE_FILTER_ID,
    TAGS_FILTER_ID,
    ORGANIZER_FILTER_ID,
    COUNTRY_FILTER_ID,
    CUSTOM_MODEL,
    CURRENT_PIVOT_NAME,
    PREVIOUS_PIVOT_NAME,
    TOP_COUNTRIES_FIGURE_ID,
    TOP_COUNTRIES_CHART_ID,
    EVENT_REPORT_MODEL,
)


class TestDashboardPatch(TransactionCase):

    def setUp(self):
        super().setUp()

        self.dashboard = self.env["spreadsheet.dashboard"].browse()
        self.events = self.env["event.event"]

    # ---------------------------------------------------------
    # 1. _compute_dashboard_status
    # ---------------------------------------------------------

    def test_compute_dashboard_status(self):
        stage = self.env["event.stage"].create({
            "name": "Booked",
        })

        event = self.env["event.event"].create({
            "name": "Test Event",
            "stage_id": stage.id,
            "active": True,
        })

        self.assertEqual(
            event.dashboard_status,
            "Booked",
        )

        event.active = False

        self.assertEqual(
            event.dashboard_status,
            "Archived",
        )

    # ---------------------------------------------------------
    # 2. formatted_read_group
    # ---------------------------------------------------------

    def test_formatted_read_group(self):
        result = self.events.formatted_read_group(
            [],
            groupby=["dashboard_status"],
            aggregates=["__count"],
        )

        self.assertIsInstance(
            result,
            list,
        )

        statuses = [
            row.get("dashboard_status")
            for row in result
            if row.get("dashboard_status")
        ]

        expected_order = {
            "New": 0,
            "Booked": 1,
            "Announced": 2,
            "Ended": 3,
            "Archived": 4,
        }

        self.assertEqual(
            statuses,
            sorted(
                statuses,
                key=lambda status: expected_order.get(
                    status,
                    999,
                ),
            ),
        )

    # ---------------------------------------------------------
    # 3. _select_clause
    # ---------------------------------------------------------

    def test_select_clause(self):
        query = self.env[
            "event.sale.report"
        ]._select_clause()

        self.assertIn(
            "event_event.country_id AS country_id",
            query,
        )

    # ---------------------------------------------------------
    # 4. _find_sheet
    # ---------------------------------------------------------

    def test_find_sheet(self):
        data = {
            "sheets": [
                {
                    "name": "Data",
                },
                {
                    "name": "Dashboard",
                },
            ]
        }

        result = self.dashboard._find_sheet(
            data,
            "Dashboard",
        )

        self.assertEqual(
            result,
            {
                "name": "Dashboard",
            },
        )

    # ---------------------------------------------------------
    # 5. _find_scorecard
    # ---------------------------------------------------------

    def test_find_scorecard(self):
        dashboard_sheet = {
            "figures": [
                {
                    "tag": "chart",
                    "data": {
                        "type": "scorecard",
                        "title": {
                            "text": "Revenue",
                        },
                    },
                },
                {
                    "tag": "chart",
                    "data": {
                        "type": "bar",
                        "title": {
                            "text": "Revenue",
                        },
                    },
                },
            ]
        }

        result = self.dashboard._find_scorecard(
            dashboard_sheet,
            "Revenue",
        )

        self.assertIsNotNone(
            result,
        )

        self.assertEqual(
            result["data"]["type"],
            "scorecard",
        )

    # ---------------------------------------------------------
    # 6. _next_pivot_ids
    # ---------------------------------------------------------

    def test_next_pivot_ids(self):
        pivots = {
            "1": {},
            "5": {},
            "10": {},
            "abc": {},
        }

        current_id, previous_id = (
            self.dashboard._next_pivot_ids(
                pivots
            )
        )

        self.assertEqual(
            current_id,
            "11",
        )

        self.assertEqual(
            previous_id,
            "12",
        )

    # ---------------------------------------------------------
    # 7. _customer_field_matching
    # ---------------------------------------------------------

    def test_customer_field_matching(self):
        result = self.dashboard._customer_field_matching(0)

        self.assertIn(
            DATE_FILTER_ID,
            result,
        )

        self.assertIn(
            VENUE_FILTER_ID,
            result,
        )

        self.assertIn(
            TEMPLATE_FILTER_ID,
            result,
        )

        self.assertIn(
            TAGS_FILTER_ID,
            result,
        )

        self.assertIn(
            ORGANIZER_FILTER_ID,
            result,
        )

        self.assertEqual(
            result[DATE_FILTER_ID]["chain"],
            "first_event_date",
        )

        self.assertEqual(
            result[VENUE_FILTER_ID]["chain"],
            "event_id.address_id",
        )

    # ---------------------------------------------------------
    # 8. _make_customer_pivot
    # ---------------------------------------------------------

    def test_make_customer_pivot(self):
        pivot = self.dashboard._make_customer_pivot(
            "20",
            previous=False,
        )

        self.assertEqual(
            pivot["id"],
            "20",
        )

        self.assertEqual(
            pivot["model"],
            CUSTOM_MODEL,
        )

        self.assertEqual(
            pivot["name"],
            CURRENT_PIVOT_NAME,
        )

        self.assertEqual(
            pivot["measures"][0]["fieldName"],
            "acquisition_count",
        )

        previous_pivot = self.dashboard._make_customer_pivot(
            "21",
            previous=True,
        )

        self.assertEqual(
            previous_pivot["name"],
            PREVIOUS_PIVOT_NAME,
        )

        self.assertEqual(
            previous_pivot["fieldMatching"][
                DATE_FILTER_ID
            ]["offset"],
            -1,
        )

    # ---------------------------------------------------------
    # 9. _patch_event_status_chart
    # ---------------------------------------------------------

    def test_patch_event_status_chart(self):
        data = {
            "sheets": [
                {
                    "name": "Dashboard",
                    "figures": [
                        {
                            "tag": "chart",
                            "data": {
                                "metaData": {
                                    "resModel": "event.event",
                                    "groupBy": [
                                        "stage_id"
                                    ],
                                },
                                "searchParams": {},
                            },
                        }
                    ],
                }
            ]
        }

        result = self.dashboard._patch_event_status_chart(
            data
        )

        self.assertTrue(
            result,
        )

        chart = data["sheets"][0]["figures"][0]["data"]

        self.assertEqual(
            chart["metaData"]["groupBy"],
            ["dashboard_status"],
        )

        self.assertEqual(
            chart["metaData"]["measure"],
            "__count",
        )

        self.assertEqual(
            chart["searchParams"]["groupBy"],
            ["dashboard_status"],
        )

        self.assertFalse(
            chart["searchParams"]["context"]["active_test"]
        )

        self.assertIn(
            DATE_FILTER_ID,
            chart["fieldMatching"],
        )

    # ---------------------------------------------------------
    # 10. _ensure_country_global_filter
    # ---------------------------------------------------------

    def test_ensure_country_global_filter(self):
        data = {}

        result = self.dashboard._ensure_country_global_filter(
            data
        )

        self.assertEqual(
            result,
            COUNTRY_FILTER_ID,
        )

        self.assertEqual(
            len(data["globalFilters"]),
            1,
        )

        country_filter = data["globalFilters"][0]

        self.assertEqual(
            country_filter["id"],
            COUNTRY_FILTER_ID,
        )

        self.assertEqual(
            country_filter["type"],
            "relation",
        )

        self.assertEqual(
            country_filter["label"],
            "Country",
        )

        # Calling again should reuse the same filter.
        result_again = (
            self.dashboard._ensure_country_global_filter(
                data
            )
        )

        self.assertEqual(
            result_again,
            COUNTRY_FILTER_ID,
        )

        self.assertEqual(
            len(data["globalFilters"]),
            1,
        )

    # ---------------------------------------------------------
    # 11. _add_country_filter_matching
    # ---------------------------------------------------------

    def test_add_country_filter_matching(self):
        data = {
            "sheets": [
                {
                    "name": "Dashboard",
                    "figures": [
                        {
                            "tag": "chart",
                            "data": {
                                "metaData": {
                                    "resModel": EVENT_REPORT_MODEL,
                                }
                            },
                        },
                        {
                            "tag": "chart",
                            "data": {
                                "metaData": {
                                    "resModel": "event.event",
                                }
                            },
                        },
                        {
                            "tag": "chart",
                            "data": {
                                "metaData": {
                                    "resModel": "event.registration",
                                }
                            },
                        },
                        {
                            "tag": "chart",
                            "data": {
                                "metaData": {
                                    "resModel": CUSTOM_MODEL,
                                }
                            },
                        },
                        {
                            "tag": "carousel",
                            "data": {
                                "chartDefinitions": {
                                    "chart1": {
                                        "metaData": {
                                            "resModel": EVENT_REPORT_MODEL,
                                        }
                                    }
                                }
                            },
                        },
                    ],
                }
            ],
            "pivots": {
                "1": {
                    "model": EVENT_REPORT_MODEL,
                },
                "2": {
                    "model": "event.event",
                },
            },
            "lists": {
                "1": {
                    "model": "event.registration",
                },
            },
        }

        self.dashboard._add_country_filter_matching(
            data
        )

        self.assertIn(
            COUNTRY_FILTER_ID,
            data["globalFilters"][0]["id"],
        )

        figures = data["sheets"][0]["figures"]

        self.assertEqual(
            figures[0]["data"]["fieldMatching"][
                COUNTRY_FILTER_ID
            ]["chain"],
            "country_id",
        )

        self.assertEqual(
            figures[1]["data"]["fieldMatching"][
                COUNTRY_FILTER_ID
            ]["chain"],
            "address_id.country_id",
        )

        self.assertEqual(
            figures[2]["data"]["fieldMatching"][
                COUNTRY_FILTER_ID
            ]["chain"],
            "event_id.address_id.country_id",
        )

        self.assertEqual(
            figures[3]["data"]["fieldMatching"][
                COUNTRY_FILTER_ID
            ]["chain"],
            "event_id.address_id.country_id",
        )

        self.assertEqual(
            figures[4]["data"]["fieldMatching"][
                "chart1"
            ][COUNTRY_FILTER_ID]["chain"],
            "country_id",
        )

        self.assertEqual(
            data["pivots"]["1"]["fieldMatching"][
                COUNTRY_FILTER_ID
            ]["chain"],
            "country_id",
        )

        self.assertEqual(
            data["pivots"]["2"]["fieldMatching"][
                COUNTRY_FILTER_ID
            ]["chain"],
            "address_id.country_id",
        )

    # ---------------------------------------------------------
    # 12. _ensure_top_countries_pivot
    # ---------------------------------------------------------

    def test_ensure_top_countries_pivot(self):
        data = {
            "pivots": {
                "3": {},
                "7": {},
            }
        }

        with patch.object(
            self.dashboard.env,
            "ref",
            return_value=False,
        ):
            pivot_id = (
                self.dashboard._ensure_top_countries_pivot(
                    data
                )
            )

        self.assertEqual(
            pivot_id,
            "8",
        )

        pivot = data["pivots"]["8"]

        self.assertEqual(
            pivot["model"],
            EVENT_REPORT_MODEL,
        )

        self.assertEqual(
            pivot["name"],
            "Top Countries",
        )

        self.assertEqual(
            pivot["rows"][0]["fieldName"],
            "country_id",
        )

        self.assertEqual(
            pivot["measures"][0]["fieldName"],
            "__count",
        )

        self.assertEqual(
            pivot["measures"][1]["fieldName"],
            "sale_price_untaxed",
        )

        self.assertEqual(
            pivot["domain"],
            [
                "&",
                ["country_id", "!=", False],
                ["sale_status", "=", "sold"],
            ],
        )

        self.assertEqual(
            data["pivotNextId"],
            "9",
        )

    # ---------------------------------------------------------
    # 13. _add_top_countries_map
    # ---------------------------------------------------------

    def test_add_top_countries_map(self):
        data = {
            "pivots": {},
        }

        dashboard_sheet = {
            "figures": [
                {
                    "id": TOP_COUNTRIES_FIGURE_ID,
                    "tag": "carousel",
                    "data": {
                        "title": {
                            "text": "Top Countries",
                        }
                    },
                }
            ]
        }

        # Patch the class method, not the Odoo recordset.
        with patch.object(
            SpreadsheetDashboard,
            "_ensure_top_countries_pivot",
            return_value="1",
        ):
            result = self.dashboard._add_top_countries_map(
                data,
                dashboard_sheet,
            )

        self.assertTrue(
            result,
        )

        figures = dashboard_sheet["figures"]

        self.assertEqual(
            len(figures),
            1,
        )

        figure = figures[0]

        self.assertEqual(
            figure["id"],
            TOP_COUNTRIES_FIGURE_ID,
        )

        self.assertEqual(
            figure["tag"],
            "carousel",
        )

        self.assertIn(
            TOP_COUNTRIES_CHART_ID,
            figure["data"]["chartDefinitions"],
        )

        chart = figure["data"]["chartDefinitions"][
            TOP_COUNTRIES_CHART_ID
        ]

        self.assertEqual(
            chart["metaData"]["resModel"],
            EVENT_REPORT_MODEL,
        )

        self.assertEqual(
            chart["metaData"]["groupBy"],
            ["country_id"],
        )

        self.assertEqual(
            chart["type"],
            "odoo_geo",
        )

        self.assertEqual(
            figure["data"]["items"][1]["type"],
            "carouselDataView",
        )

    # ---------------------------------------------------------
    # 14. _rearrange_event_dashboard_layout
    # ---------------------------------------------------------

    def test_rearrange_event_dashboard_layout(self):
        dashboard_sheet = {
            "figures": [
                {
                    "tag": "chart",
                    "data": {
                        "type": "scorecard",
                        "title": {
                            "text": "Events",
                        },
                    },
                },
                {
                    "tag": "chart",
                    "data": {
                        "type": "scorecard",
                        "title": {
                            "text": "Revenue",
                        },
                    },
                },
                {
                    "tag": "chart",
                    "data": {
                        "type": "scorecard",
                        "title": {
                            "text": "Attendees",
                        },
                    },
                },
                {
                    "id": TOP_COUNTRIES_FIGURE_ID,
                    "tag": "carousel",
                    "data": {},
                },
                {
                    "tag": "chart",
                    "data": {
                        "metaData": {
                            "resModel": "event.event",
                            "groupBy": [
                                "dashboard_status"
                            ],
                        }
                    },
                },
                {
                    "tag": "chart",
                    "data": {
                        "metaData": {
                            "resModel": "event.registration",
                        }
                    },
                },
            ],
            "cells": {},
        }

        data = {
            "pivots": {},
        }

        self.dashboard._rearrange_event_dashboard_layout(
            data,
            dashboard_sheet,
        )

        self.assertEqual(
            dashboard_sheet["colNumber"],
            5,
        )

        self.assertEqual(
            dashboard_sheet["rowNumber"],
            67,
        )

        self.assertFalse(
            dashboard_sheet["areGridLinesVisible"]
        )

        events_card = dashboard_sheet["figures"][0]

        self.assertEqual(
            events_card["width"],
            280,
        )

        self.assertEqual(
            events_card["height"],
            105,
        )

        self.assertEqual(
            events_card["offset"],
            {
                "x": 0,
                "y": 9,
            },
        )

        self.assertIn(
            "D13",
            dashboard_sheet["cells"],
        )

        self.assertIn(
            "A29",
            dashboard_sheet["cells"],
        )

        self.assertIn(
            "D29",
            dashboard_sheet["cells"],
        )

        self.assertIn(
            "A42",
            dashboard_sheet["cells"],
        )

        self.assertIn(
            "D42",
            dashboard_sheet["cells"],
        )

        self.assertIn(
            "A55",
            dashboard_sheet["cells"],
        )

        self.assertEqual(
            len(dashboard_sheet["tables"]),
            4,
        )

    # ---------------------------------------------------------
    # 15. _patch_event_dashboard_payload
    # ---------------------------------------------------------

    def test_patch_event_dashboard_payload(self):
        data = {
            "sheets": [
                {
                    "name": "Dashboard",
                    "figures": [
                        {
                            "tag": "chart",
                            "data": {
                                "type": "scorecard",
                                "title": {
                                    "text": "Events",
                                },
                            },
                        }
                    ],
                },
                {
                    "name": "Data",
                    "cells": {},
                },
            ],
            "pivots": {
                "1": {
                    "model": CUSTOM_MODEL,
                },
                "2": {
                    "model": "event.event",
                },
            },
        }

        # Patch class methods, not the Odoo recordset.
        with patch.object(
            SpreadsheetDashboard,
            "_patch_event_status_chart",
            return_value=True,
        ), patch.object(
            SpreadsheetDashboard,
            "_add_top_countries_map",
            return_value=True,
        ), patch.object(
            SpreadsheetDashboard,
            "_rearrange_event_dashboard_layout",
            return_value=None,
        ), patch.object(
            SpreadsheetDashboard,
            "_add_country_filter_matching",
            return_value=None,
        ):

            result = (
                self.dashboard._patch_event_dashboard_payload(
                    data
                )
            )

        self.assertIs(
            result,
            data,
        )

        self.assertNotIn(
            "1",
            data["pivots"],
        )

        self.assertEqual(
            len(data["pivots"]),
            3,
        )

        self.assertEqual(
            data["pivotNextId"],
            "5",
        )

        data_sheet = self.dashboard._find_sheet(
            data,
            "Data",
        )

        self.assertIn(
            "A7",
            data_sheet["cells"],
        )

        self.assertIn(
            "B7",
            data_sheet["cells"],
        )

        self.assertIn(
            "C7",
            data_sheet["cells"],
        )

        self.assertIn(
            "A8",
            data_sheet["cells"],
        )

        self.assertIn(
            "A9",
            data_sheet["cells"],
        )

    # ---------------------------------------------------------
    # 16. _get_serialized_readonly_dashboard
    # ---------------------------------------------------------

    def test_get_serialized_readonly_dashboard_non_target(self):
        dashboard = self.env[
            "spreadsheet.dashboard"
        ].browse()

        with patch(
            "odoo.addons.spreadsheet_dashboard.models.spreadsheet_dashboard.SpreadsheetDashboard._get_serialized_readonly_dashboard",
            return_value='{"snapshot": {}}',
        ):
            result = (
                dashboard._get_serialized_readonly_dashboard()
            )

        self.assertEqual(
            result,
            '{"snapshot": {}}',
        )