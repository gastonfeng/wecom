# -*- coding: utf-8 -*-

import pandas as pd

pd.set_option("max_colwidth", 4096)  # 设置最大列宽
pd.set_option("display.max_columns", 30)  # 设置最大列数
pd.set_option("expand_frame_repr", False)  # 当列太多时不换行
import logging
from odoo import _, api, exceptions, fields, models, tools, registry, SUPERUSER_ID
from odoo.addons.wecom_api.api.wecom_abstract_api import ApiException

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    """
    邮件线程模型被任何需要作为讨论主题的模型所继承，消息可以附加在讨论主题上。
    公共方法的前缀是``message```以避免与将从此类继承的模型的方法发生名称冲突。


    ``mail.thread``定义用于处理和显示通信历史记录的字段。
    ``mail.thread``还管理继承类的跟随者。所有功能和预期行为都由管理 mail.thread.
    Widgets是为7.0及以下版本的Odoo设计的。

    实现任何方法都不需要继承类，因为默认实现适用于任何模型。
    但是，在处理传入电子邮件时，通常至少重写``message_new``和``message_update``方法（调用``super``），以便在创建和更新线程时添加特定于模型的行为。

    选项:
        - _mail_flat_thread:
            如果设置为True，则所有没有parent_id的邮件将自动附加到发布在源上的第一条邮件。
            如果设置为False，则使用线程显示Chatter，并且不会自动设置parent_id。

    MailThread特性可以通过上下文键进行某种程度的控制 :

     - ``mail_create_nosubscribe``: 在创建或 message_post 时，不要向记录线程订阅uid
     - ``mail_create_nolog``: 在创建时，不要记录自动的'<Document>created'消息
     - ``mail_notrack``: 在创建和写入时，不要执行值跟踪创建消息
     - ``tracking_disable``: 在创建和写入时，不执行邮件线程功能（自动订阅、跟踪、发布…）
     - ``mail_notify_force_send``: 如果要发送的电子邮件通知少于50个，请直接发送，而不是使用队列；默认情况下为True
    """

    _inherit = "mail.thread"

    # ------------------------------------------------------
    # 消息推送API
    # MESSAGE POST API
    # ------------------------------------------------------



    # ------------------------------------------------------
    # MESSAGE POST TOOLS
    # 消息发布工具
    # ------------------------------------------------------


    # ------------------------------------------------------
    # 通知API
    # NOTIFICATION API
    # ------------------------------------------------------


    def _notify_record_by_inbox(
        self, message, recipients_data, msg_vals=False, **kwargs
    ):
        """通知方式：收件箱。做两件主要的事情

          * 为用户创建收件箱通知;
          * 创建通道/消息链接（channel_ids mail.message 字段）;
          * 发送总线通知;

          message:  mail.message 对象;

        TDE/XDO TODO: 直接标记 rdata，例如 r['notif'] = 'ocn_client' 和 r['needaction']=False 并正确覆盖notify_recipients
        """
        channel_ids = [r["id"] for r in recipients_data["channels"]]
        if channel_ids:
            message.write({"channel_ids": [(6, 0, channel_ids)]})

        inbox_pids = [
            r["id"] for r in recipients_data["partners"] if r["notif"] == "inbox"
        ]

        if inbox_pids:
            notif_create_values = [
                {
                    "mail_message_id": message.id,
                    "res_partner_id": pid,
                    "notification_type": "inbox",
                    "notification_status": "sent",
                    "is_wecom_message": True if self.env["res.partner"].browse(pid).is_wecom_user else False,
                }
                for pid in inbox_pids
            ]
            self.env["mail.notification"].sudo().create(notif_create_values)
        for pid in inbox_pids:
            if self.env["res.partner"].browse(pid).is_wecom_user:
                msg_vals["is_wecom_message"] = True
                # msg_vals["receiver_company_id"] = self.env["res.partner"].browse(pid).company_id.id #接收者的公司id
            else:
                msg_vals["is_wecom_message"] = False

        bus_notifications = []
        if inbox_pids or channel_ids:
            message_format_values = False
            if inbox_pids:
                message_format_values = message.message_format()[0]
                for partner_id in inbox_pids:
                    bus_notifications.append(
                        [
                            (self._cr.dbname, "ir.needaction", partner_id),
                            dict(message_format_values),
                        ]
                    )
            if channel_ids:
                channels = self.env["mail.channel"].sudo().browse(channel_ids)
                bus_notifications += channels._channel_message_notifications(
                    message, message_format_values
                )

        if "is_wecom_message" in  msg_vals and msg_vals["is_wecom_message"]:
            self._notify_record_by_wecom(
                message, recipients_data, msg_vals=msg_vals, **kwargs
            )

        if bus_notifications:
            self.env["bus.bus"].sudo().sendmany(bus_notifications)

    def _notify_record_by_wecom(
        self, message, recipients_data, msg_vals=False, **kwargs
    ):
        """
        :param  message: mail.message 记录
        :param list recipients_data: 收件人
        :param dic msg_vals: 消息字典值
        """

        Model = self.env[msg_vals["model"]]
        model_name = self.env["ir.model"]._get(msg_vals["model"]).display_name

        partners = []
        if "partners" in recipients_data:
            partners = [r["id"] for r in recipients_data["partners"]]
        wecom_userids = [
            p.wecom_userid
            for p in self.env["res.partner"].browse(partners)
            if p.wecom_userid
        ]



        sender = self.env.user.partner_id.browse(msg_vals["author_id"]).name

        if msg_vals.get("subject") or message.subject:
            pass
        elif msg_vals.get("subject") and message.subject is False:
            pass
        elif msg_vals.get("subject") is False and message.subject:
            msg_vals["subject"] = message.subject
        else:
            msg_vals["subject"] = _(
                "[%s] Sends a message with the record name [%s] in the application [%s]."
            ) % (sender, Model.browse(msg_vals["res_id"]).name, model_name)

        body_markdown = _(
            "### %s sent you a message,You can also view it in your inbox in the system."
            + "\n\n"
            + "> **Message content:**\n\n> %s"
        ) % (
            sender,
            msg_vals["body"],
        )

        message.write(
            {
                "subject": msg_vals["subject"],
                "message_to_user": "|".join(wecom_userids),
                "message_to_party": None,
                "message_to_tag": None,
                "body_markdown": body_markdown,
            }
        )

        # receiver_company_ids = [] #企微消息接收者的公司id
        # for wecom_userid in wecom_userids:
        #     user = self.env["res.users"].search([("wecom_userid", "=", wecom_userid)],limit=1)
        #     receiver_company_ids.append(user.company_id.id)
        # # TODO 多公司 发送消息的问题
        # new_receiver_company_ids = list(set(receiver_company_ids)) #公司去重

        send_results = []

        for user in message.message_to_user.split("|"):
            try:
                user = self.env["res.users"].search([("wecom_userid", "=", user)],limit=1)
                company = user.company_id
                wecomapi = self.env["wecom.service_api"].InitServiceApi(
                    company.corpid, company.message_app_id.secret
                )
                msg = self.env["wecom.message.api"].build_message(
                    msgtype="markdown",
                    # touser="|".join(wecom_userids),
                    touser=user.wecom_userid,
                    toparty="",
                    totag="",
                    subject=msg_vals["subject"],
                    media_id=None,
                    description=None,
                    author_id=msg_vals["author_id"],
                    body_markdown=body_markdown,
                    safe=True,
                    enable_id_trans=True,
                    enable_duplicate_check=True,
                    duplicate_check_interval=1800,
                    company=company,
                )
                del msg["company"]
                res = wecomapi.httpCall(
                    self.env["wecom.service_api_list"].get_server_api_call("MESSAGE_SEND"),
                    msg,
                )
            except ApiException as exc:
                error = self.env["wecom.service_api_error"].get_error_by_code(exc.errCode)
                result = {
                    "user": user.name,
                    "wecom_userid": user.name,
                    "failure": True,
                    "failure_reason": _("Failed to send wecom message to user [%s]. Failure reason:%s %s") % (user.name,str(error["code"]), error["name"]),
                }
                send_results.append(result)
                # message.write(
                #     {
                #         "state": "exception",
                #         "failure_reason": "%s %s" % (str(error["code"]), error["name"]),
                #     }
                # )
            else:
                result = {
                    "user": user.name,
                    "failure": False,
                    "failure_reason": _("Sending wecom message to user [%s] succeeded") % user.name,
                }
                send_results.append(result)

            df = pd.DataFrame(send_results)
            failure_reason =""
            for index, row in df.iterrows():
                failure_reason += row["failure_reason"] + "\n"
            fail_rows = len(df[df["failure"] == True])  # 获取失败行数
            state = "sent"
            if fail_rows > 0:
                state = "exception"

            message.write(
                {
                    "state": state,
                    "message_id": failure_reason,
                }
            )

    # ------------------------------------------------------
    # 关注者API
    # FOLLOWERS API
    # ------------------------------------------------------


    # ------------------------------------------------------
    # 控制器
    # CONTROLLERS
    # ------------------------------------------------------
