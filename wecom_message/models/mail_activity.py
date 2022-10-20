# -*- coding: utf-8 -*-

from odoo import models


class MailActivity(models.Model):
    _inherit = "mail.activity"

    # send_wecom_message = fields.Boolean("Send Wecom Message", default=True,)
