from odoo import _, fields, models

class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_res_partner(self):
        vals = super()._loader_params_res_partner()
        if self.company_id.country_code == 'MY':
            vals['search_params']['fields'] += ['my_invois_partner_id_type', 'my_invois_partner_id_value','status_partner_validated_tin','my_invois_ttx','my_invois_sst']
        return vals