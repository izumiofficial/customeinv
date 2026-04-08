from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import timedelta, datetime
import logging
import json

_logger = logging.getLogger(__name__)


class ConsolidatedMyinvoisWizard(models.TransientModel):
    _name = 'consolidate.myinvois.wizard'
    _description = "Consolidate Invoice Popup"

    myinvois_consolidate_date = fields.Date(string="Consolidate Date", default=fields.Date.today())
    my_invois_period_id = fields.Many2one('myinvois.period', string="MyInvois Period")
    myinvois_invoice_wrong_ids = fields.Many2many('account.move', 'condolidate_wrong_id', string="Already Consolidated / Submitted / not Confirmed")
    invoice_ids = fields.Many2many('account.move', string="Invoice List")

    @api.model
    def default_get(self, fields):
        """ Get the selected invoice records """
        values = super(ConsolidatedMyinvoisWizard, self).default_get(fields)
        
        # Fetch invoice ids from context
        active_ids = self._context.get('active_ids', [])
        
        # Search for all invoices with the active ids
        invoices = self.env['account.move'].sudo().search([('id', 'in', active_ids)])

        only_invoices_ids =  invoices.filtered(lambda inv: inv.move_type == 'out_invoice')
        if not only_invoices_ids:
            raise UserError(_("Only customer invoices can be consolidated"))
        
        # Separate consolidated need to warning
        invoice_ids_consolidated = invoices.filtered(lambda inv: inv.myinvois_consolidate_id or inv.my_invois_uuid or inv.state != 'posted')
        #this 1 is for apply in invoice_ids
        invoice_ids = invoices.filtered(lambda inv: not inv.myinvois_consolidate_id and not inv.my_invois_uuid and inv.state == 'posted')
        
        # # Raise error if any consolidated invoices are found
        if not invoice_ids:
            raise UserError(_("Selected invoice(s) have been consolidated / submitted / not yet confirmed"))
        
        # Update values with non-consolidated invoice ids
        values.update({'invoice_ids': [(6, 0, invoice_ids.ids)],
                       'myinvois_invoice_wrong_ids': [(6, 0, invoice_ids_consolidated.ids)]})
        
        return values

    def consolidate_invoice(self):
        consolidate_obj = self.env['myinvois.consolidate']
        # redundant checking, as self.invoice_ids already filtered on default_get
        # invoice_ids = self.invoice_ids.filtered(lambda x:not x.myinvois_consolidate_id and not x.my_invois_uuid)
        # if not invoice_ids:
        #     raise UserError(_("Ops, it seems invoices selected already consolidated before."))

        invoice_ids = self.invoice_ids
        consolidated_ids = []


        # create multiple batch of consolidated invoice per N
        n = self.env['ir.config_parameter'].sudo().get_param('myinvois.split_consolidated')
        if not n:
            self.env['ir.config_parameter'].sudo().set_param('myinvois.split_consolidated', 100)
        
        # calling get_params again for centralized handling the value
        n = self.env['ir.config_parameter'].sudo().get_param('myinvois.split_consolidated')

        # split consolidation per company (multi company case)
        grouped_invoices = {}
        batch_size = int(n)
        for invoice in invoice_ids:
            if invoice.company_id not in grouped_invoices:
                grouped_invoices[invoice.company_id] = self.env['account.move']
            grouped_invoices[invoice.company_id] += invoice

        for company_id, company_invoices in grouped_invoices.items():
            for start in range(0, len(company_invoices), batch_size):
                end = start + batch_size
                batch = company_invoices[start:end]
                vals = {
                    'my_invois_period_id': self.my_invois_period_id.id,
                    'myinvois_consolidate_user_id': self.env.user.partner_id.id,
                    'invoice_ids': [(6, 0, batch.ids)],
                    'myinvois_consolidate_date': self.myinvois_consolidate_date,
                    'myinvois_consolidate_state': 'Draft',
                }
                consolidate_id = consolidate_obj.create(vals)
                consolidated_ids.append(consolidate_id.id)
                consolidate_id.submit_consolidated()
            

        return {
            'type': 'ir.actions.act_window',
            'name': _("Consolidated Invoice"),
            'domain': [('id', 'in', consolidated_ids)],
            'res_model': 'myinvois.consolidate',
            'view_mode': 'tree,form',
            # 'context': "{'move_type':'in_invoice'}",
        }