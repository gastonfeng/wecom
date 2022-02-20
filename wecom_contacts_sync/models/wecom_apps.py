# -*- coding: utf-8 -*-

import logging
import datetime
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from io import StringIO
import pandas as pd

pd.set_option("max_colwidth", 4096)  # 设置最大列宽
pd.set_option("display.max_columns", 30)  # 设置最大列数
pd.set_option("expand_frame_repr", False)  # 当列太多时不换行
import time

from odoo.addons.wecom_api.api.wecom_abstract_api import ApiException

_logger = logging.getLogger(__name__)


class WeComApps(models.Model):
    _inherit = "wecom.apps"

    # ————————————————————————————————————
    # 应用回调服务
    # ————————————————————————————————————
    def generate_service_by_code(self, code):
        """
        根据code生成回调服务
        :param code:
        :return:
        """
        # ("app_id", "in", self.id),
        if code == "contacts":
            service = self.app_callback_service_ids.sudo().search(
                [
                    ("app_id", "=", self.id),
                    ("code", "=", code),
                    "|",
                    ("active", "=", True),
                    ("active", "=", False),
                ]
            )

            if not service:
                service.create(
                    {
                        "app_id": self.id,
                        "name": _("Contacts synchronization"),
                        "code": code,
                        "callback_url_token": "",
                        "callback_aeskey": "",
                        "description": _(
                            "When members modify their personal information, the modified information will be pushed to the following URL in the form of events to ensure the synchronization of the address book."
                        ),
                    }
                )
            else:
                service.write(
                    {
                        "name": _("Contacts synchronization"),
                        "code": code,
                        "callback_url": service.generate_service(),
                        "description": _(
                            "When members modify their personal information, the modified information will be pushed to the following URL in the form of events to ensure the synchronization of the address book."
                        ),
                    }
                )

    # ————————————————————————————————————
    # 应用参数配置
    # ————————————————————————————————————

    def generate_parameters_by_code(self, code):
        """
        根据code生成参数
        :param code:
        :return:
        注意：14使用 get_object_reference 方法，15 没有此方法，
        故在 \wecom_base\models\ir_model.py 添加了 get_object_reference方法
        """
        if code == "contacts":
            # 从xml 获取数据
            ir_model_data = self.env["ir.model.data"]
            contacts_auto_sync_hr_enabled = ir_model_data.get_object_reference(
                "wecom_contacts_sync", "wecom_app_config_contacts_auto_sync_hr_enabled"
            )[
                1
            ]  # 1
            contacts_sync_hr_department_id = ir_model_data.get_object_reference(
                "wecom_contacts_sync", "wecom_app_config_contacts_sync_hr_department_id"
            )[
                1
            ]  # 2
            contacts_edit_enabled = ir_model_data.get_object_reference(
                "wecom_contacts_sync", "wecom_app_config_contacts_edit_enabled"
            )[
                1
            ]  # 3
            contacts_task_sync_user_enabled = ir_model_data.get_object_reference(
                "wecom_contacts_sync",
                "wecom_app_config_contacts_task_sync_user_enabled",
            )[
                1
            ]  # 4
            contacts_use_system_default_avatar = ir_model_data.get_object_reference(
                "wecom_contacts_sync",
                "wecom_app_config_contacts_use_system_default_avatar",
            )[
                1
            ]  # 5
            contacts_update_avatar_every_time_sync = ir_model_data.get_object_reference(
                "wecom_contacts_sync",
                "wecom_app_config_contacts_update_avatar_every_time_sync",
            )[
                1
            ]  # 6
            enabled_join_qrcode = ir_model_data.get_object_reference(
                "wecom_contacts_sync", "wecom_app_config_contacts_enabled_join_qrcode"
            )[
                1
            ]  # 7
            join_qrcode = ir_model_data.get_object_reference(
                "wecom_contacts_sync", "wecom_app_config_contacts_join_qrcode"
            )[
                1
            ]  # 8
            join_qrcode_size_type = ir_model_data.get_object_reference(
                "wecom_contacts_sync", "wecom_app_config_contacts_join_qrcode_size_type"
            )[
                1
            ]  # 9
            join_qrcode_last_time = ir_model_data.get_object_reference(
                "wecom_contacts_sync",
                "wecom_app_config_acontacts_join_qrcode_last_time",
            )[
                1
            ]  # 10

            vals_list = [
                contacts_auto_sync_hr_enabled,  # 1
                contacts_sync_hr_department_id,  # 2
                contacts_edit_enabled,  # 3
                contacts_task_sync_user_enabled,  # 4
                contacts_use_system_default_avatar,  # 5
                contacts_update_avatar_every_time_sync,  # 6
                enabled_join_qrcode,  # 7
                join_qrcode,  # 8
                join_qrcode_size_type,  # 9
                join_qrcode_last_time,  # 10
            ]

            for id in vals_list:
                app_config_id = self.env["wecom.app_config"].search([("id", "=", id)])
                app_config = (
                    self.env["wecom.app_config"]
                    .sudo()
                    .search([("app_id", "=", self.id), ("key", "=", app_config_id.key)])
                )

                if not app_config:
                    app_config.sudo().create(
                        {
                            "name": app_config_id.name,
                            "app_id": self.id,
                            "key": app_config_id.key,
                            "ttype": app_config_id.ttype,
                            "value": ""
                            if app_config_id.key == "join_qrcode"
                            or app_config_id.key == "join_qrcode_last_time"
                            else app_config_id.value,
                            "description": app_config_id.description,
                        }
                    )
                else:
                    app_config.sudo().write(
                        {
                            "name": app_config_id.name,
                            "description": app_config_id.description,
                        }
                    )

        super(WeComApps, self).generate_parameters_by_code(code)

    # ————————————————————————————————————
    # 通讯录
    # ————————————————————————————————————
    def get_join_qrcode(self):
        """
        获取加入企业二维码
        :return:
        """
        ir_config = self.env["ir.config_parameter"].sudo()
        debug = ir_config.get_param("wecom.debug_enabled")
        if debug:
            _logger.info(
                _("Start getting join enterprise QR code for app [%s] of company [%s]")
                % (self.name, self.company_id.name)
            )

        if self.subtype_ids.code == "contacts":
            if len(self.app_config_ids) == 0:
                raise UserError(_("Please generate application parameters first."))

            try:
                wecomapi = self.env["wecom.service_api"].InitServiceApi(
                    self.company_id.corpid, self.secret
                )
                app_config = self.env["wecom.app_config"].sudo()
                size_type = app_config.get_param(self.id, "join_qrcode_size_type")

                # print(self.company_id.name, qrcode, size_type, last_time)
                response = wecomapi.httpCall(
                    self.env["wecom.service_api_list"].get_server_api_call(
                        "GET_JOIN_QRCODE"
                    ),
                    {"size_type": size_type},
                )
                if response["errcode"] == 0:
                    app_config.set_param(
                        self.id, "join_qrcode", response["join_qrcode"]
                    )
                    app_config.set_param(
                        self.id,
                        "join_qrcode_last_time",
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    # qrcode.write({"value": response["join_qrcode"]})
                    # last_time.write(
                    #     {"value": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                    # )

            except ApiException as ex:
                return self.env["wecomapi.tools.action"].ApiExceptionDialog(
                    ex, raise_exception=True
                )

    def cron_get_join_qrcode(self):
        """
        自动任务获取加入企业二维码
        """

        for app in self.search(
            [("company_id", "!=", False), ("type_code", "=", "['contacts']")]
        ):
            _logger.info(
                _("Automatic task:Start to get join enterprise QR code of company [%s]")
                % (app.company_id.name)
            )
            app.get_join_qrcode()

    def cron_sync_contacts(self):
        """
        自动任务同步组织架构
        同步内容:    1. hr.department
                    2. hr.employee
                    3. hr.employee.category
                    4. res.users
                    5. res.partner.category
        """
        results = []
        total_time = 0
        sync_start_time = time.time()

        for app in self.search(
            [("company_id", "!=", False), ("type_code", "=", "['contacts']")]
        ):
            _logger.info(
                _(
                    "Automatic task: start to synchronize the enterprise wechat organizational structure of the company [%s]"
                )
                % (app.company_id.name)
            )

            result = app.sync_contacts()
            results.append(result)

            _logger.info(
                _(
                    "Automatic task: end synchronizing the enterprise wechat organizational structure of the company [%s]"
                )
                % (app.company_id.name)
            )
        df = pd.DataFrame(results)

        (
            sync_task_state,
            hr_department_sync_state,
            hr_employee_sync_state,
            hr_tag_sync_state,
            res_user_sync_state,
            partner_tag_sync_state,
        ) = self.handle_sync_all_state(
            df
        )  # 处理同步状态

        # 处理同步结果和时间
        sync_task_result = ""
        hr_department_sync_result = ""
        hr_employee_sync_result = ""
        hr_tag_sync_result = ""
        res_user_sync_result = ""
        partner_tag_sync_result = ""

        hr_department_sync_times = 0
        hr_employee_sync_times = 0
        hr_tag_sync_times = 0
        res_user_sync_times = 0
        partner_tag_sync_times = 0

        rows = len(df)  # 获取所有行数

        for index, row in df.iterrows():
            if row["sync_state"] == "fail":
                sync_task_result += self.handle_sync_result(
                    index, rows, row["sync_result"]
                )

            hr_department_sync_result += self.handle_sync_result(
                index, rows, row["hr_department_sync_result"]
            )
            hr_employee_sync_result += self.handle_sync_result(
                index, rows, row["hr_employee_sync_result"]
            )
            hr_tag_sync_result += self.handle_sync_result(
                index, rows, row["hr_tag_sync_result"]
            )
            res_user_sync_result += self.handle_sync_result(
                index, rows, row["res_user_sync_result"]
            )
            partner_tag_sync_result += self.handle_sync_result(
                index, rows, row["partner_tag_sync_result"]
            )

            hr_department_sync_times += row["hr_department_sync_times"]
            hr_employee_sync_times += row["hr_employee_sync_times"]
            hr_tag_sync_times += row["hr_tag_sync_times"]
            res_user_sync_times += row["res_user_sync_times"]
            partner_tag_sync_times += row["partner_tag_sync_times"]

        sync_end_time = time.time()
        total_time = sync_end_time - sync_start_time
        _logger.info(
            _(
                """
Automatic task: end the synchronization of the enterprise wechat organizational structure of all companies.
=======================================================================================================================
Task Synchronization status:%s, Synchronization task time:%s seconds,
Synchronization results：
%s
-----------------------------------------------------------------------------------------------------------------------
Hr department sync status:%s, Synchronize HR department time: %s seconds,
Synchronize HR department results:
%s
-----------------------------------------------------------------------------------------------------------------------
Hr employee sync status:%s, Synchronize HR employee time: %s seconds,
Synchronize HR employee results:
%s
-----------------------------------------------------------------------------------------------------------------------
Hr tag sync status:%s, Synchronize HR tag time: %s seconds,
Synchronize HR tag results:
%s
-----------------------------------------------------------------------------------------------------------------------
System user status:%s, Synchronize system user time: %s seconds,
Synchronize system user results:
%s
-----------------------------------------------------------------------------------------------------------------------
Contact tag status:%s, Synchronize contact tag time: %s seconds,
Synchronize contact tag results:
%s
======================================================================================================================="""
            )
            % (
                # 任务
                self.get_state_name(sync_task_state),
                total_time,
                sync_task_result,
                # hr部门
                self.get_state_name(hr_department_sync_state),
                hr_department_sync_times,
                hr_department_sync_result,
                # hr员工
                self.get_state_name(hr_employee_sync_state),
                hr_employee_sync_times,
                hr_employee_sync_result,
                # hr标签
                self.get_state_name(hr_tag_sync_state),
                hr_tag_sync_times,
                hr_tag_sync_result,
                # 系统用户
                self.get_state_name(res_user_sync_state),
                res_user_sync_times,
                res_user_sync_result,
                # 联系人标签
                self.get_state_name(partner_tag_sync_state),
                partner_tag_sync_times,
                partner_tag_sync_result,
            )
        )

    def sync_contacts(self):
        """
        同步通讯录
        """
        result = {}
        sync_hr_enabled = self.app_config_ids.get_param(
            self.id, "contacts_auto_sync_hr_enabled"
        )  # 允许企业微信通讯簿自动更新为HR的标识
        if sync_hr_enabled:
            result = {"company_name": self.company_id.name, "sync_state": "completed"}
            # 同步HR部门
            sync_department_result = (
                self.env["hr.department"]
                .with_context(company_id=self.company_id)
                .download_wecom_deps()
            )
            (
                hr_department_sync_state,
                hr_department_sync_times,
                hr_department_sync_result,
            ) = self.handle_sync_task_state(sync_department_result, self.company_id)

            result.update(
                {
                    "hr_department_sync_state": hr_department_sync_state,
                    "hr_department_sync_times": hr_department_sync_times,
                    "hr_department_sync_result": hr_department_sync_result,
                }
            )

            # 同步HR员工
            sync_employee_result = (
                self.env["hr.employee"]
                .with_context(company_id=self.company_id)
                .download_wecom_staffs()
            )
            (
                hr_employee_sync_state,
                hr_employee_sync_times,
                hr_employee_sync_result,
            ) = self.handle_sync_task_state(sync_employee_result, self.company_id)
            result.update(
                {
                    "hr_employee_sync_state": hr_employee_sync_state,
                    "hr_employee_sync_times": hr_employee_sync_times,
                    "hr_employee_sync_result": hr_employee_sync_result,
                }
            )

            # 同步HR标签
            sync_hr_tag_result = (
                self.env["hr.employee.category"]
                .with_context(company_id=self.company_id)
                .download_wecom_tags()
            )
            (
                hr_tag_sync_state,
                hr_tag_sync_times,
                hr_tag_sync_result,
            ) = self.handle_sync_task_state(sync_hr_tag_result, self.company_id)
            result.update(
                {
                    "hr_tag_sync_state": hr_tag_sync_state,
                    "hr_tag_sync_times": hr_tag_sync_times,
                    "hr_tag_sync_result": hr_tag_sync_result,
                }
            )

            # 同步用户
            sync_user_result = (
                self.env["res.users"]
                .sudo()
                .with_context(company_id=self.company_id)
                .download_wecom_contacts()
            )

            (
                res_user_sync_state,
                res_user_sync_times,
                res_user_sync_result,
            ) = self.handle_sync_task_state(sync_user_result, self.company_id)
            result.update(
                {
                    "res_user_sync_state": res_user_sync_state,
                    "res_user_sync_times": res_user_sync_times,
                    "res_user_sync_result": res_user_sync_result,
                }
            )

            # 同步联系人标签
            sync_artner_tag_result = (
                self.env["res.partner.category"]
                .with_context(company_id=self.company_id)
                .download_wecom_contact_tags()
            )
            (
                partner_tag_sync_state,
                partner_tag_sync_times,
                partner_tag_sync_result,
            ) = self.handle_sync_task_state(sync_artner_tag_result, self.company_id)
            result.update(
                {
                    "partner_tag_sync_state": partner_tag_sync_state,
                    "partner_tag_sync_times": partner_tag_sync_times,
                    "partner_tag_sync_result": partner_tag_sync_result,
                }
            )
        else:
            result.update(
                {
                    "company_name": self.company_id.name,
                    "sync_state": "fail",
                    "sync_result": _(
                        "Synchronization of company [%s] failed. Reason:configuration does not allow synchronization to HR."
                    )
                    % self.company_id.name,
                    "hr_department_sync_state": "fail",
                    "hr_department_sync_times": 0,
                    "hr_department_sync_result": _(
                        "Synchronization of company [%s] failed. Reason:configuration does not allow synchronization to HR."
                    )
                    % self.company_id.name,
                    "hr_employee_sync_state": "fail",
                    "hr_employee_sync_times": 0,
                    "hr_employee_sync_result": _(
                        "Synchronization of company [%s] failed. Reason:configuration does not allow synchronization to HR."
                    )
                    % self.company_id.name,
                    "hr_tag_sync_state": "fail",
                    "hr_tag_sync_times": 0,
                    "hr_tag_sync_result": _(
                        "Synchronization of company [%s] failed. Reason:configuration does not allow synchronization to HR."
                    )
                    % self.company_id.name,
                    "res_user_sync_state": "fail",
                    "res_user_sync_times": 0,
                    "res_user_sync_result": _(
                        "Synchronization of company [%s] failed. Reason:configuration does not allow synchronization to HR."
                    )
                    % self.company_id.name,
                    "partner_tag_sync_state": "fail",
                    "partner_tag_sync_times": 0,
                    "partner_tag_sync_result": _(
                        "Synchronization of company [%s] failed. Reason:configuration does not allow synchronization to HR."
                    )
                    % self.company_id.name,
                }
            )

        return result

    def get_state_name(self, key):
        """
        获取状态名称
        """
        STATE = {
            "completed": _("All completed"),
            "partially": _("Partially complete"),
            "fail": _("All failed"),
        }
        return dict(STATE).get(key, _("Unknown"))  # 如果没有找到，返回Unknown

    def handle_sync_result(self, index, rows, result):
        """
        处理同步结果
        """
        if result is None:
            return ""
        if index < rows - 1:
            result = "%s:%s \n" % (str(index + 1), result)
        else:
            result = "%s:%s" % (str(index + 1), result)
        return result

    def handle_sync_all_state(self, df):
        """
        处理同步状态
        """
        all_state_rows = len(df)  # 获取所有行数
        fail_state_rows = len(df[df["sync_state"] == "fail"])  # 获取失败行数

        fail_department_state_rows = len(
            df[df["hr_department_sync_state"] == "fail"]
        )  # 获取HR部门失败行数
        fail_employee_state_rows = len(
            df[df["hr_employee_sync_state"] == "fail"]
        )  # 获取HR员工失败行数
        fail_hr_tag_state_rows = len(
            df[df["hr_tag_sync_state"] == "fail"]
        )  # 获取HR标签失败行数
        fail_user_state_rows = len(
            df[df["res_user_sync_state"] == "fail"]
        )  # 获取系统用户失败行数
        fail_partner_tag_state_rows = len(
            df[df["res_user_sync_state"] == "fail"]
        )  # 获取联系人标签失败行数

        sync_state = None
        hr_department_sync_state = None
        hr_employee_sync_state = None
        hr_tag_sync_state = None
        res_user_sync_state = None
        partner_tag_sync_state = None

        if fail_state_rows == all_state_rows:
            sync_state = "fail"
        elif fail_state_rows > 0 and fail_state_rows < all_state_rows:
            sync_state = "partially"
        elif fail_state_rows == 0:
            sync_state = "completed"

        if fail_department_state_rows == all_state_rows:
            hr_department_sync_state = "fail"
        elif (
            fail_department_state_rows > 0
            and fail_department_state_rows < all_state_rows
        ):
            hr_department_sync_state = "partially"
        elif fail_department_state_rows == 0:
            hr_department_sync_state = "completed"

        if fail_employee_state_rows == all_state_rows:
            hr_employee_sync_state = "fail"
        elif fail_employee_state_rows > 0 and fail_employee_state_rows < all_state_rows:
            hr_employee_sync_state = "partially"
        elif fail_employee_state_rows == 0:
            hr_employee_sync_state = "completed"

        if fail_hr_tag_state_rows == all_state_rows:
            hr_tag_sync_state = "fail"
        elif fail_hr_tag_state_rows > 0 and fail_hr_tag_state_rows < all_state_rows:
            hr_tag_sync_state = "partially"
        elif fail_hr_tag_state_rows == 0:
            hr_tag_sync_state = "completed"

        if fail_user_state_rows == all_state_rows:
            res_user_sync_state = "fail"
        elif fail_user_state_rows > 0 and fail_user_state_rows < all_state_rows:
            res_user_sync_state = "partially"
        elif fail_user_state_rows == 0:
            res_user_sync_state = "completed"

        if fail_partner_tag_state_rows == all_state_rows:
            partner_tag_sync_state = "fail"
        elif (
            fail_partner_tag_state_rows > 0
            and fail_partner_tag_state_rows < all_state_rows
        ):
            partner_tag_sync_state = "partially"
        elif fail_partner_tag_state_rows == 0:
            partner_tag_sync_state = "completed"

        return (
            sync_state,
            hr_department_sync_state,
            hr_employee_sync_state,
            hr_tag_sync_state,
            res_user_sync_state,
            partner_tag_sync_state,
        )

    def handle_sync_task_state(self, result, company):
        """
        处理HR部门、HR员工、HR标签、系统用户、合作伙伴标签 同步状态
        """
        df = pd.DataFrame(result)
        all_rows = len(df)  # 获取所有行数
        fail_rows = len(df[df["state"] == False])  # 获取失败行数

        sync_state = None
        if fail_rows == all_rows:
            sync_state = "fail"
        elif fail_rows > 0 and fail_rows < all_rows:
            sync_state = "partially"
        elif fail_rows == 0:
            sync_state = "completed"

        sync_result = ""
        sync_times = 0
        for index, row in df.iterrows():
            sync_times += row["time"]
            sync_result += "[%s] %s" % (company.name, row["msg"])

        return sync_state, sync_times, sync_result
