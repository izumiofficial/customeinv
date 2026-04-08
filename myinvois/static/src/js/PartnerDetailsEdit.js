odoo.define('pc_myinvois.PartnerDetailsEdit', function (require) {
    'use strict';

    const PartnerDetailsEdit = require('point_of_sale.PartnerDetailsEdit');
    const Registries = require('point_of_sale.Registries');

    const PartnerDetailsEditMyinvois = (PartnerDetailsEdit) =>
        class extends PartnerDetailsEdit {
            setup() {
                super.setup();
                this.changes.my_invois_partner_id_type = this.props.partner.my_invois_partner_id_type || "";
                this.changes.my_invois_partner_id_value = this.props.partner.my_invois_partner_id_value || "";
                this.changes.status_partner_validated_tin = this.props.partner.status_partner_validated_tin || "";
                this.changes.my_invois_sst = this.props.partner.my_invois_sst || "";
                this.changes.my_invois_ttx = this.props.partner.my_invois_ttx || "";
            }
            get partnerIDType() {
                return [
                    {
                        'value':'nric',
                        'name' : 'NRIC',
                    },
                    {
                        'value':'pass_num',
                        'name' : 'Passport Number',
                    },
                    {
                        'value':'brn',
                        'name' : 'Bussines Register Number (BRN)',
                    },
                    {
                        'value':'army',
                        'name' : 'Army Number',
                    },
                ]
            }
            saveChanges() {
                var argument = arguments[0]
                if (!this.changes.my_invois_partner_id_value && argument && argument.validate_tin) {
                    return this.showPopup('ErrorPopup', {
                        title: this.env._t("Missing Field"),
                        body: this.env._t("ID Number Is Required"),
                    });
                }
                if (!this.changes.vat && argument && argument.validate_tin) {
                    return this.showPopup('ErrorPopup', {
                        title: this.env._t("Missing Field"),
                        body: this.env._t("Tax ID Is Required"),
                    });
                }
                if (!this.changes.my_invois_partner_id_type && argument && argument.validate_tin) {
                    return this.showPopup('ErrorPopup', {
                        title: this.env._t("Missing Field"),
                        body: this.env._t("ID Type Is Required"),
                    });
                }
                return super.saveChanges(...arguments);
            }
        };

    Registries.Component.extend(PartnerDetailsEdit, PartnerDetailsEditMyinvois);

    return PartnerDetailsEdit;
});
