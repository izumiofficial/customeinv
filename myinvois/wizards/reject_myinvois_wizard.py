from odoo import _, api, fields, models
from odoo.exceptions import UserError
from datetime import timedelta, datetime
import logging
import json

_logger = logging.getLogger(__name__)


class RejectMyinvoisWizard(models.TransientModel):
    _name = 'reject.myinvois.wizard'
    _description = "Reject Myinvois"
    
    myinvois_reject_reason = fields.Char(string="Reason")
    document_ids = fields.Many2many('myinvois.document', string="Document List")

    @api.model
    def default_get(self, fields):
        """ Get the selected document records """
        values = super(RejectMyinvoisWizard, self).default_get(fields)
        company = self.env.company
        document_ids = self.env['myinvois.document'].sudo().search([
            ('id', '=', self._context.get('doc_id')),
            ('my_invois_document_status', 'not in', ['Cancelled', 'Invalid'])])
        exceed_date_list = []
        if not document_ids:
            raise UserError(_("Cannot found any document that meet the requirement to be rejected."))
        # Check validated date
        for doc in document_ids:
            if doc.my_invois_validated_date:
                if doc.my_invois_validated_date < datetime.now() + timedelta(days=-3):
                    exceed_date_list.append(doc.my_invois_uuid)
            else:
              raise UserError(_("Ops, it seems the document is not valid, please check the status.")) 
           
        if len(exceed_date_list) > 0:
            raise UserError(_("Cancellation is not permitted, 72+ Hours window since the document marked as valid.\nDocument: %s", exceed_date_list))
        values.update({'document_ids': [(6, 0, document_ids.ids)]})
        return values

    def get_reject_doc_url(self, uid):
        url = "/api/v1.0/documents/state/%s/state"
        full_url = url % (str(uid))
        return full_url

    def reject_document(self):
        document_ids = self.document_ids
        document_list = []
        for rec in document_ids:
            payload = {
                'status': 'rejected',
                'reason': self.myinvois_reject_reason,
            }
            uid = rec.my_invois_uuid
            url = '%s%s' % (self.env.company.request_token_url, self.get_reject_doc_url(uid))
            response = self.env.company.sync_myinvois(rec, "PUT", url, payload)
            if response.status_code == 200:
                document_list.append(rec.my_invois_uuid)
                rec.my_invois_reject_date = datetime.now()
                rec.my_invois_rejection = True

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'sticky': True,
                'type': 'success',
                'message': _("Ops, reject document failed. Please see API logs for the details") if response.status_code != 200 else _("Success reject myinvois document: %s", document_list),
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
