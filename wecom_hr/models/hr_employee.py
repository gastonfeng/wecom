# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class HrEmployeePrivate(models.Model):
    _inherit = "hr.employee"
    _order = "wecom_user_order"

    category_ids = fields.Many2many(
        "hr.employee.category",
        "employee_category_rel",
        "emp_id",
        "category_id",
        groups="hr.group_hr_manager",
        string="Tags",
        domain="[('is_wecom_category', '=',False)]",
    )

    wecom_user_id = fields.Char(
        string="WeCom user Id",
        readonly=True,
    )

    alias = fields.Char(
        string="Alias",
        readonly=True,
    )
    english_name = fields.Char(
        string="English Name",
        readonly=True,
    )

    department_ids = fields.Many2many(
        "hr.department",
        string="Multiple departments",
        readonly=True,
    )
    use_system_avatar = fields.Boolean(readonly=True, default=True)
    avatar = fields.Char(string="Avatar")
    # avatar = fields.Char(string="Avatar", readonly=True, img_height=95)
    qr_code = fields.Char(
        string="Personal QR code",
        help="Personal QR code, Scan can be added as external contact",
        readonly=True,
    )
    wecom_user_order = fields.Char(
        "WeCom user sort",
        default="0",
        help="The sort value within the department, the default is 0. The quantity must be the same as the department, The greater the value the more sort front.The value range is [0, 2^32)",
        readonly=True,
    )
    is_wecom_employee = fields.Boolean(
        string="WeCom employees",
        readonly=True,
        default=False,
    )

    # TODO 待处理 增加标签成员 和 删除标签成员
    # @api.onchange("category_ids")
    # def _onchange_category_ids(self):
    #     print(self.category_ids)

    # @api.model
    # def create(self, vals):
    #     employee = super(HrEmployeePrivate, self).create(vals)

    # def write(self, vals):
    #     res = super(HrEmployeePrivate, self).write(vals)

    #     if self.is_wecom_employee:
    #         # 检测是企业微信员工
    #         if len(self.category_ids) > 0:
    #             pass
    #         else:
    #             pass
    #     return res

    # def unlink(self):
    #     super(HrEmployeePrivate, self).unlink()
