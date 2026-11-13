# -*- coding: utf-8 -*-
{
    'name': 'CSSPL Payment Date Locking & Approval Workflow',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Lock payment month dates and require dynamic approval workflow for changes',
    'description': """
Odoo 19 – Payment Month Date Locking with Dynamic Approval Workflow
===================================================================
* Locks payment_month_date_from and payment_month_date_to once set on account.payment.
* Prevents modification via Form, Tree, Import/Export, RPC, and backend write().
* Dynamic approver configured via Settings -> Invoicing -> Payment Month Date Approval.
* Approval workflow (Draft, Pending Approval, Approved, Rejected, Cancelled).
* Wizard for requesting date changes with mandatory reason.
* Reject wizard with mandatory rejection reason.
* Enforces exactly one active approval request per payment record via PostgreSQL partial unique index.
* Full audit trail and chatter logging.
    """,
    'author': 'CSSPL',
    'depends': [
        'base',
        'account',
        'csspl_project',
    ],
    'data': [
        'security/payment_date_approval_security.xml',
        'security/ir.model.access.csv',
        'data/payment_date_approval_sequence.xml',
        'views/account_payment_views.xml',
        'views/payment_date_approval_views.xml',
        'views/res_config_settings_views.xml',
        'wizards/payment_date_change_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
