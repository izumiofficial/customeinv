# -*- coding: utf-8 -*-
from odoo import _, fields, models

class SchemeAgencyName(models.Model):
    _name = "scheme.agency.name"


    name = fields.Char(string="Name Agency")