from odoo import fields, models


class ResponseMessageWizard(models.TransientModel):
    _name = 'myinvois.message.wizard'
    _description = "Show response message on popup"

    def _get_message(self):
        return self._context['message']

    message = fields.Text("Response", default=_get_message, readonly=True)
