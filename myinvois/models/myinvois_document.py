from odoo import _, fields, models, api
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning
from datetime import timedelta, datetime

class MyinvoisDocument(models.Model):
    _name = "myinvois.document"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Myinvois Document"
    _rec_name = "my_invois_uuid"

    my_invois_uuid = fields.Char(string="UUID", help="Unique document ID assigned by e-Invoice. 26 Latin alphanumeric symbols.")
    my_invois_submission_uuid = fields.Char(string="Submission ID", help="Unique submission document ID.")
    my_invois_long_uid = fields.Char(string="Long ID", help="Unique long temporary Id that can be used to query document data anonymously.")
    my_invois_internal_number = fields.Char(string="Internal ID", help="Internal ID used in submission for the document.")
    my_invois_document_type = fields.Char(string="TypeName", help="Response of get document details TypeName", related="my_invois_document_type_id.code")
    my_invois_document_type_id = fields.Many2one('myinvois.einvoice.type', string="MyInvois Type")
    my_invois_move_type = fields.Selection(selection=[
           ('out_invoice', 'Customer Invoice'),
            ('out_invoice_debit', 'Customer Debit Note'),
            ('out_refund', 'Customer Credit Note'),
            ('out_refund_paid', 'Customer Refund Note'),
            ('in_invoice', 'Vendor Bill'),
            ('in_refund', 'Vendor Credit Note'),
            ('in_refund_paid', 'Vendor Refund Note'),
            ('in_invoice_debit', 'Vendor Debit Note'),
            ('out_receipt', 'Sales Receipt'),
            ('in_receipt', 'Purchase Receipt'),
            ('in_invoice_debit', 'Vendor Debit Note'),
        ], compute="_compute_my_invois_company", store=True, string='Odoo Type')
    my_invois_doc_type_version = fields.Char(string="E-invoices Version")
    my_invois_partner_id = fields.Many2one('res.partner', string="Issuer Name")
    my_invois_partner_tin = fields.Char(string="Issuer Tin", related="my_invois_partner_id.vat")
    my_invois_created_by = fields.Char(string="Created by")
    my_invois_date_issued = fields.Datetime(string="Issued Date")
    my_invois_submit_date = fields.Datetime(string="Received Date")
    my_invois_validated_date = fields.Datetime(string="Validated On")
    my_invois_cancelled_date = fields.Datetime(string="Canceled Date")
    my_invois_rejection = fields.Boolean(string="Reject Requested", default=False)
    my_invois_reject_date = fields.Datetime(string="Reject Request Date")
    my_invois_document_status = fields.Selection([
        ('Submitted', 'Submitted'), ('Valid', 'Valid'),
        ('Invalid', 'Invalid'), ('Cancelled', 'Cancelled')
        ],string="Document Status", tracking=True)
    my_invois_cancel_reason = fields.Char(string="Reason")
    my_invois_receiver_type = fields.Selection([
        ('NRIC', 'NRIC'), ('PASSPORT', 'Passport Number'),
        ('BRN', 'Bussines Register Number (BRN)'),('ARMY', 'Army Number')
        ], string="Receiver ID Type")
    my_invois_receiver_id_number = fields.Char(string="Receiver ID")
    my_invois_receiver_name = fields.Char(string="Receiver Name")
    my_invois_currency = fields.Many2one('res.currency', string="Currency")
    my_invois_total_discount = fields.Monetary(string="Total Discount", currency_field='my_invois_currency')
    my_invois_net_amount = fields.Monetary(string="Net Amount", currency_field='my_invois_currency')
    my_invois_total_sale = fields.Monetary(string="Total Sales (Exclude Tax)", currency_field='my_invois_currency')
    my_invois_total_amount = fields.Monetary(string="Total Amount", currency_field='my_invois_currency')
    my_invois_total_ori_sale = fields.Monetary(string="Total Original Sales", currency_field='my_invois_currency')
    my_invois_total_ori_discount = fields.Monetary(string="Total Original Discount", currency_field='my_invois_currency')
    my_invois_net_ori_amount = fields.Monetary(string="Original Net Amount", currency_field='my_invois_currency')
    my_invois_total_ori = fields.Monetary(string="Original Total Amount", currency_field='my_invois_currency')
    my_invois_payable_amount = fields.Monetary(string="Payable Amount", currency_field='my_invois_currency')
    my_invois_id_submission = fields.Char(string="ID Submission", copy=False)#for submision uid after submit or get document details
    # my_invois_company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company)
    company_id = fields.Many2one('res.company', string="Company", compute="_compute_my_invois_company", store=True)

    my_invois_company_id_number = fields.Char(
        string="Company ID Number", related="company_id.vat")
    my_invois_is_billed = fields.Many2one('account.move', string="Vendor bill")
    my_invois_origin = fields.Char('Origin')
    
    
    
    @api.depends("my_invois_partner_id", "my_invois_document_type_id")
    def _compute_my_invois_company(self):
        for record in self:
            if record.my_invois_partner_id:
                company_partner_id = self.env['res.company'].search([('partner_id', '=', record.my_invois_partner_id.id)], limit=1)
                if company_partner_id:
                    record.company_id = company_partner_id.id
            else:
                record.company_id = self.env.company.id

            is_issuer = True if record.my_invois_partner_id == record.company_id.partner_id else False
            if is_issuer:
                record.my_invois_move_type = record.my_invois_document_type_id.my_invois_einvoice_type
            else :
                record.my_invois_move_type = record.my_invois_document_type_id.my_invois_einvoice_type_buyer


    def reject_myinvois_doc(self):
        """ Reject myinvois wizard """
        self.ensure_one()
        form = self.env.ref('pc_myinvois.reject_myinvois_wizard_form_view')
        context = dict(self.env.context or {})
        context['doc_id'] = self.id
        res = {
            'name': "%s - %s" % (_('Rejecting Myinvois Document'), self.my_invois_uuid),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'reject.myinvois.wizard',
            'view_id': form.id,
            'type': 'ir.actions.act_window',
            'context': context,
            'target': 'new'
        }
        return res
    
    def odoo_tax_id(self):
        # tax = self.my_invois_total_amount - self.my_invois_total_sale
        decimals = self.env['decimal.precision'].precision_get('Product Price')
        tax = round(self.my_invois_total_amount - self.my_invois_total_sale, decimals)
            
        percentage = tax / self.my_invois_total_amount  * 100
        tax_id = self.env['account.tax'].search([('amount', '=', percentage), ('amount_type', '=', 'percent'), ('type_tax_use', '=', 'purchase')], limit=1)
        if not tax_id:
            tax_id = self.env['account.tax'].create({
                'name': 'Myinvois Tax %s' % tax,
                'type_tax_use': 'none',
                'amount': tax,
                'amount_type': 'fixed'
            })
        return tax_id

    def myinvois_generate_bill(self):
        return self.myinvois_generate_vendor_doc('in_invoice')

    def myinvois_generate_vendor_credit_note(self):
        return self.myinvois_generate_vendor_doc('in_refund')

    def myinvois_generate_vendor_doc(self, type):
        my_invois_product_bill_id = self.env.company.my_invois_product_bill_id.id
        if not my_invois_product_bill_id:
            raise UserError(_("Please configure MyInvois Product in setting configuration for Generate Bill"))
        for data in self:
            invoice_vals = {}
            tax_id = data.odoo_tax_id() if data.my_invois_total_amount else self.env['account.tax']
            if data:
                invoice_line_vals = {
                    'product_id': my_invois_product_bill_id,
                    'quantity': 1,
                    'price_unit': data.my_invois_total_sale,
                    'tax_ids': tax_id.ids,
                }

                invoice_vals = {
                    'my_invois_einvoice_type_id': data.my_invois_document_type_id.id,
                    'partner_id' : data.my_invois_partner_id.id,
                    'move_type' : type,
                    'invoice_date' : fields.Datetime.today(),
                    'my_invois_einvoice_currency_id' : data.my_invois_currency.id,
                    'invoice_line_ids' : [(0, 0, invoice_line_vals)],
                    'myinvois_document_id': data.id,
                    'my_invois_uuid': data.my_invois_uuid,
                    'my_invois_id_submission': data.my_invois_id_submission
                }

                # Create Account Move
                create_vb = self.env['account.move'].create(invoice_vals)
                data.write({
                    'my_invois_is_billed' : create_vb.id,
                })       
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vendor Bill' if type == 'in_invoice' else 'Vendor Credit Note',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': create_vb.id,
            'target': 'current',
        }
    
    def action_view_vendor_bill(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
             "name": _("Vendor Bill"),
            'domain': [('myinvois_document_id', '=', self.id), ('move_type', '=', 'in_invoice')],
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'context': "{'move_type':'in_invoice'}",
        }
    
    def action_view_vendor_credit_note(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
             "name": _("Vendor Credit Note"),
            'domain': [('myinvois_document_id', '=', self.id), ('move_type', '=', 'in_refund')],
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'context': "{'move_type':'in_refund'}",
        }
    
    def action_view_customer_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
             "name": _("Customer Invoice"),
            'domain': [('myinvois_document_id', '=', self.id), ('move_type', '=', 'out_invoice')],
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'context': "{'move_type':'out_invoice'}",
        }
