# -*- coding: utf-8 -*-
# License: Odoo Proprietary License v1.0
{
    'name': "MyInvois Malaysia",
    'version': '14.0.0.0.1',
    'category': 'Accounting and API',
    "license": "AGPL-3",
    'author': 'Computs Sdn Bhd',
    'description': """
        V.16.0 \n
        Contributors : \n
        Computs\n
        Integrate Odoo with MyInvois Malaysia.
        
    """,
    'website': 'https://www.computs.com.my',
    'depends': [
        'account_debit_note','account_accountant', 'base', 'uom', 'queue_job', 'contacts'
    ],
    'data': [
        'data/ir_cron.xml',
        'security/ir.model.access.csv',
        'security/myinvois_security.xml',
        'data/tax_type_data.xml',
        'data/myinvois_product_classification_data.xml',
        'data/einvoice_type.xml',
        'data/template/res.partner.industry.csv',
        'data/sequence_consolidated_data.xml',
        'views/menuitem.xml',
        'views/account_move_views.xml',
        'views/myinvois_product_classification.xml',
        'views/myinvois_einvoice_type_view.xml',
        'data/einvoice_payment_mode_data.xml',
        'data/my_invois_country_data.xml',
        'views/res_company_view.xml',
        'views/tax_type_view.xml',
        'views/einvoice_payment_mode_view.xml',
        'views/prepaid_payment_view.xml',
        'views/payment_terms_view.xml',
        'views/product_category_views.xml',
        'views/res_country_view.xml',
        'views/partner_view.xml',
        'views/uom_uom_view.xml',
        'views/myinvois_industry_classificatin_views.xml',
        'views/myinvois_document_view.xml',
        'views/res_config_settings_views.xml',
        'wizards/reject_myinvois_wizard_view.xml',
        'wizards/cancel_myinvois_wizard_view.xml',
        'wizards/myinvois_document_search_view.xml',
        'wizards/check_document_wizard_view.xml',
        'views/myinvois_log_views.xml',
        'views/account_tax_views.xml',
        'views/myinvois_period_views.xml',
        'report/report_myinvois.xml',
        'report/myinvois_report_template.xml',
        'views/myinvois_consolidate_views.xml',
        'wizards/consolidate_myinvois_wizard_view.xml',
    ],
    "installable": True,
    "auto_install": False,
    'application': False,
    'post_init_hook': 'post_init_my_invois',#for apply code of res country
}
