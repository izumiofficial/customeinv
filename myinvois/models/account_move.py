import json
import base64
import qrcode
from pytz import UTC
import pytz
import time
from odoo import api, fields, models, _
from datetime import timedelta, datetime, date
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning
from odoo.addons.queue_job.exception import RetryableJobError, FailedJobError
import json
from odoo.tools import file_open, misc#for getting file local json text
from hashlib import sha256
from io import BytesIO
from collections import defaultdict


from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import load_pem_private_key, pkcs12
from OpenSSL import crypto

class AccountMove(models.Model):
    _inherit = "account.move"
    myinvois_consolidate_id = fields.Many2one('myinvois.consolidate', 'Consolidated Invois' , copy=False)
    my_invois_qr_code = fields.Binary(copy=False)
    my_invois_digital_signature = fields.Char(copy=False, readonly=True)
    my_invois_validated_date = fields.Datetime(string='Validation Date and Time', 
                                               related='myinvois_document_id.my_invois_validated_date')
    
    def generate_qr_code(self):
       for rec in self:
            if not rec.my_invois_uuid or not rec.myinvois_document_id.my_invois_long_uid:
                msg = _('QRCode will appear once document submission status is valid')
                rec.message_post(body=msg)
                return
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=3,
                border=4,
            )
            qr.add_data("%s/%s/share/%s " % (rec.company_id.my_invois_portal_url, rec.my_invois_uuid, rec.myinvois_document_id.my_invois_long_uid ))
            qr.make(fit=True)
            img = qr.make_image()
            temp = BytesIO()
            img.save(temp, format="PNG")
            qr_image = base64.b64encode(temp.getvalue())
            rec.update({'my_invois_qr_code': qr_image})

    def _default_einvoice_type(self):
        move_type = self.env.context.get("default_move_type")
        return self.env["myinvois.einvoice.type"].search([("my_invois_einvoice_type", "=", move_type)] ,limit=1)

    my_invois_version = fields.Char()
    my_invois_time = fields.Datetime(
        string="Invois Time"
    )
    my_invois_ref = fields.Text(
        string="Billing Reference"
    )
    my_invois_einvoice_type_id = fields.Many2one(
        "myinvois.einvoice.type",
        default=lambda self: self._default_einvoice_type(),
        copy=False
    )
    my_invois_additional_doc_ids = fields.One2many(
        "myinvois.additional.document",
        "my_invois_additonal_move_id",
        string="Additional MyInvois Document"
    )
    my_invois_einvoice_version = fields.Char(
        string="Einvoice Code",
    )
    total_payable_amount = fields.Monetary(
        string="Total Payable Amount",
        currency_field="currency_id"
    )
    total_amount_after_discount = fields.Monetary(
        string="Total Amount After Discount",
        currency_field="currency_id"
    )
    total_charge = fields.Monetary(
        string="Total Fee / Charge Amount",
        currency_field="currency_id"
    )
    rounding_amount = fields.Monetary(
        string="Rounding Amount",
        currency_field="currency_id"
    )
    my_invois_einvoice_currency_id = fields.Many2one(
        "res.currency",
        string="Currency Code",
    )
    prepaid_payment_id = fields.Many2one(
        "prepaid.payment",
        string="Prepaid Payment"
    )

    my_invois_uuid = fields.Char(string="UUID Myinvois", copy=False)#for UUID after submit or get document details
    my_invois_status_submission = fields.Selection(related="myinvois_document_id.my_invois_document_status", string="Status Submission", copy=False, tracking=True, help="""Invois Status """)
    my_invois_id_submission = fields.Char(string="ID Submission", copy=False)#for submision uid after submit or get document details

    myinvois_document_id = fields.Many2one(
        "myinvois.document",
        string="MYInvois Document",
        copy=False
    )
    my_invois_rejection = fields.Boolean(string="Reject Requested", related="myinvois_document_id.my_invois_rejection", help="Rejected by the Buyer", store=True, readonly=False)
    my_invois_rejection_date = fields.Datetime(string="Reject Date", related="myinvois_document_id.my_invois_reject_date", help="Rejection date from MyInvoice API", store=True)
    my_invois_period_id = fields.Many2one('myinvois.period', string="MyInvois Period")

    my_invois_is_consolidated = fields.Boolean()
    my_invois_access_token = fields.Char(related="company_id.myinvois_access_token")
    # batch_my_invois_id = fields.Many2one('myinvois.consolidate', string="MyInvois Consolidate")
    
    #field for import purpose
    my_invois_tin_partner = fields.Char(string="Tin Partner", copy=False)
    my_invois_partner_id_type = fields.Selection(selection=[('nric', 'NRIC'),
                                                     ('pass_num', 'Passport Number'),
                                                     ('brn', 'Bussines Register Number (BRN)'),
                                                     ('army', 'Army Number')], string="ID Type", help="NRIC, Passport number, Business registration number, army number", copy=False)
    
    my_invois_partner_id_value = fields.Char(string="ID Number" , help="The actual value of the ID Type selected. For example, if NRIC selected as ID Type, then pass the NRIC value here.", copy=False)
    my_invois_cancel_reason = fields.Char(string="MyInvois Cancel Reason", related="myinvois_document_id.my_invois_cancel_reason")
    my_invois_cancelled_date = fields.Datetime(string="MyInvois Cancel Date", related="myinvois_document_id.my_invois_cancelled_date")


    @api.onchange("my_invois_rejection_date")
    def onchange_myinvois_rejection(self):
        """ Set rejection as Tru if rejection date not false """
        if self.my_invois_rejection_date:
            self.my_invois_rejection = True
        else:
            self.my_invois_rejection = False

    def get_tax_totals(self):
        tax_amount_by_id = {}
        if self.currency_id == self.company_id.currency_id:
            tax_line_ids = self.line_ids.filtered(lambda l:l.tax_line_id and not l.display_type)
            if tax_line_ids:
                for line in tax_line_ids:
                    amount = 0
                    if line not in tax_amount_by_id:
                        tax_amount_by_id[line] = 0
                    amount += line.debit+line.credit
                    tax_amount_by_id[line] += amount
            else:
                tax_line_ids = self.invoice_line_ids.filtered(lambda l:l.tax_ids and not l.display_type)
                taxes_amount = sum(tax_line_ids.tax_ids.mapped('amount'))
                if taxes_amount == 0:
                    for line in tax_line_ids:
                        amount = 0
                        if line not in tax_amount_by_id:
                            tax_amount_by_id[line] = 0
                        tax_amount_by_id[line] = 0
        else:
            tax_line_ids = self.invoice_line_ids.filtered(lambda l:l.tax_ids and not l.display_type)
            taxes_amount = sum(tax_line_ids.tax_ids.mapped('amount'))
            for line in tax_line_ids:
                amount = 0
                amount_line_tax = self.prepare_tax_total(line, line.tax_ids)
                if line not in tax_amount_by_id:
                    tax_amount_by_id[line] = 0
                amount += amount_line_tax
                tax_amount_by_id[line] += amount
        return tax_amount_by_id

    # FUNCTION FORMAT JSON
    def convert_format_json(self,key, value, additional_attributes=None):
        if additional_attributes is None:
            additional_attributes = {}

        return dict([
            (key, [dict({"_": value}, **additional_attributes)])
        ])

    # FUNCTION MERGE JSON
    def merge_data_json(self,parent,*childs):
        merged_child = dict()
        for child in childs:
            merged_child.update(child)
        
        return {parent: [merged_child]}

    # INVOICE SECTION
    # TODO OPTIONAL
    def prepare_data_invoice_period(self):
        data = self.my_invois_period_id

        value = data.my_invois_periode_start.strftime("%Y-%m-%d") if data.my_invois_periode_start else "NULL"
        invoice_periode_start = self.convert_format_json("StartDate",value)

        value = data.my_invois_periode_end.strftime("%Y-%m-%d") if data.my_invois_periode_end else "NULL"
        invoice_periode_end = self.convert_format_json("EndDate",value)
        
        value = data.my_invois_periode_description if data.my_invois_periode_description else "NULL"
        invoice_periode_description = self.convert_format_json("Description",value)

        InvoicePeriod = self.merge_data_json("InvoicePeriod",invoice_periode_start,invoice_periode_end,invoice_periode_description)
        return InvoicePeriod
    

    def prepare_data_id(self):
        value = self.name
        id = self.convert_format_json("ID",value)
        return id
    
    def get_invoice_pdf_report_attachment(self):
        pdf_content, pdf_name = super().get_invoice_pdf_report_attachment()
        if self.my_invois_uuid:
            pdf_content = self.env['ir.actions.report']._render('pc_myinvois.report_myinvois', self.ids)[0]
    
        return pdf_content, pdf_name

    def prepare_data_issues_date(self):
        n = self.env['ir.config_parameter'].sudo().get_param('myinvois.backdate_submission')
        invoice_date = self.invoice_date
        if n:
            invoice_date = self.invoice_date - timedelta(days=int(n))
         
        value = invoice_date.strftime("%Y-%m-%d") if self.invoice_date else "NULL"
        IssueDate = self.convert_format_json("IssueDate",value)
        return IssueDate

    
    # TODO time format
    def prepare_data_issues_time(self):
        kl_time = pytz.utc.localize(datetime.now(), is_dst=None).astimezone(pytz.timezone(self.env.user.tz))
        kl_time = kl_time.strftime("%H:%M:%SZ")
        utctime = datetime.now(tz=UTC).strftime("%H:%M:%SZ")
        # value = self.my_invois_time.strftime("%H-%m-%d") if self.my_invois_time else datetime.now().strftime("%H:%M:%SZ")
        IssueTime = self.convert_format_json("IssueTime", utctime)
        return IssueTime

    # E-INVOICE VERSION SECTION
    def prepare_data_invoice_type(self):
        value = self.my_invois_einvoice_type_id.code
        additional_attributes = {
             "listVersionID" : self.company_id.myinv_version()
        }
        InvoiceTypeCode = self.convert_format_json("InvoiceTypeCode",value,additional_attributes)
        return InvoiceTypeCode
    
    def prepare_data_documentary_currency(self):
        value = self.currency_id.name
        DocumentCurrencyCode = self.convert_format_json("DocumentCurrencyCode",value)
        return DocumentCurrencyCode

   # BILLING REFERENCE
    def prepare_data_billing_reference(self):
        # TODO add required or validation ref if empty
        value = self.ref or ''
        AdditionalDocumentID = self.convert_format_json("ID",value)
        AdditionalDocumentReference = self.merge_data_json("AdditionalDocumentReference",AdditionalDocumentID)
        # ('02', '04', '12', '14') are codes for reversed entry (credit note)
        if self.my_invois_einvoice_type_id.code in ('02', '04', '12', '14'):
            doc_ref = self.reversed_entry_id
            value = doc_ref.my_invois_uuid or doc_ref.myinvois_consolidate_id.my_invois_uuid or ''
            InvoiceDocumentReferenceUUID = self.convert_format_json("UUID",value)
            value = doc_ref.name or ''
            InvoiceDocumentReferenceID = self.convert_format_json("ID",value)
            InvoiceDocumentReference = self.merge_data_json("InvoiceDocumentReference",InvoiceDocumentReferenceUUID,InvoiceDocumentReferenceID)
            BillingReference = self.merge_data_json("BillingReference",AdditionalDocumentReference,InvoiceDocumentReference)
        
        # ('03', '13') are codes for reversed entry (debit note)
        elif self.my_invois_einvoice_type_id.code in ('03', '13'):
            doc_ref = self.debit_origin_id
            value = doc_ref.my_invois_uuid or doc_ref.myinvois_consolidate_id.my_invois_uuid or ''
            InvoiceDocumentReferenceUUID = self.convert_format_json("UUID",value)
            value = doc_ref.name or ''
            InvoiceDocumentReferenceID = self.convert_format_json("ID",value)
            InvoiceDocumentReference = self.merge_data_json("InvoiceDocumentReference",InvoiceDocumentReferenceUUID,InvoiceDocumentReferenceID)
            BillingReference = self.merge_data_json("BillingReference",AdditionalDocumentReference,InvoiceDocumentReference)
        
        else:
            BillingReference = self.merge_data_json("BillingReference",AdditionalDocumentReference)

        return BillingReference


    # ADDITIONAL DOCUMENT REFERENCE
    def prepare_data_additional_document(self):
        AdditionalDocumentReference = {"AdditionalDocumentReference":list()}
        for rec in self.my_invois_additional_doc_ids:
            AdditionalDocumentReferenceDict = dict()
            value = rec.name
            AdditionalDocumentID = self.convert_format_json("ID",value)
            value2 = rec.document_type
            DocumentType = self.convert_format_json("DocumentType",value2)
            AdditionalDocumentReferenceDict.update(**AdditionalDocumentID,**DocumentType)
            AdditionalDocumentReference['AdditionalDocumentReference'].append(AdditionalDocumentReferenceDict)

        # AdditionalDocumentReference =self.merge_data_json("AdditionalDocumentReference",AdditionalDocumentID,DocumentType)

        return AdditionalDocumentReference

    # SUPPLIER SECTION Company partner
    
    def prepare_data_accounting_supplier(self):
        # additional_account = self.prepare_additional_account()
        SupplierParty = self.prepare_data_party_supplier()
        AccountingSupplierParty = self.merge_data_json("AccountingSupplierParty",SupplierParty)

        return AccountingSupplierParty
    
    # TODO OPTIONAL
    # def prepare_additional_account(self)

    def prepare_data_party_supplier(self):
        # To check customer/vendor is it personal or company
        # if have parent and parent is company change to use company instead of personal
        if self.partner_id.parent_id:
            partner_company = self.partner_id.parent_id if self.partner_id.parent_id.is_company else self.partner_id
        else:
            partner_company = self.partner_id
            
        if self.my_invois_einvoice_type_id.code in ('11' ,'12', '13', '14'):
            partner = partner_company
        else:
            partner = self.company_id.partner_id
        
        # INDUSTRY CLASSIFICATION CODE
        value = partner.industry_id.code
        additional_attributes = {
            "name" : partner.industry_id.name
        }
        IndustryClassificationCode = self.convert_format_json("IndustryClassificationCode",value,additional_attributes)
        
        # PARTY INDENTIFICATION
        value = partner.vat
        additional_attributes = {
            "schemeID" : "TIN"
        }
        party_identification_id = self.convert_format_json("ID",value,additional_attributes)
        
        value = self.company_id.extract_sst(partner.my_invois_sst) if partner.my_invois_sst else 'NA'
        additional_attributes = {
            "schemeID" : "SST"
        }
        party_sst = self.convert_format_json("ID",value,additional_attributes)

        value = partner.my_invois_ttx or 'NA'
        additional_attributes = {
            "schemeID" : "TTX"
        }
        party_ttx = self.convert_format_json("ID",value,additional_attributes)

        value = partner.my_invois_partner_id_value
        additional_attributes = {
            "schemeID" : partner.my_invois_partner_id_type.upper() if partner.my_invois_partner_id_type else ""
        }
        party_identification_id_2 = self.convert_format_json("ID",value,additional_attributes)

        PartyIdentification = {'PartyIdentification' : [party_identification_id,party_identification_id_2,party_sst,party_ttx]}
        
        # POSTAL ADDRESS 
        value = partner.city
        city = self.convert_format_json("CityName",value)
        # optional
        # value = partner.zip
        # postal_zone = self.convert_format_json("PostalZone",value)
        value = partner.state_id.myinvois_state_code
        country_subentity = self.convert_format_json("CountrySubentityCode",value)
        value = partner.country_id.myinvois_code
        additional_attributes = {
            "listID": "ISO3166-1",
            "listAgencyID": "6"
        }
        IdentificationCode = self.convert_format_json("IdentificationCode",value,additional_attributes)
        country = self.merge_data_json("Country",IdentificationCode)
        # ADRESSS LINE
        value = partner.street
        Line = self.convert_format_json("Line",value)
        AddressLine = self.merge_data_json("AddressLine",Line)

        PostalAddress = self.merge_data_json("PostalAddress",city,country_subentity,AddressLine,country)
        
        # PARTY LEGAL ENTITY
        value = partner.name
        RegistrationName = self.convert_format_json("RegistrationName",value)
        PartyLegalEntity = self.merge_data_json("PartyLegalEntity",RegistrationName)

        # CONTACT
        value = self.company_id.extract_phone_number(partner.phone)
        phone = self.convert_format_json("Telephone",value)
        value = partner.email
        # optional
        ElectronicMail = self.convert_format_json("ElectronicMail",value)
        Contact = self.merge_data_json("Contact",phone,ElectronicMail)

        Party = self.merge_data_json("Party",IndustryClassificationCode,PartyIdentification,PostalAddress,PartyLegalEntity,Contact)

        return Party

    # BUYER SECTION -> Customer partner

    def prepare_data_accounting_customer(self):
        CustomerParty = self.prepare_data_party_customer()
        AccountingCustomerParty = self.merge_data_json("AccountingCustomerParty",CustomerParty)
        return AccountingCustomerParty

    def prepare_data_party_customer(self):
        # To check customer/vendor is it personal or company
        # if have parent and parent is company change to use company instead of personal
        if self.partner_id.parent_id:
            partner_company = self.partner_id.parent_id if self.partner_id.parent_id.is_company else self.partner_id
        else:
            partner_company = self.partner_id
            
        if self.my_invois_einvoice_type_id.code in ('11' ,'12', '13', '14'):
            partner = self.company_id.partner_id
        else:
            partner = partner_company
        
        # PARTY INDENTIFICATION
        all_Data = []
        vat = partner.vat
        additional_attributes = {
            "schemeID" : "TIN"
        }
        party_identification_id = self.convert_format_json("ID",vat,additional_attributes)
        if vat:
            all_Data.append(party_identification_id)
        id_number = partner.my_invois_partner_id_value
        additional_attributes = {
            "schemeID" :partner.my_invois_partner_id_type.upper() if partner.my_invois_partner_id_type else ""
        }
        party_identification_id_2 = self.convert_format_json("ID",id_number,additional_attributes)
        if id_number:
            all_Data.append(party_identification_id_2)
        value = self.company_id.extract_sst(partner.my_invois_sst) if partner.my_invois_sst else 'NA'
        additional_attributes = {
            "schemeID" : "SST"
        }
        party_sst = self.convert_format_json("ID",value,additional_attributes)
        all_Data.append(party_sst)

        PartyIdentification = {'PartyIdentification' : all_Data}

        # POSTAL ADDRESS 
        value = partner.city
        city = self.convert_format_json("CityName",value)
        # optional
        # value = partner.zip
        # postal_zone = self.convert_format_json("PostalZone",value)
        value = partner.state_id.myinvois_state_code
        country_subentity = self.convert_format_json("CountrySubentityCode",value)
        value = partner.country_id.myinvois_code
        additional_attributes = {
            "listID": "ISO3166-1",
            "listAgencyID": "6"
        }
        IdentificationCode = self.convert_format_json("IdentificationCode",value,additional_attributes)
        country = self.merge_data_json("Country",IdentificationCode)
        # ADRESSS LINE
        value = partner.street
        Line = self.convert_format_json("Line",value)
        AddressLine = self.merge_data_json("AddressLine",Line)

        PostalAddress = self.merge_data_json("PostalAddress",city,country_subentity,AddressLine,country)
        
        # PARTY LEGAL ENTITY
        value = partner.name
        RegistrationName = self.convert_format_json("RegistrationName",value)
        PartyLegalEntity = self.merge_data_json("PartyLegalEntity",RegistrationName)

        # CONTACT
        value = self.company_id.extract_phone_number(partner.phone)
        phone = self.convert_format_json("Telephone",value)
        value = partner.email
        # optional
        ElectronicMail = self.convert_format_json("ElectronicMail",value)
        Contact = self.merge_data_json("Contact",phone,ElectronicMail)

        Party = self.merge_data_json("Party",PostalAddress,PartyLegalEntity,PartyIdentification,Contact)

        return Party

    # DELIVERY SECTION 

    def prepare_data_delivery(self):
        DeliveryParty = self.prepare_data_delivery_party()
        Delivery = self.merge_data_json("Delivery",DeliveryParty)
        return Delivery

    def prepare_data_delivery_party(self):
        # To check customer/vendor is it personal or company
        # if have parent and parent is company change to use company instead of personal
        if self.partner_id.parent_id:
            partner_company = self.partner_id.parent_id if self.partner_id.parent_id.is_company else self.partner_id
        else:
            partner_company = self.partner_id
            
        partner = self.partner_shipping_id if self.partner_shipping_id else partner_company
        if self.move_type in ('in_invoice', 'in_refund', 'in_receipt'):
            partner = self.company_id.partner_id
        # PARTY LEGAL ENTITY
        value = partner.name
        RegistrationName = self.convert_format_json("RegistrationName",value)
        PartyLegalEntity = self.merge_data_json("PartyLegalEntity",RegistrationName)

        # PARTY INDENTIFICATION
        value = partner.vat
        additional_attributes = {
            "schemeID" : "TIN"
        }
        party_identification_id = self.convert_format_json("ID",value,additional_attributes)
        
        value = partner.my_invois_partner_id_value
        additional_attributes = {
            "schemeID" :partner.my_invois_partner_id_type.upper() if partner.my_invois_partner_id_type else False
        }
        party_identification_id_2 = self.convert_format_json("ID",value,additional_attributes)

        PartyIdentification = {'PartyIdentification' : [party_identification_id,party_identification_id_2]}

        # POSTAL ADDRESS 
        value = partner.city
        city = self.convert_format_json("CityName",value)
        # optional
        # value = partner.zip
        # postal_zone = self.convert_format_json("PostalZone",value)
        value = partner.state_id.myinvois_state_code
        country_subentity = self.convert_format_json("CountrySubentityCode",value)
        value = partner.country_id.myinvois_code
        additional_attributes = {
            "listID": "ISO3166-1",
            "listAgencyID": "6"
        }
        IdentificationCode = self.convert_format_json("IdentificationCode",value,additional_attributes)
        country = self.merge_data_json("Country",IdentificationCode)
        # ADRESSS LINE
        value = partner.street
        Line = self.convert_format_json("Line",value)
        AddressLine = self.merge_data_json("AddressLine",Line)

        PostalAddress = self.merge_data_json("PostalAddress",city,country_subentity,AddressLine,country)

        DeliveryParty = self.merge_data_json("DeliveryParty",PartyLegalEntity,PostalAddress,PartyIdentification)
        return DeliveryParty
    
    # TAX TOTAL
    def prepare_data_tax_total(self):
        tax_amount_by_id = self.get_tax_totals()
        TaxAmount = self.prepare_data_tax_amount(tax_amount_by_id)
        TaxSubtotal = self.prepare_data_tax_subtotal(tax_amount_by_id)

        TaxTotal = self.merge_data_json("TaxTotal",TaxAmount,TaxSubtotal)
        return TaxTotal
    
    # TAX AMOUNT 
    def prepare_data_tax_amount(self,tax_group):
        value = sum(tax_group.values())
        additional_attributes = {
            "currencyID" : self.currency_id.name
        }
        TaxAmount = self.convert_format_json("TaxAmount",value,additional_attributes)
        
        return TaxAmount
    
    # TAX SUBTOTAL
    def prepare_data_tax_subtotal(self, tax_group):
        TaxSubtotal = {"TaxSubtotal":list()}
        # tax_line is account move line/journal item generated from invoice line tax_ids
        for tax_line in tax_group:
            TaxSubtotalDict = dict()
            TaxCategoryDict = dict()
            value = tax_line.tax_base_amount if tax_line.tax_base_amount > 0 else tax_line.price_subtotal
            additional_attributes = {
                "currencyID" : self.currency_id.name
            }
            TaxableAmount = self.convert_format_json("TaxableAmount",value,additional_attributes)
            TaxSubtotalDict.update(TaxableAmount)
            value = tax_group[tax_line]
            TaxAmount = self.convert_format_json("TaxAmount",value,additional_attributes)
            TaxSubtotalDict.update(TaxAmount)
            TaxCategory = {"TaxCategory":list()}
            # for line in self.invoice_line_ids:
            # use search instead of browse so we can search by string / int id
            tax_id = tax_line.tax_line_id if tax_line.tax_line_id else tax_line.tax_ids
            TaxCategID = self.convert_format_json("ID",tax_id.tax_type_id.code)
            TaxCategoryDict.update(TaxCategID)
                # if line.tax_type_id.code == 'E':
            additional_attributes = {
                "schemeID": "UN/ECE 5153",
                "schemeAgencyID": "6"
            }
            TaxSchemeID = self.convert_format_json("ID","OTH",additional_attributes)
            TaxScheme = self.merge_data_json("TaxScheme",TaxSchemeID)
            TaxCategoryDict.update(TaxScheme)
            TaxCategory["TaxCategory"].append(TaxCategoryDict)
            TaxSubtotalDict.update(TaxCategory)
            TaxSubtotal["TaxSubtotal"].append(TaxSubtotalDict)
        return TaxSubtotal

    
    # LEGAL MONETARY SECTION
    
    def prepare_data_legalmonetary_total(self):
        LegalMonetaryTotal = {}
        # TAX EXCLUSIVE AMOUNT
        value = self.amount_untaxed
        additional_attributes = {
            "currencyID" : self.currency_id.name
        }
        TaxExclusiveAmount  = self.convert_format_json("TaxExclusiveAmount",value,additional_attributes)


        value = self.amount_total

        # TAX INCLUSIVE AMOUNT
        additional_attributes = {
            "currencyID" : self.currency_id.name
        }
        TaxInclusiveAmount = self.convert_format_json("TaxInclusiveAmount",value,additional_attributes)

        # TOTAL PAYABLE AMOUNT
        # need to check later
        # payable == amount total transaction
        additional_attributes = {
            "currencyID" : self.currency_id.name
        }
        PayableAmount = self.convert_format_json("PayableAmount",value,additional_attributes)

        LegalMonetaryTotal  = self.merge_data_json("LegalMonetaryTotal",TaxExclusiveAmount,TaxInclusiveAmount,PayableAmount)
        return LegalMonetaryTotal


    def prepare_data_myinvois(self):
        Invoice = {
            "_D": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
            "_A": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "_B": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        }
        for inv in self:
            ID = inv.prepare_data_id()
            # InvoicePeriod = inv.prepare_data_invoice_period()
            IssueDate = inv.prepare_data_issues_date() #
            IssueTime = inv.prepare_data_issues_time() #
            InvoiceTypeCode = inv.prepare_data_invoice_type() #
            DocumentCurrencyCode = inv.prepare_data_documentary_currency() #
            # AdditionalDocumentReference = self.prepare_data_additional_document()
            BillingReference = inv.prepare_data_billing_reference()
            AccountingSupplierParty = inv.prepare_data_accounting_supplier() #
            AccountingCustomerParty = inv.prepare_data_accounting_customer() #
            Delivery = inv.prepare_data_delivery() #
            TaxTotal = inv.prepare_data_tax_total() # 
            LegalMonetaryTotal = inv.prepare_data_legalmonetary_total() #
            InvoiceLine = inv.prepare_data_invoice_line() #
            # inv_payload data structure === {"Invoice": [inv_Data]}
            Invoice.update(self.merge_data_json("Invoice",ID,IssueDate,IssueTime,BillingReference,
                    InvoiceTypeCode,DocumentCurrencyCode,AccountingSupplierParty,
                    AccountingCustomerParty,Delivery,TaxTotal,LegalMonetaryTotal,InvoiceLine))
            # digital sign certificate 
            version = self.company_id.myinv_version()
            if version == '1.1':
                sign_element = inv.company_id.sign_document(Invoice, inv)
                Invoice['Invoice'][0].update(sign_element)
        
        return Invoice
    
    def prepare_tax_total(self, line, tax):
        tax_total = 0
        line_discount_price_unit = line.price_unit * (1 - (line.discount / 100.0))
        tax_result = line.tax_ids.compute_all(
            line_discount_price_unit,
            quantity=line.quantity,
            currency=line.currency_id,
            product=line.product_id,
            partner=line.partner_id,
        )

        if 'taxes' in tax_result:
            for tax_res in tax_result['taxes']:
                if tax and tax['id'] == tax_res['id']:
                    return abs(tax_res['amount'])
                tax_total += abs(tax_res['amount'])
        return tax_total


    def prepare_data_invoice_line_tax_subtotal(self,data):
        TaxSubtotal = {"TaxSubtotal":list()}
        for tax in data.tax_ids:
            TaxSubtotalDict = dict()
            TaxCategoryDict = dict()
            # TODO need discuss value amount
            value = self.prepare_tax_total(data,tax)
            taxable_amount = data.price_subtotal
            additional_attributes = {
                "currencyID" : self.currency_id.name
            }
            TaxableAmount = self.convert_format_json("TaxableAmount",taxable_amount,additional_attributes)
            TaxSubtotalDict.update(TaxableAmount)
            TaxAmount = self.convert_format_json("TaxAmount",value,additional_attributes)
            TaxSubtotalDict.update(TaxAmount)
            TaxCategory = {"TaxCategory":list()}
            TaxCategID = self.convert_format_json("ID",tax.tax_type_id.code)
            TaxCategoryDict.update(TaxCategID)
            Percent = self.convert_format_json("Percent",tax.amount)
            TaxCategoryDict.update(Percent)
            additional_attributes = {
                "schemeID": "UN/ECE 5153",
                "schemeAgencyID": "6"
            }
            TaxSchemeID = self.convert_format_json("ID","OTH",additional_attributes)
            TaxScheme = self.merge_data_json("TaxScheme",TaxSchemeID)
            TaxCategoryDict.update(TaxScheme)
            TaxExemptionReason = self.convert_format_json("TaxExemptionReason","")
            TaxCategoryDict.update(TaxExemptionReason)
            TaxSubtotalDict.update(TaxCategory)
            TaxCategory["TaxCategory"].append(TaxCategoryDict)
            
            TaxSubtotal["TaxSubtotal"].append(TaxSubtotalDict)
        return TaxSubtotal
    
    def prepare_data_invoice_line(self):
        InvoiceLine = {"InvoiceLine":list()}
        for data in self.invoice_line_ids.filtered(lambda x: not x.display_type):
            return_dict = {}
            
            ID = self.convert_format_json("ID",str(data.id))
            return_dict.update(ID)

            InvoicedQuantity_UnitCode = {"unitCode" : data.product_id.uom_id.myinvois_code}
            InvoicedQuantity = self.convert_format_json("InvoicedQuantity",data.quantity,InvoicedQuantity_UnitCode)
            return_dict.update(InvoicedQuantity)

            currencyID = {"currencyID" : data.currency_id.name}
            LineExtensionAmount = self.convert_format_json("LineExtensionAmount",data.price_subtotal,currencyID)
            return_dict.update(LineExtensionAmount)

            # TODO AllowanceCharge OPTIONAL
            tax_total = self.prepare_tax_total(data,False)
            
            TaxTotal_TaxAmount = self.convert_format_json("TaxAmount",tax_total,currencyID)
            TaxSubtotal = self.prepare_data_invoice_line_tax_subtotal(data)
            

            TaxTotal = self.merge_data_json("TaxTotal",TaxTotal_TaxAmount,TaxSubtotal)
            return_dict.update(TaxTotal)

            additional_attributes = {
                "listID" : "CLASS"
            }
            product_classification = data.product_id.categ_id.get_product_classification_id()
            ItemClassificationCode = self.convert_format_json("ItemClassificationCode",product_classification.code,additional_attributes)
            CommodityClassification = self.merge_data_json("CommodityClassification",ItemClassificationCode)
            Description = self.convert_format_json("Description",data.name)
            Item = self.merge_data_json("Item",CommodityClassification,Description)
            return_dict.update(Item)

            Price_val = self.convert_format_json("PriceAmount",data.price_unit,currencyID)
            Price = self.merge_data_json("Price",Price_val)
            return_dict.update(Price)

            # TODO TANYA MAS HAJI
            ItemPriceExtension_val = self.convert_format_json("Amount",data.price_subtotal,currencyID)
            ItemPriceExtension = self.merge_data_json("ItemPriceExtension",ItemPriceExtension_val)
            return_dict.update(ItemPriceExtension)
            
            InvoiceLine["InvoiceLine"].append(return_dict)
        
        # invoiceLine = self.merge_data_json("InvoiceLine",invoice_line)
        return InvoiceLine

    def cancel_myinvois_doc(self):
        """ Cancel myinvois wizard """
        self.ensure_one()
        form = self.env.ref("pc_myinvois.cancel_myinvois_wizard_form_view")
        context = dict(self.env.context or {})
        res = {
            "name": "%s - %s" % (_("Cancelling Myinvois"), self.name),
            "view_type": "form",
            "view_mode": "form",
            "res_model": "cancel.myinvois.wizard",
            "view_id": form.id,
            "type": "ir.actions.act_window",
            "context": context, 
            "target": "new"
        }
        return res
    
    #part of requirement api get document
    #from now get document details is only uid need 
    #will return warning if requirement is not fullfiled
    def requirement_document_invois(self):
        warning_msg = ""
        if not self.my_invois_uuid:
            warning_msg += "UUID Document\n"
        if warning_msg:
            if self.env.context.get("job_uuid", False):
                raise RetryableJobError(_("Please input %s" % ", ".join(warning_msg)))
            else:
                raise ValidationError(_("Please input %s" % ", ".join(warning_msg)))
            
    def get_url_document_details(self):
        url = "/api/v1.0/documents/%s/details"
        full_url = url % (self.my_invois_uuid)
        return full_url

    def action_get_document_details(self):
        self.ensure_one()
        self.requirement_document_invois()
        url = "%s%s" % (self.company_id.request_token_url, self.get_url_document_details())
        payload = {}#since url only no need payload
        response = self.company_id.sync_myinvois(self, "GET", url, payload)
        if response.status_code == 200:
            self.document_details_success_response(response.json())
        
        return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "danger" if response.status_code != 200 else "success",
                    "message": _("Ops, something wrong happen. Please see API logs for the details") if response.status_code != 200 else _("Success Check Document"),
                    "next": {"type": "ir.actions.act_window_close"},
                }
            }
    
    #response must be on json
    #when get document details and the response status code is not error means only 200 
    # the response return as DocumentDetails is 1 object 
    
    # API UPDATE OCT 2024 - possibly we will remove this function as LHDN already standardize the API response
    # between document detail and search API now have same data structure
    def document_details_success_response(self, response):
        """API to get document details based on UUID document myinvois / invoice"""
        MyInvois = self.env['myinvois.document']
        document_exist_id = MyInvois.search([('my_invois_uuid', '=', response.get('uuid'))])
        issuer_id, einvoice_type_id, submit_date, issued_date, cancel_date, reject_date, validate_date = self.env['res.company'].preprocessing_myinvois_data(response)
        currency = self.env.ref('base.MYR')
        data = {
            'my_invois_uuid': response.get('uuid'),
            'my_invois_submission_uuid': response.get('submissionUUID'),
            'my_invois_long_uid': response.get('longId'),
            'my_invois_internal_number': response.get('internalId'),
            'my_invois_document_status': response.get('status'),
            'my_invois_cancel_reason': response.get('documentStatusReason'),
            'my_invois_doc_type_version': response.get('typeVersionName'),
            'my_invois_receiver_type': response.get('receiverIDType'),
            'my_invois_receiver_id_number': self.company_id.get_value_case_insensitive(response, 'receiverID'),
            'my_invois_receiver_name': response.get('receiverName'),
            'my_invois_partner_tin': self.company_id.get_value_case_insensitive(response, 'issuerTIN'),
            'my_invois_created_by': response.get('createdByUserId'),
            'my_invois_currency': currency.id if currency else False,
            'my_invois_date_issued': issued_date,
            'my_invois_submit_date': submit_date,
            'my_invois_reject_date': reject_date,
            'my_invois_validated_date': validate_date,
            'my_invois_cancelled_date': cancel_date,
            'my_invois_origin': self.name,
            'my_invois_uuid': response.get('uuid'),
            'my_invois_total_discount': response.get('totalDiscount'),
            'my_invois_total_ori_sale': response.get('totalOriginalSales'),
            'my_invois_total_ori_discount': response.get('totalOriginalDiscount'),
            'my_invois_net_ori_amount': response.get('netOriginalAmount'),
            'my_invois_total_ori': response.get('totalOriginal'),
            'my_invois_net_amount': response.get('totalNetAmount'),
            'my_invois_total_sale': response.get('totalExcludingTax'),
            'my_invois_total_amount': response.get('totalPayableAmount'),
            # 'my_invois_document_type': response.get('typeName'),
            'my_invois_id_submission': response.get('submissionUid'),
        }
        if einvoice_type_id:
            data.update({
                'my_invois_document_type_id': einvoice_type_id.id,
                })
        if issuer_id:
            data.update({'my_invois_partner_id': issuer_id.id}) 


        if document_exist_id:
            document_exist_id.write(data)
        else:
            # create document invois
            document_exist_id = MyInvois.create(data)
        # case when the function called from the CRON, self sometime empty move
        if self:
            self.write({
                'myinvois_document_id': document_exist_id.id,
                'my_invois_id_submission': response.get('submissionUid')
            })
            self.generate_qr_code()

        return document_exist_id
    
    def document_search_success_response(self, response):
        """API to get document from search API"""
        MyInvois = self.env['myinvois.document']
        document_exist_id = MyInvois.search([('my_invois_uuid', '=', response.get('uuid'))])
        issuer_id, einvoice_type_id, submit_date, issued_date, cancel_date, reject_date, validate_date = self.env['res.company'].preprocessing_myinvois_data(response)
        currency = self.env.ref('base.MYR')
        data = {
            'my_invois_uuid': response.get('uuid'),
            'my_invois_submission_uuid': response.get('submissionUUID'),
            'my_invois_long_uid': response.get('longId'),
            'my_invois_internal_number': response.get('internalId'),
            'my_invois_document_status': response.get('status'),
            'my_invois_cancel_reason': response.get('documentStatusReason'),
            'my_invois_doc_type_version': response.get('typeVersionName'),
            'my_invois_receiver_type': response.get('receiverIDType'),
            'my_invois_receiver_id_number': self.company_id.get_value_case_insensitive(response, 'receiverID'),
            'my_invois_receiver_name': response.get('receiverName'),
            'my_invois_created_by': response.get('createdByUserId'),
            'my_invois_currency': currency.id if currency else False,
            'my_invois_date_issued': issued_date,
            'my_invois_submit_date': submit_date,
            'my_invois_reject_date': reject_date,
            'my_invois_validated_date': validate_date,
            'my_invois_cancelled_date': cancel_date,
            'my_invois_origin': self.name,
            'my_invois_uuid': response.get('uuid'),
            'my_invois_total_discount': response.get('totalDiscount'),
            'my_invois_total_ori_sale': response.get('totalOriginalSales'),
            'my_invois_total_ori_discount': response.get('totalOriginalDiscount'),
            'my_invois_net_ori_amount': response.get('netOriginalAmount'),
            'my_invois_total_ori': response.get('totalOriginal'),
            'my_invois_net_amount': response.get('netAmount'),
            'my_invois_total_sale': response.get('totalSales'),
            'my_invois_total_amount': response.get('total'),
            # 'my_invois_document_type': response.get('typeName')
        }
        if einvoice_type_id:
            data.update({
                'my_invois_document_type_id': einvoice_type_id.id,
                })
        if issuer_id:
            data.update({'my_invois_partner_id': issuer_id.id})
            
        if document_exist_id:
            document_exist_id.write(data)
        else:
            # create document invois
            document_exist_id = MyInvois.create(data)
        # case when the function called from the CRON, self sometime empty move
        if self:
            self.write({
                'myinvois_document_id': document_exist_id.id,
                'my_invois_id_submission': response.get('submissionUid')
            })
            self.generate_qr_code()
        return document_exist_id
    
            
    def hash_json_data(self, data):
        hashed = sha256(json.dumps(data, indent = 4).encode('utf8')).hexdigest()
        return hashed

    def parse_response_string(self,response_str):
        # Convert single quotes to double quotes for JSON compatibility
        json_compatible_str = response_str.replace("'", '"')
        # Convert the string to a dictionary
        response_dict = json.loads(json_compatible_str)
        return response_dict
    
    def check_field_submit_mandatory(self):
        # field_mandatory_account_move = ["ref"]
        # field_mandatory_invoice_period = ["my_invois_periode_start","my_invois_periode_end","my_invois_periode_description"]
        # field_mandatory_invoice_period = []
        #check mandatory field
        field_mandatory_supplier = ["industry_id","state_id","vat","my_invois_partner_id_value","city","country_id","street","phone","email"]
        field_mandatory_buyer = ["state_id","vat","my_invois_partner_id_value","city","country_id","street","phone","email"]
        field_mandatory_tax = ["tax_type_id"]
        field_mandatory_prod_categ = ["product_classification_id"]
        field_mandatory_prod_uom = ["myinvois_code"]
        mandatory_field = []
        
        # To check customer/vendor is it personal or company
        # if have parent and parent is company change to use company instead of personal
        if self.partner_id.parent_id:
            partner_company = self.partner_id.parent_id if self.partner_id.parent_id.is_company else self.partner_id
        else:
            partner_company = self.partner_id
            
        if self.my_invois_einvoice_type_id.code in ('11' ,'12', '13', '14'):
            suplier = partner_company
            buyer = self.company_id.partner_id
        else:
            suplier = self.company_id.partner_id
            buyer = partner_company

        # invoice_period = self.my_invois_period_id
        
        data_move = {'Invoice':[]}
        # for field_move in field_mandatory_account_move:
        #     if not self[field_move]:
        #         data_move['Invoice'].append(self._fields[field_move].string)
        if len(data_move['Invoice']) > 0:
            mandatory_field.append(data_move)

        # invoice period no longer mandatory
        # data_invoice_period = {'Invoice Period':[]}
        # for field_invoice_period in field_mandatory_invoice_period:
        #     if not invoice_period[field_invoice_period]:
        #         data_invoice_period['Invoice Period'].append(invoice_period._fields[field_invoice_period].string)
        # if len(data_invoice_period['Invoice Period']) > 0:
        #     mandatory_field.append(data_invoice_period)
        
        suplier_name = 'Supplier (Must be a company) - ' + suplier.name
        data_suplier = {suplier_name:[]}
        for field_suplier in field_mandatory_supplier:
            if suplier and not suplier[field_suplier]:
                data_suplier[suplier_name].append(suplier._fields[field_suplier].string)
            elif suplier and field_suplier == "state_id" and not suplier.state_id.myinvois_state_code:
                data_suplier[suplier_name].append(suplier.state_id._fields['myinvois_state_code'].string + ' (State)')
            elif suplier and field_suplier == "country_id" and not suplier.country_id.myinvois_code:
                data_suplier[suplier_name].append(suplier.country_id._fields['myinvois_code'].string + ' (Country)')
        if len(data_suplier[suplier_name]) > 0:
            mandatory_field.append(data_suplier)

        buyer_name = 'Buyer - ' + buyer.name
        data_buyer = {buyer_name:[]}
        for field_buyer in field_mandatory_buyer:
            if buyer and not buyer[field_buyer]:
                data_buyer[buyer_name].append(buyer._fields[field_buyer].string)
            elif buyer and field_buyer == "state_id" and not buyer.state_id.myinvois_state_code:
                data_buyer[buyer_name].append(buyer.state_id._fields['myinvois_state_code'].string + ' (State)')
            elif buyer and field_buyer == "country_id" and not buyer.country_id.myinvois_code:
                data_buyer[buyer_name].append(buyer.country_id._fields['myinvois_code'].string + ' (Country)')
        if len(data_buyer[buyer_name]) > 0:
            mandatory_field.append(data_buyer)
        
        for taxes in self.invoice_line_ids.tax_ids:
            for tax in taxes:
                data_tax = {tax.name:[]}
                for field_tax in field_mandatory_tax:
                    if not tax[field_tax]:
                        data_tax[tax.name].append(tax._fields[field_tax].string)
                if len(data_tax[tax.name]) > 0:
                    mandatory_field.append(data_tax)
        
        for line in self.invoice_line_ids:
            if not line.tax_ids and not line.display_type:
                data_tax = {'Invoice Line' : 'Taxes'}
                mandatory_field.append(data_tax)
                 
        if not self.invoice_line_ids.mapped('tax_ids'):
            data_tax = {'Invoice Line' : 'Taxes'}
            mandatory_field.append(data_tax)
        
        for uom_ids in self.invoice_line_ids.mapped('product_uom_id'):
            for uom in uom_ids:
                naming = 'UoM - %s' % uom.name
                data_uom = {naming:[]}
                for field_uom in field_mandatory_prod_uom:
                    if not uom[field_uom]:
                        data_uom[naming].append(uom._fields[field_uom].string)
                if len(data_uom[naming]) > 0:
                    mandatory_field.append(data_uom)
        for product in self.invoice_line_ids.mapped('product_id'):
            naming = 'Product Category - %s' % product.categ_id.name
            data_categ = {naming:[]}
            for field_categ in field_mandatory_prod_categ:
                if field_categ == 'product_classification_id':
                    field_value = product.categ_id.get_product_classification_id()
                else:
                    field_value = product.categ_id[field_categ]
                if not field_value:
                    data_categ[naming].append(product.categ_id._fields[field_categ].string)
            if len(data_categ[naming]) > 0:
                mandatory_field.append(data_categ)
            
        return mandatory_field
    
    def check_field_submit_consolidate_mandatory(self):
        field_mandatory_tax = ["tax_type_id"]
        mandatory_field = []
        for tax in self.invoice_line_ids.tax_ids:
            data_tax = {tax.name:[]}
            for field_tax in field_mandatory_tax:
                if not tax[field_tax]:
                    data_tax[tax.name].append(tax._fields[field_tax].string)
            if len(data_tax[tax.name]) > 0:
                mandatory_field.append(data_tax)
        return mandatory_field

    #improve part Multi if has multi mean called from ids not 1 record
    #multi is name of invoice 
    def message_warning_submit_document(self,fields_empty, multi=False):
        message = 'Please fill fields below, before Submit Document\n'
        if multi:
            message = 'Please fill fields below, before Submit Document of %s\n' % multi
        for data in fields_empty:
            for category in data:
                if len(data[category]) > 0:
                    message += '%s : ' % (category)
                else:
                    continue
                message += str(data[category]).replace("[", '').replace("]", '').replace("'",'') + " \n"
        return message
    
    def pre_check_invoice(self):
        for inv in self:
            if inv.myinvois_consolidate_id:
                raise ValidationError(_('This invoice is consolidated, you may check the consolidated invoice %s status' % inv.myinvois_consolidate_id.name))
            if inv.company_id.status_partner_validated_tin == 'draft':
                inv.company_id.validate_tin_company()
            # if self.partner_id.status_partner_validated_tin == 'draft':
            #     self.partner_id.validate_tin_partner()
            fields_empty = inv.check_field_submit_mandatory()
            if len(fields_empty) > 0:
                message = inv.message_warning_submit_document(fields_empty)
                raise ValidationError(_(message))
    
    def submit_document_batch(self):
        grouped_invoices = {}
        batch_size = 100
        for invoice in self:
            if invoice.company_id not in grouped_invoices:
                grouped_invoices[invoice.company_id] = self.env['account.move']
            grouped_invoices[invoice.company_id] += invoice

        for company_id, company_invoices in grouped_invoices.items():
            for start in range(0, len(company_invoices), batch_size):
                end = start + batch_size
                batch = company_invoices[start:end]
                batch.submit_document_action()
    
    def submit_document_action(self):
        self.pre_check_invoice()
        #this action will called if all presquite field has been added 
        url = '%s%s' % (self.company_id.request_token_url, "/api/v1.0/documentsubmissions")
        payload = {"documents": []}
        for inv in self:
            data = inv.prepare_data_myinvois()
            base64_str = inv.company_id.convert_json_to_base64(data)
            hash256_str = inv.company_id.hash_json_data(data)
            
            payload["documents"].append({
                                        "format": "JSON",
                                        "documentHash": hash256_str,
                                        "codeNumber": inv.name,
                                        "document": base64_str
                                    })
        response = self.company_id.sync_myinvois(self,"POST", url, payload, raw_payload=data, version=self.company_id.myinv_version())
        if response.status_code == 202:
            response_str = response.json()
            if response_str["submissionUid"] and response_str["acceptedDocuments"]:
                if self.env.context.get('is_from_pos'):
                    time.sleep(3)
                # call this method immediately as the data need to cencel submission
                for inv in self:
                    if len(self) > 1:
                        inv.with_delay().action_get_document_details()
                    else:
                        inv.action_get_document_details()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'type': 'success',
                        'message': _("Document Submitted"),
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'type': 'danger',
                        'message': _("Ops, submit document failed. Please see API logs for the details"),
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
            # self.document_details_sucess_response(response.json)
        return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'danger' if response.status_code != 202 else 'success',
                    'message': _("Ops, submit document failed. Please see API logs for the details") if response.status_code != 202 else _("Document Submitted"),
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
    
    def button_draft(self):
        res = super(AccountMove, self).button_draft()
        if self.myinvois_document_id and self.my_invois_status_submission in ('Submitted', 'Valid'):
            raise ValidationError(_("You cannot reset to draft because the document has already been submitted. \n"
                                    "Please cancel document it first."))
        self.write({
                    'my_invois_uuid': False,
                    'my_invois_id_submission' : False,
                    'myinvois_document_id' : False,
                    'my_invois_qr_code' : False,
                })
        return res
    
    @api.model_create_multi
    def create(self, vals_list):
        
        moves = super().create(vals_list)
        if self.env.context.get('import_file'):
            for each_moves in moves:
                each_moves.update_partner()
        return moves
    
    def update_partner(self):
        vals = {}
        if self.partner_id.vat != self.my_invois_tin_partner and self.my_invois_tin_partner != False:
            vals['vat'] = self.my_invois_tin_partner
        if self.partner_id.my_invois_partner_id_type != self.my_invois_partner_id_type:
            vals['my_invois_partner_id_type'] = self.my_invois_partner_id_type
        if self.partner_id.my_invois_partner_id_value != self.my_invois_partner_id_value:
            vals['my_invois_partner_id_value'] = self.my_invois_partner_id_value

        self.partner_id.write(vals)

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    myinvois_product_classification_code = fields.Char('Product Classification', compute="compute_product_classification_code")
    
    @api.depends('product_id')
    def compute_product_classification_code(self):
        for line in self:
            product_classification = line.product_id.categ_id.get_product_classification_id()
            line.myinvois_product_classification_code = product_classification.code
