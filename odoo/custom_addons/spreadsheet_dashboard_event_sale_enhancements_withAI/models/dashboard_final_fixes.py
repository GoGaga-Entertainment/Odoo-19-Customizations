# -*- coding: utf-8 -*-
import json
import logging

from odoo import models


_logger = logging.getLogger(__name__)

DATE_FILTER_ID = "f849aaa6-4c1a-43f6-9c0b-7a5ea9c83eae"
VENUE_FILTER_ID = "62e15eb2-9410-4803-b189-5fa789a7e94f"
TEMPLATE_FILTER_ID = "d9cfb0b0-01a0-45be-996e-723f4283000b"
TAGS_FILTER_ID = "43c04fb0-d3b7-47c8-852b-b823c36df0ee"
ORGANIZER_FILTER_ID = "4a35bef8-8a57-48ae-8dc6-5883d97cc9da"
COUNTRY_FILTER_ID = "e6db018b-19ec-42c3-b29e-11b1e3910916"

EVENT_REPORT_MODEL = "event.sale.report"
TOP_COUNTRIES_FIGURE_ID = "event-top-countries-map"
TOP_COUNTRIES_CHART_ID = "event-top-countries-chart"
TOP_COUNTRIES_PIVOT_NAME = "Top Countries"


class SpreadsheetDashboardFinalFixes(models.Model):
    _inherit = "spreadsheet.dashboard"

    @staticmethod
    def _find_sheet(data, name):
        return next(
            (sheet for sheet in data.get("sheets", []) if sheet.get("name") == name),
            None,
        )

    @staticmethod
    def _find_top_countries(dashboard):
        return next(
            (
                figure
                for figure in dashboard.get("figures", [])
                if (
                    figure.get("tag") == "carousel"
                    and ((figure.get("data") or {}).get("title") or {}).get("text")
                    == "Top Countries"
                )
            ),
            None,
        )

    @staticmethod
    def _ensure_country_filter(data):
        filters = data.setdefault("globalFilters", [])
        for item in filters:
            if item.get("id") == COUNTRY_FILTER_ID:
                item.update({
                    "type": "relation",
                    "label": "Country",
                    "modelName": "res.country",
                    "defaultValueDisplayNames": [],
                })
                return COUNTRY_FILTER_ID

        filters.append({
            "id": COUNTRY_FILTER_ID,
            "type": "relation",
            "label": "Country",
            "modelName": "res.country",
            "defaultValueDisplayNames": [],
        })
        return COUNTRY_FILTER_ID

    def _top_country_field_matching(self, data):
        country_filter_id = self._ensure_country_filter(data)
        return {
            DATE_FILTER_ID: {
                "chain": "event_date_begin",
                "type": "date",
                "offset": 0,
            },
            VENUE_FILTER_ID: {
                "chain": "event_id.address_id",
                "type": "many2one",
            },
            TEMPLATE_FILTER_ID: {
                "chain": "event_type_id",
                "type": "many2one",
            },
            TAGS_FILTER_ID: {
                "chain": "event_id.tag_ids",
                "type": "many2many",
            },
            ORGANIZER_FILTER_ID: {
                "chain": "event_id.organizer_id",
                "type": "many2one",
            },
            country_filter_id: {
                "chain": "country_id",
                "type": "many2one",
            },
        }

    @staticmethod
    def _get_top_country_pivot_id(data):
        for pivot_id, pivot in (data.get("pivots") or {}).items():
            if (
                pivot.get("model") == EVENT_REPORT_MODEL
                and pivot.get("name") == TOP_COUNTRIES_PIVOT_NAME
                and any(
                    row.get("fieldName") == "country_id"
                    for row in (pivot.get("rows") or [])
                )
            ):
                return str(pivot_id)
        return None

    def _ensure_top_country_pivot(self, data):
        pivot_id = self._get_top_country_pivot_id(data)
        if pivot_id:
            return pivot_id

        pivots = data.setdefault("pivots", {})
        numeric_ids = []
        for key in pivots:
            try:
                numeric_ids.append(int(key))
            except (TypeError, ValueError):
                pass

        pivot_id = str(max(numeric_ids, default=0) + 1)

        action = self.env.ref(
            "event_sale.event_sale_report_action",
            raise_if_not_found=False,
        )
        context = {
            "group_by": [],
            "pivot_measures": [
                "__count__",
                "sale_price_untaxed",
                "sale_price",
            ],
        }
        if action:
            context["params"] = {
                "action": action.id,
                "model": EVENT_REPORT_MODEL,
                "view_type": "pivot",
                "cids": self.env.companies.ids,
            }

        pivots[pivot_id] = {
            "type": "ODOO",
            "fieldMatching": self._top_country_field_matching(data),
            "context": context,
            "domain": [
                ["country_id", "!=", False],
                ["sale_status", "=", "sold"],
            ],
            "id": pivot_id,
            "measures": [
                {
                    "id": "__count",
                    "fieldName": "__count",
                    "userDefinedName": "Orders",
                },
                {
                    "id": "sale_price_untaxed",
                    "fieldName": "sale_price_untaxed",
                    "userDefinedName": "Revenue",
                },
            ],
            "model": EVENT_REPORT_MODEL,
            "name": TOP_COUNTRIES_PIVOT_NAME,
            "sortedColumn": {
                "measure": "sale_price_untaxed",
                "order": "desc",
                "domain": [],
            },
            "formulaId": pivot_id,
            "columns": [],
            "rows": [{"fieldName": "country_id"}],
        }
        data["pivotNextId"] = str(int(pivot_id) + 1)
        return pivot_id

    def _fix_top_countries_carousel(self, data, dashboard):
        carousel = self._find_top_countries(dashboard)
        if not carousel:
            return

        pivot_id = self._ensure_top_country_pivot(data)
        matching = self._top_country_field_matching(data)

        chart_definitions = (
            carousel.setdefault("data", {})
            .setdefault("chartDefinitions", {})
        )
        chart = chart_definitions.get(TOP_COUNTRIES_CHART_ID)

        if chart is None:
            chart = {
                "title": {"text": ""},
                "background": "#FFFFFF",
                "legendPosition": "left",
                "metaData": {
                    "groupBy": ["country_id"],
                    "measure": "sale_price_untaxed",
                    "order": None,
                    "resModel": EVENT_REPORT_MODEL,
                    "mode": "bar",
                    "cumulatedStart": False,
                },
                "searchParams": {
                    "comparison": None,
                    "context": {"group_by": []},
                    "domain": [
                        ["country_id", "!=", False],
                        ["sale_status", "=", "sold"],
                    ],
                    "groupBy": ["country_id"],
                    "orderBy": [],
                },
                "type": "odoo_geo",
                "actionXmlId": "event_sale.event_sale_report_action",
                "dataSets": [{}],
                "colorScale": "blues",
            }
            chart_definitions[TOP_COUNTRIES_CHART_ID] = chart

        search_params = chart.setdefault("searchParams", {})
        search_params["domain"] = [
            ["country_id", "!=", False],
            ["sale_status", "=", "sold"],
        ]
        search_params.setdefault("context", {})
        search_params["groupBy"] = ["country_id"]

        meta = chart.setdefault("metaData", {})
        meta["resModel"] = EVENT_REPORT_MODEL
        meta["groupBy"] = ["country_id"]
        meta["measure"] = "sale_price_untaxed"
        meta["mode"] = "bar"

        carousel_data = carousel.setdefault("data", {})
        carousel_data["items"] = [
            {
                "type": "chart",
                "chartId": TOP_COUNTRIES_CHART_ID,
                "title": "Map",
            },
            {
                "type": "carouselDataView",
                "title": "Top 10",
            },
        ]
        carousel_data["fieldMatching"] = {
            TOP_COUNTRIES_CHART_ID: matching,
        }

        # -------------------------------------------------------------
        # TOP COUNTRIES COMPONENT GEOMETRY
        # -------------------------------------------------------------
        # Same y, width and height as Events Status. This is what keeps
        # both components visually aligned in the first dashboard row.
        carousel["offset"] = {"x": 0, "y": 300}
        carousel["width"] = 475
        carousel["height"] = 345
        carousel["col"] = 0
        carousel["row"] = 0

        # -------------------------------------------------------------
        # TOP 10 TABLE
        # -------------------------------------------------------------
        # carouselDataView is the selector; the actual Top 10 values are
        # supplied by these spreadsheet cells and the Odoo pivot.
        cells = dashboard.setdefault("cells", {})

        for row in range(14, 25):
            cells.pop(f"A{row}", None)
            cells.pop(f"B{row}", None)

        cells["A14"] = '=_t("Country")'
        cells["B14"] = '=_t("Revenue")'

        for index in range(1, 11):
            row = 14 + index
            cells[f"A{row}"] = (
                f'=PIVOT.HEADER({pivot_id},"#country_id",{index})'
            )
            cells[f"B{row}"] = (
                f'=PIVOT.VALUE({pivot_id},"sale_price_untaxed",'
                f'"#country_id",{index})'
            )

        # Native Events dashboard style IDs:
        #   2 = numeric/right-aligned header
        #   3 = normal body
        #   4 = numeric/right-aligned value/header style.
        styles = dashboard.setdefault("styles", {})
        styles.update({
            "A14": 2,
            "B14": 4,
            "A15:A24": 3,
            "B15:B24": 4,
        })

        # Do not add a custom top/header border here. The Odoo spreadsheet
        # default carousel/header already provides the correct divider.
        # A manually added border makes an extra horizontal line appear
        # above Top Countries and breaks the native dashboard alignment.

        tables = dashboard.setdefault("tables", [])
        tables[:] = [
            table
            for table in tables
            if table.get("range") != "A14:B24"
        ]
        tables.append({
            "range": "A14:B24",
            "type": "static",
            "config": {
                "hasFilters": False,
                "totalRow": False,
                "firstColumn": False,
                "lastColumn": False,
                "numberOfHeaders": 1,
                "bandedRows": True,
                "bandedColumns": False,
                "automaticAutofill": True,
                "styleId": "None",
            },
        })

        country_filter_id = self._ensure_country_filter(data)
        carousel_data["fieldMatching"].setdefault(
            TOP_COUNTRIES_CHART_ID, {}
        )[country_filter_id] = {
            "chain": "country_id",
            "type": "many2one",
        }

    def _fix_kpi_positions(self, dashboard):
        titles = [
            ("Events", 0, 9),
            ("Revenue", 290, 9),
            ("Attendees", 580, 9),
            ("Customer Acquisitions", 0, 124),
            ("Average Registrations Per Event", 290, 124),
            ("Average Revenue Per Event", 580, 124),
        ]

        for title, x, y in titles:
            card = next(
                (
                    figure
                    for figure in dashboard.get("figures", [])
                    if (
                        figure.get("tag") == "chart"
                        and (figure.get("data") or {}).get("type") == "scorecard"
                        and (
                            ((figure.get("data") or {}).get("title") or {}).get("text")
                            == title
                        )
                    )
                ),
                None,
            )
            if card:
                card["width"] = 280
                card["height"] = 105
                card["offset"] = {"x": x, "y": y}
                card["col"] = 0
                card["row"] = 0

    def _fix_event_status(self, data, dashboard):
        status_chart = None
        for figure in dashboard.get("figures", []):
            if figure.get("tag") != "chart":
                continue
            meta = (figure.get("data") or {}).get("metaData") or {}
            if (
                meta.get("resModel") == "event.event"
                and meta.get("groupBy") == ["dashboard_status"]
            ):
                status_chart = figure
                break

        if not status_chart:
            return

        chart = status_chart.setdefault("data", {})
        meta = chart.setdefault("metaData", {})
        search = chart.setdefault("searchParams", {})

        meta["resModel"] = "event.event"
        meta["groupBy"] = ["dashboard_status"]
        meta["measure"] = "__count"

        # Odoo 19 Spreadsheet chart runtime expects the chart title object
        # to exist and contain a `text` property. Keep it empty so the
        # visible heading comes from the native spreadsheet cell below,
        # while preventing getChartTitle() from crashing.
        chart["title"] = {"text": ""}

        cells = dashboard.setdefault("cells", {})
        cells["D13"] = '=_t("Events Status")'

        styles = dashboard.setdefault("styles", {})
        styles["D13"] = 1

        search["groupBy"] = ["dashboard_status"]
        search.setdefault("domain", [])
        context = dict(search.get("context") or {})
        context["active_test"] = False
        search["context"] = context

        # Reuse Odoo's existing native heading divider.  D13:E13 is the
        # heading row for the right-hand first-row component in the Events
        # dashboard, so the line appears directly below "Events Status".
        borders = dashboard.setdefault("borders", {})
        borders["D13:E13"] = 1

        # Keep the native Odoo heading row above the chart.
        # D13 contains the visible "Events Status" heading, so the chart
        # starts one heading row below it. This prevents the chart canvas
        # from covering the heading cell.
        status_chart["width"] = 475
        status_chart["height"] = 345
        status_chart["offset"] = {"x": 525, "y": 340}
        status_chart["col"] = 0
        status_chart["row"] = 0

    def _apply_final_dashboard_fixes(self, snapshot):
        dashboard = self._find_sheet(snapshot, "Dashboard")
        if not dashboard:
            return snapshot

        self._fix_kpi_positions(dashboard)
        self._fix_event_status(snapshot, dashboard)
        self._fix_top_countries_carousel(snapshot, dashboard)
        return snapshot