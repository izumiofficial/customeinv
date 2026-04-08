from odoo import api, fields, models

class ResPartnerIndustry(models.Model):
    _inherit = "res.partner.industry"

    code = fields.Char(string="Code")
    misc_category_reference = fields.Char(string="MSIC Category Reference")