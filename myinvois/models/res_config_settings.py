from odoo import api, fields, models, _

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    my_invois_product_bill_id = fields.Many2one('product.product',related='company_id.my_invois_product_bill_id', string='MYInvois Product Bill', readonly=False, help='Product will be generated as invoice line')
    my_invois_consolidated_partner_id = fields.Many2one('res.partner', 'Consolidate Invoice Partner Config', related="company_id.my_invois_consolidated_partner_id", readonly=False)
    my_invois_p12 = fields.Binary(related='company_id.my_invois_p12', readonly=False, string='Digital Certificate')
    my_invois_p12_pin = fields.Char(related='company_id.my_invois_p12_pin', readonly=False, string='Digital Certificate PIN')
    my_invois_p12_fname = fields.Char(related='company_id.my_invois_p12_fname', readonly=False)

    def check_myinvois_cert(self):
        self.company_id.load_keystore()
        return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'message': _("Certificate Valid"),
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }