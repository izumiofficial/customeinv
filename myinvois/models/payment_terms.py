from odoo import _, fields, models


class PaymentTerms(models.Model):
    _name = "payment.terms"

    note = fields.Char(string="Note")
