# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class Uom(models.Model):

    _inherit = 'uom.uom'

    myinvois_code = fields.Char('MyInvois Code', help='This code will be used on MyInvois.')
