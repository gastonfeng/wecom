# -*- coding: utf-8 -*-

import werkzeug.urls
import werkzeug.utils
from odoo import models, fields, api, _
from ...wxwork_api.helper.common import *
import urllib


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    auth_agentid = fields.Char(
        "Agent Id",
        help="The web application ID of the authorizing party, which can be viewed in the specific web application",
        config_parameter="wxwork.auth_agentid",
    )
    auth_secret = fields.Char("Secret", config_parameter="wxwork.auth_secret",)
    auth_redirect_uri = fields.Char(
        "Callback link address redirected after authorization",
        help="Please use urlencode to process the link",
        config_parameter="wxwork.auth_redirect_uri",
        readonly=True,
    )
    qr_redirect_uri = fields.Char(
        "Scan the QR code to log in and call back the link address",
        help="Please use urlencode to process the link",
        config_parameter="wxwork.qr_redirect_uri",
        readonly=True,
    )

    def set_oauth_provider_wxwork(self):
        client_id = self.env["ir.config_parameter"].get_param("wxwork.corpid")

        web_base_url = self.env["ir.config_parameter"].get_param("web.base.url")

        auth_redirect_uri = self.env["ir.config_parameter"].get_param(
            "wxwork.auth_redirect_uri"
        )
        qr_redirect_uri = self.env["ir.config_parameter"].get_param(
            "wxwork.qr_redirect_uri"
        )

        new_auth_redirect_uri = (
            urllib.parse.urlparse(web_base_url).scheme
            + "://"
            + urllib.parse.urlparse(web_base_url).netloc
            + urllib.parse.urlparse(auth_redirect_uri).path
        )
        new_qr_redirect_uri = (
            urllib.parse.urlparse(web_base_url).scheme
            + "://"
            + urllib.parse.urlparse(web_base_url).netloc
            + urllib.parse.urlparse(qr_redirect_uri).path
        )

        # 设置回调链接地址
        self.env["ir.config_parameter"].sudo().set_param(
            "wxwork.auth_redirect_uri", new_auth_redirect_uri
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "wxwork.qr_redirect_uri", new_qr_redirect_uri
        )

        auth_endpoint = "https://open.weixin.qq.com/connect/oauth2/authorize"
        qr_auth_endpoint = "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"

        try:
            providers = (
                self.env["auth.oauth.provider"]
                .sudo()
                .search(["|", ("enabled", "=", True), ("enabled", "=", False),])
            )
        except Exception:
            providers = []

        for provider in providers:
            if auth_endpoint in provider["auth_endpoint"]:
                provider.write(
                    {
                        "client_id": client_id,
                        "validation_endpoint": auth_redirect_uri,
                        "enabled": True,
                    }
                )
            if qr_auth_endpoint in provider["auth_endpoint"]:
                provider.write(
                    {
                        "client_id": client_id,
                        "validation_endpoint": qr_redirect_uri,
                        "enabled": True,
                    }
                )
