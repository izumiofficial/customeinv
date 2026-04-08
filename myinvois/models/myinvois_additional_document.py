from odoo import _, fields, models


class MyinvoisAdditionalDocument(models.Model):
    _name = "myinvois.additional.document"

    name = fields.Char(string="ID")
    document_type = fields.Char(required=True)
    my_invois_additonal_move_id = fields.Many2one('account.move')
    # MANY@ONE KE e-Invoice Type Code
    # document_description = fields.Many2one()
