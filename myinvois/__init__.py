from . import models
from . import wizards
from . import controller
from odoo import api, SUPERUSER_ID

def post_init_my_invois(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    """Sync Code of invois in res country"""
    env['res.country'].sync_my_invois_country()
    env['res.country'].sync_state()