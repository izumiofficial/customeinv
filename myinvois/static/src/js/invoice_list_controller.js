/** @odoo-module */
import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { session } from '@web/session';
import { AccountMoveListController } from '@account/components/bils_uploads';

patch(AccountMoveListController.prototype, 'invoice_list_controller', {

    getActionMenuItems() {
        const actionMenuItems = super.getActionMenuItems();
        var model = this.props.resModel
        var ctx_supplier_rank = this.props.context['default_is_supplier']
        var restrict_product = (model == 'product.template' || model == 'product.product') && !this.session.group_product_creation
        var restrict_vendor = model == 'res.partner' && ctx_supplier_rank && this.session.group_purchase_user
        if (restrict_product || restrict_vendor) {
            let ActionToDelete = ["archive", "unarchive", "duplicate", "delete"];
            ActionToDelete.forEach(key => {
                delete list_of_action[key];
            });
        }
        return list_of_action
    },

});
