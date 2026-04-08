from odoo import api, models, http
from odoo.http import request
from odoo.addons.website.controllers.main import Website

class BackendControllerInherit(Website):
    """Website Inherit"""
    @http.route('/switch/user/company', type='json', auth="user")
    def switch_user_company_details(self, company_id, **kw):
        """Check selected user company"""
        restricted_menu = 'your_module.your_menuitem_id'
        menu_id = None
        try:
            menu_id = request.env.ref(restricted_menu).id
        except:
            pass
        if menu_id:
            menu = request.env['ir.ui.menu'].browse(menu_id)
            if company_id:
                if company_id == 1:
                    menu.sudo().update({'active': False})
                else:
                    menu.sudo().update({'active': True}) 