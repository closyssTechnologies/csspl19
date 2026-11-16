# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    date_change_approval_ids = fields.One2many(
        comodel_name='payment.month.date.change.approval',
        inverse_name='payment_id',
        string='Date Change Approvals'
    )
    date_change_approval_count = fields.Integer(
        string='Date Change Approvals Count',
        compute='_compute_date_change_approval_count'
    )
    has_active_date_change_approval = fields.Boolean(
        string='Has Active Approval',
        compute='_compute_active_date_change_approval'
    )
    is_payment_month_date_locked = fields.Boolean(
        string='Date Locked',
        compute='_compute_is_payment_month_date_locked'
    )

    @api.depends('date_change_approval_ids')
    def _compute_date_change_approval_count(self):
        for rec in self:
            rec.date_change_approval_count = len(rec.date_change_approval_ids)

    @api.depends('date_change_approval_ids.state')
    def _compute_active_date_change_approval(self):
        for rec in self:
            rec.has_active_date_change_approval = any(
                a.state in ('draft', 'pending') for a in rec.date_change_approval_ids
            )

    @api.depends('payment_month_date_from', 'payment_month_date_to')
    def _compute_is_payment_month_date_locked(self):
        for rec in self:
            rec.is_payment_month_date_locked = bool(
                rec.id and isinstance(rec.id, int) and (rec.payment_month_date_from or rec.payment_month_date_to)
            )

    @api.model_create_multi
    def create(self, vals_list):
        return super(AccountPayment, self.with_context(bypass_payment_date_lock=True)).create(vals_list)

    def write(self, vals):
        check_from = 'payment_month_date_from' in vals
        check_to = 'payment_month_date_to' in vals

        if check_from or check_to:
            is_authorized = bool(self.env.context.get('bypass_payment_date_lock'))
            if not is_authorized:
                approval_id = self.env.context.get('_authorized_date_approval_id')
                token = self.env.context.get('_authorized_date_approval_token')
                if approval_id:
                    approval = self.env['payment.month.date.change.approval'].sudo().browse(approval_id)
                    if approval.exists() and approval.payment_id in self and approval.state == 'pending':
                        if token and approval._verify_approval_token(token):
                            is_authorized = True
                        elif self.env.user == approval.approver_id or self.env.user.has_group('csspl_payment_date_approval.group_payment_date_change_admin') or self.env.is_admin():
                            is_authorized = True

            if not is_authorized:
                for payment in self:
                    if check_from and payment.payment_month_date_from:
                        new_from = fields.Date.to_date(vals.get('payment_month_date_from'))
                        if new_from != payment.payment_month_date_from:
                            raise ValidationError(_(
                                "Payment Month Date From (%s) on payment '%s' is locked and cannot be directly modified or cleared. "
                                "Please click 'Request Date Change' to submit an approval request.",
                                payment.payment_month_date_from, payment.name or payment.id
                            ))
                    if check_to and payment.payment_month_date_to:
                        new_to = fields.Date.to_date(vals.get('payment_month_date_to'))
                        if new_to != payment.payment_month_date_to:
                            raise ValidationError(_(
                                "Payment Month Date To (%s) on payment '%s' is locked and cannot be directly modified or cleared. "
                                "Please click 'Request Date Change' to submit an approval request.",
                                payment.payment_month_date_to, payment.name or payment.id
                            ))

        return super().write(vals)

    def _apply_approved_payment_month_dates(self, approval):
        self.ensure_one()
        if approval.payment_id != self:
            raise UserError(_("Approval request does not belong to this payment."))
        if approval.state != 'pending':
            raise UserError(_("Approval request is not in pending state."))

        is_approver = (self.env.user == approval.approver_id)
        is_admin = self.env.user.has_group('csspl_payment_date_approval.group_payment_date_change_admin') or self.env.is_admin()
        if not (is_approver or is_admin):
            raise UserError(_("Only the assigned approver (%s) or an administrator can approve this request.", approval.approver_id.name))

        if self.payment_month_date_from != approval.requested_date_from or self.payment_month_date_to != approval.requested_date_to:
            raise UserError(_("The payment's dates have changed since this request was created."))

        token = approval._generate_approval_token()
        self.with_context(
            bypass_payment_date_lock=True,
            _authorized_date_approval_id=approval.id,
            _authorized_date_approval_token=token,
        ).write({
            'payment_month_date_from': approval.payment_month_date_from,
            'payment_month_date_to': approval.payment_month_date_to,
        })

    def action_request_date_change(self):
        self.ensure_one()
        if self.has_active_date_change_approval:
            active_approval = self.date_change_approval_ids.filtered(lambda a: a.state in ('draft', 'pending'))[:1]
            raise ValidationError(_(
                "An active Date Change Approval request (%s) is already pending for this payment. "
                "Only one active request is allowed at a time. Please wait for it to be processed or cancel it.",
                active_approval.name if active_approval else ''
            ))

        return {
            'name': _('Request Payment Month Date Change'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.date.change.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payment_id': self.id,
                'default_current_date_from': self.payment_month_date_from,
                'default_current_date_to': self.payment_month_date_to,
                'default_new_date_from': self.payment_month_date_from,
                'default_new_date_to': self.payment_month_date_to,
            }
        }

    def action_view_date_change_approvals(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('csspl_payment_date_approval.action_payment_month_date_change_approval')
        action['domain'] = [('payment_id', '=', self.id)]
        action['context'] = {'default_payment_id': self.id}
        if self.date_change_approval_count == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.date_change_approval_ids[0].id
        return action
