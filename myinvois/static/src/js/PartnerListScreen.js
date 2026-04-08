odoo.define('pc_myinvois.PartnerListScreen', function (require) {
    'use strict';

    const PartnerListScreen = require('point_of_sale.PartnerListScreen');
    const Registries = require('point_of_sale.Registries');
    const { _lt } = require('@web/core/l10n/translation');

    const PartnerListScreenMyinvois = (PartnerListScreen) =>
        class extends PartnerListScreen {
            setup() {
                super.setup();
            }
            async validateTIN(){
                $.blockUI()
                var partner_id = this.state.editModeProps.partner.id
                var ctx = this.context || {};
                ctx.is_from_pos = true
                this.state.validate_tin = true
                await this.env.bus.trigger('save-partner',{
                    'validate_tin' : true
                })
                await this.env.pos._loadPartners([partner_id]);
                var partner_update = this.env.pos.db.get_partner_by_id(partner_id);
                if(partner_update.my_invois_partner_id_type && partner_update.my_invois_partner_id_value && partner_update.status_partner_validated_tin){
                    const result = await this.rpc({
                        model: 'res.partner',
                        method: 'validate_tin_partner',
                        args: [partner_id],
                        context: ctx,
                    }).catch((error) => {
                        console.log("===FAILED VALIDATE TIN===",error);
                        return false
                    });
                    if(!result){
                        $.unblockUI()
                        return await this.showPopup('ConfirmPopupExt', {
                            title: _lt("Validate Tin"),
                            hide_cancel: true,
                            result: result,
                            body:_lt("Failed to save Data , Please try submitting again")
                        });
                    }
                    await this.env.pos._loadPartners([partner_id]);
                    this.state.validate_tin = false
                    $.unblockUI()
                    this.state.selectedPartner = this.env.pos.db.get_partner_by_id(partner_id);
            
                    const confirm = await this.showPopup('ConfirmPopupExt', {
                        title: _lt("Validate Tin"),
                        hide_cancel: true,
                        result: result,
                        body:_lt("Tin Status : "+ result.toUpperCase())
                    }); 
                    if(confirm){
                        this.props.resolve({ confirmed: true, payload: this.state.selectedPartner });
                        return this.back(true)
                    }
                }
                $.unblockUI()
                
            }
            async saveChanges(event) {
                if(this.state.validate_tin){
                    try {
                        let partnerId = await this.rpc({
                            model: 'res.partner',
                            method: 'create_from_ui',
                            args: [event.detail.processedChanges],
                        });
                        return partnerId
                    } catch (error) {
                        if (isConnectionError(error)) {
                            await this.showPopup('OfflineErrorPopup', {
                                title: this.env._t('Offline'),
                                body: this.env._t('Unable to save changes.'),
                            });
                        } else {
                            throw error;
                        }
                    }
                }
                return super.saveChanges(...arguments);
            }
        };

    Registries.Component.extend(PartnerListScreen, PartnerListScreenMyinvois);

    return PartnerListScreen;
});
