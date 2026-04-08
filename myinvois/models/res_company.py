import json
import logging
from datetime import timedelta, datetime, timezone
import requests
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.queue_job.exception import RetryableJobError, FailedJobError
import traceback
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.primitives import serialization
import base64
from requests.adapters import HTTPAdapter
import ssl
import re


_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    # Company level QuickBooks Configuration fields
    client_id = fields.Char(help="The client ID you obtain from the MyInvois.", string="Client ID")
    client_secret = fields.Char(help="The client secret you obtain from the MyInvois.")

    client_credentials = fields.Char(help="User authenticate client credential, ex:client_credentials",
        default="client_credentials")
    scope = fields.Char('Authorization Token URL', help="information on scope granted to token",
        default="InvoicingAPI")
    token_type = fields.Char(string="Token Type", )
    request_token_url = fields.Char(default="https://", help="MyInvois API URIs, use access token to call MyInvois API's",
                         string="Instance URL")

    # used for api calling, generated during authorization process.
    myinvois_access_token = fields.Char('Access Token', help="The token that must be used to access the MyInvois API.", readonly=True)
    expire_token = fields.Datetime('Expire Token', help="The expire token access", readonly=True)

    status_partner_validated_tin = fields.Selection(related='partner_id.status_partner_validated_tin')
    last_check_validate_tin = fields.Datetime(related='partner_id.last_check_validate_tin')


    my_invois_partner_id_type = fields.Selection(string="My Invois Partner ID Type", selection=[('nric', 'NRIC'),
                                                     ('pass_num', 'Passport Number'),
                                                     ('brn', 'Bussines Register Number (BRN)'),
                                                     ('army', 'Army Number')], compute='_compute_myinvois_id', inverse='_inverse_id_type')
    
    my_invois_partner_id_value = fields.Char(string="My Invois Partner ID Value", compute='_compute_myinvois_id', inverse='_inverse_id_value')

    # Configuration
    my_invois_product_bill_id = fields.Many2one('product.product', string='MY Invois Product Bill')
    my_invois_consolidated_partner_id = fields.Many2one('res.partner', 'Consolidate Invoice Partner Config')
    is_malaysia_country = fields.Boolean(compute="_compute_is_malaysia")
    my_invois_private_key = fields.Text()
    my_invois_portal_url = fields.Char()
    my_invois_p12 = fields.Binary('Digital Certificate')
    my_invois_p12_pin = fields.Char("Digital Certificate PIN")
    my_invois_p12_fname = fields.Char()

    def extract_phone_number(self, phone):
        # This pattern matches any digit or the plus sign
        pattern = r'[+\d]+'
        # Join all matched parts to get a clean number
        return ''.join(re.findall(pattern, phone))

    def extract_sst(self, sst):
        # This pattern matches any uppercase/lowercase letters or digits
        pattern = r'[A-Za-z0-9]+'
        # Join all matched parts to get a clean reference string
        return ''.join(re.findall(pattern, sst))

    def _compute_is_malaysia(self):
        for record in self:
            record.is_malaysia_country = False
            if record.partner_id.country_id:
                if record.partner_id.country_id == record.env.ref('base.my'):
                    record.is_malaysia_country = True
    
    def full_chain_request(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        cert_path = "/tmp/cert.pem"          # Path to your client certificate
        key_path = "/tmp/private_key.pem"    # Path to your private key
        chain_path = "/tmp/full_chain.pem"
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)  # Load client cert and private key
        context.load_verify_locations(cafile=chain_path)
        class SSLAdapter(HTTPAdapter):
            def __init__(self, context):
                self.context = context
                super().__init__()

            def init_poolmanager(self, *args, **kwargs):
                kwargs['ssl_context'] = self.context  # Pass the SSL context to the pool manager
                return super().init_poolmanager(*args, **kwargs)

        # Create a requests session
        session = requests.Session()

        # Mount the custom adapter to the session for HTTPS requests
        session.mount('https://', SSLAdapter(context))
        return session

    def myinv_version(self):
        if self.my_invois_p12 and self.my_invois_p12_pin:
            return '1.1'
        return '1.0'
    
    def validate_tin_company(self):
        self.ensure_one()
        return self.partner_id.validate_tin_partner(company=self)

    def _inverse_id_type(self):
        for company in self:
            company.partner_id.my_invois_partner_id_type = company.my_invois_partner_id_type

    def _inverse_id_value(self):
        for company in self:
            company.partner_id.my_invois_partner_id_value = company.my_invois_partner_id_value

    def create_log(self, url, payload, records, response, raw_payload=False):
        logs = self.env['myinvois.log']
        for record in records:
            logs += self.env['myinvois.log'].create({
                'name': url,
                'my_invois_payload': str(payload),
                'res_id': record.id,
                'res_model': record._name,
                'my_invois_date': datetime.now(),
                'my_invois_status_code': response.status_code,
                'raw_payload': raw_payload
            })
        return logs
    
    def _compute_myinvois_id(self):
        for company in self.filtered(lambda company: company.partner_id):
            if company.partner_id.my_invois_partner_id_type:
                company.my_invois_partner_id_type = company.partner_id.my_invois_partner_id_type
            if company.partner_id.my_invois_partner_id_value:
                company.my_invois_partner_id_value = company.partner_id.my_invois_partner_id_value

    def sync_myinvois(self, record, method, url, payload, headers=False, raw_payload=False, version=False):
        auth_token = self.myinvois_access_token
        
        if not headers:
            headers = {'Authorization':auth_token, 'X-Rate-Limit-Remaining':'900'}
            # if 'submission' in url.lower():
                # session = self.full_chain_request()
            #     response = session.post(url, headers=headers, json=payload)
            #     print()
            # else:
            response = requests.request(method, url, headers=headers, json=payload)
            
        else:
            response = requests.request(method, url, headers=headers, data=payload)
        log_id = False
        try:
            # use try becuase sometime response cant be converted to json even tho it success
            data = response.json()
            # invoice submission API
            accepted_docs = data.get('acceptedDocuments', [])
            rejected_docs = data.get('rejectedDocuments', [])
            submissionUid = data.get('submissionUid')
            all_docs = accepted_docs+rejected_docs
            for doc in all_docs:
                rec = record.filtered(lambda r:r.name == doc.get('invoiceCodeNumber'))
                if rec:
                    log_id = self.create_log(url, payload, rec, response, raw_payload)
                    rec.write({
                        'my_invois_uuid': doc.get('uuid'),
                        'my_invois_id_submission' : submissionUid,
                        'my_invois_is_consolidated' : True,
                        'my_invois_version': version
                    })

        except Exception as e:
            print()

        if not log_id:
            log_id = self.create_log(url, payload, record, response, raw_payload)
        try:
            msg = _('API status code %s', log_id._get_log_link())
            for rec in record:
                rec.message_post(body=msg)
            log_id.write({
                'my_invois_response': response.json()
            })
           
        except Exception as e:
            # just continue
            print()

        # only auto retyable when triggered by jobqueue
        if response.status_code == 401:
            self.get_access_token()
        if self.env.context.get('job_uuid', False):
            if response.status_code >= 500:
                raise RetryableJobError(_("MyInvois API Down %s %s" % (response.status_code, response.reason)))
            elif response.status_code == 429:
                raise RetryableJobError(_("Rate Limit %s %s" % (response.status_code, response.reason)))
        return response

    def sanitize_data(self, field_to_sanitize):
        '''
            This method sanitizes the data to remove UPPERCASE and 
            spaces between field chars
            @params : field_to_sanitize(char)
            @returns : field_to_sanitize(char)
        '''
        return field_to_sanitize.strip()
            
    def get_access_token(self):
        '''
            This method gets access token, 
            This token there is expirate time.
        '''
        if self:
            companies = self
        else:
            companies = self.search([('client_secret', '!=', False)])
        for company in companies:
            headers = {}
            client_id = company.sanitize_data(company.client_id) if company.client_id else ''
            client_secret = company.sanitize_data(company.client_secret) if company.client_secret else ''
            url = '%s%s' % (company.sanitize_data(company.request_token_url), '/connect/token')
            headers['accept'] = '*/*'
            headers['Connection'] = 'keep-alive'
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            payload = {
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': company.client_credentials,
                'scope': company.scope,
            }
            try:
                token_response = company.sync_myinvois(company, 'POST', url, payload, headers)
                if token_response.status_code == 200:
                    try:
                        # try getting JSON repr of it
                        parsed_response = token_response.json()
                        if 'access_token' in parsed_response:
                            _logger.info("REFRESHING ACCESS TOKEN {}".format(parsed_response.get('access_token')))
                            company.myinvois_access_token = parsed_response.get('access_token')
                        if 'expires_in' in parsed_response:
                            second = parsed_response.get('expires_in')
                            company.expire_token = datetime.now() + timedelta(seconds=second)
                        if 'token_type' in parsed_response:
                            company.token_type = parsed_response.get('token_type')
                    except Exception as ex:
                        _logger.info("EXCEPTION : {}".format(ex))
                elif token_response.status_code == 400:
                    _logger.info("Error 400 Bad Request: {}".format(token_response.reason))
                else:
                    raise UserError(_("Authorization Failed !! \nDesc : {}".format(token_response.reason)))
                    # _logger.info("We got a issue !!!! \nDesc : {}".format(token_response.reason))
            except Exception as ex:
                _logger.info("EXCEPTION : {}".format(ex))
    
    # Case-insensitive dictionary lookup
    def get_value_case_insensitive(self, d, key):
        key_lower = key.lower()  # Convert the search key to lowercase
        for k, v in d.items():
            if k.lower() == key_lower:  # Compare dictionary keys in lowercase
                return v
        return None
    
    def get_doc_search_url_cron(self):
        """ Prepare complete API url based on inputted filter """
        full_url = '/api/v1.0/documents/search?'
        # Set submission date from 
        date_from = datetime.now() + timedelta(days=-30)
        str_sub_date_from = date_from.strftime("%Y-%m-%dT%H:%M:%SZ")
        full_url += '&submissionDateFrom=' + str_sub_date_from
        # Set submission date to
        str_sub_date_to = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        full_url += '&submissionDateTo=' + str_sub_date_to
        return full_url
    
    def processing_date(self, date_str):
        if 'Z' not in date_str:
            if '.' in date_str:
                date_str = date_str[:date_str.index('.')]
                date_obj = datetime.fromisoformat(date_str)
            else:
                date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
                # convert to naive datetime without timezone
                date_obj = date_obj.replace(tzinfo=None)
        elif '.' in date_str:
            date_str = date_str[:date_str.index('.')] + 'Z'
            date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        else:
            date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        return date_obj

    
    def preprocessing_myinvois_data(self, item):
        issuer_id = False
        einvoice_type_id = False
        submit_date = False
        issued_date = False
        cancel_date = False
        reject_date = False
        validate_date = False
        if item.get('dateTimeReceived', False):
            submit_date = item.get('dateTimeReceived', False)
            submit_date = self.processing_date(submit_date)
        if item.get('dateTimeValidated', False):
            validate_date = item.get('dateTimeValidated', False)
            validate_date = self.processing_date(validate_date)
        if item.get('dateTimeIssued', False):
            issued_date = item.get('dateTimeIssued', False)
            issued_date = self.processing_date(issued_date)
        if item.get('cancelDateTime', False):
            cancel_date = item.get('cancelDateTime')
            cancel_date = self.processing_date(cancel_date)
        if item.get('rejectRequestDateTime', False):
            reject_date = item.get('rejectRequestDateTime')
            reject_date = self.processing_date(reject_date)
            # Check account move with the same submission ID
            if item.get("uuid"):
                invoice = self.env['account.move'].sudo().search([
                    ('my_invois_uuid', '=', item.get("uuid"))
                ], limit=1)
                # Update invoice rejection date and status
                if invoice:
                    invoice.my_invois_rejection = True
                    invoice.my_invois_rejection_date = reject_date
        if item.get('typeName', False):
            einvoice_type_id = self.env['myinvois.einvoice.type'].sudo().search(
                ['|', ('code', '=', item.get('typeName')), ('name', '=', item.get('typeName'))], limit=1)
        issuer_tin = self.get_value_case_insensitive(item, 'issuerTIN')
        issuerid = self.get_value_case_insensitive(item, 'issuerID')
        issuerName = self.get_value_case_insensitive(item, 'issuerName')
        if issuer_tin:
            issuer_id = self.env['res.partner'].sudo().search(
                [('vat', '=', issuer_tin)], limit=1)
            if not issuer_id and issuerid:
                issuer_id = self.env['res.partner'].sudo().search(
                    [('my_invois_partner_id_value','=', issuerid)], limit=1)
            if not issuer_id and issuerName:
                issuer_id = self.env['res.partner'].sudo().search(
                    [('name','=', issuerName)], limit=1)
            if not issuer_id:
                issuer_id = self.env['res.partner'].sudo().create({
                    'name': issuerName or issuer_tin,
                    'vat': issuer_tin
                })
            else:
                issuer_id.write({
                    'name': issuerName or issuer_id.name,
                    'vat': issuer_tin
                })
        return issuer_id, einvoice_type_id, submit_date, issued_date, cancel_date, reject_date, validate_date


    def fetch_manual_data(self, full_url=None):
        """ Fetch myinvois document based on issuer and submission date filter """
        self = self.env.company
        payload = {}
        url = ''
        if full_url:
            url = full_url
        else:
            url = '%s%s' % (self.env.company.request_token_url, self.env.company.get_doc_search_url_cron())
        try:
            response = self.env.company.sync_myinvois(self, "GET", url, payload)
            if response.status_code == 200:
                try:
                    ids = []
                    data = response.json()
                    uuids_ids = [i.get('uuid') for i in data.get('result')]
                    move_ids = self.env['account.move'].search([('my_invois_uuid','in',uuids_ids)])
                    move_id_by_uuid = {}
                    # looping first to generate dict, avoid performance cost of calling search/filtered inside loop
                    for move in move_ids:
                        move_id_by_uuid[move.my_invois_uuid] = move
                    for item in data.get('result'):
                        move_id = move_id_by_uuid.get(item.get('uuid'), self.env['account.move'])
                        myinvois_id = move_id.document_details_success_response(item)
                        ids.append(myinvois_id.id)
                
                    # TODO CHANGE Return to list with domain document ids
                    return {
                        'type': 'ir.actions.act_window',
                        'name': 'Myinvois Document',
                        'res_model': 'myinvois.document',
                        "view_mode": "tree,form",
                        "domain": [("id", "in", ids)],
                        'target': 'current',
                    }
                except Exception as ex:
                    raise UserError(_("EXCEPTION : {}".format(traceback.format_exc())))
            elif response.status_code == 400:
                raise UserError(_("Error 400 Bad Request: {}".format(response.reason)))
            else:
                raise UserError(_("We got a issue !!!! \nDesc : {}".format(response.reason)))
        except Exception as ex:
            _logger.info("EXCEPTION : {}".format(traceback.format_exc()))
            
    
    def _fetch_myinvois_data(self, move_type):
        """ Fetch myinvois document based on issuer and submission date filter 
        params: Type = to get myinvois based on move type invoice or vendor bill"""
        payload = {}
        partner_TIN = self.partner_id.vat or ''
        if move_type == 'invoice':
            payload = {
                'issuerTin': partner_TIN
            }
        else :
            payload = {
                'receiverTin': partner_TIN
            }
        url = '%s%s' % (self.env.company.request_token_url, self.env.company.get_doc_search_url_cron())
        try:
            response = self.env.company.sync_myinvois(self, "GET", url, payload)
            if response.status_code == 200:
                try:
                    data = response.json()
                    uuids_ids = [i.get('uuid') for i in data.get('result')]
                    # check normal invoice and consolidated invoices
                    move_ids = self.env['account.move'].search([('my_invois_uuid','in',uuids_ids)])
                    consolidate_ids = self.env['myinvois.consolidate'].search([('my_invois_uuid','in',uuids_ids)])
                    move_id_by_uuid = {}
                    consolidate_id_by_uuid = {}
                    # looping first to generate dict, avoid performance cost of calling search/filtered inside loop
                    for move in move_ids:
                        move_id_by_uuid[move.my_invois_uuid] = move
                    for consolidate in consolidate_ids:
                        consolidate_id_by_uuid[consolidate.my_invois_uuid] = consolidate
                    for item in data.get('result'):
                        consolidate_or_move_id = move_id_by_uuid.get(item.get('uuid'), self.env['account.move'])
                        if not consolidate_or_move_id:
                            consolidate_or_move_id = consolidate_id_by_uuid.get(item.get('uuid'), self.env['account.move'])
                        consolidate_or_move_id.document_details_success_response(item)

                    _logger.info("Success run fetch cron ")
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'type': 'success',
                            'sticky': True,
                            'message': _("Document found: %s. [%s] Please refresh the page and go to Myinvois Document menu to see the document." % (len(uuids_ids), ','.join(uuids_ids))),
                            'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
                except Exception as ex:
                    raise UserError(_("EXCEPTION : {}".format(ex)))
            elif response.status_code == 400:
                raise UserError(_("Error 400 Bad Request: {}".format(response.reason)))
            else:
                raise UserError(_("We got a issue !!!! \nDesc : {}".format(response.reason)))
        except Exception as ex:
            _logger.info("EXCEPTION : {}".format(ex))
            
    
    def fetch_all_myinvois_document_company(self):
        """ function Ir Cron to Fetch myinvois document 
         params : {company TIN}
         fetch data : invoice and vendor bill"""  
        myinvois_company_ids = self.env['res.company'].search([('myinvois_access_token', '!=', False)])    
        for company in myinvois_company_ids:
            # fetch invoice data from myinvois
            company._fetch_myinvois_data('invoice')
            
            # fetch vendor bill data from myinvois
            company._fetch_myinvois_data('vendor_bill')