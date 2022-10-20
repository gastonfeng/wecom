# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.addons.wecom_api.api.wecom_abstract_api import ApiException


import werkzeug.urls
import werkzeug.utils
import urllib
import datetime
import logging

_logger = logging.getLogger(__name__)


class Company(models.Model):
    _inherit = "res.company"

    auth_app_id = fields.Many2one(
        "wecom.apps",
        string="Application",
        # required=True,
        # default=lambda self: self.env.company,
        # domain="[('company_id', '=', current_company_id)]",
        domain="[('company_id', '=', current_company_id)]",
    )

    def set_oauth_provider_wxwork(self):
        web_base_url = self.env["ir.config_parameter"].get_param("web.base.url")

        new_auth_redirect_uri = (
            urllib.parse.urlparse(web_base_url).scheme
            + "://"
            + urllib.parse.urlparse(web_base_url).netloc
            + urllib.parse.urlparse(self.auth_redirect_uri).path
        )
        new_qr_redirect_uri = (
            urllib.parse.urlparse(web_base_url).scheme
            + "://"
            + urllib.parse.urlparse(web_base_url).netloc
            + urllib.parse.urlparse(self.qr_redirect_uri).path
        )

        # 设置回调链接地址
        self.auth_redirect_uri = new_auth_redirect_uri
        self.qr_redirect_uri = new_qr_redirect_uri

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
                        # "client_id": client_id,
                        "validation_endpoint": self.auth_redirect_uri,
                        "enabled": True,
                    }
                )
            if qr_auth_endpoint in provider["auth_endpoint"]:
                provider.write(
                    {
                        # "client_id": client_id,
                        "validation_endpoint": self.qr_redirect_uri,
                        "enabled": True,
                    }
                )

    def cron_get_join_qrcode(self):
        """
        获取加入企业二维码任务
        """
        ir_config = self.env["ir.config_parameter"].sudo()
        debug = ir_config.get_param("wecom.debug_enabled")

        try:
            if debug:
                _logger.info(_("Task:Start getting join enterprise QR code"))
            companies = (
                self.env["res.company"]
                .sudo()
                .search([(("is_wecom_organization", "=", True))])
            )
            if len(companies) > 0:
                for company in companies:

                    wxapi = (
                        self.env["wecom.service_api"]
                        .sudo()
                        .InitServiceApi(company.corpid, company.contacts_app_id.secret)
                    )
                    response = wxapi.httpCall(
                        self.env["wecom.service_api_list"].get_server_api_call(
                            "GET_JOIN_QRCODE"
                        ),
                        {"size_type": company.join_qrcode_size_type,},
                    )

                    if response["errcode"] == 0:
                        company.join_qrcode = response["join_qrcode"]
                        company.join_qrcode_last_time = datetime.datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if debug:
                            _logger.info(
                                _(
                                    "Task:Complete obtaining the QR code to join the enterprise"
                                )
                            )
        except ApiException as ex:
            return self.env["wecomapi.tools.action"].ApiExceptionDialog(
                ex, raise_exception=True
            )

    @api.model
    def get_login_join_qrcode(self):
        """[summary]
        获取登陆页面的 加入企业微信的二维码
        """
        data = []
        # 获取 标记为 企业微信组织 的公司
        companies = (
            self.env["res.company"]
            .sudo()
            .search([(("is_wecom_organization", "=", True))])
        )

        if len(companies) > 0:
            for company in companies:
                if company["enabled_join_qrcode"]:
                    data.append(
                        {
                            "id": company["id"],
                            "name": company["abbreviated_name"],
                            "url": company["join_qrcode"],
                        }
                    )

        return data
