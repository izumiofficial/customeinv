
from odoo import _, fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    product_classification_id = fields.Many2one('myinvois.product.classification',string='MyInvois Product Classification')
    
    def get_product_classification_id(self):
        # Initialize a variable to store the current category (self)
        category = self
        if category.product_classification_id:
            return category.product_classification_id
        # Traverse upwards through the parent category hierarchy
        while category.parent_id:
            # Check if the parent category has a value in 'x_new_field'
            if category.parent_id.product_classification_id:
                return category.parent_id.product_classification_id
            category = category.parent_id
        
        # If no parent category has the field filled, return the current category's field or False
        return category.product_classification_id or self.env['myinvois.product.classification']
