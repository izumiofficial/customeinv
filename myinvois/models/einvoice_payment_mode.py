from odoo import _, fields, models


class EinvoicePaymentMode(models.Model):
    _name = "einvoice.payment.mode"

    code = fields.Char(string="Code")
    name = fields.Char(string="Name", required=True)
    payee_financial_account = fields.Char(string="Bank Account Number")
