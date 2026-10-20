# -*- coding: utf-8 -*-
import base64
import copy
import json

from odoo import api, fields, models


# These are the filter IDs from the STANDARD Odoo Events dashboard.
# We reuse them instead of creating a new date filter.
DATE_FILTER_ID = "f849aaa6-4c1a-43f6-9c0b-7a5ea9c83eae"
VENUE_FILTER_ID = "62e15eb2-9410-4803-b189-5fa789a7e94f"
TEMPLATE_FILTER_ID = "d9cfb0b0-01a0-45be-996e-723f4283000b"
TAGS_FILTER_ID = "43c04fb0-d3b7-47c8-852b-b823c36df0ee"
ORGANIZER_FILTER_ID = "4a35bef8-8a57-48ae-8dc6-5883d97cc9da"

# Dedicated relation filter used by the Top Countries Top-10 view.
# This mirrors the native Sales dashboard's Country global filter.
COUNTRY_FILTER_ID = "e6db018b-19ec-42c3-b29e-11b1e3910916"

CUSTOM_MODEL = "event.customer.acquisition"

CURRENT_PIVOT_NAME = "Customer Acquisition"
PREVIOUS_PIVOT_NAME = "Customer Acquisition Previous"

CUSTOM_CARD_ID = "customer-acquisition-scorecard"
AVG_REGISTRATION_CARD_ID = "average-registration-scorecard"
AVG_REVENUE_CARD_ID = "average-revenue-scorecard"
TOP_COUNTRIES_FIGURE_ID = "event-top-countries-map"
TOP_COUNTRIES_CHART_ID = "event-top-countries-chart"
EVENT_REPORT_MODEL = "event.sale.report"


class EventEvent(models.Model):
    _inherit = "event.event"

    dashboard_status = fields.Selection(
        selection=[
            ("New", "New"),
            ("Booked", "Booked"),
            ("Announced", "Announced"),
            ("Ended", "Ended"),
            ("Archived", "Archived"),
        ],
        string="Dashboard Status",
        compute="_compute_dashboard_status",
        store=True,
        index=True,
        group_expand=True,
    )

    @api.depends("active", "stage_id")
    def _compute_dashboard_status(self):
        for event in self:
            if not event.active:
                event.dashboard_status = "Archived"
            else:
                event.dashboard_status = event.stage_id.name or "New"

    @api.model
    def formatted_read_group(
        self,
        domain,
        groupby=(),
        aggregates=(),
        having=(),
        offset=0,
        limit=None,
        order=None,
    ):
        """Return Event Status groups in the real Event workflow order.

        Odoo 19 spreadsheet charts use ``formatted_read_group`` as their
        public grouped-data API.  Sorting ``read_group`` is therefore not
        enough for this dashboard chart.

        The status chart groups by ``dashboard_status`` and the spreadsheet
        chart keeps the order of the groups returned by this method.  We
        therefore sort only that specific grouped result here.  No Event
        workflow value is changed.
        """
        result = super().formatted_read_group(
            domain,
            groupby=groupby,
            aggregates=aggregates,
            having=having,
            offset=offset,
            limit=limit,
            order=order,
        )

        normalized_groupby = [groupby] if isinstance(groupby, str) else list(groupby or [])

        if "dashboard_status" not in normalized_groupby or not isinstance(result, list):
            return result

        status_order = {
            "New": 0,
            "Booked": 1,
            "Announced": 2,
            "Ended": 3,
            "Archived": 4,
        }

        result.sort(
            key=lambda row: (
                status_order.get(row.get("dashboard_status"), 999),
                row.get("dashboard_status") or "",
            )
        )

        return result

class EventSaleReportCountry(models.Model):
    """Expose the Event's actual event.event.country_id on event.sale.report.

    The Top Countries dashboard must use the event's Country field, not the
    customer's country.  event.sale.report is a SQL reporting model, so the
    field is added to the SELECT clause of the inherited report query.
    """

    _inherit = "event.sale.report"

    country_id = fields.Many2one(
        "res.country",
        string="Country",
        readonly=True,
    )

    def _select_clause(self, *select):
        return super()._select_clause(
            *select,
            "event_event.country_id AS country_id",
        )


