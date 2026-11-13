# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PaymentDateChangeWizard(models.TransientModel):
    _name = 'payment.date.change.wizard'
    _description = 'Payment Date Change Request Wizard'

    payment_id = fields.Many2one(
        'account.payment',
        string='Payment',
        required=True,
        readonly=True
    )
    current_date_from = fields.Date(
        string='Current From Date',
        readonly=True
    )
    current_date_to = fields.Date(
        string='Current To Date',
        readonly=True
    )
    new_date_from = fields.Date(
        string='Proposed From Date',
        required=True
    )
    new_date_to = fields.Date(
        string='Proposed To Date',
        required=True
    )
    reason = fields.Text(
        string='Reason for Change',
        required=True
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Configured Approver',
        readonly=True
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('default_payment_id') or self.env.context.get('active_id')
        if active_id:
            payment = self.env['account.payment'].browse(active_id)
            if payment.exists():
                res.update({
                    'payment_id': payment.id,
                    'current_date_from': payment.payment_month_date_from,
                    'current_date_to': payment.payment_month_date_to,
                    'new_date_from': res.get('new_date_from') or payment.payment_month_date_from,
                    'new_date_to': res.get('new_date_to') or payment.payment_month_date_to,
                })

        if not res.get('approver_id'):
            approver_id_str = self.env['ir.config_parameter'].sudo().get_param('csspl_payment_date_approval.payment_month_date_approver_id')
            if approver_id_str and approver_id_str.isdigit():
                res['approver_id'] = int(approver_id_str)
        return res

    def action_submit(self):
        self.ensure_one()
        payment = self.payment_id
        if not payment:
            raise UserError(_("No payment record specified."))

        if not self.reason or not self.reason.strip():
            raise ValidationError(_("A reason is mandatory for submitting a date change request."))

        if not self.new_date_from or not self.new_date_to:
            raise ValidationError(_("Both Proposed From Date and Proposed To Date must be provided."))

        if self.new_date_to < self.new_date_from:
            raise ValidationError(_("Proposed End Date cannot be earlier than Proposed Start Date."))

        if self.new_date_from == self.current_date_from and self.new_date_to == self.current_date_to:
            raise ValidationError(_("The proposed dates are identical to the current dates. Please enter new dates."))

        # Check approver
        approver = self.approver_id
        if not approver:
            approver_id_str = self.env['ir.config_parameter'].sudo().get_param('csspl_payment_date_approval.payment_month_date_approver_id')
            if approver_id_str and approver_id_str.isdigit():
                approver = self.env['res.users'].browse(int(approver_id_str))
            if not approver or not approver.exists():
                raise UserError(_("Payment Month Date Approver is not configured in Settings. Please contact an Administrator."))

        # Check existing active request
        existing_active = self.env['payment.month.date.change.approval'].search([
            ('payment_id', '=', payment.id),
            ('state', 'in', ('draft', 'pending'))
        ], limit=1)
        if existing_active:
            raise ValidationError(_(
                "An active Date Change Approval request (%s) is already pending for payment '%s'. "
                "Only one active request is allowed at a time. Please cancel or resolve the existing request first.",
                existing_active.name, payment.display_name
            ))

        # Create approval request in pending state
        approval_vals = {
            'payment_id': payment.id,
            'requested_date_from': payment.payment_month_date_from,
            'requested_date_to': payment.payment_month_date_to,
            'payment_month_date_from': self.new_date_from,
            'payment_month_date_to': self.new_date_to,
            'reason': self.reason.strip(),
            'requested_by': self.env.user.id,
            'requested_on': fields.Datetime.now(),
            'approver_id': approver.id,
            'state': 'pending',
        }
        approval = self.env['payment.month.date.change.approval'].create(approval_vals)

        # Log chatter on payment
        payment.message_post(body=_(
            "<strong>Date Change Approval Request Submitted</strong><br/>"
            "Request Reference: <b>%s</b><br/>"
            "Current Dates: %s to %s<br/>"
            "Proposed Dates: %s to %s<br/>"
            "Reason: %s<br/>"
            "Submitted By: %s<br/>"
            "Assigned Approver: %s",
            approval.name,
            payment.payment_month_date_from, payment.payment_month_date_to,
            self.new_date_from, self.new_date_to,
            self.reason,
            self.env.user.name,
            approver.name
        ))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Request Submitted"),
                'message': _("Date change approval request '%s' has been submitted to %s.", approval.name, approver.name),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


class PaymentDateChangeRejectWizard(models.TransientModel):
    _name = 'payment.date.change.reject.wizard'
    _description = 'Payment Date Change Reject Wizard'

    approval_id = fields.Many2one(
        'payment.month.date.change.approval',
        string='Approval Request',
        required=True,
        readonly=True
    )
    reason = fields.Text(
        string='Rejection Reason',
        required=True
    )

    def action_confirm_reject(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise ValidationError(_("A rejection reason is mandatory."))
        self.approval_id.action_reject(self.reason.strip())
        return {'type': 'ir.actions.act_window_close'}
