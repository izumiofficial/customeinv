from odoo import api, fields, models, _

class AccountTaxGroup(models.Model):
    _inherit = "account.tax.group"

    tax_type_id = fields.Many2one("tax.type", string="MyInvois Tax Type")
    
    
class AccountTax(models.Model):
    _inherit = "account.tax"

    tax_type_id = fields.Many2one("tax.type", string="MyInvois Tax Type")