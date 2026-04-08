# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.queue_job.exception import RetryableJobError
import requests


general_tin = ['EI00000000010', 'EI00000000020', 'EI00000000030', 'EI00000000040']
class ResPartner(models.Model):
    _inherit = 'res.partner'

    status_partner_validated_tin = fields.Selection(selection=[
        ('draft', 'Never Verified Before'),
        ('validated', 'Validated'),
        ('invalid', 'Invalid'),
    ], string='TIN Status', tracking=True, help='''Partner TIN Status ''')
    last_check_validate_tin = fields.Datetime(string="TIN Last Checked")


    my_invois_partner_id_type = fields.Selection(selection=[('nric', 'NRIC'),
                                                     ('pass_num', 'Passport Number'),
                                                     ('brn', 'Bussines Register Number (BRN)'),
                                                     ('army', 'Army Number')], string="ID Type", help="NRIC, Passport number, Business registration number, army number")
    
    my_invois_partner_id_value = fields.Char(string="ID Number" , help="The actual value of the ID Type selected. For example, if NRIC selected as ID Type, then pass the NRIC value here.")
    
    street3 = fields.Char(string="Street 3", help="An additional address line in an address that can be used to give further details supplementing the main line.")
    my_invois_sst = fields.Char('MyInvois SST Registration Number')
    my_invois_ttx = fields.Char('MyInvois Tourism Tax Registration Number')
    scheme_agency_name_id = fields.Many2one('scheme.agency.name', string="Scheme Agency Name")#not required in api
    my_invois_partner_tin = fields.Char(string="Partner Tin")
    is_malaysia_country = fields.Boolean(compute="_compute_is_malaysia")
    
    def _compute_is_malaysia(self):
        for record in self:
            record.is_malaysia_country = False
            if record.country_id:
                if record.country_id == record.env.ref('base.my'):
                    record.is_malaysia_country = True

    
    def write(self, vals):
        if 'vat' in vals:
            vals['status_partner_validated_tin'] = 'draft'
        return super(ResPartner, self).write(vals)
    
    @api.onchange('my_invois_partner_id_type', 'my_invois_partner_id_value')
    def _onchange_my_invois_partner_type_or_tin(self):
        for record in self:
            record.status_partner_validated_tin = 'draft'

    #part check validate tin
    #need vat , my_invois_partner_id_type, my_invois_partner_id_value
    #if one of them is not have value should return warning
    def check_value_validate_url(self):
        warning_message = []
        if not self.vat:
            warning_message.append("vat number (TIN)")
        if not self.my_invois_partner_id_type:
            warning_message.append("ID Type")
        if not self.my_invois_partner_id_value:
            warning_message.append("ID Number")
        if warning_message:
            if self.env.context.get('job_uuid', False):
                raise RetryableJobError(_("Please input %s" % ', '.join(warning_message)))
            else:
                raise UserError(_("Please input %s" % ', '.join(warning_message)))

    # return url only
    def get_validate_url_tin(self):
        url = "/api/v1.0/taxpayer/validate/%s?idType=%s&idValue=%s"
        full_url = url % (self.vat, self.my_invois_partner_id_type, self.my_invois_partner_id_value)
        return full_url
    
    def validate_tin_partner(self, company=False):
        self.ensure_one()
        self.check_value_validate_url()#part check 1st before move to validate tin
        # case when this is called on company formview with the active company != opened company form
        company = company or self.env.company
        url = '%s%s' % (company.request_token_url, self.get_validate_url_tin())
        payload = {
            'idType': self.my_invois_partner_id_type,
            'idValue': self.my_invois_partner_id_value
        }
        
        response = company.sync_myinvois(self, "GET", url, payload)
        if self.vat in general_tin or response.status_code == 200:
            self.status_partner_validated_tin = 'validated'
        else:
            self.status_partner_validated_tin = 'invalid'
        
        self.last_check_validate_tin = fields.Datetime.now()
        return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'danger' if self.status_partner_validated_tin != 'validated' else 'success',
                    'message': _("Ops, it seems we have invalid TIN or ID number. Please see API logs for the details") if self.status_partner_validated_tin != 'validated' else _("TIN Valid"),
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
        