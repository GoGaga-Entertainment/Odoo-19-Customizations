# Part of custom addon - ecommerce_product_custom_discounts
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo import fields, Command
from datetime import timedelta, date


@tagged('post_install', '-at_install')
class TestDiscountLogic(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create a test customer
        cls.customer = cls.env['res.partner'].create({
            'name': 'Test Customer',
            'email': 'customer@test.com',
        })

        # Create a portal user for the customer to test wishlist flow
        cls.user = cls.env['res.users'].create({
            'name': 'Test Customer User',
            'login': 'customer@test.com',
            'partner_id': cls.customer.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })

        # Create products
        cls.product_storable = cls.env['product.product'].create({
            'name': 'Storable Product',
            'type': 'consu',  # consumable/storable
            'list_price': 100.0,
        })
        cls.product_service = cls.env['product.product'].create({
            'name': 'Service Product',
            'type': 'service',
            'list_price': 50.0,
        })

        # Get or create website
        cls.website = cls.env['website'].search([], limit=1)
        if not cls.website:
            cls.website = cls.env['website'].create({
                'name': 'Test Website',
            })

        # Create Sale Order
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.customer.id,
            'website_id': cls.website.id,
            'order_line': [
                Command.create({
                    'product_id': cls.product_storable.id,
                    'product_uom_qty': 1,
                    'price_unit': 100.0,
                }),
                Command.create({
                    'product_id': cls.product_service.id,
                    'product_uom_qty': 1,
                    'price_unit': 50.0,
                }),
            ]
        })

        # Clear/initialize config parameters to avoid interference from other tests
        cls.Param = cls.env['ir.config_parameter'].sudo()

    def test_abandoned_cart_recovery_disabled(self):
        """When disabled, action_apply_abandoned_cart_discount should do nothing."""
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_enabled', 'False')

        self.order.action_apply_abandoned_cart_discount()

        self.assertFalse(self.order.abandoned_cart_offer_expiry)
        self.assertEqual(self.order.abandoned_cart_active_discount, 0.0)
        self.assertEqual(self.order.order_line[0].discount, 0.0)

    def test_abandoned_cart_recovery_enabled_and_escalating(self):
        """When enabled, discount starts at starting discount and escalates/caps correctly."""
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_enabled', 'True')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_strategy', 'escalating')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_delay_hours', '0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_start', '5.0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_step', '5.0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_max', '15.0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_hours', '24')

        # First run: Initialize offer and set to starting discount (5.0%)
        self.order.action_apply_abandoned_cart_discount()
        self.order._apply_best_discounts_to_lines()
        self.assertTrue(self.order.abandoned_cart_offer_expiry)
        self.assertEqual(self.order.abandoned_cart_active_discount, 5.0)
        self.assertEqual(self.order.abandoned_cart_discount_step_count, 1)
        self.assertEqual(self.order.order_line[0].discount, 5.0)
        self.assertEqual(self.order.order_line[1].discount, 0.0)  # Service shouldn't be discounted

    def test_abandoned_cart_recovery_diminishing(self):
        """Test diminishing (reverse) strategy starts at max discount."""
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_enabled', 'True')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_strategy', 'reverse')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_delay_hours', '0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_start', '5.0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_step', '5.0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_max', '20.0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_hours', '24')

        self.order.action_apply_abandoned_cart_discount()
        self.order._apply_best_discounts_to_lines()
        self.assertEqual(self.order.abandoned_cart_active_discount, 20.0)
        self.assertEqual(self.order.order_line[0].discount, 20.0)

    def test_abandoned_cart_recovery_expired(self):
        """When expiry is passed, the discount resets to 0."""
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_enabled', 'True')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_delay_hours', '0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_start', '5.0')
        self.Param.set_param('ecommerce_product_custom_discounts.abandoned_cart_discount_hours', '24')

        # First run: set initial discount
        self.order.action_apply_abandoned_cart_discount()
        self.order._apply_best_discounts_to_lines()
        self.assertTrue(self.order.abandoned_cart_active_discount > 0)

        # Set the expiry to the past
        self.order.write({
            'abandoned_cart_offer_expiry': fields.Datetime.now() - timedelta(hours=1)
        })

        # Run again: should trigger reset because it's expired
        self.order.action_apply_abandoned_cart_discount()
        self.order._apply_best_discounts_to_lines()
        self.assertFalse(self.order.abandoned_cart_offer_expiry)
        self.assertEqual(self.order.abandoned_cart_active_discount, 0.0)
        self.assertEqual(self.order.abandoned_cart_discount_step_count, 0)
        self.assertEqual(self.order.order_line[0].discount, 0.0)

    def test_wishlist_special_day_discount(self):
        """Test the wishlist special day discount logic."""
        # Enable config
        self.Param.set_param('ecommerce_product_custom_discounts.wishlist_special_day_enabled', 'True')
        self.Param.set_param('ecommerce_product_custom_discounts.wishlist_special_day_discount', '25.0')

        # Add storable product to the user's wishlist
        wishlist = self.env['product.wishlist'].sudo().create({
            'partner_id': self.customer.id,
            'product_id': self.product_storable.id,
            'website_id': self.website.id,
        })

        # Scenario 1: Configured date is NOT today
        yesterday_str = fields.Date.to_string(date.today() - timedelta(days=1))
        self.Param.set_param('ecommerce_product_custom_discounts.wishlist_special_day_date', yesterday_str)

        self.order._apply_best_discounts_to_lines()
        self.assertEqual(self.order.order_line[0].discount, 0.0)

        # Scenario 2: Configured date IS today
        today_str = fields.Date.to_string(date.today())
        self.Param.set_param('ecommerce_product_custom_discounts.wishlist_special_day_date', today_str)

        self.order._apply_best_discounts_to_lines()
        self.assertEqual(self.order.order_line[0].discount, 25.0)
        self.assertEqual(self.order.order_line[1].discount, 0.0)  # Service product not in wishlist

        # Scenario 3: Disabled flag
        self.Param.set_param('ecommerce_product_custom_discounts.wishlist_special_day_enabled', 'False')
        # Reset line discount
        self.order.order_line[0].write({'discount': 0.0})
        self.order._apply_best_discounts_to_lines()
        self.assertEqual(self.order.order_line[0].discount, 0.0)
