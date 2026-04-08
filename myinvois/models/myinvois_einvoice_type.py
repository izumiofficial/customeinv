from odoo import api, fields, models, _

class MyinvoisEinvoiceType(models.Model):
    _name = "myinvois.einvoice.type"
    _description = "E-Invoice Type"

    code = fields.Char(string="Code")
    name = fields.Char(string="Description")
    my_invois_einvoice_type = fields.Selection(
        string="Odoo Document Type (Issuer)",
        selection=[
            ('out_invoice', 'Customer Invoice'),
            ('out_invoice_debit', 'Customer Debit Note'),
            ('out_refund', 'Customer Credit Note'),
            ('out_refund_paid', 'Customer Refund Note'),
            ('in_invoice', 'Vendor Bill'),
            ('in_invoice_debit', 'Vendor Debit Note'),
            ('in_refund', 'Vendor Credit Note'),
            ('in_refund_paid', 'Vendor Refund Note'),
        ]
    )
    my_invois_einvoice_type_buyer = fields.Selection(
        string="Odoo Document Type (Receiver)",
        selection=[
            ('out_invoice', 'Customer Invoice'),
            ('out_invoice_debit', 'Customer Debit Note'),
            ('out_refund', 'Customer Credit Note'),
            ('in_invoice', 'Vendor Bill'),
            ('in_refund', 'Vendor Credit Note'),
        ]
    )
    my_invois_einvoice_currency_id = fields.Many2one(
        'res.currency',
        string="Currency"
    )
