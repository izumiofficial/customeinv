# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api


class AccountDebitNote(models.TransientModel):
    _inherit = 'account.debit.note'

    def _prepare_default_values(self, move):
        values = super()._prepare_default_values(move)
        move_type = False
        if move.move_type == 'out_invoice':
            move_type = 'out_invoice_debit'
            
        elif move.move_type == 'in_invoice':
            move_type = 'in_invoice_debit'
        
        if move_type:
            myinvois_type = self.env["myinvois.einvoice.type"].search([("my_invois_einvoice_type", "=", move_type)] ,limit=1)
            values.update({
                'my_invois_einvoice_type_id': myinvois_type.id
            })
        
        return values