# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payment_month_date_approver_id = fields.Many2one(
        'res.users',
        string='Payment Month Date Approver',
        config_parameter='csspl_payment_date_approval.payment_month_date_approver_id',
        help='User responsible for approving changes to Payment Month Dates.'
    )
