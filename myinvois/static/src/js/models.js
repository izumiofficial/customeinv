odoo.define('pc_myinvois.models', function (require) {
    var { PosGlobalState, Order, Orderline } = require('point_of_sale.models');
    const { Gui } = require('point_of_sale.Gui');
    var core    = require('web.core');
    var _t      = core._t;
    var rpc = require('web.rpc');
    const Registries = require('point_of_sale.Registries');

    const PosGlobalStateMyinvois = (PosGlobalState) => class PosGlobalStateMyinvois extends PosGlobalState {
        async push_single_order(order, opts) {
            var results = await super.push_single_order(...arguments);
            for (let i = 0; i < results.length; i++) {
                const result = results[i];
                if(result.account_move){
                    var result_submit = await rpc.query(
                        "account.move",
                        "action_submit_doc_from_pos",
                        [result.account_move],
                    ).catch((error) => {
                        console.log("===FAILED SUBMIT===",error);
                        return false
                    });
                    if(result_submit){
                        this.showPopup("ConfirmPopupExt", {
                            title: _t("Submit Document"),
                            body: _t(result_submit.message),
                            hide_cancel: true,
                        });
                    }
                }
            }
            return results
        }
    }
    Registries.Model.extend(PosGlobalState, PosGlobalStateMyinvois);

    const OrderMyinvois = (Order) => class OrderMyinvois extends Order {
        constructor() {
            super(...arguments);
            this.my_invois_status_submission_rel = this.my_invois_status_submission_rel || false;
        }
        init_from_JSON(json) {
            super.init_from_JSON(...arguments);
            this.my_invois_status_submission_rel = json.my_invois_status_submission_rel || false;
        }
        export_as_JSON() {
            var json = super.export_as_JSON(...arguments);

            var to_return = _.extend(json, {
                'my_invois_status_submission_rel': this.my_invois_status_submission_rel,
            });
            return to_return;
        }
    }
    Registries.Model.extend(Order, OrderMyinvois);
});
