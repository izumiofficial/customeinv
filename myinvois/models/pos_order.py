from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning


class PosOrder(models.Model):
    _inherit = "pos.order"

    def consolidate_invoice(self):
        order_ids = self.filtered(lambda o:not o.account_move.myinvois_consolidate_id and not o.account_move.my_invois_uuid)
        no_customer_id = order_ids.filtered(lambda o:not o.partner_id)
        customer_id = self.env.company.my_invois_consolidated_partner_id
        no_customer_id.partner_id = customer_id.id

        order_ids.action_pos_order_invoice()
        invoice_ids = order_ids.account_move
        consolidate_obj = self.env['myinvois.consolidate']
        vals = {
            'myinvois_consolidate_user_id': self.env.user.partner_id.id,
            'invoice_ids': [(6, 0, invoice_ids.ids)],
            'myinvois_consolidate_date': fields.Datetime.now(),
        }
        if invoice_ids:
            consolidated_id = consolidate_obj.create(vals)
            consolidated_id.submit_consolidated()

        if not order_ids:
            raise ValidationError('Ops, it seems orders selected already cosolidated before.')