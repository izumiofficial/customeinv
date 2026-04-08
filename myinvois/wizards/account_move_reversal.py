# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def _prepare_default_reversal(self, move):
        # check for credit note or refund note
        # refund note is when the original invoice already paid (payment_state == 'in_payment')
        
        values = super()._prepare_default_reversal(move)
        if move.move_type == 'out_invoice':
            if move.payment_state in ('in_payment', 'paid', 'partial'):
                move_type = 'out_refund_paid'
            else:
                move_type = 'out_refund'
            
            myinvois_type = self.env["myinvois.einvoice.type"].search([("my_invois_einvoice_type", "=", move_type)] ,limit=1)
            values.update({
                'my_invois_einvoice_type_id': myinvois_type.id
            })

        elif move.move_type == 'in_invoice':
            if move.payment_state in ('in_payment', 'paid', 'partial'):
                move_type = 'in_refund_paid'
            else:
                move_type = 'in_refund'
            
            myinvois_type = self.env["myinvois.einvoice.type"].search([("my_invois_einvoice_type", "=", move_type)] ,limit=1)
            values.update({
                'my_invois_einvoice_type_id': myinvois_type.id
            })

        return values
