from odoo import models, api, tools


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    @tools.ormcache('frozenset(self.env.user.groups_id.ids)', 'debug')
    def _visible_menu_ids(self, debug=False):
        menus = super(IrUiMenu, self)._visible_menu_ids(debug)
        if self.env.company and not self.env.user.has_group('base.group_system'):
            for rec in self.env.user.hide_menu_access_ids:
                menus.discard(rec.id)
            return menus
        return menus
