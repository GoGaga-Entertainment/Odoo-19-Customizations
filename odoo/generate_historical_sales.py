# ============================================================
# ODOO 19 - GENERATE DUMMY HISTORICAL SALES ORDERS
# ============================================================
#
# Creates confirmed sales orders for the last 6 months.
#
# Uses:
# - Existing customers from res.partner
# - Existing saleable products from product.product
# - Random historical dates
# - Random quantities
# - Existing product prices
#
# The orders are automatically confirmed.
# ============================================================

import random
from datetime import datetime, timedelta, time

from dateutil.relativedelta import relativedelta


# ============================================================
# CONFIGURATION
# ============================================================

NUMBER_OF_ORDERS = 150

# Set this to False if you only want quotations.
AUTO_CONFIRM_ORDERS = True

# Avoid creating duplicate dummy orders on repeated execution.
DELETE_OLD_DUMMY_ORDERS = False

# Prefix used to identify generated orders.
ORDER_PREFIX = "DUMMY-HIST-"

# Minimum and maximum quantity per order line.
MIN_QUANTITY = 1
MAX_QUANTITY = 5

# Number of products in each order.
MIN_LINES_PER_ORDER = 1
MAX_LINES_PER_ORDER = 4


# ============================================================
# MODEL REFERENCES
# ============================================================

SaleOrder = env["sale.order"]
SaleOrderLine = env["sale.order.line"]
Partner = env["res.partner"]
Product = env["product.product"]


# ============================================================
# DELETE PREVIOUSLY GENERATED ORDERS
# ============================================================

if DELETE_OLD_DUMMY_ORDERS:
    old_orders = SaleOrder.search([
        ("client_order_ref", "like", ORDER_PREFIX),
    ])

    print("Old dummy orders found:", len(old_orders))

    for old_order in old_orders:
        # Cancel confirmed orders before deletion.
        if old_order.state not in ("draft", "sent", "cancel"):
            old_order.action_cancel()

        old_order.unlink()

    print("Old dummy orders deleted.")


# ============================================================
# LOAD CUSTOMERS
# ============================================================

customers = Partner.search([
    ("customer_rank", ">", 0),
    ("active", "=", True),
])

if not customers:
    raise Exception(
        "No customers found. Create or import customers first."
    )

print("Customers available:", len(customers))


# ============================================================
# LOAD PRODUCTS
# ============================================================

products = Product.search([
    ("sale_ok", "=", True),
    ("active", "=", True),
    ("list_price", ">", 0),
])

if not products:
    raise Exception(
        "No saleable products found. Create or import products first."
    )

print("Saleable products available:", len(products))


# ============================================================
# DATE RANGE
# ============================================================

today = datetime.now()

# Start date is six months before today.
start_date = today - relativedelta(months=6)

# End date is yesterday so that generated orders are fully historical.
end_date = today - timedelta(days=1)

date_range_days = (end_date.date() - start_date.date()).days

if date_range_days <= 0:
    raise Exception("Invalid historical date range.")


# ============================================================
# CREATE ORDERS
# ============================================================

created_orders = []
failed_orders = []

print()
print("Generating historical sales orders...")
print("From:", start_date)
print("To:", end_date)
print("Total orders:", NUMBER_OF_ORDERS)
print()


for order_number in range(1, NUMBER_OF_ORDERS + 1):

    try:
        # ----------------------------------------------------
        # Select random customer
        # ----------------------------------------------------
        customer = random.choice(customers)

        # ----------------------------------------------------
        # Generate a random historical datetime
        # ----------------------------------------------------
        random_days = random.randint(0, date_range_days)

        historical_date = start_date + timedelta(days=random_days)

        historical_date = datetime.combine(
            historical_date.date(),
            time(
                hour=random.randint(9, 17),
                minute=random.randint(0, 59),
                second=random.randint(0, 59),
            ),
        )

        # ----------------------------------------------------
        # Select random products without duplicates
        # ----------------------------------------------------
        number_of_lines = random.randint(
            MIN_LINES_PER_ORDER,
            min(MAX_LINES_PER_ORDER, len(products)),
        )

        selected_products = random.sample(
            list(products),
            number_of_lines,
        )

        order_lines = []

        for product in selected_products:

            quantity = random.randint(
                MIN_QUANTITY,
                MAX_QUANTITY,
            )

            # Use the current product sales price.
            unit_price = product.lst_price

            order_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "product_uom_qty": quantity,
                        "price_unit": unit_price,
                        "name": product.display_name,
                    },
                )
            )

        # ----------------------------------------------------
        # Create quotation
        # ----------------------------------------------------
        order = SaleOrder.create({
            "partner_id": customer.id,
            "date_order": historical_date,
            "client_order_ref": (
                f"{ORDER_PREFIX}{order_number:05d}"
            ),
            "order_line": order_lines,
        })

        # ----------------------------------------------------
        # Confirm quotation through Odoo workflow
        # ----------------------------------------------------
        if AUTO_CONFIRM_ORDERS:
            order.action_confirm()

            # Odoo may update the order date during confirmation.
            # Restore the intended historical sales order date.
            order.write({
                "date_order": historical_date,
            })

        created_orders.append(order)

        print(
            f"[{order_number}/{NUMBER_OF_ORDERS}] "
            f"{order.name} | "
            f"{customer.display_name} | "
            f"{historical_date.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"State: {order.state}"
        )

    except Exception as error:
        failed_orders.append({
            "order_number": order_number,
            "error": str(error),
        })

        print(
            f"FAILED order {order_number}: {error}"
        )


# ============================================================
# COMMIT TRANSACTION
# ============================================================

env.cr.commit()


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("HISTORICAL SALES ORDER GENERATION COMPLETED")
print("=" * 70)
print("Orders requested:", NUMBER_OF_ORDERS)
print("Orders created:", len(created_orders))
print("Orders failed:", len(failed_orders))
print("Auto-confirm enabled:", AUTO_CONFIRM_ORDERS)
print("Date range:", start_date.date(), "to", end_date.date())


if failed_orders:
    print()
    print("FAILED ORDERS")
    print("-" * 70)

    for failed in failed_orders:
        print(
            failed["order_number"],
            "=>",
            failed["error"],
        )

print()
print("Generated orders use reference prefix:", ORDER_PREFIX)
print("You can find them using Client Reference contains:", ORDER_PREFIX)