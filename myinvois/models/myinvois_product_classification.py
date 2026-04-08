from odoo import api, fields, models, _

class MyinvoisClassificationCode(models.Model):
    _name = "myinvois.product.classification"
    _description = "Classification Code"

    code = fields.Char(string="Code",required=True)
    name = fields.Char(string="Description",required=True)