class SpreadsheetDashboard(models.Model):
    _inherit = "spreadsheet.dashboard"

    def _find_sheet(self, data, name):
        return next(
            (
                sheet
                for sheet in data.get("sheets", [])
                if sheet.get("name") == name
            ),
            None,
        )

    def _find_scorecard(self, dashboard_sheet, title):
        return next(
            (
                figure
                for figure in dashboard_sheet.get("figures", [])
                if (
                    figure.get("tag") == "chart"
                    and figure.get("data", {}).get("type") == "scorecard"
                    and figure.get("data", {})
                    .get("title", {})
                    .get("text") == title
                )
            ),
            None,
        )

    def _next_pivot_ids(self, pivots):
        ids = []

        for key in pivots:
            try:
                ids.append(int(key))
            except (TypeError, ValueError):
                continue

        first = max(ids, default=10) + 1

        return str(first), str(first + 1)

    def _customer_field_matching(self, offset):
        """
        IMPORTANT:
        Reuse the EXISTING Events dashboard filter IDs.

        This means:
        - Today
        - Yesterday
        - Last 7 Days
        - Last 30 Days
        - Last 90 Days
        - Month
        - Quarter
        - Year
        - All Time
        - Custom Range

        continue to control this KPI through the normal
        Odoo dashboard date filter.
        """

        return {
            DATE_FILTER_ID: {
                "chain": "first_event_date",
                "type": "datetime",
                "offset": offset,
            },

            VENUE_FILTER_ID: {
                "chain": "event_id.address_id",
                "type": "many2one",
            },

            TEMPLATE_FILTER_ID: {
                "chain": "event_id.event_type_id",
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
        }

    def _make_customer_pivot(self, pivot_id, previous=False):
        return {
            "type": "ODOO",

            "fieldMatching": self._customer_field_matching(
                -1 if previous else 0
            ),

            "context": {},

            "domain": [],

            "id": pivot_id,

            "measures": [
                {
                    "id": "acquisition_count",
                    "fieldName": "acquisition_count",
                    "userDefinedName": "Customer Acquisition",
                }
            ],

            "model": CUSTOM_MODEL,

            "name": (
                PREVIOUS_PIVOT_NAME
                if previous
                else CURRENT_PIVOT_NAME
            ),

            "sortedColumn": None,

            "formulaId": pivot_id,

            "columns": [],

            "rows": [],
        }

    def _patch_event_status_chart(self, data):
        """
        Patch the actual Odoo Events Status BAR CHART.

        IMPORTANT:
        The standard Events Status component is NOT a pivot.
        Odoo 19 stores it as a chart figure whose metadata is:

            resModel = event.event
            groupBy  = stage_id

        Therefore changing data["pivots"] does not affect this chart.

        We change only this chart:
        - model remains event.event
        - archived records are included with active_test=False
        - groupBy changes from stage_id to dashboard_status
        - dashboard_status is "Archived" when active=False
        - all existing global filters remain connected
        """

        dashboard_sheet = self._find_sheet(data, "Dashboard")
        if dashboard_sheet is None:
            return False

        target = None

        for figure in dashboard_sheet.get("figures", []):
            if figure.get("tag") != "chart":
                continue

            chart = figure.get("data") or {}
            meta = chart.get("metaData") or {}
            search = chart.get("searchParams") or {}

            if meta.get("resModel") != "event.event":
                continue

            group_by = meta.get("groupBy") or search.get("groupBy") or []

            if group_by == ["stage_id"]:
                target = figure
                break

        if target is None:
            return False

        chart = target.setdefault("data", {})
        meta = chart.setdefault("metaData", {})
        search = chart.setdefault("searchParams", {})

        # ---------------------------------------------------------
        # Change the grouping dimension.
        # ---------------------------------------------------------

        meta["resModel"] = "event.event"
        meta["groupBy"] = ["dashboard_status"]
        meta["measure"] = "__count"

        search["modelName"] = "event.event"
        search["groupBy"] = ["dashboard_status"]

        # ---------------------------------------------------------
        # Include archived event.event records.
        #
        # Odoo normally applies active_test=True.  Without this,
        # active=False records never reach the graph query.
        # ---------------------------------------------------------

        context = dict(search.get("context") or {})
        context["active_test"] = False
        search["context"] = context

        # Keep the existing domain and ordering.
        search.setdefault("domain", [])
        search.setdefault("orderBy", [])
        search.setdefault("comparison", None)

        # ---------------------------------------------------------
        # Keep the standard Events dashboard global filters.
        # ---------------------------------------------------------

        field_matching = dict(chart.get("fieldMatching") or {})

        field_matching[DATE_FILTER_ID] = {
            "chain": "date_begin",
            "type": "datetime",
            "offset": 0,
        }

        field_matching[VENUE_FILTER_ID] = {
            "chain": "address_id",
            "type": "many2one",
        }

        field_matching[TEMPLATE_FILTER_ID] = {
            "chain": "event_type_id",
            "type": "many2one",
        }

        field_matching[TAGS_FILTER_ID] = {
            "chain": "tag_ids",
            "type": "many2many",
        }

        field_matching[ORGANIZER_FILTER_ID] = {
            "chain": "organizer_id",
            "type": "many2one",
        }

        chart["fieldMatching"] = field_matching

        # Do not change the visual type, size, position, or styling.
        return True

    def _ensure_country_global_filter(self, data):
        """Ensure the Events dashboard has the same kind of Country
        relation filter used by the native Odoo Sales dashboard.

        The important part is that the filter has a stable UUID and that the
        Top Countries carousel references this exact filter ID through
        ``fieldMatching``.  The spreadsheet engine then handles the click on
        a Top-10 country and adds that country to the dashboard filter bar.
        """
        filters = data.setdefault("globalFilters", [])

        # If the exact native-style filter already exists, reuse it.
        for global_filter in filters:
            if global_filter.get("id") == COUNTRY_FILTER_ID:
                global_filter.update({
                    "type": "relation",
                    "label": "Country",
                    "modelName": "res.country",
                    "defaultValueDisplayNames": [],
                })
                return COUNTRY_FILTER_ID

        # Do not reuse an unrelated/custom Country filter ID.  The Sales
        # dashboard uses one stable relation-filter UUID and fieldMatching
        # points to that exact UUID.
        filters.append({
            "id": COUNTRY_FILTER_ID,
            "type": "relation",
            "label": "Country",
            "modelName": "res.country",
            "defaultValueDisplayNames": [],
        })
        return COUNTRY_FILTER_ID

    def _add_country_filter_matching(self, data):
        """Connect the native-style Country relation filter to every
        compatible Events dashboard source.

        This is the same mechanism used by the native Sales dashboard:
            globalFilters -> relation(res.country)
                -> carousel.fieldMatching
                -> report field country_id

        For Events the report field is ``country_id``.
        """
        country_filter_id = self._ensure_country_global_filter(data)

        def set_matching(container, chain):
            container.setdefault("fieldMatching", {})[country_filter_id] = {
                "chain": chain,
                "type": "many2one",
            }

        for sheet in data.get("sheets", []):
            for figure in sheet.get("figures", []):
                chart = figure.get("data") or {}

                # Native Sales structure: the fieldMatching map for a
                # carousel is keyed first by chartId, then by globalFilterId.
                if figure.get("tag") == "carousel":
                    definitions = chart.get("chartDefinitions") or {}
                    carousel_matching = chart.setdefault("fieldMatching", {})

                    for chart_id, definition in definitions.items():
                        meta = definition.get("metaData") or {}
                        if meta.get("resModel") == EVENT_REPORT_MODEL:
                            carousel_matching.setdefault(chart_id, {})[
                                country_filter_id
                            ] = {
                                "chain": "country_id",
                                "type": "many2one",
                            }
                    continue

                if figure.get("tag") != "chart":
                    continue

                meta = chart.get("metaData") or {}
                model = meta.get("resModel")

                if model == EVENT_REPORT_MODEL:
                    set_matching(chart, "country_id")
                elif model == "event.event":
                    set_matching(chart, "address_id.country_id")
                elif model == "event.registration":
                    set_matching(chart, "event_id.address_id.country_id")
                elif model == CUSTOM_MODEL:
                    set_matching(chart, "event_id.address_id.country_id")

        for pivot in (data.get("pivots") or {}).values():
            model = pivot.get("model")
            if model == EVENT_REPORT_MODEL:
                set_matching(pivot, "country_id")
            elif model == "event.event":
                set_matching(pivot, "address_id.country_id")
            elif model == "event.registration":
                set_matching(pivot, "event_id.address_id.country_id")
            elif model == CUSTOM_MODEL:
                set_matching(pivot, "event_id.address_id.country_id")

        for listing in (data.get("lists") or {}).values():
            model = listing.get("model")
            if model == EVENT_REPORT_MODEL:
                set_matching(listing, "country_id")
            elif model == "event.event":
                set_matching(listing, "address_id.country_id")
            elif model == "event.registration":
                set_matching(listing, "event_id.address_id.country_id")
            elif model == CUSTOM_MODEL:
                set_matching(listing, "event_id.address_id.country_id")

    def _ensure_top_countries_pivot(self, data):
        """Create the spreadsheet pivot that supplies the Top 10 view.

        The Top 10 item in an Odoo spreadsheet carousel is backed by the
        spreadsheet data model.  It is not a normal ir.actions.act_window
        list view.  The map can therefore work while the Top 10 pane is
        empty if this pivot is missing.

        Keep this pivot on the same event.sale.report model, country field,
        sold domain and revenue measure used by the map.
        """
        pivots = data.setdefault("pivots", {})

        # Reuse an existing compatible pivot if the dashboard payload is
        # patched more than once during the same request/session.
        for pivot_id, pivot in pivots.items():
            if (
                pivot.get("model") == EVENT_REPORT_MODEL
                and pivot.get("name") == "Top Countries"
                and any(
                    row.get("fieldName") == "country_id"
                    for row in (pivot.get("rows") or [])
                )
                and any(
                    measure.get("fieldName") == "__count"
                    for measure in (pivot.get("measures") or [])
                )
                and any(
                    measure.get("fieldName") == "sale_price_untaxed"
                    for measure in (pivot.get("measures") or [])
                )
            ):
                return str(pivot_id)

        numeric_ids = []
        for pivot_id in pivots:
            try:
                numeric_ids.append(int(pivot_id))
            except (TypeError, ValueError):
                continue

        pivot_id = str(max(numeric_ids, default=0) + 1)
        country_filter_id = self._ensure_country_global_filter(data)

        field_matching = {
            DATE_FILTER_ID: {
                "chain": "event_date_begin",
                "type": "date",
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

        # Match the native Sales dashboard pivot structure.  In native Odoo,
        # the Top Countries carousel is backed by an ODOO Spreadsheet pivot
        # whose context identifies the report action/model and whose rows are
        # grouped by country.  Use the existing Events report action rather
        # than creating a second action just for Top 10.
        event_action = self.env.ref(
            "event_sale.event_sale_report_action",
            raise_if_not_found=False,
        )
        pivot_context = {
            "group_by": [],
            "pivot_measures": [
                "__count__",
                "sale_price_untaxed",
            ],
        }
        if event_action:
            pivot_context["params"] = {
                "action": event_action.id,
                "model": EVENT_REPORT_MODEL,
                "view_type": "pivot",
                "cids": self.env.companies.ids,
            }

        pivots[pivot_id] = {
            "type": "ODOO",
            "fieldMatching": field_matching,
            "context": pivot_context,
            "domain": [
                "&",
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
            "name": "Top Countries",
            "sortedColumn": {
                "measure": "sale_price_untaxed",
                "order": "desc",
                "domain": [],
            },
            "formulaId": pivot_id,
            "columns": [],
            "rows": [
                {
                    "fieldName": "country_id",
                }
            ],
        }

        data["pivotNextId"] = str(
            max(numeric_ids + [int(pivot_id)]) + 1
        )
        return pivot_id

    def _add_top_countries_map(self, data, dashboard_sheet):
        """Add Top Countries using the native Odoo Sales-style carousel.

        The standard Odoo Sales dashboard uses a ``carousel`` figure for
        Top Countries.  The carousel contains the native geo map and the
        ``Top 10`` data view.  Keeping this structure gives us the same:

        - Odoo default dashboard title/font styling
        - Map / Top 10 selector
        - expand and options controls
        - map value/index legend
        - Top 10 table view

        Only the model, fields, filters and event-specific domain are
        different from the Sales dashboard.
        """
        figures = dashboard_sheet.setdefault("figures", [])

        # The native Sales Top Countries carousel gets its Top 10 data from
        # a Spreadsheet ODOO pivot.  Create the equivalent event.sale.report
        # pivot before creating the carousel.
        self._ensure_top_countries_pivot(data)

        # Remove any previous version of our Top Countries figure so the
        # runtime patch remains idempotent when the dashboard is reloaded.
        figures[:] = [
            figure
            for figure in figures
            if figure.get("id") not in {
                TOP_COUNTRIES_FIGURE_ID,
                TOP_COUNTRIES_CHART_ID,
            }
            and not (
                figure.get("tag") == "carousel"
                and (figure.get("data") or {})
                .get("title", {})
                .get("text") == "Top Countries"
            )
        ]

        # Create/reuse the global Country relation filter.  The native Sales
        # dashboard uses this filter to turn a Top 10 selection into a
        # dashboard-wide filter.
        country_filter_id = self._ensure_country_global_filter(data)

        # Reuse the existing Events dashboard filters.  These are the same
        # filter IDs used by the standard event charts and scorecards.
        field_matching = {
            DATE_FILTER_ID: {
                "chain": "event_date_begin",
                "type": "date",
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

        # This is intentionally the same structure used by Odoo's native
        # Sales Top Countries carousel.  In particular, ``items`` must use
        # ``carouselDataView`` for the Top 10 view and the map definition
        # must live inside ``chartDefinitions``.
        figure = {
            "id": TOP_COUNTRIES_FIGURE_ID,
            "col": 0,
            "row": 0,
            "offset": {"x": 0, "y": 300},
            "width": 475,
            "height": 345,
            "tag": "carousel",
            "data": {
                "chartDefinitions": {
                    TOP_COUNTRIES_CHART_ID: {
                        "title": {},
                        "background": "#FFFFFF",
                        "legendPosition": "left",
                        "metaData": {
                            "groupBy": ["country_id"],
                            "measure": "sale_price_untaxed",
                            "order": None,
                            "resModel": EVENT_REPORT_MODEL,
                            "mode": "bar",
                        },
                        "searchParams": {
                            "modelName": EVENT_REPORT_MODEL,
                            "comparison": None,
                            "context": {
                                "group_by": [],
                                "pivot_measures": [
                                    "__count__",
                                    "sale_price_untaxed",
                                ],
                            },
                            "domain": "[\"&\", (\"country_id\", \"!=\", false), (\"sale_status\", \"=\", \"sold\")]",
                            "groupBy": ["country_id"],
                            "orderBy": [],
                        },
                        "type": "odoo_geo",
                        "actionXmlId": "event_sale.event_sale_report_action",
                        "dataSets": [{}],
                        "colorScale": "blues",
                    }
                },
                "items": [
                    {
                        "type": "chart",
                        "chartId": TOP_COUNTRIES_CHART_ID,
                        "title": "Map",
                    },
                    {
                        "type": "carouselDataView",
                        "title": "Top 10",
                    },
                ],
                # Use the same native Odoo title configuration as Sales.
                # No custom font family is supplied, so Odoo's normal
                # Spreadsheet/dashboard font is used automatically.
                "title": {
                    "text": "Top Countries",
                    "fontSize": 21,
                    "bold": True,
                    "color": "#01666B",
                },
                "fieldMatching": {
                    TOP_COUNTRIES_CHART_ID: field_matching,
                },
            },
        }

        figures.append(figure)
        return True

    def _rearrange_event_dashboard_layout(self, data, dashboard_sheet):
        """Arrange the Events dashboard into a clean two-column layout.

        The layout deliberately follows the geometry of the standard Odoo
        Events dashboard instead of creating a second, unrelated grid.

        Layout:

            KPI row 1: Events | Revenue | Attendees
            KPI row 2: Customer Acquisition | Average Registration | Average Revenue

            Row 1: Top Countries | Events Status
            Row 2: Registration Status | Top Venues
            Row 3: Top Tags | Top Templates
            Row 4: Top Organisers

        Only the in-memory dashboard payload is changed.  The stored Odoo
        dashboard remains untouched.
        """
        figures = dashboard_sheet.setdefault("figures", [])
        cells = dashboard_sheet.setdefault("cells", {})

        # ---------------------------------------------------------
        # Keep the native Odoo Events spreadsheet geometry.
        # The standard dashboard uses 5 columns: A:B on the left,
        # C as the gutter, and D:E on the right.
        # ---------------------------------------------------------
        dashboard_sheet["colNumber"] = 5
        dashboard_sheet["rowNumber"] = 67
        dashboard_sheet["cols"] = {
            "0": {"size": 374},
            "1": {"size": 100},
            "2": {"size": 50},
            "3": {"size": 375},
            "4": {"size": 100},
        }

        # Remove the old custom row metadata created by the previous
        # layout patch and rebuild only the rows needed by this layout.
        dashboard_sheet["rows"] = {
            "6": {"size": 40},
            "13": {"size": 40},
            "29": {"size": 40},
            "30": {"size": 29},
            "31": {"size": 29},
            "32": {"size": 29},
            "33": {"size": 29},
            "34": {"size": 29},
            "35": {"size": 29},
            "36": {"size": 29},
            "37": {"size": 29},
            "38": {"size": 29},
            "39": {"size": 29},
            "40": {"size": 29},
            "42": {"size": 40},
            "43": {"size": 29},
            "44": {"size": 29},
            "45": {"size": 29},
            "46": {"size": 29},
            "47": {"size": 29},
            "48": {"size": 29},
            "49": {"size": 29},
            "50": {"size": 29},
            "51": {"size": 29},
            "52": {"size": 29},
            "53": {"size": 29},
            "55": {"size": 40},
            "56": {"size": 29},
            "57": {"size": 29},
            "58": {"size": 29},
            "59": {"size": 29},
            "60": {"size": 29},
            "61": {"size": 29},
            "62": {"size": 29},
            "63": {"size": 29},
            "64": {"size": 29},
            "65": {"size": 29},
            "66": {"size": 29},
        }

        # Grid lines are not part of the dashboard design.  The component
        # borders/table borders are kept, but the raw spreadsheet grid is
        # hidden so a line cannot visually run through the middle of a card.
        dashboard_sheet["areGridLinesVisible"] = False

        # ---------------------------------------------------------
        # Find all standard/custom scorecards.
        # ---------------------------------------------------------
        scorecards = {}
        for figure in figures:
            if figure.get("tag") != "chart":
                continue
            chart = figure.get("data") or {}
            if chart.get("type") != "scorecard":
                continue
            title = (chart.get("title") or {}).get("text")
            if title:
                scorecards[title] = figure

        events_card = scorecards.get("Events")
        revenue_card = scorecards.get("Revenue")
        attendees_card = scorecards.get("Attendees")

        # ---------------------------------------------------------
        # KPI cards: exactly 3 per row.
        # ---------------------------------------------------------
        # Wider KPI cards so the renamed titles fit while keeping
        # the same native 3-cards-per-row layout.
        card_width = 280
        card_height = 105
        card_gap = 10
        kpi_x = [0, 290, 580]

        for card, x in zip(
            (events_card, revenue_card, attendees_card),
            kpi_x,
        ):
            if not card:
                continue
            card["width"] = card_width
            card["height"] = card_height
            card["offset"] = {"x": x, "y": 9}
            card["col"] = 0
            card["row"] = 0

        for title, x in zip(
            (
                "Customer Acquisitions",
                "Average Registrations Per Event",
                "Average Revenue Per Event",
            ),
            kpi_x,
        ):
            card = scorecards.get(title)
            if not card:
                # The three custom cards are added later by
                # _patch_event_dashboard_payload.  They are found after
                # that method adds them, so this loop is intentionally safe.
                continue
            card["width"] = card_width
            card["height"] = card_height
            card["offset"] = {"x": x, "y": 124}
            card["col"] = 0
            card["row"] = 0

        # Custom cards have already been added before this layout method is
        # called. Find them again because scorecards was built above.
        for title, x in zip(
            (
                "Customer Acquisitions",
                "Average Registrations Per Event",
                "Average Revenue Per Event",
            ),
            kpi_x,
        ):
            card = self._find_scorecard(dashboard_sheet, title)
            if card:
                card["width"] = card_width
                card["height"] = card_height
                card["offset"] = {"x": x, "y": 124}
                card["col"] = 0
                card["row"] = 0

        # ---------------------------------------------------------
        # Locate the standard/custom charts.
        # ---------------------------------------------------------
        registration_chart = None
        event_status_chart = None
        top_countries_map = None

        for figure in figures:
            tag = figure.get("tag")
            chart = figure.get("data") or {}
            meta = chart.get("metaData") or {}

            if figure.get("id") == TOP_COUNTRIES_FIGURE_ID:
                top_countries_map = figure
                continue

            if tag != "chart":
                continue

            if meta.get("resModel") == "event.registration":
                registration_chart = figure
            elif meta.get("resModel") == "event.event":
                group_by = meta.get("groupBy") or []
                if group_by == ["dashboard_status"]:
                    event_status_chart = figure

        # ---------------------------------------------------------
        # Exactly two large components per dashboard row.
        # ---------------------------------------------------------
        content_width = 475
        content_height = 345
        left_x = 0
        right_x = 525

        # Row 1 starts below the two KPI rows.
        top_row_y = 300

        # Row 2 starts immediately after the row-2 heading line.
        second_row_y = 708

        if top_countries_map:
            top_countries_map["width"] = content_width
            top_countries_map["height"] = content_height
            top_countries_map["offset"] = {
                "x": left_x,
                "y": top_row_y,
            }
            top_countries_map["col"] = 0
            top_countries_map["row"] = 0

        if event_status_chart:
            event_status_chart["width"] = content_width
            event_status_chart["height"] = content_height
            event_status_chart["offset"] = {
                "x": right_x,
                # Keep the heading cell clearly above the chart.  The
                # standard Events dashboard has a separate heading row
                # before the chart figure.
                "y": top_row_y + 40,
            }
            event_status_chart["col"] = 0
            event_status_chart["row"] = 0

        if registration_chart:
            registration_chart["width"] = content_width
            registration_chart["height"] = content_height
            registration_chart["offset"] = {
                "x": left_x,
                "y": second_row_y,
            }
            registration_chart["col"] = 0
            registration_chart["row"] = 0

        # ---------------------------------------------------------
        # Presentation cells.
        #
        # Use the same native spreadsheet columns as Odoo.  The headings
        # are placed on the same rows as the corresponding component.
        # ---------------------------------------------------------
        def graph_link(label, model, group_by, views):
            return (
                f'[{label}](odoo://view/{{"viewType":"graph","action":'
                f'{{"domain":[],"context":{{"group_by":{json.dumps(group_by)},'
                f'"graph_measure":"__count","graph_mode":"bar",'
                f'"graph_groupbys":{json.dumps(group_by)}}},"modelName":"{model}",'
                f'"views":{json.dumps(views)}}},"threshold":0,"name":"{label}"}})'
            )

        # Remove only presentation cells created by the previous custom
        # layout. Standard Odoo helper/KPI cells remain untouched.
        custom_ranges = (
            ("A", 7, 66),
            ("B", 7, 66),
            ("D", 7, 66),
            ("E", 7, 66),
        )
        for col, start_row, end_row in custom_ranges:
            for row in range(start_row, end_row + 1):
                cells.pop(f"{col}{row}", None)

        # Row 1: Top Countries | Events Status
        # Top Countries title is rendered by the carousel itself.
        cells["D13"] = graph_link(
            "Events Status",
            "event.event",
            ["dashboard_status"],
            [[False, "kanban"], [False, "calendar"], [False, "list"],
             [False, "form"], [False, "pivot"], [False, "graph"],
             [False, "search"]],
        )

        # Row 2: Registration Status | Top Venues
        cells["A29"] = graph_link(
            "Registration Status",
            "event.registration",
            ["state"],
            [[False, "graph"], [False, "pivot"], [False, "kanban"],
             [False, "list"], [False, "form"], [False, "search"]],
        )
        cells["D29"] = (
            '[Top Venues](odoo://view/{"viewType":"pivot","action":'
            '{"domain":[["address_id","!=",false]],"context":'
            '{"group_by":["address_id"],"pivot_measures":["__count"],'
            '"pivot_column_groupby":[],"pivot_row_groupby":["address_id"]},'
            '"modelName":"event.event","views":[[false,"kanban"],'
            '[false,"calendar"],[false,"list"],[false,"form"],[false,"pivot"],'
            '[false,"graph"],[false,"search"]]},"threshold":0,"name":"Events"})'
        )
        cells["D30"] = '=_t("Venue")'
        cells["E30"] = '=_t("Events")'
        for i in range(1, 11):
            row = 30 + i
            cells[f"D{row}"] = f'=PIVOT.HEADER(1,"#address_id",{i})'
            cells[f"E{row}"] = f'=PIVOT.VALUE(1,"__count","#address_id",{i})'

        # Row 3: Top Tags | Top Templates
        cells["A42"] = (
            '[Top Tags](odoo://view/{"viewType":"pivot","action":'
            '{"domain":[["tag_ids","!=",false]],"context":'
            '{"group_by":["tag_ids"],"pivot_measures":["__count"],'
            '"pivot_column_groupby":[],"pivot_row_groupby":["tag_ids"]},'
            '"modelName":"event.event","views":[[false,"kanban"],'
            '[false,"calendar"],[false,"list"],[false,"form"],[false,"pivot"],'
            '[false,"graph"],[false,"search"]]},"threshold":0,"name":"Events"})'
        )
        cells["A43"] = '=_t("Tag")'
        cells["B43"] = '=_t("Events")'
        for i in range(1, 11):
            row = 43 + i
            cells[f"A{row}"] = f'=PIVOT.HEADER(3,"#tag_ids",{i})'
            cells[f"B{row}"] = f'=PIVOT.VALUE(3,"__count","#tag_ids",{i})'

        cells["D42"] = (
            '[Top Templates](odoo://view/{"viewType":"pivot","action":'
            '{"domain":[["event_type_id","!=",false]],"context":'
            '{"group_by":["event_type_id"],"pivot_measures":["__count"],'
            '"pivot_column_groupby":[],"pivot_row_groupby":["event_type_id"]},'
            '"modelName":"event.event","views":[[false,"kanban"],'
            '[false,"calendar"],[false,"list"],[false,"form"],[false,"pivot"],'
            '[false,"graph"],[false,"search"]]},"threshold":0,"name":"Events"})'
        )
        cells["D43"] = '=_t("Template")'
        cells["E43"] = '=_t("Events")'

        # Use the actual Odoo pivot whose dimension is event_type_id instead
        # of assuming that pivot ID 2 is always the Templates pivot.
        # The pivot IDs in Odoo are assigned by the dashboard payload, so a
        # hard-coded ID can point to a different pivot after other pivots are
        # added or reordered.
        template_pivot_id = None
        for pivot_id, pivot in (data.get("pivots") or {}).items():
            if pivot.get("model") != "event.event":
                continue

            def contains_dimension(value):
                if isinstance(value, str):
                    return value == "event_type_id" or value.endswith(".event_type_id")
                if isinstance(value, dict):
                    return any(contains_dimension(v) for v in value.values())
                if isinstance(value, (list, tuple)):
                    return any(contains_dimension(v) for v in value)
                return False

            if contains_dimension(pivot.get("rows")) or contains_dimension(
                pivot.get("columns")
            ):
                template_pivot_id = pivot_id
                break

        # Keep the previous value only as a safe fallback if the stock payload
        # does not expose a matching event_type_id pivot.
        template_pivot_id = template_pivot_id or "2"

        for i in range(1, 11):
            row = 43 + i
            cells[f"D{row}"] = (
                f'=PIVOT.HEADER({template_pivot_id},"#event_type_id",{i})'
            )
            cells[f"E{row}"] = (
                f'=PIVOT.VALUE({template_pivot_id},"__count","#event_type_id",{i})'
            )

        # Row 4: Top Organisers
        cells["A55"] = (
            '[Top Organisers](odoo://view/{"viewType":"pivot","action":'
            '{"domain":[["organizer_id","!=",false]],"context":'
            '{"group_by":["organizer_id"],"pivot_measures":["__count"],'
            '"pivot_column_groupby":[],"pivot_row_groupby":["organizer_id"]},'
            '"modelName":"event.event","views":[[false,"kanban"],'
            '[false,"calendar"],[false,"list"],[false,"form"],[false,"pivot"],'
            '[false,"graph"],[false,"search"]]},"threshold":0,"name":"Events"})'
        )
        cells["A56"] = '=_t("Organizer")'
        cells["B56"] = '=_t("Events")'
        for i in range(1, 11):
            row = 56 + i
            cells[f"A{row}"] = f'=PIVOT.HEADER(4,"#organizer_id",{i})'
            cells[f"B{row}"] = f'=PIVOT.VALUE(4,"__count","#organizer_id",{i})'

        # ---------------------------------------------------------
        # Native Odoo-style table definitions for the moved tables.
        # ---------------------------------------------------------
        dashboard_sheet["tables"] = [
            {
                "range": "D30:E40",
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
            },
            {
                "range": "A43:B53",
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
            },
            {
                "range": "D43:E53",
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
            },
            {
                "range": "A56:B66",
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
            },
        ]

        # ---------------------------------------------------------
        # Reuse the native Events dashboard style IDs already present in
        # the standard JSON.  This keeps the Odoo font and heading sizes.
        # ---------------------------------------------------------
        dashboard_sheet["styles"] = {
            "D13": 1,
            "A29": 1,
            "D29": 1,
            "A42": 1,
            "D42": 1,
            "A55": 1,
            "D30": 2,
            "E30": 4,
            "D31:E40": 3,
            "A43": 2,
            "B43": 4,
            "A44:B53": 3,
            "D43": 2,
            "E43": 4,
            "D44:E53": 3,
            "A56": 2,
            "B56": 4,
            "A57:B66": 3,
        }

        # Native-looking separator borders for each section.
        dashboard_sheet["borders"] = {
            "A29:B29": 1,
            "D29:E29": 1,
            "A42:B42": 1,
            "D42:E42": 1,
            "A55:B55": 1,
            "D30:E30": 2,
            "A43:B43": 2,
            "D43:E43": 2,
            "A56:B56": 2,
        }
    def _patch_event_dashboard_payload(self, data):
        """
        Add Customer Acquisition, Average Registration,
        and Average Revenue to the standard Odoo Events dashboard.

        IMPORTANT:
        We do NOT create or replace the standard date filter.
        We reuse the existing Events dashboard filter IDs.
        """

        # Patch the in-memory dashboard payload only.
        # Nothing is written to spreadsheet.dashboard, so uninstalling this
        # module immediately removes all visual/dashboard changes.

        dashboard_sheet = self._find_sheet(
            data,
            "Dashboard",
        )

        data_sheet = self._find_sheet(
            data,
            "Data",
        )

        if dashboard_sheet is None or data_sheet is None:
            return False

        # Patch the standard Events Status chart before touching the custom
        # KPI pivots. This keeps the existing chart/filter wiring intact.
        # Patch the actual Events Status chart.
        # The stock component is a chart figure, not a pivot.
        self._patch_event_status_chart(data)

        pivots = data.setdefault(
            "pivots",
            {},
        )

        cells = data_sheet.setdefault(
            "cells",
            {},
        )

        # ---------------------------------------------------------
        # Remove ONLY our own previous Customer Acquisition pivots.
        # ---------------------------------------------------------

        for pivot_id, pivot in list(pivots.items()):
            if pivot.get("model") == CUSTOM_MODEL:
                pivots.pop(
                    pivot_id,
                    None,
                )

        # ---------------------------------------------------------
        # Create fresh current/previous pivots.
        # ---------------------------------------------------------

        current_id, previous_id = self._next_pivot_ids(
            pivots
        )

        pivots[current_id] = self._make_customer_pivot(
            current_id,
            previous=False,
        )

        pivots[previous_id] = self._make_customer_pivot(
            previous_id,
            previous=True,
        )

        data["pivotNextId"] = str(
            int(previous_id) + 1
        )

        # ---------------------------------------------------------
        # KPI helper cells.
        # ---------------------------------------------------------

        cells["A7"] = '= _t("Customer Acquisitions")'.replace(
            "= ",
            "=",
        )

        cells["B7"] = (
            f'=IFERROR(PIVOT.VALUE({current_id},"acquisition_count"),0)'
        )

        cells["C7"] = (
            f'=IFERROR(PIVOT.VALUE({previous_id},"acquisition_count"),0)'
        )

        cells["D7"] = (
            "=FORMAT.LARGE.NUMBER(B7)"
        )

        cells["E7"] = (
            "=FORMAT.LARGE.NUMBER(C7)"
        )

        # ---------------------------------------------------------
        # Remove our previous custom KPI cards if present.
        # ---------------------------------------------------------

        figures = dashboard_sheet.setdefault(
            "figures",
            [],
        )

        custom_titles = {
            "Customer Acquisitions",
            "Average Registrations Per Event",
            "Average Revenue Per Event",
        }

        custom_ids = {
            CUSTOM_CARD_ID,
            AVG_REGISTRATION_CARD_ID,
            AVG_REVENUE_CARD_ID,
        }

        figures[:] = [
            figure
            for figure in figures
            if not (
                figure.get("id") in custom_ids
                or (
                    figure.get("tag") == "chart"
                    and figure.get("data", {}).get("type") == "scorecard"
                    and figure.get("data", {})
                    .get("title", {})
                    .get("text") in custom_titles
                )
            )
        ]

        # ---------------------------------------------------------
        # Copy a standard KPI scorecard as the visual template.
        # ---------------------------------------------------------

        template = (
            self._find_scorecard(dashboard_sheet, "Events")
            or self._find_scorecard(dashboard_sheet, "Revenue")
            or self._find_scorecard(dashboard_sheet, "Attendees")
        )

        if template is None:
            return False

        def add_scorecard(card_id, title, key_cell, baseline_cell, x, y, card_width, card_height):
            figure = copy.deepcopy(template)

            figure["id"] = card_id
            figure["data"]["chartId"] = card_id
            figure["data"]["type"] = "scorecard"
            # Preserve the exact title styling from the native Odoo
            # scorecard template. Only replace the displayed title text.
            native_title = copy.deepcopy(
                template.get("data", {}).get("title") or {}
            )
            native_title["text"] = title
            figure["data"]["title"] = native_title
            figure["data"]["keyValue"] = key_cell
            figure["data"]["baseline"] = baseline_cell
            figure["data"]["baselineDescr"] = {
                "text": "since last period",
            }
            figure["data"]["baselineMode"] = "percentage"

            figure["width"] = card_width
            figure["height"] = card_height
            figure["offset"] = {
                "x": x,
                "y": y,
            }
            figure["col"] = 0
            figure["row"] = 0

            figures.append(figure)

        # ---------------------------------------------------------
        # Custom KPI cells.
        #
        # Customer Acquisition:
        #     B7 = current value
        #     C7 = previous value
        #
        # Average Registration:
        #     Attendees / Events
        #
        # Average Revenue:
        #     Revenue / Events
        #
        # The standard Events, Revenue and Attendees scorecards remain
        # controlled by Odoo's existing date filter. These formulas read
        # those dashboard values instead of creating another date filter.
        # ---------------------------------------------------------

        cells["A7"] = '= _t("Customer Acquisitions")'.replace(
            "= ",
            "=",
        )
        cells["B7"] = (
            f'=IFERROR(PIVOT.VALUE({current_id},"acquisition_count"),0)'
        )
        cells["C7"] = (
            f'=IFERROR(PIVOT.VALUE({previous_id},"acquisition_count"),0)'
        )
        cells["D7"] = "=FORMAT.LARGE.NUMBER(B7)"
        cells["E7"] = "=FORMAT.LARGE.NUMBER(C7)"

        # The standard Odoo Events dashboard already calculates the
        # three base KPIs in the Data sheet:
        #
        # D2 = current Attendees
        # D3 = current Events
        # D4 = current Revenue
        # E2 = previous Attendees
        # E3 = previous Events
        # E4 = previous Revenue
        #
        # Reusing these cells is important: they are already connected to
        # Odoo's standard Events date filter.

        cells["A7"] = '=_t("Customer Acquisitions")'
        cells["B7"] = (
            f'=IFERROR(PIVOT.VALUE({current_id},"acquisition_count"),0)'
        )
        cells["C7"] = (
            f'=IFERROR(PIVOT.VALUE({previous_id},"acquisition_count"),0)'
        )
        cells["D7"] = "=FORMAT.LARGE.NUMBER(B7)"
        cells["E7"] = "=FORMAT.LARGE.NUMBER(C7)"

        # Average Registration = Attendees / Events
        cells["A8"] = '=_t("Average Registrations Per Event")'
        cells["B8"] = "=IFERROR(Data!D2/Data!D3,0)"
        cells["C8"] = "=IFERROR(Data!E2/Data!E3,0)"
        cells["D8"] = "=FORMAT.LARGE.NUMBER(B8)"
        cells["E8"] = "=FORMAT.LARGE.NUMBER(C8)"

        # Average Revenue = Revenue / Events
        cells["A9"] = '=_t("Average Revenue Per Event")'
        cells["B9"] = "=IFERROR(Data!D4/Data!D3,0)"
        cells["C9"] = "=IFERROR(Data!E4/Data!E3,0)"
        cells["D9"] = "=B9"
        cells["E9"] = "=C9"

        # Apply the Rupee symbol only to the Average Revenue KPI cells.
        # Odoo Spreadsheet keeps format definitions at the top level and
        # applies them to individual sheet cells through the sheet mapping.
        formats = data.setdefault("formats", {})
        formats["rs_currency"] = "[$₹]#,##0"

        data_sheet.setdefault("formats", {})["D9"] = "rs_currency"
        data_sheet.setdefault("formats", {})["E9"] = "rs_currency"

        # ---------------------------------------------------------
        # Position all 6 KPI cards in ONE row.
        # ---------------------------------------------------------

        events_card = self._find_scorecard(
            dashboard_sheet,
            "Events",
        )
        revenue_card = self._find_scorecard(
            dashboard_sheet,
            "Revenue",
        )
        attendees_card = self._find_scorecard(
            dashboard_sheet,
            "Attendees",
        )

        if events_card:
            events_offset = events_card.get("offset", {})
            base_x = events_offset.get("x", 420)
            base_y = events_offset.get("y", 9)
        elif attendees_card:
            attendees_offset = attendees_card.get("offset", {})
            base_x = attendees_offset.get("x", 420) - 2 * 116
            base_y = attendees_offset.get("y", 9)
        else:
            base_x = 420
            base_y = 9

        # Keep the existing two-row KPI layout: three cards per row.
        # This prevents the longer renamed KPI titles from being clipped
        # because a fourth, fifth, or sixth card is pushed outside the
        # dashboard's visible width.
        # Match the wider KPI width used by the final dashboard layout.
        # Keeping three cards per row gives the longer titles enough room.
        card_width = 280
        card_height = (
            events_card.get("height", 105)
            if events_card
            else 105
        )
        gap = 10
        kpi_x = [0, 290, 580]

        def set_card_position(card, x, y):
            if not card:
                return
            card["width"] = card_width
            card["height"] = card_height
            card["offset"] = {"x": x, "y": y}
            card["col"] = 0
            card["row"] = 0

        # Row 1: Events | Revenue | Attendees
        set_card_position(events_card, kpi_x[0], 9)
        set_card_position(revenue_card, kpi_x[1], 9)
        set_card_position(attendees_card, kpi_x[2], 9)

        # Row 2: Customer Acquisitions | Average Registrations Per Event
        # | Average Revenue Per Event
        add_scorecard(
            CUSTOM_CARD_ID,
            "Customer Acquisitions",
            "Data!D7",
            "Data!E7",
            kpi_x[0],
            124,
            card_width,
            card_height,
        )

        add_scorecard(
            AVG_REGISTRATION_CARD_ID,
            "Average Registrations Per Event",
            "Data!D8",
            "Data!E8",
            kpi_x[1],
            124,
            card_width,
            card_height,
        )

        add_scorecard(
            AVG_REVENUE_CARD_ID,
            "Average Revenue Per Event",
            "Data!D9",
            "Data!E9",
            kpi_x[2],
            124,
            card_width,
            card_height,
        )

        # ---------------------------------------------------------
        # Add the Sales-style Top Countries map.
        # ---------------------------------------------------------
        self._add_top_countries_map(data, dashboard_sheet)

        # Apply the final two-column layout after every custom component has
        # been created, so no later component can overwrite its position.
        self._rearrange_event_dashboard_layout(data, dashboard_sheet)

        # Make the Top 10 country selection behave like Sales: it populates
        # the Country global filter and propagates to compatible event sources.
        self._add_country_filter_matching(data)

        return data
    def _get_serialized_readonly_dashboard(self):
        """Return the stock Events dashboard patched only in memory.

        This mirrors the safe architecture used by the Sales enhancement:
        the stored ``spreadsheet_binary_data`` is never modified.  The
        standard dashboard is loaded by ``super()`` and our changes are
        applied only to the JSON response sent to the browser.
        """
        result = super()._get_serialized_readonly_dashboard()

        target = self.env.ref(
            "spreadsheet_dashboard_event_sale.spreadsheet_dashboard_events",
            raise_if_not_found=False,
        )
        if not target or self.id != target.id:
            return result

        try:
            payload = json.loads(result)
            payload["snapshot"] = self._patch_event_dashboard_payload(
                payload["snapshot"]
            )
            # Final in-memory fixes for the requested second KPI row and
            # the Sales-style Top Countries Map / Top 10 view.
            payload["snapshot"] = self._apply_final_dashboard_fixes(
                payload["snapshot"]
            )
            return json.dumps(payload)
        except Exception:
            # Never let a custom dashboard patch break the standard Events
            # dashboard. Serve the untouched stock payload instead.
            import logging
            logging.getLogger(__name__).exception(
                "spreadsheet_dashboard_event_sale_enhancements_withAI: "
                "failed to patch the Events dashboard JSON; serving stock "
                "dashboard instead."
            )
            return result