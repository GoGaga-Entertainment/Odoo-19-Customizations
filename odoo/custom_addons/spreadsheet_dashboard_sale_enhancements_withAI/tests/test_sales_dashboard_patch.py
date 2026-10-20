from odoo.tests.common import TransactionCase

from ..models.sales_dashboard_patch import (
    _copy_field_matching,
    patch_sales_dashboard_json,
    _add_cancellation_pivot,
    _add_positive_product_revenue_pivot,
    _set_cells,
    _add_data_sheet_helper_cells,
    _add_kpi_scorecards,
    _add_contribution_table,
    _register_menu_references,
    NEW_CANCELLATION_PIVOT_ID,
    NEW_KPI_FIGURE_IDS,
    TOP_PRODUCTS_PIVOT_ID,
    POSITIVE_PRODUCT_REVENUE_PIVOT_ID,
)


class TestSalesDashboardPatch(TransactionCase):

    # ---------------------------------------------------------
    # 1. Test _copy_field_matching()
    # ---------------------------------------------------------

    def test_copy_field_matching(self):

        pivots = {
            "11": {
                "fieldMatching": {
                    "period": "period",
                    "country": "country",
                    "product": "product",
                }
            }
        }

        result = _copy_field_matching(pivots, "11")

        # Check that the fieldMatching data was copied
        self.assertEqual(
            result,
            pivots["11"]["fieldMatching"]
        )

        # Check that it is a separate copy
        self.assertIsNot(
            result,
            pivots["11"]["fieldMatching"]
        )

    # ---------------------------------------------------------
    # 2. Test patch_sales_dashboard_json()
    # ---------------------------------------------------------

    def test_patch_sales_dashboard_json(self):

        data = {
            "pivots": {
                "11": {
                    "fieldMatching": {}
                }
            },
            "sheets": [
                {
                    "id": "Dashboard",
                    "name": "Dashboard",
                    "cells": {},
                    "figures": [],
                },
                {
                    "id": "Data",
                    "name": "Data",
                    "cells": {},
                }
            ],
            "formats": {},
            "chartOdooMenusReferences": {},
        }

        result = patch_sales_dashboard_json(data)

        # Check cancellation pivot was added
        self.assertIn(
            NEW_CANCELLATION_PIVOT_ID,
            result["pivots"]
        )

        # Check positive revenue pivot was added
        self.assertIn(
            POSITIVE_PRODUCT_REVENUE_PIVOT_ID,
            result["pivots"]
        )

        # Find Data sheet
        data_sheet = next(
            sheet
            for sheet in result["sheets"]
            if sheet["name"] == "Data"
        )

        # Check helper cells were added
        self.assertIn(
            "H10",
            data_sheet["cells"]
        )

        # Find Dashboard sheet
        dashboard_sheet = next(
            sheet
            for sheet in result["sheets"]
            if sheet["name"] == "Dashboard"
        )

        # Check three KPI cards were added
        self.assertEqual(
            len(dashboard_sheet["figures"]),
            3
        )

        # Check menu references were added
        self.assertEqual(
            len(result["chartOdooMenusReferences"]),
            3
        )

    # ---------------------------------------------------------
    # 3. Test _add_cancellation_pivot()
    # ---------------------------------------------------------

    def test_add_cancellation_pivot(self):

        pivots = {
            "11": {
                "fieldMatching": {}
            }
        }

        _add_cancellation_pivot(pivots)

        # Check that new pivot was created
        self.assertIn(
            NEW_CANCELLATION_PIVOT_ID,
            pivots
        )

        pivot = pivots[NEW_CANCELLATION_PIVOT_ID]

        # Check basic configuration
        self.assertEqual(
            pivot["id"],
            NEW_CANCELLATION_PIVOT_ID
        )

        self.assertEqual(
            pivot["type"],
            "ODOO"
        )

        self.assertEqual(
            pivot["model"],
            "sale.report"
        )

        # Check cancellation pivot groups by state
        self.assertEqual(
            pivot["rows"],
            [{"fieldName": "state"}]
        )

        # Check order measure
        self.assertEqual(
            pivot["measures"][0]["fieldName"],
            "order_reference"
        )

    # ---------------------------------------------------------
    # 4. Test _add_positive_product_revenue_pivot()
    # ---------------------------------------------------------

    def test_add_positive_product_revenue_pivot(self):

        pivots = {
            "11": {
                "fieldMatching": {}
            }
        }

        _add_positive_product_revenue_pivot(pivots)

        # Check that new pivot was created
        self.assertIn(
            POSITIVE_PRODUCT_REVENUE_PIVOT_ID,
            pivots
        )

        pivot = pivots[POSITIVE_PRODUCT_REVENUE_PIVOT_ID]

        # Check pivot ID
        self.assertEqual(
            pivot["id"],
            POSITIVE_PRODUCT_REVENUE_PIVOT_ID
        )

        # Check pivot type
        self.assertEqual(
            pivot["type"],
            "ODOO"
        )

        # Check model
        self.assertEqual(
            pivot["model"],
            "sale.report"
        )

        # Check positive revenue condition
        self.assertEqual(
            pivot["domain"],
            [["price_subtotal", ">", 0]]
        )

        # Check revenue measure
        self.assertEqual(
            pivot["measures"][0]["fieldName"],
            "price_subtotal"
        )

    # ---------------------------------------------------------
    # 5. Test _set_cells()
    # ---------------------------------------------------------

    def test_set_cells(self):

        sheet = {
            "name": "Data",
            "cells": {
                "A1": "Old value"
            }
        }

        new_cells = {
            "B1": "New value",
            "C1": "=SUM(A1:B1)"
        }

        _set_cells(
            sheet,
            new_cells
        )

        # Check new cells were added
        self.assertEqual(
            sheet["cells"]["B1"],
            "New value"
        )

        self.assertEqual(
            sheet["cells"]["C1"],
            "=SUM(A1:B1)"
        )

        # Check existing cell was not removed
        self.assertEqual(
            sheet["cells"]["A1"],
            "Old value"
        )

    # ---------------------------------------------------------
    # 6. Test _add_data_sheet_helper_cells()
    # ---------------------------------------------------------

    def test_add_data_sheet_helper_cells(self):

        data_sheet = {
            "id": "Data",
            "name": "Data",
            "cells": {},
        }

        _add_data_sheet_helper_cells(
            data_sheet
        )

        cells = data_sheet["cells"]

        # Check customer pivot formula
        self.assertEqual(
            cells["J1"],
            "=PIVOT(4,1000,0,0)"
        )

        # Check customer count
        self.assertEqual(
            cells["H10"],
            "=COUNTA(J1:J1000)"
        )

        # Check revenue per customer
        self.assertEqual(
            cells["H11"],
            "=IFERROR(B7/H10,0)"
        )

        # Check sales growth
        self.assertEqual(
            cells["H13"],
            "=IFERROR((B7-C7)/C7,0)"
        )

        # Check cancellation rate
        self.assertEqual(
            cells["H17"],
            "=IFERROR(H16/H15,0)"
        )

        # Check positive revenue denominator
        self.assertEqual(
            cells["H19"],
            '=PIVOT.VALUE(14,"price_subtotal")'
        )

    # ---------------------------------------------------------
    # 7. Test _add_kpi_scorecards()
    # ---------------------------------------------------------

    def test_add_kpi_scorecards(self):

        dashboard_sheet = {
            "id": "Dashboard",
            "name": "Dashboard",
            "cells": {},
            "figures": [],
        }

        _add_kpi_scorecards(
            dashboard_sheet
        )

        figures = dashboard_sheet["figures"]

        # Three custom KPI cards should be added
        self.assertEqual(
            len(figures),
            3
        )

        # Get all figure IDs
        figure_ids = {
            figure["id"]
            for figure in figures
        }

        # Check all three KPI IDs
        for kpi_id in NEW_KPI_FIGURE_IDS.values():

            self.assertIn(
                kpi_id,
                figure_ids
            )

        # Get all KPI titles
        titles = {
            figure["data"]["title"]["text"]
            for figure in figures
        }

        # Check Revenue Per Customer
        self.assertIn(
            "Revenue Per Customer",
            titles
        )

        # Check Sales Growth Percentage
        self.assertIn(
            "Sales Growth Percentage",
            titles
        )

        # Check Order Cancellation Percentage
        self.assertIn(
            "Order Cancellation Percentage",
            titles
        )

    # ---------------------------------------------------------
    # 8. Test _add_contribution_table()
    # ---------------------------------------------------------

    def test_add_contribution_table(self):

        dashboard_sheet = {
            "id": "Dashboard",
            "name": "Dashboard",
            "cells": {},
            "figures": [],
        }

        data = {
            "sheets": [
                {
                    "id": "Data",
                    "name": "Data",
                    "cells": {},
                }
            ],
            "formats": {},
        }

        _add_contribution_table(
            dashboard_sheet,
            data
        )

        cells = dashboard_sheet["cells"]

        # Check header
        self.assertEqual(
            cells["H36"],
            '=_t("% of Revenue")'
        )

        # Check the 10 contribution formulas
        for row in range(37, 47):

            cell_id = f"H{row}"

            # Check cell exists
            self.assertIn(
                cell_id,
                cells
            )

            formula = cells[cell_id]

            # Check formula uses Top Products pivot
            self.assertIn(
                f"PIVOT.VALUE({TOP_PRODUCTS_PIVOT_ID}",
                formula
            )

            # Check formula uses positive revenue denominator
            self.assertIn(
                "Data!$H$19",
                formula
            )

    # ---------------------------------------------------------
    # 9. Test _register_menu_references()
    # ---------------------------------------------------------

    def test_register_menu_references(self):

        data = {
            "chartOdooMenusReferences": {}
        }

        _register_menu_references(
            data
        )

        references = data[
            "chartOdooMenusReferences"
        ]

        # Three KPI cards should have menu references
        self.assertEqual(
            len(references),
            3
        )

        # Check each KPI reference
        for chart_id in NEW_KPI_FIGURE_IDS.values():

            # Check chart ID exists
            self.assertIn(
                chart_id,
                references
            )

            # Check correct menu reference
            self.assertEqual(
                references[chart_id],
                "sale.menu_reporting_sales"
            )