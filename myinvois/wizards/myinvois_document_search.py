from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import timezone, datetime
import logging
import requests
import pytz
import json

_logger = logging.getLogger(__name__)


class MyinvoisDocumentSearch(models.TransientModel):
    _name = "myinvois.document.search"
    _description = "Myinvois Document Search"

    name = fields.Char(string="Name")
    submission_date_from = fields.Datetime(string="Submission Date From")
    submission_date_to = fields.Datetime(string="Submission Date To")
    issue_date_from = fields.Datetime(string="Issue Date From")
    issue_date_to = fields.Datetime(string="Issue Date To")
    direction = fields.Selection([
        ('sent', 'Sent'), ('received', 'Received')
        ],string="Direction")
    doc_status = fields.Selection([
        ('Valid', 'Valid'), ('Invalid', 'Invalid'),
        ('Cancelled', 'Cancelled'), ('Submitted', 'Submitted')
        ], string="Status")
    issuer_tin = fields.Char(string="Issuer TIN")
    receiver_tin = fields.Char(string="Receiver TIN")

    def get_doc_search_url(self):
        """ Prepare complete API url based on inputted filter """
        full_url = '/api/v1.0/documents/search?'
        if self.name:
            full_url += '&uuid=' + self.name
        if self.submission_date_from:
            utc_sub_date_from = self.submission_date_from.replace(tzinfo=timezone.utc)
            str_sub_date_from = utc_sub_date_from.strftime("%Y-%m-%dT%H:%M:%SZ")
            full_url += '&submissionDateFrom=' + str_sub_date_from
        if self.submission_date_to:
            utc_sub_date_to = self.submission_date_to.replace(tzinfo=timezone.utc)
            str_sub_date_to = utc_sub_date_to.strftime("%Y-%m-%dT%H:%M:%SZ")
            full_url += '&submissionDateTo=' + str_sub_date_to
        if self.issue_date_from:
            utc_issue_date_from = self.issue_date_from.replace(tzinfo=timezone.utc)
            str_issue_date_from = utc_issue_date_from.strftime("%Y-%m-%dT%H:%M:%SZ")
            full_url += '&issueDateFrom=' + str_issue_date_from
        if self.issue_date_to:
            utc_issue_date_to = self.issue_date_to.replace(tzinfo=timezone.utc)
            str_issue_date_to = utc_issue_date_to.strftime("%Y-%m-%dT%H:%M:%SZ")
            full_url += '&issueDateTo=' + str_issue_date_to
        if self.direction:
            full_url += '&invoiceDirection=' + self.direction
        if self.doc_status:
            full_url += '&status=' + self.doc_status
        # if self.issuer_tin and self.direction == 'received':
        #     full_url += '&issuerTin' + self.issuer_tin
        # if self.receiver_tin and self.direction == 'received':
        #     full_url += '&receiverTin=' + self.receiver_tin
        return full_url

    def search_myinvois_document_dummy(self):
        """ Search myinvois document based on document ID and filter """
        url = '%s%s' % (self.env.company.request_token_url, self.get_doc_search_url())
        data = [
                {
                    "uuid":"42S512YACQBRSRHYKBXBTGQG21",
                    "submissionUUID":"42S512YACQBRSRHYKBXBTGQG21",
                    "longId":"YQH73576FY9VR57B…",
                    "internalId":"PZ-234-A",
                    "typeName":"01",
                    "typeVersionName":"1.0",
                    "issuerTin":"C25469231010",
                    "issuerName":"PCM TEST",
                    "receiverId":"087377381",
                    "receiverIdType":"PASSPORT",
                    "receiverName":"AMS Setia Jaya Sdn. Bhd",
                    "dateTimeIssued":"2015-02-13T13:15:00Z",
                    "dateTimeReceived":"2015-02-13T14:20:00Z",
                    "totalSales":147,
                    "totalDiscount":0,
                    "netAmount":147,
                    "total":161.70,
                    "totalOriginalSales":147,
                    "totalOriginalDiscount":0,
                    "netOriginalAmount":147,
                    "totalOriginal":161.70,
                    "status":"Valid",
                    "dateTimeValidated": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    # "documentStatusReason":"Wrong invoice details",
                    "createdByUserId":"admin@portcities.net"

                },
                {
                    "uuid":"42S512YACQBRSRHYKBXBTGQG22",
                    "submissionUUID": "42S512YACQBRSRHYKBXBTGQG22",
                    "longId":"YQH73576FY9VR57B…",
                    "internalId":"PZ-234-A",
                    "typeName":"01",
                    "typeVersionName":"1.0",
                    "issuerTin":"C2584563202",
                    "issuerName":"AMS Setia Jaya Sdn. Bhd.",
                    "receiverId":"201701003951",
                    "receiverIdType":"BRN",
                    "receiverName":"PCM TEST",
                    "dateTimeIssued":"2015-02-13T13:15:00Z",
                    "dateTimeReceived":"2015-02-13T14:20:00Z",
                    "dateTimeValidated": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "totalSales":147,
                    "totalDiscount":0,
                    "netAmount":147,
                    "total":161.70,
                    "totalOriginalSales":147,
                    "totalOriginalDiscount":0,
                    "netOriginalAmount":147,
                    "totalOriginal":161.70,
                    "status":"Valid",
                    # "cancelDateTime":"2021-02-25T01:59:10.2095172Z",
                    # "rejectRequestDateTime":"2021-02-25T01:59:10.2095172Z",
                    "documentStatusReason":"Wrong invoice details",
                    "createdByUserId":"admin@portcities.net"

                },
                {
                    "uuid":"42S512YACQBRSRHYKBXBTGQG23",
                    "submissionUUID": "42S512YACQBRSRHYKBXBTGQG23",
                    "longId":"YQH73576FY9VR57B…",
                    "internalId":"PZ-234-A",
                    "typeName":"02",
                    "typeVersionName":"1.0",
                    "issuerTin":"C2584563202",
                    "issuerName":"AMS Setia Jaya Sdn. Bhd.",
                    "receiverId":"201701003951",
                    "receiverIdType":"BRN",
                    "receiverName":"PCM TEST",
                    "dateTimeIssued":"2015-02-13T13:15:00Z",
                    "dateTimeReceived":"2015-02-13T14:20:00Z",
                    "dateTimeValidated": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "totalSales":147,
                    "totalDiscount":0,
                    "netAmount":147,
                    "total":161.70,
                    "totalOriginalSales":147,
                    "totalOriginalDiscount":0,
                    "netOriginalAmount":147,
                    "totalOriginal":161.70,
                    "status":"Valid",
                    # "cancelDateTime":"2021-02-25T01:59:10.2095172Z",
                    # "rejectRequestDateTime":"2021-02-25T01:59:10.2095172Z",
                    "documentStatusReason":"Wrong invoice details",
                    "createdByUserId":"admin@portcities.net"

                },
                {
                    "uuid":"42S512YACQBRSRHYKBXBTGQG24",
                    "submissionUUID": "42S512YACQBRSRHYKBXBTGQG24",
                    "longId":"YQH73576FY9VR57B…",
                    "internalId":"PZ-234-A",
                    "typeName":"02",
                    "typeVersionName":"1.0",
                    "issuerTin":"C25469231010",
                    "issuerName":"PCM TEST",
                    "receiverId":"087377381",
                    "receiverIdType":"PASSPORT",
                    "receiverName":"AMS Setia Jaya Sdn. Bhd.",
                    "dateTimeIssued":"2015-02-13T13:15:00Z",
                    "dateTimeReceived":"2015-02-13T14:20:00Z",
                    "dateTimeValidated": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "totalSales":147,
                    "totalDiscount":0,
                    "netAmount":147,
                    "total":161.70,
                    "totalOriginalSales":147,
                    "totalOriginalDiscount":0,
                    "netOriginalAmount":147,
                    "totalOriginal":161.70,
                    "status":"Valid",
                    # "cancelDateTime":"2021-02-25T01:59:10.2095172Z",
                    # "rejectRequestDateTime":"2021-02-25T01:59:10.2095172Z",
                    # "documentStatusReason":"Wrong invoice details",
                    "createdByUserId":"admin@portcities.net"

                },
                {
                    "uuid":"42S512YACQBRSRHYKBXBTGQG25",
                    "submissionUUID": "42S512YACQBRSRHYKBXBTGQG25",
                    "longId":"YQH73576FY9VR57B…",
                    "internalId":"PZ-234-A",
                    "typeName":"11",
                    "typeVersionName":"1.0",
                    "issuerTin":"C25469231010",
                    "issuerName":"PCM TEST",
                    "receiverId":"087377381",
                    "receiverIdType":"PASSPORT",
                    "receiverName":"AMS Setia Jaya Sdn. Bhd.",
                    "dateTimeIssued":"2015-02-13T13:15:00Z",
                    "dateTimeReceived":"2015-02-13T14:20:00Z",
                    "dateTimeValidated": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "totalSales":147,
                    "totalDiscount":0,
                    "netAmount":147,
                    "total":161.70,
                    "totalOriginalSales":147,
                    "totalOriginalDiscount":0,
                    "netOriginalAmount":147,
                    "totalOriginal":161.70,
                    "status":"Valid",
                    # "cancelDateTime":"2021-02-25T01:59:10.2095172Z",
                    # "rejectRequestDateTime":"2021-02-25T01:59:10.2095172Z",
                    # "documentStatusReason":"Wrong invoice details",
                    "createdByUserId":"admin@portcities.net"

                }
            ]
        ids = []
        uuids_ids = [i.get('uuid') for i in data]
        move_ids = self.env['account.move'].search([('my_invois_uuid','in',uuids_ids)])
        move_id_by_uuid = {}
        # looping first to generate dict, avoid performance cost of calling search/filtered inside loop
        for move in move_ids:
            move_id_by_uuid[move.my_invois_uuid] = move
        for item in data:
            move_id = move_id_by_uuid.get(item.get('uuid'), self.env['account.move'])
            myinvois_id = move_id.document_search_success_response(item)
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
        
    def search_myinvois_document(self):
        """ Search myinvois document based on document ID and filter """
        url = '%s%s' % (self.env.company.request_token_url, self.get_doc_search_url())
        return self.env.company.fetch_manual_data(url)
