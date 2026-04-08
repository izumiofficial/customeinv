from odoo import api, fields, models, _

class MyinvoisPeriod(models.Model):
    _name = "myinvois.period"
    _description = "My Invois Period"
    _rec_name = "my_invois_periode_description"

    my_invois_periode_start = fields.Date(
        string="Invois Period Start"
    )
    my_invois_periode_end = fields.Date(
        string="Invois Period End"
    )
    my_invois_periode_description = fields.Char(
        string="Invois Period Description"
    )