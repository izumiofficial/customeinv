from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class TaxType(models.Model):
    _name = "tax.type"

    code = fields.Char(string="Code")
    name = fields.Char(string="Description")
