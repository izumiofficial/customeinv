odoo.define('pc_myinvois.SubmitDocumentButton', function (require) {
    'use strict';

    const { useListener } = require("@web/core/utils/hooks");
    const { isConnectionError } = require('point_of_sale.utils');
    const PosComponent = require('point_of_sale.PosComponent');
    const Registries = require('point_of_sale.Registries');
    const { _t } = require("web.core");

    class SubmitDocumentButton extends PosComponent {
        setup() {
            super.setup();
            useListener('click', this._onClick);
        }
        get commandName() {
            return 'Submit Document'
        }
        async _onClick() {
            $.blockUI()
            var order = this.props.order
            if(order.account_move){
                var partner = order.partner
                var ctx = this.context || {};
                ctx.is_from_pos = true
                const result = await this.rpc({
                    model: 'res.partner',
                    method: 'validate_tin_partner',
                    args: [partner.id],
                    context: ctx,
                }).catch((error) => {
                    console.log("===FAILED VALIDATE TIN===",error);
                    return false
                });
                if(result == 'validated'){
                    await this.env.pos._loadPartners([partner.id]);
                }else{
                    $.unblockUI()
                    return this.showPopup("ErrorPopup", {
                        title: _t("Incorrect Customer"),
                        body: _t("The selected customer needs a Validate Tin."),
                    });
                }
                var result_submit = await this.rpc(
                    "account.move",
                    "action_submit_doc_from_pos",
                    [order.account_move],
                ).catch((error) => {
                    console.log(error);
                });
                if(result_submit){
                    this.trigger('order-invoiced', order.backendId);
                    this.showPopup("ConfirmPopupExt", {
                        title: _t("Submit Document"),
                        body: _t(result_submit.message),
                        hide_cancel: true,
                    });
                }
            }
            $.unblockUI()
            try {
                this.el.style.pointerEvents = 'none';
                await this._invoiceOrder();
            } catch (error) {
                if (isConnectionError(error)) {
                    this.showPopup('ErrorPopup', {
                        title: this.env._t('Network Error'),
                        body: this.env._t('Unable to invoice order.'),
                    });
                } else {
                    throw error;
                }
            } finally {
                this.el.style.pointerEvents = 'auto';
            }
        }
    }
    SubmitDocumentButton.template = 'SubmitDocumentButton';
    Registries.Component.add(SubmitDocumentButton);

    return SubmitDocumentButton;
});
