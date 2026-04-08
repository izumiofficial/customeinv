from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import timedelta, datetime
import logging
import json

_logger = logging.getLogger(__name__)


class CheckDocument(models.TransientModel):
    _name = 'check.document.wizard'
    _description = "Check Document wizard"

    invoice_ids = fields.Many2many('account.move', string="Invoice List")
    myinvois_consolidate_ids = fields.Many2many('myinvois.consolidate', string="Consolidate List")
    text_information_success = fields.Text(string="Document Can be Cancel")
    text_information_fail = fields.Text(string="Document Can Not Be Cancelled")

    @api.model
    def default_get(self, fields):
        """ Get the selected invoice records """
        values = super(CheckDocument, self).default_get(fields)
        # invoice_ids = self.env['account.move'].sudo().search([
        #     ('id', 'in', self._context.get('active_ids')), ('my_invois_uuid', '!=', False)])
        # if not invoice_ids:
        #     raise UserError(_("Ops, it seems invoices selected havent submitted to MyInvois before"))
        # values.update({'invoice_ids': [(6, 0, invoice_ids.ids)]})
        text_information_fail = ""
        text_information_success = "" 
        if self._context.get('active_model') == 'myinvois.consolidate':
            records = self.env['myinvois.consolidate'].sudo().search([
                ('id', 'in', self._context.get('active_ids')), ('my_invois_uuid', '=', False)])
        else:
            records = self.env['account.move'].sudo().search([
                ('id', 'in', self._context.get('active_ids')), ('my_invois_uuid', '=', False)])
        if records:
            name_list = [record.name for record in records]
            text_information_fail += 'Cannot check document because its not submitted \n Invoice : {} \n'.format(', '.join(name_list))  

        records = self.env[self._context.get('active_model')].sudo().search([
                ('id', 'in', self._context.get('active_ids')), ('my_invois_uuid', '!=', False)])
        #part raise if no records means cant be cancelled
        if self._context.get('active_model') == 'myinvois.consolidate':
            values.update({'myinvois_consolidate_ids': [(6, 0, records.ids)]})
        else:
            values.update({'invoice_ids': [(6, 0, records.ids)]})

        #get invoice that it can be cancceled
        for each in records:
            text_information_success += each.name + ' \n'
        if text_information_fail:
            values.update({'text_information_fail':text_information_fail})
        text_information_success += '*This process will be queued, its normal that the update will be delayed. For realtime update please check the document submission individually.'
        values.update({'text_information_success':text_information_success})
        return values

    def get_url_document_details(self):
        url = "/api/v1.0/documents/%s/details"
        full_url = url % (self.myinvois_document_id.my_invois_uuid)
        return full_url

    def get_document_detail(self, rec):
        rec.requirement_document_invois()
        url = "%s%s" % (self.env.company.request_token_url, rec.get_url_document_details())
        payload = {}#since url only no need payload
        response = self.env.company.sync_myinvois(rec, "GET", url, payload)
        if response.status_code == 200:
            rec.document_details_success_response(response.json())
        
        return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "danger" if response.status_code != 200 else "success",
                    "message": _("Ops, something wrong happen. Please see API logs for the details") if response.status_code != 200 else _("Success Check Document"),
                    "next": {"type": "ir.actions.act_window_close"},
                }
            }

    def get_document_details(self):
        if self._context.get('active_model') == 'myinvois.consolidate':
            records = self.myinvois_consolidate_ids
        else:
            records = self.invoice_ids
        is_batch = True if len(records) > 1 else False
        for rec in records:
            if is_batch:
                self.with_delay().get_document_detail(rec)
            else:
                return self.get_document_detail(rec)
