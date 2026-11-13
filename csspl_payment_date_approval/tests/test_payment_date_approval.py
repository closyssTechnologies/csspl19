# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError, UserError


@tagged('post_install', '-at_install')
class TestPaymentMonthDateApproval(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_group = cls.env.ref('csspl_payment_date_approval.group_payment_date_change_user')
        cls.approver_group = cls.env.ref('csspl_payment_date_approval.group_payment_date_change_approver')
        cls.admin_group = cls.env.ref('csspl_payment_date_approval.group_payment_date_change_admin')

        # Create test users
        cls.test_user = cls.env['res.users'].create({
            'name': 'Test Payment User',
            'login': 'test_payment_user',
            'email': 'user@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.user_group.id])],
        })

        cls.approver_user = cls.env['res.users'].create({
            'name': 'Test Approver User',
            'login': 'test_approver_user',
            'email': 'approver@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.approver_group.id])],
        })

        cls.approver_user2 = cls.env['res.users'].create({
            'name': 'Test Secondary Approver',
            'login': 'test_approver2_user',
            'email': 'approver2@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.approver_group.id])],
        })

        cls.unauthorized_user = cls.env['res.users'].create({
            'name': 'Unauthorized User',
            'login': 'unauthorized_user',
            'email': 'unauth@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

        # Configure default approver in ir.config_parameter
        cls.env['ir.config_parameter'].sudo().set_param(
            'csspl_payment_date_approval.payment_month_date_approver_id',
            cls.approver_user.id
        )

        # Partner and Journal for test payments
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Vendor Partner',
            'cust_partner_type': 'vendor',
        })

        cls.bank_journal = cls.env['account.journal'].search([('type', '=', 'bank')], limit=1)
        if not cls.bank_journal:
            cls.bank_journal = cls.env['account.journal'].create({
                'name': 'Test Bank Journal',
                'type': 'bank',
                'code': 'TBANK',
            })

        cls.payment_method_line = cls.bank_journal.outbound_payment_method_line_ids[:1]

        # Classification if required
        cls.classification = cls.env['expense.classification'].search([], limit=1)
        if not cls.classification:
            cls.classification = cls.env['expense.classification'].create({
                'name': 'Internal',
            })

    def _create_test_payment(self, date_from=None, date_to=None):
        vals = {
            'partner_id': self.partner.id,
            'partner_type': 'supplier',
            'payment_type': 'outbound',
            'amount': 1500.0,
            'journal_id': self.bank_journal.id,
            'payment_method_line_id': self.payment_method_line.id if self.payment_method_line else False,
            'classification_id': self.classification.id,
            'payment_month_date_from': date_from or date(2026, 10, 1),
            'payment_month_date_to': date_to or date(2026, 10, 31),
        }
        return self.env['account.payment'].create(vals)

    def test_01_create_payment_with_dates_allowed(self):
        """Scenario: Create payment with both dates -> Allowed."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(payment.payment_month_date_from, date(2026, 10, 1))
        self.assertEqual(payment.payment_month_date_to, date(2026, 10, 31))
        self.assertTrue(payment.is_payment_month_date_locked)

    def test_02_edit_dates_after_creation_blocked(self):
        """Scenario: Direct ORM / API / Import modification of dates is blocked."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))

        # Attempt to change From date directly
        with self.assertRaises(ValidationError):
            payment.write({'payment_month_date_from': date(2026, 11, 1)})

        # Attempt to change To date directly
        with self.assertRaises(ValidationError):
            payment.write({'payment_month_date_to': date(2026, 11, 30)})

        # Attempt to change both dates directly
        with self.assertRaises(ValidationError):
            payment.write({
                'payment_month_date_from': date(2026, 11, 1),
                'payment_month_date_to': date(2026, 11, 30),
            })

    def test_03_clear_dates_blocked(self):
        """Scenario: Clearing either date to False/None is blocked."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))

        with self.assertRaises(ValidationError):
            payment.write({'payment_month_date_from': False})

        with self.assertRaises(ValidationError):
            payment.write({'payment_month_date_to': False})

    def test_04_update_unrelated_fields_allowed(self):
        """Scenario: Modifying unrelated payment fields is allowed normally."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))
        payment.write({'memo': 'Updated Memo Reference'})
        self.assertEqual(payment.memo, 'Updated Memo Reference')

    def test_05_reimport_same_dates_allowed(self):
        """Scenario: Export and re-import with unchanged dates is allowed."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))
        # Re-writing identical dates does not raise ValidationError
        payment.write({
            'payment_month_date_from': date(2026, 10, 1),
            'payment_month_date_to': date(2026, 10, 31),
        })
        self.assertEqual(payment.payment_month_date_from, date(2026, 10, 1))

    def test_06_single_active_approval_constraint(self):
        """Scenario: Only one active approval request allowed per payment."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))

        # First request created
        req1 = self.env['payment.month.date.change.approval'].create({
            'payment_id': payment.id,
            'requested_date_from': payment.payment_month_date_from,
            'requested_date_to': payment.payment_month_date_to,
            'payment_month_date_from': date(2026, 11, 1),
            'payment_month_date_to': date(2026, 11, 30),
            'reason': 'First change request',
            'approver_id': self.approver_user.id,
            'state': 'pending',
        })
        self.assertTrue(req1.name)
        self.assertTrue(payment.has_active_date_change_approval)

        # Attempt to create a second pending request for the same payment -> Blocked
        with self.assertRaises(ValidationError):
            self.env['payment.month.date.change.approval'].create({
                'payment_id': payment.id,
                'requested_date_from': payment.payment_month_date_from,
                'requested_date_to': payment.payment_month_date_to,
                'payment_month_date_from': date(2026, 12, 1),
                'payment_month_date_to': date(2026, 12, 31),
                'reason': 'Second duplicate request',
                'approver_id': self.approver_user.id,
                'state': 'draft',
            })

    def test_07_submit_without_reason_blocked(self):
        """Scenario: Submitting request without a reason is blocked."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))
        req = self.env['payment.month.date.change.approval'].create({
            'payment_id': payment.id,
            'requested_date_from': payment.payment_month_date_from,
            'requested_date_to': payment.payment_month_date_to,
            'payment_month_date_from': date(2026, 11, 1),
            'payment_month_date_to': date(2026, 11, 30),
            'reason': 'Temp',
            'approver_id': self.approver_user.id,
            'state': 'draft',
        })
        req.reason = ''
        with self.assertRaises(ValidationError):
            req.action_submit()

    def test_08_cancel_and_recreate_allowed(self):
        """Scenario: Cancellation by requester allows new request while preserving history."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))

        req1 = self.env['payment.month.date.change.approval'].with_user(self.test_user).create({
            'payment_id': payment.id,
            'requested_date_from': payment.payment_month_date_from,
            'requested_date_to': payment.payment_month_date_to,
            'payment_month_date_from': date(2026, 11, 1),
            'payment_month_date_to': date(2026, 11, 30),
            'reason': 'Change needed',
            'approver_id': self.approver_user.id,
            'state': 'pending',
        })

        # Cancel request
        req1.with_user(self.test_user).action_cancel()
        self.assertEqual(req1.state, 'cancelled')
        self.assertFalse(payment.has_active_date_change_approval)

        # New request can now be created
        req2 = self.env['payment.month.date.change.approval'].with_user(self.test_user).create({
            'payment_id': payment.id,
            'requested_date_from': payment.payment_month_date_from,
            'requested_date_to': payment.payment_month_date_to,
            'payment_month_date_from': date(2026, 12, 1),
            'payment_month_date_to': date(2026, 12, 31),
            'reason': 'New revised request',
            'approver_id': self.approver_user.id,
            'state': 'pending',
        })
        self.assertTrue(req2.id)
        self.assertNotEqual(req1.name, req2.name)
        # History is preserved
        self.assertEqual(len(payment.date_change_approval_ids), 2)

    def test_09_unauthorized_user_approval_blocked(self):
        """Scenario: User other than the configured approver cannot approve."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))

        req = self.env['payment.month.date.change.approval'].create({
            'payment_id': payment.id,
            'requested_date_from': payment.payment_month_date_from,
            'requested_date_to': payment.payment_month_date_to,
            'payment_month_date_from': date(2026, 11, 1),
            'payment_month_date_to': date(2026, 11, 30),
            'reason': 'Adjustment',
            'approver_id': self.approver_user.id,
            'state': 'pending',
        })

        # Unauthorized user tries to approve -> Blocked
        with self.assertRaises(UserError):
            req.with_user(self.unauthorized_user).action_approve()

    def test_10_approver_approves_and_dates_updated(self):
        """Scenario: Configured approver approves -> Dates updated securely."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))

        req = self.env['payment.month.date.change.approval'].create({
            'payment_id': payment.id,
            'requested_date_from': payment.payment_month_date_from,
            'requested_date_to': payment.payment_month_date_to,
            'payment_month_date_from': date(2026, 11, 1),
            'payment_month_date_to': date(2026, 11, 30),
            'reason': 'Vendor revised billing period',
            'approver_id': self.approver_user.id,
            'state': 'pending',
        })

        # Approver approves
        req.with_user(self.approver_user).action_approve()
        self.assertEqual(req.state, 'approved')
        self.assertEqual(req.approved_by, self.approver_user)
        self.assertTrue(req.approved_on)

        # Payment dates updated
        self.assertEqual(payment.payment_month_date_from, date(2026, 11, 1))
        self.assertEqual(payment.payment_month_date_to, date(2026, 11, 30))

        # Attempt direct modification after approval -> Still blocked
        with self.assertRaises(ValidationError):
            payment.write({'payment_month_date_from': date(2026, 12, 1)})

    def test_11_reject_workflow(self):
        """Scenario: Approver rejects request -> Dates remain unchanged."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))

        req = self.env['payment.month.date.change.approval'].create({
            'payment_id': payment.id,
            'requested_date_from': payment.payment_month_date_from,
            'requested_date_to': payment.payment_month_date_to,
            'payment_month_date_from': date(2026, 11, 1),
            'payment_month_date_to': date(2026, 11, 30),
            'reason': 'Incorrect period entered',
            'approver_id': self.approver_user.id,
            'state': 'pending',
        })

        # Reject
        req.with_user(self.approver_user).action_reject('Audit period closed; rejection required.')
        self.assertEqual(req.state, 'rejected')
        self.assertEqual(req.rejected_by, self.approver_user)
        self.assertEqual(req.rejection_reason, 'Audit period closed; rejection required.')

        # Dates remain original
        self.assertEqual(payment.payment_month_date_from, date(2026, 10, 1))
        self.assertEqual(payment.payment_month_date_to, date(2026, 10, 31))

    def test_12_dynamic_approver_configuration(self):
        """Scenario: Changing approver in settings affects newly created requests while retaining pending ones."""
        payment = self._create_test_payment(date(2026, 10, 1), date(2026, 10, 31))

        # Request 1 gets approver 1
        req1 = self.env['payment.month.date.change.approval'].create({
            'payment_id': payment.id,
            'requested_date_from': payment.payment_month_date_from,
            'requested_date_to': payment.payment_month_date_to,
            'payment_month_date_from': date(2026, 11, 1),
            'payment_month_date_to': date(2026, 11, 30),
            'reason': 'Adjustment',
            'approver_id': self.approver_user.id,
            'state': 'pending',
        })
        self.assertEqual(req1.approver_id, self.approver_user)

        # Change approver in settings
        self.env['ir.config_parameter'].sudo().set_param(
            'csspl_payment_date_approval.payment_month_date_approver_id',
            self.approver_user2.id
        )

        # Cancel req1 to test creation of req2
        req1.action_cancel()

        # Wizard creates req2: it must fetch the newly configured approver
        wizard = self.env['payment.date.change.wizard'].create({
            'payment_id': payment.id,
            'current_date_from': payment.payment_month_date_from,
            'current_date_to': payment.payment_month_date_to,
            'new_date_from': date(2026, 11, 1),
            'new_date_to': date(2026, 11, 30),
            'reason': 'Re-submitting with new approver',
        })
        wizard.action_submit()

        req2 = self.env['payment.month.date.change.approval'].search([
            ('payment_id', '=', payment.id),
            ('state', '=', 'pending')
        ], limit=1)
        self.assertEqual(req2.approver_id, self.approver_user2)
        # req1 retained its original approver
        self.assertEqual(req1.approver_id, self.approver_user)
