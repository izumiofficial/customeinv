from odoo import api, fields, models, _

class AllowanceCharge(models.Model):
    _name = "allowanace.charge"
    _description = "Allowance Charge"

    is_charge_indicator = fields.Boolean()
    allowance_charge_reason = fields.Text()
    charge_amount = fields.Float()
    my_invois_allowance_move_id = fields.Many2one('account.move')