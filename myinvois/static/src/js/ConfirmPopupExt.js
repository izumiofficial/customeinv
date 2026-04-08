odoo.define('pc_myinvois.ConfirmPopupExt', function(require) {
    'use strict';

    const AbstractAwaitablePopup = require('point_of_sale.AbstractAwaitablePopup');
    const Registries = require('point_of_sale.Registries');
    const { _lt } = require('@web/core/l10n/translation');

    // formerly ConfirmPopupExtWidget
    class ConfirmPopupExt extends AbstractAwaitablePopup {}
    ConfirmPopupExt.template = 'ConfirmPopupExt';
    ConfirmPopupExt.defaultProps = {
        confirmText: _lt("Ok"),
        cancelText: _lt("Cancel"),
        title: _lt("Title"),
        body: "",
        hide_cancel: false,
        hide_confirm: false,
    };

    Registries.Component.add(ConfirmPopupExt);

    return ConfirmPopupExt;
});
