# -*- coding: utf-8 -*-
import uuid
import hmac
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PaymentMonthDateChangeApproval(models.Model):
    _name = 'payment.month.date.change.approval'
    _description = 'Payment Month Date Change Approval'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True
    )
    payment_id = fields.Many2one(
        'account.payment',
        string='Payment',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True
    )
    payment_name = fields.Char(
        related='payment_id.name',
        string='Payment Reference',
        readonly=True
    )

    # Requested new dates
    payment_month_date_from = fields.Date(
        string='Requested From Date',
        required=True,
        tracking=True
    )
    payment_month_date_to = fields.Date(
        string='Requested To Date',
        required=True,
        tracking=True
    )

    # Original dates on payment at time of request
    requested_date_from = fields.Date(
        string='Original From Date',
        readonly=True,
        tracking=True
    )
    requested_date_to = fields.Date(
        string='Original To Date',
        readonly=True,
        tracking=True
    )

    reason = fields.Text(
        string='Reason for Change',
        required=True,
        tracking=True
    )

    requested_by = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        readonly=True,
        tracking=True
    )
    requested_on = fields.Datetime(
        string='Requested On',
        default=fields.Datetime.now,
        readonly=True,
        tracking=True
    )

    approver_id = fields.Many2one(
        'res.users',
        string='Configured Approver',
        tracking=True
    )

    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        tracking=True
    )
    approved_on = fields.Datetime(
        string='Approved On',
        readonly=True,
        tracking=True
    )

    rejected_by = fields.Many2one(
        'res.users',
        string='Rejected By',
        readonly=True,
        tracking=True
    )
    rejected_on = fields.Datetime(
        string='Rejected On',
        readonly=True,
        tracking=True
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        tracking=True
    )

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('pending', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True
    )

    # Internal secure token for one-time controlled date update
    _approval_token = fields.Char(copy=False)

    can_approve = fields.Boolean(
        string='Can Approve',
        compute='_compute_can_approve'
    )
    can_cancel = fields.Boolean(
        string='Can Cancel',
        compute='_compute_can_cancel'
    )

    def init(self):
        super().init()
        # Database-level partial unique index to guarantee only one active approval per payment
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS payment_month_date_change_approval_unique_active
            ON payment_month_date_change_approval (payment_id)
            WHERE state IN ('draft', 'pending');
        """)

    @api.depends('approver_id', 'state')
    def _compute_can_approve(self):
        is_admin = self.env.user.has_group('csspl_payment_date_approval.group_payment_date_change_admin') or self.env.is_admin()
        for rec in self:
            rec.can_approve = (rec.state == 'pending') and (is_admin or rec.approver_id == self.env.user)

    @api.depends('requested_by', 'state')
    def _compute_can_cancel(self):
        is_admin = self.env.user.has_group('csspl_payment_date_approval.group_payment_date_change_admin') or self.env.is_admin()
        for rec in self:
            rec.can_cancel = (rec.state in ('draft', 'pending')) and (is_admin or rec.requested_by == self.env.user)

    @api.constrains('payment_id', 'state')
    def _check_unique_active_approval(self):
        for rec in self:
            if rec.state in ('draft', 'pending'):
                dup = self.search([
                    ('payment_id', '=', rec.payment_id.id),
                    ('state', 'in', ('draft', 'pending')),
                    ('id', '!=', rec.id)
                ], limit=1)
                if dup:
                    raise ValidationError(_(
                        "An active Date Change Approval request (%s) already exists for payment '%s'. "
                        "You must cancel or resolve the existing request before creating a new one.",
                        dup.name, rec.payment_id.display_name
                    ))

    @api.constrains('payment_month_date_from', 'payment_month_date_to')
    def _check_requested_dates(self):
        for rec in self:
            if rec.payment_month_date_from and rec.payment_month_date_to:
                if rec.payment_month_date_to < rec.payment_month_date_from:
                    raise ValidationError(_("Requested End Date cannot be earlier than Requested Start Date."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('payment.month.date.change.approval') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        # Prevent editing dates or payment once terminal
        for rec in self:
            if rec.state in ('approved', 'rejected', 'cancelled'):
                forbidden_fields = {'payment_id', 'payment_month_date_from', 'payment_month_date_to', 'requested_date_from', 'requested_date_to', 'reason'}
                if any(k in vals for k in forbidden_fields):
                    raise UserError(_("Cannot modify request details once it has reached a terminal status (%s).", rec.state))
        return super().write(vals)

    def _generate_approval_token(self):
        self.ensure_one()
        token = uuid.uuid4().hex
        self.sudo().write({'_approval_token': token})
        return token

    def _verify_approval_token(self, token):
        self.ensure_one()
        if not token or not self._approval_token:
            return False
        valid = hmac.compare_digest(self._approval_token, token)
        if valid:
            self.sudo().write({'_approval_token': False})
        return valid

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only draft requests can be submitted."))
            if not rec.reason or not rec.reason.strip():
                raise ValidationError(_("A reason is mandatory for submitting a date change request."))
            if not rec.payment_month_date_from or not rec.payment_month_date_to:
                raise ValidationError(_("Both Requested From Date and Requested To Date must be provided."))
            if rec.payment_month_date_to < rec.payment_month_date_from:
                raise ValidationError(_("Requested End Date cannot be earlier than Requested Start Date."))

            if not rec.approver_id:
                approver_id_str = self.env['ir.config_parameter'].sudo().get_param('csspl_payment_date_approval.payment_month_date_approver_id')
                approver_id = int(approver_id_str) if approver_id_str and approver_id_str.isdigit() else False
                if not approver_id:
                    raise UserError(_("Payment Month Date Approver is not configured in Settings. Please contact an Administrator."))
                rec.approver_id = approver_id

            rec.write({
                'state': 'pending',
                'requested_on': fields.Datetime.now(),
            })

            rec.message_post(body=_("Date Change Request submitted to %s for approval.", rec.approver_id.name))
            rec.payment_id.message_post(body=_(
                "Date Change Approval Request <a href='#' data-oe-model='payment.month.date.change.approval' data-oe-id='%s'>%s</a> "
                "submitted by %s (Requested Dates: %s to %s).",
                rec.id, rec.name, rec.requested_by.name, rec.payment_month_date_from, rec.payment_month_date_to
            ))
        return True

    def action_approve(self):
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_("Only pending requests can be approved."))

            is_approver = (self.env.user == rec.approver_id)
            is_admin = self.env.user.has_group('csspl_payment_date_approval.group_payment_date_change_admin') or self.env.is_admin()
            if not (is_approver or is_admin):
                raise UserError(_("Only the assigned approver (%s) or an administrator can approve this request.", rec.approver_id.name))

            # Apply the dates securely onto the payment
            rec.payment_id._apply_approved_payment_month_dates(rec)

            rec.write({
                'approved_by': self.env.user.id,
                'approved_on': fields.Datetime.now(),
                'state': 'approved',
            })

            rec.message_post(body=_("Request approved by %s.", self.env.user.name))
            rec.payment_id.message_post(body=_(
                "<p><strong>Payment Month Dates Updated via Approval %s</strong></p>"
                "<ul>"
                "<li><strong>Original Dates:</strong> %s to %s</li>"
                "<li><strong>New Dates:</strong> %s to %s</li>"
                "<li><strong>Reason:</strong> %s</li>"
                "<li><strong>Requested By:</strong> %s (%s)</li>"
                "<li><strong>Approved By:</strong> %s (%s)</li>"
                "</ul>",
                rec.name,
                rec.requested_date_from, rec.requested_date_to,
                rec.payment_month_date_from, rec.payment_month_date_to,
                rec.reason,
                rec.requested_by.name, fields.Datetime.to_string(rec.requested_on),
                rec.approved_by.name, fields.Datetime.to_string(rec.approved_on)
            ))
        return True

    def action_open_reject_wizard(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("Only pending requests can be rejected."))
        is_approver = (self.env.user == self.approver_id)
        is_admin = self.env.user.has_group('csspl_payment_date_approval.group_payment_date_change_admin') or self.env.is_admin()
        if not (is_approver or is_admin):
            raise UserError(_("Only the assigned approver (%s) or an administrator can reject this request.", self.approver_id.name))

        return {
            'name': _("Reject Date Change Request"),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.date.change.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_approval_id': self.id,
            }
        }

    def action_reject(self, rejection_reason):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("Only pending requests can be rejected."))
        is_approver = (self.env.user == self.approver_id)
        is_admin = self.env.user.has_group('csspl_payment_date_approval.group_payment_date_change_admin') or self.env.is_admin()
        if not (is_approver or is_admin):
            raise UserError(_("Only the assigned approver (%s) or an administrator can reject this request.", self.approver_id.name))
        if not rejection_reason or not rejection_reason.strip():
            raise ValidationError(_("A rejection reason is mandatory."))

        self.write({
            'rejected_by': self.env.user.id,
            'rejected_on': fields.Datetime.now(),
            'rejection_reason': rejection_reason.strip(),
            'state': 'rejected',
        })

        self.message_post(body=_("Request rejected by %s. Reason: %s", self.env.user.name, rejection_reason))
        self.payment_id.message_post(body=_(
            "Date Change Approval Request %s was rejected by %s. Reason: %s",
            self.name, self.env.user.name, rejection_reason
        ))
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('draft', 'pending'):
                raise UserError(_("Only draft or pending requests can be cancelled."))

            is_creator = (self.env.user == rec.requested_by)
            is_admin = self.env.user.has_group('csspl_payment_date_approval.group_payment_date_change_admin') or self.env.is_admin()
            if not (is_creator or is_admin):
                raise UserError(_("Only the requester (%s) or an administrator can cancel this request.", rec.requested_by.name))

            rec.write({
                'state': 'cancelled',
            })

            rec.message_post(body=_("Request cancelled by %s.", self.env.user.name))
            rec.payment_id.message_post(body=_(
                "Date Change Approval Request %s was cancelled by %s.",
                rec.name, self.env.user.name
            ))
        return True
