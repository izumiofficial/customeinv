from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning
from datetime import timedelta, datetime, date
import json
import base64
from hashlib import sha256
from collections import defaultdict

from odoo.addons.queue_job.exception import RetryableJobError, FailedJobError
import pytz
import qrcode
from io import BytesIO
from pytz import UTC


class MyinvoisConsolidate(models.Model):
    _name = "myinvois.consolidate"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Batch Submit My Invois"

    name = fields.Char(string="Name", default='/',copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    myinvois_consolidate_user_id = fields.Many2one('res.partner', string="Responsible")
    invoice_ids = fields.One2many('account.move', 'myinvois_consolidate_id', string='Invoices', domain="[('state', '=', 'posted'), ('my_invois_uuid', '=', False), ('myinvois_consolidate_id', '=', False)]")
    myinvois_consolidate_date = fields.Date(string="Consolidate Date")
    myinvois_consolidate_state = fields.Selection([
        ('Draft', 'To Submit'),
        ('Submitted', 'Submitted'), ('Valid', 'Valid'),
        ('Invalid', 'Invalid'), ('Cancelled', 'Cancelled')
        ],string="Myinvois Submission Status", default='Draft', tracking=True, copy=False)
    my_invois_uuid = fields.Char(string="UUID Myinvois", copy=False)#for UUID after submit or get document details
    my_invois_id_submission = fields.Char(string="ID Submission", copy=False)#for submision uid after submit or get document details
    my_invois_period_id = fields.Many2one('myinvois.period', string="MyInvois Period")
    myinvois_document_id = fields.Many2one(
        "myinvois.document",
        string="MYInvois Document",
        copy=False
    )
    my_invois_qr_code = fields.Binary(copy=False)

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


    @api.model_create_multi
    def create(self, vals_list):
        vals_list = self.vals_sequence_name(vals_list)
        return super().create(vals_list)
    
    #for sequence name
    def vals_sequence_name(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env["ir.sequence"].next_by_code("myinvois.consolidate")
        return vals_list
    
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
    # because this is consolidate no need value
    def prepare_data_invoice_period(self):
        data = self.my_invois_period_id

        value = data.my_invois_periode_start.strftime("%Y-%m-%d") if data.my_invois_periode_start else "NA"
        invoice_periode_start = self.convert_format_json("StartDate",value)

        value = data.my_invois_periode_end.strftime("%Y-%m-%d") if data.my_invois_periode_end else "NA"
        invoice_periode_end = self.convert_format_json("EndDate",value)
        
        value = data.my_invois_periode_description if data.my_invois_periode_description else "NA"
        invoice_periode_description = self.convert_format_json("Description",value)

        InvoicePeriod = self.merge_data_json("InvoicePeriod",invoice_periode_start,invoice_periode_end,invoice_periode_description)
        
        return InvoicePeriod
    
    # Name of consolidate 
    def prepare_data_id(self):
        value = self.name
        id = self.convert_format_json("ID",value)
        return id

    def prepare_data_issues_date(self):
        value = self.myinvois_consolidate_date.strftime("%Y-%m-%d") if self.myinvois_consolidate_date else ""
        IssueDate = self.convert_format_json("IssueDate",value)
        return IssueDate
    
    # TODO time format
    # consolidate issue time consider now
    def prepare_data_issues_time(self):
        utctime = datetime.now(tz=UTC).strftime("%H:%M:%SZ")
        IssueTime = self.convert_format_json("IssueTime", utctime)
        return IssueTime

    # E-INVOICE VERSION SECTION
    def prepare_data_invoice_type(self):
        value = '01' # always 01 because user can only consolidate invoices (01)
        additional_attributes = {
            "listVersionID" : self.company_id.myinv_version()
        }
        InvoiceTypeCode = self.convert_format_json("InvoiceTypeCode",value,additional_attributes)
        return InvoiceTypeCode
    
    #in consolidate currency get from company
    def prepare_data_documentary_currency(self):
        currency_id = self.invoice_ids.mapped('currency_id')
        if len(currency_id) > 1:
            raise ValidationError(_("All invoice must have same currency"))
        value = self.invoice_ids[0].currency_id.name
        DocumentCurrencyCode = self.convert_format_json("DocumentCurrencyCode",value)
        return DocumentCurrencyCode

    # BILLING REFERENCE (Optional)
    # the reference is Invoice Consolidate itself
    def prepare_data_billing_reference(self):
        # TODO add required or validation ref if empty
        value = "NA" #new field in consolidate so not all ref all invoice into 1 we set it null
        AdditionalDocumentID = self.convert_format_json("ID",value)
        AdditionalDocumentReference = self.merge_data_json("AdditionalDocumentReference",AdditionalDocumentID)
        # if self.my_invois_einvoice_type_id.code == '02':
        #     doc_ref = self.reversed_entry_id
        #     value = doc_ref.my_invois_uuid
        #     InvoiceDocumentReferenceUUID = self.convert_format_json("UUID",value)
        #     value = doc_ref.name
        #     InvoiceDocumentReferenceID = self.convert_format_json("ID",value)
        #     InvoiceDocumentReference = self.merge_data_json("InvoiceDocumentReference",InvoiceDocumentReferenceUUID,InvoiceDocumentReferenceID)
        #     BillingReference = self.merge_data_json("BillingReference",AdditionalDocumentReference,InvoiceDocumentReference)
        # else:
        BillingReference = self.merge_data_json("BillingReference",AdditionalDocumentReference)

        return BillingReference


    # ADDITIONAL DOCUMENT REFERENCE
    # def prepare_data_additional_document(self):
    #     AdditionalDocumentReference = {"AdditionalDocumentReference":list()}
    #     for rec in self.my_invois_additional_doc_ids:
    #         AdditionalDocumentReferenceDict = dict()
    #         value = rec.name
    #         AdditionalDocumentID = self.convert_format_json("ID",value)
    #         value2 = rec.document_type
    #         DocumentType = self.convert_format_json("DocumentType",value2)
    #         AdditionalDocumentReferenceDict.update(**AdditionalDocumentID,**DocumentType)
    #         AdditionalDocumentReference['AdditionalDocumentReference'].append(AdditionalDocumentReferenceDict)

    #     # AdditionalDocumentReference =self.merge_data_json("AdditionalDocumentReference",AdditionalDocumentID,DocumentType)

    #     return AdditionalDocumentReference

    # SUPPLIER SECTION Company partner
    
    def prepare_data_accounting_supplier(self):
        # additional_account = self.prepare_additional_account()
        SupplierParty = self.prepare_data_party_supplier()
        AccountingSupplierParty = self.merge_data_json("AccountingSupplierParty",SupplierParty)

        return AccountingSupplierParty
    
    # TODO OPTIONAL
    # def prepare_additional_account(self)
    # getting from partner company
    def prepare_data_party_supplier(self):
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
        email = self.convert_format_json("ElectronicMail",value)
        Contact = self.merge_data_json("Contact",phone)

        Party = self.merge_data_json("Party",IndustryClassificationCode,PartyIdentification,PostalAddress,PartyLegalEntity,Contact)

        return Party

    # BUYER SECTION -> Customer partner

    def prepare_data_accounting_customer(self):
        CustomerParty = self.prepare_data_party_customer()
        AccountingCustomerParty = self.merge_data_json("AccountingCustomerParty",CustomerParty)
        return AccountingCustomerParty

    #special Case of customer 
    #in consolidate is fixed
    def prepare_data_party_customer(self):
        consolidated_partner_id = self.env.company.my_invois_consolidated_partner_id
        # PARTY INDENTIFICATION
        # vat = consolidated_partner_id.vat 
        vat = "EI00000000010"
        additional_attributes = {
            "schemeID" : "TIN"
        }
        party_identification_id = self.convert_format_json("ID",vat,additional_attributes)
        # brn = consolidated_partner_id.my_invois_partner_id_value
        brn = "NA"
        additional_attributes = {
            "schemeID" : "BRN"
        }

        party_identification_id_2 = self.convert_format_json("ID",brn,additional_attributes)
        value = self.company_id.extract_sst(consolidated_partner_id.my_invois_sst) if consolidated_partner_id.my_invois_sst else 'NA'
        additional_attributes = {
            "schemeID" : "SST"
        }
        party_sst = self.convert_format_json("ID",value,additional_attributes)
        
        PartyIdentification = {'PartyIdentification' : [party_identification_id, party_identification_id_2, party_sst]}

        # POSTAL ADDRESS 
        value = consolidated_partner_id.street
        city = self.convert_format_json("CityName",value)
        # optional
        # value = partner.zip
        # postal_zone = self.convert_format_json("PostalZone",value)
        value = consolidated_partner_id.state_id.myinvois_state_code
        country_subentity = self.convert_format_json("CountrySubentityCode",value)
        value = consolidated_partner_id.country_id.myinvois_code
        additional_attributes = {
            "listID": "ISO3166-1",
            "listAgencyID": "6"
        }
        IdentificationCode = self.convert_format_json("IdentificationCode",value,additional_attributes)
        country = self.merge_data_json("Country",IdentificationCode)
        # ADRESSS LINE
        Line = self.convert_format_json("Line",value)
        AddressLine = self.merge_data_json("AddressLine",Line)

        PostalAddress = self.merge_data_json("PostalAddress",city,country_subentity,AddressLine,country)
        
        # PARTY LEGAL ENTITY
        customer_name = consolidated_partner_id.name
        RegistrationName = self.convert_format_json("RegistrationName",customer_name)
        PartyLegalEntity = self.merge_data_json("PartyLegalEntity",RegistrationName)

        # CONTACT
        # value = partner.phone
        phone = self.convert_format_json("Telephone",self.env.company.extract_phone_number(consolidated_partner_id.phone))
        # value = partner.email
        # optional
        # email = self.convert_format_json("ElectronicMail",value)
        Contact = self.merge_data_json("Contact",phone)

        Party = self.merge_data_json("Party",PostalAddress,PartyLegalEntity,PartyIdentification,Contact)

        return Party

    # DELIVERY SECTION 
    # Optional?
    def prepare_data_delivery(self):
        DeliveryParty = self.prepare_data_delivery_party()
        Delivery = self.merge_data_json("Delivery",DeliveryParty)
        return Delivery

    def prepare_data_delivery_party(self):
        partner = self.env.company.my_invois_consolidated_partner_id #use partner shiping from 1st invoice?
        # PARTY LEGAL ENTITY
        value = partner.name
        RegistrationName = self.convert_format_json("RegistrationName",value)
        PartyLegalEntity = self.merge_data_json("PartyLegalEntity",RegistrationName)

        # PARTY INDENTIFICATION
        # value = partner.vat
        value = "EI00000000010"
        additional_attributes = {
            "schemeID" : "TIN"
        }
        party_identification_id = self.convert_format_json("ID",value,additional_attributes)
        
        # value = partner.my_invois_partner_id_value
        value = "NA"
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

    

    def merge_tax_groups(self, data):
        # Initialize a defaultdict to hold the merged data
        merged_data = defaultdict(lambda: {
            "group_key": None,
            "tax_group_id": None,
            "tax_group_name": None,
            "tax_group_amount": 0,
            "tax_group_base_amount": 0,
            "formatted_tax_group_amount": "",
            "formatted_tax_group_base_amount": ""
        })

        # Merge the data
        for group in data:
            for item in group:
                tax_group_id = item["tax_group_id"]
                
                if merged_data[tax_group_id]["group_key"] is None:
                    merged_data[tax_group_id]["group_key"] = item["group_key"]
                    merged_data[tax_group_id]["tax_group_id"] = item["tax_group_id"]
                    merged_data[tax_group_id]["tax_group_name"] = item["tax_group_name"]
                
                merged_data[tax_group_id]["tax_group_amount"] += item["tax_group_amount"]
                merged_data[tax_group_id]["tax_group_base_amount"] += item["tax_group_base_amount"]

        # Convert merged data to a list of dictionaries
        merged_data_list = []
        for tax_group in merged_data.values():
            # Formatting the amounts as currency
            tax_group["formatted_tax_group_amount"] = "${:,.2f}".format(tax_group["tax_group_amount"])
            tax_group["formatted_tax_group_base_amount"] = "${:,.2f}".format(tax_group["tax_group_base_amount"])
            merged_data_list.append(tax_group)
        
        return merged_data_list


    def get_tax_totals(self):
        return self.invoice_ids.get_tax_totals()

    # TAX TOTAL
    def prepare_data_tax_total(self):
        tax_group = self.get_tax_totals()
        TaxAmount = self.prepare_data_tax_amount(tax_group)
        TaxSubtotal = self.prepare_data_tax_subtotal(tax_group)

        TaxTotal = self.merge_data_json("TaxTotal",TaxAmount,TaxSubtotal)
        return TaxTotal
    
    # TAX AMOUNT 
    def prepare_data_tax_amount(self,tax_group):
        value = sum(tax_group.values())
        additional_attributes = {
            "currencyID" : self.invoice_ids[0].currency_id.name #update for consolidated 
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
                "currencyID" : self.invoice_ids[0].currency_id.name
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
    # because this is consit of some of invoice 
    def prepare_data_legalmonetary_total(self):
        LegalMonetaryTotal = {}
        # TAX EXCLUSIVE AMOUNT
        # value = self.amount_untaxed
        amount_untaxed = sum(line.amount_untaxed for line in self.invoice_ids)
        currency_name = self.invoice_ids[0].currency_id.name
        cuurency_id = self.invoice_ids[0].currency_id
        additional_attributes = {
            "currencyID" : currency_name
        }
        TaxExclusiveAmount  = self.convert_format_json("TaxExclusiveAmount",amount_untaxed,additional_attributes)


        value = sum(line.amount_total for line in self.invoice_ids)
        # TAX INCLUSIVE AMOUNT
        # value = self.amount_total_signed
        amount_total_signed = sum(line.amount_total_signed for line in self.invoice_ids)
        TaxInclusiveAmount = self.convert_format_json("TaxInclusiveAmount", value, additional_attributes)

        # TOTAL PAYABLE AMOUNT
        # need to check later
        amount_tax = sum(line.amount_total_signed for line in self.invoice_ids)
        PayableAmount = self.convert_format_json("PayableAmount", value, additional_attributes)

        LegalMonetaryTotal  = self.merge_data_json("LegalMonetaryTotal", TaxExclusiveAmount, TaxInclusiveAmount,PayableAmount)
        return LegalMonetaryTotal
    
    def prepare_tax_total(self, line,tax):
        tax_total = 0
        if tax:
            tax_result = tax._origin.with_context(force_sign=1).compute_all(line.price_subtotal) or {}
        else:
            tax_result = line.tax_ids._origin.with_context(force_sign=1).compute_all(line.price_subtotal) or {}

        if 'taxes' in tax_result:
            for tax in tax_result['taxes']:
                tax_total += abs(tax['amount'])
        return tax_total


    def prepare_data_invoice_line_tax_subtotal(self,data):
        TaxSubtotal = {"TaxSubtotal":list()}
        for each_invoice_line in data.invoice_line_ids:
            for tax in each_invoice_line.tax_ids:
                TaxSubtotalDict = dict()
                TaxCategoryDict = dict()
                # TODO need discuss value amount
                value = self.prepare_tax_total(each_invoice_line,tax)
                additional_attributes = {
                    "currencyID" : self.invoice_ids[0].currency_id.name
                }
                TaxableAmount = self.convert_format_json("TaxableAmount",each_invoice_line.price_subtotal,additional_attributes)
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
                TaxExemptionReason = self.convert_format_json("TaxExemptionReason","NA")
                TaxCategoryDict.update(TaxExemptionReason)
                TaxSubtotalDict.update(TaxCategory)
                TaxCategory["TaxCategory"].append(TaxCategoryDict)
                
                TaxSubtotal["TaxSubtotal"].append(TaxSubtotalDict)
        return TaxSubtotal

    #in consolidate this is must use an invoice
    #and be called by looping
    # data in here is account.move
    def prepare_data_invoice_line(self):
        InvoiceLine = {"InvoiceLine":list()}
        for data in self.invoice_ids:
            return_dict = {}
            
            ID = self.convert_format_json("ID",str(data.id))
            return_dict.update(ID)

            InvoicedQuantity_UnitCode = {"unitCode" : "C62"}
            InvoicedQuantity = self.convert_format_json("InvoicedQuantity",1,InvoicedQuantity_UnitCode)#always 1
            return_dict.update(InvoicedQuantity)

            currencyID = {"currencyID" : data.currency_id.name}
            LineExtensionAmount = self.convert_format_json("LineExtensionAmount",sum(data.invoice_line_ids.mapped('price_subtotal')),currencyID)
            return_dict.update(LineExtensionAmount)

            # TODO AllowanceCharge OPTIONAL
            
            tax_total = 0.0
            for line in data.invoice_line_ids:
                if line.tax_ids:
                    tax_total += sum(line.tax_ids.mapped('amount'))
            
            TaxTotal_TaxAmount = self.convert_format_json("TaxAmount",tax_total,currencyID)
            TaxSubtotal = self.prepare_data_invoice_line_tax_subtotal(data)
            

            TaxTotal = self.merge_data_json("TaxTotal",TaxTotal_TaxAmount,TaxSubtotal)
            return_dict.update(TaxTotal)

            additional_attributes = {
                "listID" : "CLASS"
            }
            ItemClassificationCode = self.convert_format_json("ItemClassificationCode","004",additional_attributes) #consolidate 004
            CommodityClassification = self.merge_data_json("CommodityClassification",ItemClassificationCode)
            Description = self.convert_format_json("Description",data.name)
            Item = self.merge_data_json("Item",CommodityClassification,Description)
            return_dict.update(Item)

            Price_val = self.convert_format_json("PriceAmount",sum(data.invoice_line_ids.mapped('price_unit')),currencyID)
            Price = self.merge_data_json("Price",Price_val)
            return_dict.update(Price)

            # TODO TANYA MAS HAJI
            ItemPriceExtension_val = self.convert_format_json("Amount",data.amount_untaxed,currencyID)
            ItemPriceExtension = self.merge_data_json("ItemPriceExtension",ItemPriceExtension_val)
            return_dict.update(ItemPriceExtension)
            
            InvoiceLine["InvoiceLine"].append(return_dict)
        
        # invoiceLine = self.merge_data_json("InvoiceLine",invoice_line)
        return InvoiceLine

    def prepare_data_myinvois(self):
        Invoice = {
            "_D": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
            "_A": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "_B": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        }
        
        for inv in self:
            ID = inv.prepare_data_id()
            # InvoicePeriod = self.prepare_data_invoice_period()
            IssueDate = inv.prepare_data_issues_date() #
            IssueTime = inv.prepare_data_issues_time() #
            InvoiceTypeCode = inv.prepare_data_invoice_type() #
            DocumentCurrencyCode = inv.prepare_data_documentary_currency() #
            BillingReference = inv.prepare_data_billing_reference()
            AccountingSupplierParty = inv.prepare_data_accounting_supplier() #
            AccountingCustomerParty = inv.prepare_data_accounting_customer() #
            Delivery = inv.prepare_data_delivery() #
            TaxTotal = inv.prepare_data_tax_total() # 
            LegalMonetaryTotal = inv.prepare_data_legalmonetary_total() #
            InvoiceLine = inv.prepare_data_invoice_line() #
            Invoice.update(self.merge_data_json("Invoice",ID,IssueDate,IssueTime,BillingReference,
                        InvoiceTypeCode,DocumentCurrencyCode,AccountingSupplierParty,
                        AccountingCustomerParty,Delivery,TaxTotal,LegalMonetaryTotal,InvoiceLine))
            # digital sign certificate 
            version = self.company_id.myinv_version()
            if version == '1.1' and inv.invoice_ids:
                sign_element = inv.company_id.sign_document(Invoice)
                Invoice['Invoice'][0].update(sign_element)
        return Invoice
    
    def pre_check_consolidation(self):
        if self.env.company.status_partner_validated_tin == 'draft':
            self.env.company.validate_tin_company()
        #part loop invoice to check if can submit it or not each of them
        message = ''
        for each_invoice in self.invoice_ids:
            fields_empty = each_invoice.check_field_submit_consolidate_mandatory()
            if len(fields_empty) > 0:
                message += each_invoice.message_warning_submit_document(fields_empty, each_invoice.name) + '\n'
            #     raise ValidationError(_(message))

        currency_invoice_ids = self.invoice_ids.mapped('currency_id')
        if len(currency_invoice_ids) > 1:
            message += 'All invoice must have same currency\n'

        if message:
            raise ValidationError(_(message))
    
    def submit_consolidated(self):
        self.pre_check_consolidation()
        
        #this action will called if all presquite field has been added 
        url = '%s%s' % (self.env.company.request_token_url, "/api/v1.0/documentsubmissions")
        data = self.prepare_data_myinvois()
        print(json.dumps(data,indent=4))
        base64_str = self.company_id.convert_json_to_base64(data)
        hash256_str = self.company_id.hash_json_data(data)
        payload = { "documents": [{
                                    "format": "JSON",
                                    "documentHash": hash256_str,
                                    "codeNumber": self.name,
                                    "document": base64_str
                                }]
                }
        response = self.env.company.sync_myinvois(self, "POST", url, payload, raw_payload=data)
        print(">>>> response",response.json)
        if response.status_code == 202:
            response_str = response.json()
            if response_str["submissionUid"] and response_str["acceptedDocuments"]:
                uuids = ', '.join([doc["uuid"] for doc in response_str["acceptedDocuments"]])
                submission_id = response_str["submissionUid"]
                self.write({
                    'my_invois_uuid': uuids,
                    'my_invois_id_submission' : submission_id,
                    'myinvois_consolidate_state': 'Submitted'
                })
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



    def test_submit_doc_consolidate(self):
        data = {
            "_D": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
            "_A": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "_B": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            "Invoice": [
                {
                "ID": [
                    {
                    "_": self.name + '/090'
                    }
                ],
                "DocumentCurrencyCode": [
                    {
                    "_": "USD"
                    }
                ],
                "IssueDate": [
                    {
                    "_": "2024-06-27"
                    }
                ],
                "IssueTime": [
                    {
                    "_": "15:30:00Z"
                    }
                ],
                "InvoiceTypeCode": [
                    {
                    "_": "01",
                    "listVersionID": "1.1"
                    }
                ],
                "InvoicePeriod": [
                    {
                    "StartDate": [
                        {
                        "_": ""
                        }
                    ],
                    "EndDate": [
                        {
                        "_": ""
                        }
                    ],
                    "Description": [
                        {
                        "_": ""
                        }
                    ]
                    }
                ],
                "BillingReference": [
                    {
                    "AdditionalDocumentReference": [
                        {
                        "ID": [
                            {
                            "_": "-"
                            }
                        ]
                        }
                    ]
                    }
                ],
                "AccountingSupplierParty": [
                    {
                    "Party": [
                        {
                        "IndustryClassificationCode": [
                            {
                            "_": "01111",
                            "name": "Growing of maize"
                            }
                        ],
                        "PartyIdentification": [
                            {
                            "ID": [
                                {
                                "_": "C25469231010",
                                "schemeID": "TIN"
                                }
                            ]
                            },
                            {
                            "ID": [
                                {
                                "_": "201701003951",
                                "schemeID": "BRN"
                                }
                            ]
                            }
                        ],
                        "PostalAddress": [
                            {
                            "CityName": [
                                {
                                "_": "Kuala Lumpur"
                                }
                            ],
                            "PostalZone": [
                                {
                                "_": "50480"
                                }
                            ],
                            "CountrySubentityCode": [
                                {
                                "_": "14"
                                }
                            ],
                            "AddressLine": [
                                {
                                "Line": [
                                    {
                                    "_": "Lot 66"
                                    }
                                ]
                                },
                                {
                                "Line": [
                                    {
                                    "_": "Bangunan Merdeka"
                                    }
                                ]
                                },
                                {
                                "Line": [
                                    {
                                    "_": "Persiaran Jaya"
                                    }
                                ]
                                }
                            ],
                            "Country": [
                                {
                                "IdentificationCode": [
                                    {
                                    "_": "MYS",
                                    "listID": "ISO3166-1",
                                    "listAgencyID": "6"
                                    }
                                ]
                                }
                            ]
                            }
                        ],
                        "PartyLegalEntity": [
                            {
                            "RegistrationName": [
                                {
                                "_": "AMS Setia Jaya Sdn. Bhd."
                                }
                            ]
                            }
                        ],
                        "Contact": [
                            {
                            "Telephone": [
                                {
                                "_": "+60-123456789"
                                }
                            ],
                            "ElectronicMail": [
                                {
                                "_": "general.ams@supplier.com"
                                }
                            ]
                            }
                        ]
                        }
                    ]
                    }
                ],
                "AccountingCustomerParty": [
                    {
                        "Party": [
                            {
                                "PostalAddress": [
                                    {
                                        "CityName": [
                                            {
                                                "_": "NA"
                                            }
                                        ],
                                        "CountrySubentityCode": [
                                            {
                                                "_": "NA"
                                            }
                                        ],
                                        "AddressLine": [
                                            {
                                                "Line": [
                                                    {
                                                        "_": "MYS"
                                                    }
                                                ]
                                            }
                                        ],
                                        "Country": [
                                            {
                                                "IdentificationCode": [
                                                    {
                                                        "_": "MYS",
                                                        "listID": "ISO3166-1",
                                                        "listAgencyID": "6"
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ],
                                "PartyLegalEntity": [
                                    {
                                        "RegistrationName": [
                                            {
                                                "_": "General Public"
                                            }
                                        ]
                                    }
                                ],
                                "PartyIdentification": [
                                    {
                                        "ID": [
                                            {
                                                "_": "EI00000000010",
                                                "schemeID": "TIN"
                                            }
                                        ]
                                    },
                                    {
                                        "ID": [
                                            {
                                                "_": "EI00000000010",
                                                "schemeID": "BRN"
                                            }
                                        ]
                                    }
                                ],
                                "Contact": [
                                    {
                                        "Telephone": [
                                            {
                                                "_": "NA"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "Delivery": [
                    {
                    "DeliveryParty": [
                        {
                        "PartyLegalEntity": [
                            {
                            "RegistrationName": [
                                {
                                "_": "Greenz Sdn. Bhd."
                                }
                            ]
                            }
                        ],
                        "PostalAddress": [
                            {
                            "CityName": [
                                {
                                "_": "Kuala Lumpur"
                                }
                            ],
                            "PostalZone": [
                                {
                                "_": "50480"
                                }
                            ],
                            "CountrySubentityCode": [
                                {
                                "_": "14"
                                }
                            ],
                            "AddressLine": [
                                {
                                "Line": [
                                    {
                                    "_": "Lot 66"
                                    }
                                ]
                                },
                                {
                                "Line": [
                                    {
                                    "_": "Bangunan Merdeka"
                                    }
                                ]
                                },
                                {
                                "Line": [
                                    {
                                    "_": "Persiaran Jaya"
                                    }
                                ]
                                }
                            ],
                            "Country": [
                                {
                                "IdentificationCode": [
                                    {
                                    "_": "MYS",
                                    "listID": "ISO3166-1",
                                    "listAgencyID": "6"
                                    }
                                ]
                                }
                            ]
                            }
                        ],
                        "PartyIdentification": [
                            {
                            "ID": [
                                {
                                "_": "C2584563200",
                                "schemeID": "TIN"
                                }
                            ]
                            },
                            {
                            "ID": [
                                {
                                "_": "201901234567",
                                "schemeID": "BRN"
                                }
                            ]
                            }
                        ]
                        }
                    ],
                    "Shipment": [
                        {
                        "ID": [
                            {
                            "_": "1234"
                            }
                        ],
                        "FreightAllowanceCharge": [
                            {
                            "ChargeIndicator": [
                                {
                                "_": True
                                }
                            ],
                            "AllowanceChargeReason": [
                                {
                                "_": "Service charge"
                                }
                            ],
                            "Amount": [
                                {
                                "_": 100,
                                "currencyID": "USD"
                                }
                            ]
                            }
                        ]
                        }
                    ]
                    }
                ],
                "PaymentMeans": [
                    {
                    "PaymentMeansCode": [
                        {
                        "_": "01"
                        }
                    ],
                    "PayeeFinancialAccount": [
                        {
                        "ID": [
                            {
                            "_": "1234567890123"
                            }
                        ]
                        }
                    ]
                    }
                ],
                "PaymentTerms": [
                    {
                    "Note": [
                        {
                        "_": "Payment method is cash"
                        }
                    ]
                    }
                ],
                "PrepaidPayment": [
                    {
                    "ID": [
                        {
                        "_": "E12345678912"
                        }
                    ],
                    "PaidAmount": [
                        {
                        "_": 1.00,
                        "currencyID": "USD"
                        }
                    ],
                    "PaidDate": [
                        {
                        "_": "2000-01-01"
                        }
                    ],
                    "PaidTime": [
                        {
                        "_": "12:00:00Z"
                        }
                    ]
                    }
                ],
                "AllowanceCharge": [
                    {
                    "ChargeIndicator": [
                        {
                        "_": False
                        }
                    ],
                    "AllowanceChargeReason": [
                        {
                        "_": "Sample Description"
                        }
                    ],
                    "Amount": [
                        {
                        "_": 100,
                        "currencyID": "USD"
                        }
                    ]
                    },
                    {
                    "ChargeIndicator": [
                        {
                        "_": True
                        }
                    ],
                    "AllowanceChargeReason": [
                        {
                        "_": "Service charge"
                        }
                    ],
                    "Amount": [
                        {
                        "_": 100,
                        "currencyID": "USD"
                        }
                    ]
                    }
                ],
                "TaxTotal": [
                    {
                    "TaxAmount": [
                        {
                        "_": 87.63,
                        "currencyID": "USD"
                        }
                    ],
                    "TaxSubtotal": [
                        {
                        "TaxableAmount": [
                            {
                            "_": 87.63,
                            "currencyID": "USD"
                            }
                        ],
                        "TaxAmount": [
                            {
                            "_": 87.63,
                            "currencyID": "USD"
                            }
                        ],
                        "TaxCategory": [
                            {
                            "ID": [
                                {
                                "_": "01"
                                }
                            ],
                            "TaxScheme": [
                                {
                                "ID": [
                                    {
                                    "_": "OTH",
                                    "schemeID": "UN/ECE 5153",
                                    "schemeAgencyID": "6"
                                    }
                                ]
                                }
                            ]
                            }
                        ]
                        }
                    ]
                    }
                ],
                "LegalMonetaryTotal": [
                    {
                    "LineExtensionAmount": [
                        {
                        "_": 1436.50,
                        "currencyID": "USD"
                        }
                    ],
                    "TaxExclusiveAmount": [
                        {
                        "_": 1436.50,
                        "currencyID": "USD"
                        }
                    ],
                    "TaxInclusiveAmount": [
                        {
                        "_": 1436.50,
                        "currencyID": "USD"
                        }
                    ],
                    "AllowanceTotalAmount": [
                        {
                        "_": 1436.50,
                        "currencyID": "USD"
                        }
                    ],
                    "ChargeTotalAmount": [
                        {
                        "_": 1436.50,
                        "currencyID": "USD"
                        }
                    ],
                    "PayableRoundingAmount": [
                        {
                        "_": 0.30,
                        "currencyID": "USD"
                        }
                    ],
                    "PayableAmount": [
                        {
                        "_": 1436.50,
                        "currencyID": "USD"
                        }
                    ]
                    }
                ],
                "InvoiceLine": [
                    {
                    "ID": [
                        {
                        "_": "1234"
                        }
                    ],
                    "InvoicedQuantity": [
                        {
                        "_": 1,
                        "unitCode": "C62"
                        }
                    ],
                    "LineExtensionAmount": [
                        {
                        "_": 1436.50,
                        "currencyID": "USD"
                        }
                    ],
                    "AllowanceCharge": [
                        {
                        "ChargeIndicator": [
                            {
                            "_": False
                            }
                        ],
                        "AllowanceChargeReason": [
                            {
                            "_": "Sample Description"
                            }
                        ],
                        "MultiplierFactorNumeric": [
                            {
                            "_": 0.15
                            }
                        ],
                        "Amount": [
                            {
                            "_": 100,
                            "currencyID": "USD"
                            }
                        ]
                        },
                        {
                        "ChargeIndicator": [
                            {
                            "_": True
                            }
                        ],
                        "AllowanceChargeReason": [
                            {
                            "_": "Sample Description"
                            }
                        ],
                        "MultiplierFactorNumeric": [
                            {
                            "_": 0.10
                            }
                        ],
                        "Amount": [
                            {
                            "_": 100,
                            "currencyID": "USD"
                            }
                        ]
                        }
                    ],
                    "TaxTotal": [
                        {
                        "TaxAmount": [
                            {
                            "_": 1460.50,
                            "currencyID": "USD"
                            }
                        ],
                        "TaxSubtotal": [
                            {
                            "TaxableAmount": [
                                {
                                "_": 1460.50,
                                "currencyID": "USD"
                                }
                            ],
                            "TaxAmount": [
                                {
                                "_": 1460.50,
                                "currencyID": "USD"
                                }
                            ],
                            "TaxCategory": [
                                {
                                "ID": [
                                    {
                                    "_": "01"
                                    }
                                ],
                                "Percent": [
                                    {
                                    "_": 6.00
                                    }
                                ],
                                "TaxScheme": [
                                    {
                                    "ID": [
                                        {
                                        "_": "OTH",
                                        "schemeID": "UN/ECE 5153",
                                        "schemeAgencyID": "6"
                                        }
                                    ]
                                    }
                                ]
                                }
                            ]
                            }
                        ]
                        }
                    ],
                    "Item": [
                        {
                        "CommodityClassification": [
                            {
                            "ItemClassificationCode": [
                                {
                                "_": "001",
                                "listID": "CLASS"
                                }
                            ]
                            }
                            
                        ],
                        "Description": [
                            {
                            "_": "Laptop Peripherals"
                            }
                        ]
                        }
                    ],
                    "Price": [
                        {
                        "PriceAmount": [
                            {
                            "_": 17,
                            "currencyID": "USD"
                            }
                        ]
                        }
                    ],
                    "ItemPriceExtension": [
                        {
                        "Amount": [
                            {
                            "_": 100,
                            "currencyID": "USD"
                            }
                        ]
                        }
                    ]
                    }
                ]
                }
            ]
        }
        # data = self.prepare_data_myinvois()
        print(">>> data", json.dumps(data, indent=4))
        base64_str = self.convert_json_to_base64(data)
        hash256_str = self.hash_json_data(data)
        url = 'https://preprod-api.myinvois.hasil.gov.my/api/v1.0/documentsubmissions'
        payload = {
            "documents": [
                {
                    "format": "JSON",
                    "documentHash": hash256_str,
                    "codeNumber": self.name  + '/04',
                    "document": base64_str
                }
            ]
        }
        res = self.env.company.sync_myinvois(self, "POST", url, payload)
        if res.status_code == 202:
            response_str = self.parse_response_string(res.text)
            if response_str["acceptedDocuments"] and response_str["submissionUid"]:
                uuids = ', '.join([doc["uuid"] for doc in response_str["acceptedDocuments"]])
                submission_id = response_str["submissionUid"]
                self.write({
                    'my_invois_uuid': uuids,
                    'my_invois_id_submission' : submission_id,
                })
        return res
    
    def parse_response_string(self,response_str):
        # Convert single quotes to double quotes for JSON compatibility
        json_compatible_str = response_str.replace("'", '"')
        # Convert the string to a dictionary
        response_dict = json.loads(json_compatible_str)
        return response_dict

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
            'my_invois_validated_date': validate_date,
            'my_invois_cancelled_date': cancel_date,
            'my_invois_reject_date': reject_date,
            'my_invois_total_discount': response.get('totalDiscount'),
            'my_invois_total_ori_sale': response.get('totalOriginalSales'),
            'my_invois_total_ori_discount': response.get('totalOriginalDiscount'),
            'my_invois_net_ori_amount': response.get('netOriginalAmount'),
            'my_invois_total_ori': response.get('totalOriginal'),
            'my_invois_net_amount': response.get('netAmount'),
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
                'my_invois_id_submission': response.get('submissionUid'),
                'myinvois_consolidate_state': response.get('status')
            })
            self.generate_qr_code()

        return document_exist_id
    
            
    def requirement_document_invois(self):
        warning_msg = ""
        if not self.my_invois_uuid:
            warning_msg += "UUID Document\n"
        if warning_msg:
            if self.env.context.get("job_uuid", False):
                raise FailedJobError(_("Please input %s" % ", ".join(warning_msg)))
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
    
    def cancel_myinvois_doc(self):
        """ Cancel myinvois wizard """
        self.ensure_one()
        form = self.env.ref("pc_myinvois.cancel_myinvois_wizard_form_view")
        context = dict(self.env.context or {})
        context["model"] = 'myinvois.consolidate'
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
