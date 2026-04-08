from odoo import _, fields, models


class PrepaidPayment(models.Model):
    _name = "prepaid.payment"

    paid_date = fields.Datetime(string="Paid Date")
    paid_amount = fields.Float(string="Paid Amount")
