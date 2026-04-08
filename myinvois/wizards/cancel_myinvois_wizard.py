from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import timedelta, datetime
import logging
import json

_logger = logging.getLogger(__name__)


class CancelMyinvoisWizard(models.TransientModel):
    _name = 'cancel.myinvois.wizard'
    _description = "Cancel MyInvois"

    myinvois_cancel_reason = fields.Char(string="Reason")
    invoice_ids = fields.Many2many('account.move', string="Invoice List")
    myinvois_consolidate_ids = fields.Many2many('myinvois.consolidate', string="Consolidate List")
    text_information_success = fields.Text(string="Document Can be Cancel")
    text_information_fail = fields.Text(string="Document Can Not Be Cancelled")

    @api.model
    def default_get(self, fields):
        """ Get the selected invoice records """
        values = super(CancelMyinvoisWizard, self).default_get(fields)
        text_information_fail = ""
        text_information_success = "" 
        if self._context.get('active_model') == 'myinvois.consolidate':
            records = self.env['myinvois.consolidate'].sudo().search([
                ('id', 'in', self._context.get('active_ids')), ('my_invois_uuid', '=', False)])
        else:
            records = self.env['account.move'].sudo().search([
                ('id', 'in', self._context.get('active_ids')), ('my_invois_uuid', '=', False)])
        exceed_date_list = []
        if records:
            name_list = [record.name for record in records]
            text_information_fail += 'Cannot cancel Document because its not submitted or has been consolidated \n Invoice : {} \n'.format(', '.join(name_list))  
        # Check submitted date
        records = self.env[self._context.get('active_model')].sudo().search([
                ('id', 'in', self._context.get('active_ids')), ('myinvois_document_id', '!=', False)])
        # part get document that has been canceled
        if records:
            record_already_cancelled = []
            for each_record in records:
                if each_record.myinvois_document_id.my_invois_document_status == "Cancelled":
                    record_already_cancelled.append(each_record.name)
            if len(record_already_cancelled) > 0:
                text_information_fail += 'Cannot cancel Document because its already cancelled : {}\n'.format(', '.join(record_already_cancelled))
        #part filter record that has no invois document state is cancelled
        records = records.filtered(lambda line: line.myinvois_document_id.my_invois_document_status != "Cancelled")

        for inv in records:
            if inv.myinvois_document_id:
                if inv.myinvois_document_id.my_invois_submit_date < datetime.now() + timedelta(days=-3):
                    exceed_date_list.append(inv.name)
        if len(exceed_date_list) > 0:
            # raise UserError(_("Cannot cancel document, Document already 72 hours after submitted.\nInvoice: %s", exceed_date_list))
            text_information_fail += "Cannot cancel document, Document already 72 hours after submitted.\n Invoice: {}\n".format(', '.join(exceed_date_list))

        #after all information is has been checked records need to be filltered again with correct 
        records = records.filtered(lambda line: line.myinvois_document_id and line.myinvois_document_id.my_invois_submit_date > datetime.now() + timedelta(days=-3))
        #part raise if no records means cant be cancelled
        if not records:
            if text_information_fail:
                raise UserError(text_information_fail)
            else:
                raise UserError(_('There is no document that can be cancelled. \n Please check document submission or consolidated invoice'))
        if self._context.get('active_model') == 'myinvois.consolidate':
            values.update({'myinvois_consolidate_ids': [(6, 0, records.ids)]})
        else:
            values.update({'invoice_ids': [(6, 0, records.ids)]})

        #get invoice that it can be cancceled
        for each in records:
            text_information_success += each.name + ' \n'
        if text_information_fail:
            values.update({'text_information_fail':text_information_fail})
        text_information_success += '*This process will be queued, its normal that the update will be delayed. For realtime update please cancel the document submission individually.'
        values.update({'text_information_success':text_information_success})

        return values

    def get_cancel_doc_url(self, uid):
        url = "/api/v1.0/documents/state/%s/state"
        full_url = url % (str(uid))
        return full_url

    def cancel_document(self, rec):
        payload = {
            'status': 'cancelled',
            'reason': self.myinvois_cancel_reason,
        }
        uid = rec.myinvois_document_id.my_invois_uuid
        url = '%s%s' % (self.env.company.request_token_url, self.get_cancel_doc_url(uid))
        response = self.env.company.sync_myinvois(rec, "PUT", url, payload)
        if response.status_code == 200:
            rec.myinvois_document_id.write({
                'my_invois_document_status': 'Cancelled',
                'my_invois_cancel_reason': self.myinvois_cancel_reason,
                'my_invois_cancelled_date': fields.Datetime.now()
            })
            if self._context.get('active_model') == 'myinvois.consolidate':
                rec.myinvois_consolidate_state = 'Cancelled'

        return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "danger" if response.status_code != 200 else "success",
                    "message": _("Ops, cancel document failed. Please see API logs for the details") if response.status_code != 200 else _("MyInvois document cancelled"),
                    "next": {"type": "ir.actions.act_window_close"},
                }
            }
    def cancel_documents(self):
        if self._context.get('active_model') == 'myinvois.consolidate':
            records = self.myinvois_consolidate_ids
        else:
            records = self.invoice_ids
        is_batch = True if len(records) > 1 else False
        for rec in records:
            if is_batch:
                self.with_delay().cancel_document(rec)
            else:
                return self.cancel_document(rec)
