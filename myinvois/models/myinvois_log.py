from odoo import api, fields, models, _
from markupsafe import Markup
class EinvoiceType(models.Model):
    _name = "myinvois.log"
    _description = "My Invois API Logs"

    name = fields.Char(string="EndPoint")
    my_invois_status_code = fields.Char()
    my_invois_response = fields.Text()
    my_invois_date = fields.Datetime()
    res_id = fields.Integer('Resource ID')
    res_model = fields.Char('Resource Model')
    my_invois_payload = fields.Text()
    raw_payload = fields.Text()

    def _get_log_link(self, title=None):
        """Generate the record html reference for chatter use.

        :param str title: optional reference title, the record display_name
            is used if not provided. The title/display_name will be escaped.
        :returns: generated html reference,
            in the format <a href data-oe-model="..." data-oe-id="...">title</a>
        :rtype: str
        """
        self.ensure_one()
        return Markup("<b>%s</b><br/><a href=# data-oe-model='%s' data-oe-id='%s'>%s</a>") % (
            self.my_invois_status_code, self._name, self.id, self.name)
