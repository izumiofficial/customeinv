odoo.define('pc_myinvois.PaymentScreen', function(require) {
    'use strict';

    const PaymentScreen = require('point_of_sale.PaymentScreen');
    const Registries = require('point_of_sale.Registries');
    const { _t } = require("web.core");

    const PaymentScreenMyinvois = PaymentScreen =>
        class extends PaymentScreen {
			constructor() {
                super(...arguments);
            }
            async _isOrderValid(isForceValidate) {
                if (!await super._isOrderValid(...arguments)) {
                    return false;
                }
                const partner = this.currentOrder.get_partner();
                if(partner && partner.status_partner_validated_tin != 'validated' && this.currentOrder.is_to_invoice()){
                    // validate tin before payment
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
                        return true
                    }else{
                        this.showPopup("ErrorPopup", {
                            title: _t("TIN Invalid"),
                            body: _t("The selected customer need valid TIN."),
                        });
                    }
                    return false;
                }
                return true
            }
	};
	Registries.Component.extend(PaymentScreen, PaymentScreenMyinvois);

	return PaymentScreen;
});
