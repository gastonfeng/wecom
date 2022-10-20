# -*- coding: utf-8 -*-

import logging
import time
import io
import requests
import json
import base64
import logging
import platform
from PIL import Image
from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, Warning
from odoo.modules.module import get_module_resource, get_resource_path
from lxml import etree


from odoo.addons.wecom_api.api.wecom_abstract_api import ApiException
import pandas as pd

pd.set_option("max_colwidth", 4096)  # 设置最大列宽
pd.set_option("display.max_columns", 30)  # 设置最大列数
pd.set_option("expand_frame_repr", False)  # 当列太多时不换行

_logger = logging.getLogger(__name__)

FORMATTED_MESSAGE_TYPE = [
    "text",
    "image",
    "link",
    "mixed",
]


class WeComMsgauditChatData(models.Model):
    _name = "wecom.chat.data"
    _description = "Wecom Chat Data"
    _order = "seq desc"

    name = fields.Char(string="Name", compute="_compute_name")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    # commented = fields.Boolean(string="Commented")
    seq = fields.Integer(
        string="Message sequence number",
        help="When pulling again, you need to bring the largest SEQ in the last packet.",
    )
    msgid = fields.Char(
        string="Message ID", help="You can use this field for message de duplication."
    )
    is_external_msg = fields.Boolean(
        string="External message", compute="_compute_is_external_msg"
    )

    publickey_ver = fields.Integer(
        string="Public key version",
        help="The version number of the public key used to encrypt this message.",
    )
    encrypt_random_key = fields.Char(string="Encrypt random key")
    encrypt_chat_msg = fields.Char(string="Encrypt chat message")
    decrypted_chat_msg = fields.Text(string="Decrypted chat message")

    action = fields.Selection(
        string="Message Action",
        selection=[
            ("send", "Send message"),
            ("recall", "Recall message"),
            ("switch", "Switch enterprise log"),
        ],
    )
    from_user = fields.Char(string="From user")

    # 消息发送者
    sender = fields.Many2one("wecom.chat.sender", string="Related Sender",)

    sender_id = fields.Char(related="sender.sender_id", store=True)
    sender_type = fields.Selection(
        string="Sender type", related="sender.sender_type", store=True
    )
    sender_name = fields.Char(string="Sender Name", related="sender.name", store=True)
    employee_id_of_sender = fields.Integer(
        string="Employee ID", compute="_compute_employee_id_of_sender", store=True
    )
    partner_id_of_sender = fields.Integer(
        string="Contact ID", compute="_compute_partner_id_of_sender", store=True
    )

    tolist = fields.Char(string="Message recipient list")

    # 聊天群
    room = fields.Many2one("wecom.chat.group", string="Related Group chat",)
    roomid = fields.Char(related="room.roomid", store=True)
    room_name = fields.Char(related="room.room_name", store=True)
    room_creator = fields.Char(related="room.room_creator", store=True)
    room_create_time = fields.Datetime(related="room.room_create_time", store=True)
    room_notice = fields.Text(related="room.room_notice", store=True)
    room_members = fields.Text(related="room.room_members", store=True)

    msgtime = fields.Datetime(string="Message time")
    msgtype = fields.Selection(
        string="Message type",
        selection=[
            ("text", "Text message"),
            ("image", "Image message"),
            ("revoke", "Revoke message"),
            ("agree", "Agree message"),
            ("disagree", "Disagree message"),
            ("voice", "Voice message"),
            ("video", "Video message"),
            ("card", "Card message"),
            ("location", "Location message"),
            ("emotion", "Emotion message"),
            ("file", "File message"),
            ("link", "Link message"),
            ("weapp", "Weapp message"),
            ("chatrecord", "Chat record message"),
            ("todo", "Todo message"),
            ("vote", "Vote message"),
            ("collect", "Collect message"),
            ("redpacket", "Red packet message"),
            ("meeting", "Meeting invitation message"),
            ("docmsg", "Online document messages"),
            ("markdown", "MarkDown messages"),
            ("news", "News messages"),
            ("calendar", "Calendar messages"),
            ("mixed", "Mixed messages"),
            ("meeting_voice_call", "Audio archive message"),
            ("voip_doc_share", "Audio shared document messages"),
            ("external_redpacket", "Interworking red packet messages"),
            ("sphfeed", "Video account messages"),
        ],
    )
    formatted = fields.Boolean(
        string="Formatted", default=False, compute="_compute_formatted", store=True
    )

    time = fields.Datetime(string="Message sending time",)
    user = fields.Char(string="User")

    text = fields.Text(string="Text message content")  # msgtype=text
    image = fields.Text(string="Image message content")  # msgtype=image
    revoke = fields.Text(string="Revoke message content")  # msgtype=revoke
    agree = fields.Text(string="Agree message content")  # msgtype=agree
    disagree = fields.Text(string="Disagree message content")  # msgtype=disagree
    voice = fields.Text(string="Voice message content")  # msgtype=voice
    video = fields.Text(string="Video message content")  # msgtype=video
    card = fields.Text(string="Card message content")  # msgtype=card
    location = fields.Text(string="Location message content")  # msgtype=location
    emotion = fields.Text(string="Emotion message content")  # msgtype=emotion
    file = fields.Text(string="File message content")  # msgtype=file
    link = fields.Text(string="Link message content")  # msgtype=link
    weapp = fields.Text(string="Weapp message content")  # msgtype=weapp
    chatrecord = fields.Text(string="Chat record message content")  # msgtype=chatrecord
    todo = fields.Text(string="Todo message content")  # msgtype=todo
    vote = fields.Text(string="Vote message content")  # msgtype=vote
    collect = fields.Text(string="Collect message content")  # msgtype=collect
    redpacket = fields.Text(string="Red packet message content")  # msgtype=redpacket
    meeting = fields.Text(
        string="Meeting invitation message content"
    )  # msgtype=meeting
    docmsg = fields.Text(string="Online document messages content")  # msgtype=docmsg
    markdown = fields.Text(string="MarkDown messages content")  # msgtype=markdown
    news = fields.Text(string="News messages content")  # msgtype=news
    calendar = fields.Text(string="Calendar messages content")  # msgtype=calendar
    mixed = fields.Text(string="Mixed messages content")  # msgtype=mixed
    meeting_voice_call = fields.Text(
        string="Audio archive message content"
    )  # msgtype=meeting_voice_call
    voip_doc_share = fields.Text(
        string="Audio shared document messages content"
    )  # msgtype=voip_doc_share
    external_redpacket = fields.Text(
        string="Interworking red packet messages content"
    )  # msgtype=external_redpacket
    sphfeed = fields.Text(string="Video account messages content")  # msgtype=sphfeed

    @api.depends("msgid", "action")
    def _compute_name(self):
        for record in self:
            if record.room_name:
                record.name = record.room_name
            else:
                record.name = record.msgid

    @api.depends("msgtype", "action")
    def _compute_formatted(self):
        for record in self:
            if record.action == "switch" or record.action == "recall":
                record.formatted = False
            else:
                content = record[record.msgtype]
                if content[0] == "{":
                    record.formatted = False
                else:
                    record.formatted = True

    @api.onchange("sender")
    def _onchange_sender(self):
        if self.sender:
            self.employee_id_of_sender = self.sender.employee_id.id
            self.partner_id_of_sender = self.sender.partner_id.id

    @api.depends("sender")
    def _compute_employee_id_of_sender(self):
        for record in self:
            if record.sender:
                record.employee_id_of_sender = record.sender.employee_id.id
            else:
                record.employee_id_of_sender = 0

    @api.depends("sender")
    def _compute_partner_id_of_sender(self):
        for record in self:
            if record.sender:
                record.partner_id_of_sender = record.sender.partner_id.id
            else:
                record.partner_id_of_sender = 0

    @api.depends("msgid", "action")
    def _compute_is_external_msg(self):
        for record in self:
            if "external" in record.msgid:
                # 消息ID 包含 external 字符串，则为外部消息
                record.is_external_msg = True
            else:
                record.is_external_msg = False

    def download_chatdatas(self):
        """
        获取聊天记录
        注:获取会话记录内容不能超过3天，如果企业需要全量数据，则企业需要定期拉取聊天消息。返回的ChatDatas内容为json格式。
        """
        get_param = self.env["ir.config_parameter"].sudo().get_param
        company = self.company_id
        if not company:
            company = self.env.company

        corpid = company.corpid
        if corpid == False:
            raise UserError(_("Corp ID cannot be empty!"))
        if company.msgaudit_app_id is False:
            raise UserError(
                _(
                    'Please bind the session content archiving application on the "Settings" page after switching company [%s].'
                )
                % company.name
            )
        secret = company.msgaudit_app_id.secret
        if secret == False:
            raise UserError(
                _(
                    "Application secret key of company [%s] session content archive cannot be empty!"
                )
                % company.name
            )

        private_keys = company.msgaudit_app_id.private_keys
        if len(private_keys) == 0:
            raise UserError(_("No message encryption key exists!"))
        key_list = []

        for key in private_keys:
            key_dic = {
                "publickey_ver": key.publickey_ver,
                "private_key": key.private_key,
            }
            key_list.append(key_dic)

        # 首次访问填写0，非首次使用上次企业微信返回的最大seq。允许从任意seq重入拉取。
        max_seq_id = 0
        self.env.cr.execute(
            """
            SELECT MAX(seq)
            FROM wecom_chat_data
            WHERE company_id=%s
            """
            % (company.id)
        )  # 查询最大seq的记录
        results = self.env.cr.dictfetchall()
        if results[0]["max"] is not None:
            max_seq_id = results[0]["max"]

        try:
            msgaudit_sdk_url = get_param("wecom.msgaudit.msgaudit_sdk_url")
            msgaudit_chatdata_url = get_param("wecom.msgaudit.msgaudit_chatdata_url")

            chatdata_url = msgaudit_sdk_url + msgaudit_chatdata_url

            proxy = True if get_param("wecom.msgaudit_sdk_proxy") == "True" else False
            headers = {"content-type": "application/json"}
            body = {
                "seq": max_seq_id,
                "corpid": corpid,
                "secret": secret,
                "private_keys": key_list,
            }

            if proxy:
                body.update(
                    {"proxy": msgaudit_chatdata_url, "paswd": "odoo:odoo",}
                )

            response = requests.get(
                chatdata_url, data=json.dumps(body), headers=headers
            ).json()

            if response["code"] == 0:
                chat_datas = response["data"]
                if len(chat_datas) > 0:
                    for data in chat_datas:
                        dic_data = {}

                        is_external_msg = True if "external" in data["msgid"] else False
                        dic_data = {
                            "seq": data["seq"],
                            "msgid": data["msgid"],
                            "publickey_ver": data["publickey_ver"],
                            "encrypt_random_key": data["encrypt_random_key"],
                            "encrypt_chat_msg": data["encrypt_chat_msg"],
                            "decrypted_chat_msg": json.dumps(
                                data["decrypted_chat_msg"]
                            ),
                            "is_external_msg": is_external_msg,
                        }
                        # auto_get_internal_groupchat_name = ir_config.get_param(
                        #     "wecom.msgaudit.auto_get_internal_groupchat_name"
                        # )
                        # 以下为解密聊天信息内容
                        for key, value in data["decrypted_chat_msg"].items():
                            if key == "msgid":
                                pass
                            elif key == "voiceid":
                                pass
                            elif key == "from":
                                dic_data["from_user"] = value
                                # 创建发送者
                                sender = self.get_and_create_chat_sender(value)
                                dic_data.update({"sender": sender.id})
                            elif key == "tolist":
                                dic_data["tolist"] = json.dumps(value)
                            elif key == "roomid" and value:
                                room = {}
                                if is_external_msg:
                                    # 外部消息
                                    room = {
                                        "roomid": value,
                                    }
                                else:
                                    # 内部群可以通过API获取群信息
                                    room = self.get_group_chat_info_by_roomid(
                                        company, value
                                    )
                                group_chat = self.create_group_chat(room)
                                dic_data.update({"room": group_chat.id})
                            elif key == "msgtime" or key == "time":
                                time_stamp = value
                                # dic_data[key] = self.timestamp2datetime(time_stamp)
                                dic_data.update(
                                    {key: self.timestamp2datetime(time_stamp)}
                                )
                            else:
                                dic_data.update({key: value})
                        self.sudo().create(dic_data)
                    return True
                else:
                    return False
            else:
                return _(
                    "Request error, error code:%s, error description:%s, suggestion:%s"
                ) % (response["code"], response["description"], response["suggestion"])
        except ApiException as e:
            return self.env["wecomapi.tools.action"].ApiExceptionDialog(
                e, raise_exception=True
            )
        except Exception as e:
            _logger.exception("Exception: %s" % e)
            return str(e)

    def bind_internal_group_chat(self):
        """
        绑定内部群聊 到模型
        """
        if self.is_external_msg:
            # 外部消息，pass
            pass
        else:
            if self.room_name:
                pass
            else:
                # 无群名称，获取群名称
                pass

    @api.model
    def _default_image(self):
        image_path = get_module_resource(
            "wecom_api", "static/src/img", "default_image.png"
        )
        return base64.b64encode(open(image_path, "rb").read())

    def get_group_chat_info_by_roomid(self, company_id, roomid):
        """
        获取内部群聊信息
        """
        company = company_id
        if not company:
            company = self.env.company
        room_dic = {}
        try:
            wxapi = self.env["wecom.service_api"].InitServiceApi(
                company.corpid, company.msgaudit_app_id.secret
            )
            response = wxapi.httpCall(
                self.env["wecom.service_api_list"].get_server_api_call(
                    "MSGAUDIT_GROUPCHAT_GET"
                ),
                {"roomid": roomid},
            )

            if response["errcode"] == 0:
                time_stamp = response["room_create_time"]
                room_create_time = self.timestamp2datetime(time_stamp)
                room_dic = {
                    "roomid": roomid,
                    "room_name": response["roomname"],
                    "room_creator": response["creator"],
                    "room_notice": response["notice"],
                    "room_create_time": room_create_time,
                    "room_members": json.dumps(response["members"]),
                }
        except ApiException as ex:
            return self.env["wecomapi.tools.action"].ApiExceptionDialog(
                ex, raise_exception=True
            )
        finally:
            return room_dic

    def create_group_chat(self, room):
        """
        创建群聊
        """
        groupchat = (
            self.env["wecom.chat.group"]
            .sudo()
            .search([("roomid", "=", room["roomid"])], limit=1)
        )
        if groupchat:
            pass
        else:
            company = self.company_id
            if not company:
                company = self.env.company
            room.update({"company_id": company.id})
            groupchat.create(room)
        return groupchat

    def update_group_chat(self):
        """
        更新群聊信息
        """
        company = self.company_id
        if not company:
            company = self.env.company

        try:
            wxapi = self.env["wecom.service_api"].InitServiceApi(
                company.corpid, company.msgaudit_app_id.secret
            )
            response = wxapi.httpCall(
                self.env["wecom.service_api_list"].get_server_api_call(
                    "MSGAUDIT_GROUPCHAT_GET"
                ),
                {"roomid": self.roomid},
            )
            if response["errcode"] == 0:
                time_stamp = response["room_create_time"]
                room_create_time = self.timestamp2datetime(time_stamp)
                self.write(
                    {
                        "room_name": response["roomname"],
                        "room_creator": response["creator"],
                        "room_notice": response["notice"],
                        "room_create_time": room_create_time,
                        "room_members": json.dumps(response["members"]),
                    }
                )
                same_group_chats = self.search([("roomid", "=", self.roomid)])
                group = self.env["wecom.chat.group"].search(
                    [("roomid", "=", self.roomid)], limit=1,
                )
                group.write({"room_name": response["roomname"]})
                for chat in same_group_chats:
                    chat.write(
                        {"room_name": response["roomname"],}
                    )
        except ApiException as ex:
            return self.env["wecomapi.tools.action"].ApiExceptionDialog(
                ex, raise_exception=True
            )

    def get_and_create_chat_sender(self, sender_id):
        """
        获取和创建发送者
        """
        sender = (
            self.env["wecom.chat.sender"]
            .sudo()
            .search([("sender_id", "=", sender_id)], limit=1)
        )
        if sender:
            return sender
        else:
            dic = {}
            dic.update({"sender_id": sender_id})
            if "wo-" in sender_id or "wm-" in sender_id:
                dic.update({"name": sender_id[-6:]})
                if "wo-" in sender_id:
                    dic.update({"sender_type": "wecom"})
                if "wm-" in sender_id:
                    dic.update({"sender_type": "wechat"})
            else:
                dic.update({"sender_type": "staff"})
                partner = self.env["res.partner"].search(
                    [("wecom_userid", "=", sender_id),], limit=1,
                )
                company = self.company_id
                if not company:
                    company = self.env.company
                employee = self.env["hr.employee"].search(
                    [
                        ("wecom_userid", "=", sender_id),
                        ("company_id", "=", company.id),
                    ],
                    limit=1,
                )

                if employee:
                    dic.update({"employee_id": employee.id})
                # 优先使用 联系人的名称
                if partner:
                    dic.update(
                        {"partner_id": partner.id, "name": partner.name,}
                    )
                else:
                    if employee:
                        dic.update({"name": employee.name})
                    else:
                        dic.update(
                            {
                                "name": sender_id[-6:]
                                if len(sender_id) > 6
                                else sender_id
                            }
                        )
            sender = self.env["wecom.chat.sender"].sudo().create(dic)
            return sender

    def create_chat_sender(self):
        """
        创建消息发送者
        同时修改相同发送者的消息记录
        """
        sender_id = (
            self.from_user if self.from_user else eval(self.decrypted_chat_msg)["from"]
        )
        dic = {}
        dic.update({"sender_id": sender_id})
        chats = self.search([("from_user", "=", sender_id)])

        for chat in chats:
            if chat.sender:
                pass
            else:
                if (
                    chat.from_user == sender_id
                    or eval(self.decrypted_chat_msg)["from"] == sender_id
                ):
                    if "wo-" in sender_id or "wm-" in sender_id:
                        if "wo-" in sender_id:
                            dic.update({"sender_type": "wecom"})
                        if "wm-" in sender_id:
                            dic.update({"sender_type": "wechat"})
                    else:
                        dic.update({"sender_type": "staff"})
                        partner = self.env["res.partner"].search(
                            [("wecom_userid", "=", sender_id),], limit=1,
                        )
                        employee = self.env["hr.employee"].search(
                            [
                                ("wecom_userid", "=", sender_id),
                                ("company_id", "=", self.company_id.id),
                            ],
                            limit=1,
                        )
                        if employee:
                            dic.update({"employee_id": employee.id})
                        # 优先使用 联系人的名称
                        if partner:
                            dic.update(
                                {"partner_id": partner.id, "name": partner.name,}
                            )
                        else:
                            if employee:
                                dic.update({"name": employee.name})
                            else:
                                dic.update(
                                    {
                                        "name": sender_id[-6:]
                                        if len(sender_id) > 6
                                        else sender_id
                                    }
                                )
                    sender = (
                        self.env["wecom.chat.sender"]
                        .sudo()
                        .search([("sender_id", "=", sender_id)], limit=1)
                    )
                    if len(sender) == 0:
                        sender = self.env["wecom.chat.sender"].sudo().create(dic)
                    chat.write({"sender": sender.id})

    def get_decrypted_chat_msg_fields(self):
        fields = [f for f in self._fields.keys()]
        remove_field = [
            "id",
            "name",
            "company_id",
            "seq",
            "msgid",
            "publickey_ver",
            "encrypt_random_key",
            "encrypt_chat_msg",
            "decrypted_chat_msg",
            "create_date",
            "create_uid",
            "write_date",
            "write_uid",
            "__last_update",
        ]
        for r in remove_field:
            fields.remove(r)
        return fields

    def timestamp2datetime(self, time_stamp):
        """
        时间戳转日期时间
        """
        if len(str(time_stamp)) > 10:
            # 一般爬取下来的时间戳长度都是13位的数字，而time.localtime的参数要的长度是10位，所以我们需要将其/1000并取整即可
            time_stamp = int(time_stamp / 1000)
        loc_time = time.localtime(time_stamp)
        return time.strftime("%Y-%m-%d %H:%M:%S", loc_time)

    # ------------------------------------------------------------
    # 任务
    # ------------------------------------------------------------
    def cron_download_chatdatas(self):
        """
        自动任务定时下载聊天记录
        """
        for app in self.env["wecom.apps"].search(
            [("company_id", "!=", False), ("type_code", "=", "['msgaudit']")]
        ):
            _logger.info(
                _("Automatic task: Start download session content record for [%s]")
                % app.company_id.name
            )
            corpid = app.company_id.corpid
            secret = app.secret
            private_keys = app.private_keys
            key_list = []

            for key in private_keys:
                key_dic = {
                    "publickey_ver": key.publickey_ver,
                    "private_key": key.private_key,
                }
                key_list.append(key_dic)
            # 首次访问填写0，非首次使用上次企业微信返回的最大seq。允许从任意seq重入拉取。
            max_seq_id = 0
            self.env.cr.execute(
                """
                SELECT MAX(seq)
                FROM wecom_chat_data
                WHERE company_id=%s
                """
                % (app.company_id.id)
            )  # 查询最大seq的记录
            results = self.env.cr.dictfetchall()
            if results[0]["max"] is not None:
                max_seq_id = results[0]["max"]

            try:
                get_param = self.env["ir.config_parameter"].sudo().get_param

                msgaudit_sdk_url = get_param("wecom.msgaudit.msgaudit_sdk_url")
                msgaudit_chatdata_url = get_param(
                    "wecom.msgaudit.msgaudit_chatdata_url"
                )

                chatdata_url = msgaudit_sdk_url + msgaudit_chatdata_url

                proxy = (
                    True if get_param("wecom.msgaudit_sdk_proxy") == "True" else False
                )
                headers = {"content-type": "application/json"}
                body = {
                    "seq": max_seq_id,
                    "corpid": corpid,
                    "secret": secret,
                    "private_keys": key_list,
                }
                if proxy:
                    body.update(
                        {"proxy": msgaudit_chatdata_url, "paswd": "odoo:odoo",}
                    )

                response = requests.get(
                    chatdata_url, data=json.dumps(body), headers=headers
                ).json()

                if response["code"] == 0:
                    chat_datas = response["data"]

                    if len(chat_datas) > 0:
                        for data in chat_datas:
                            dic_data = {}
                            is_external_msg = (
                                True if "external" in data["msgid"] else False
                            )
                            dic_data = {
                                "company_id": app.company_id.id,
                                "seq": data["seq"],
                                "msgid": data["msgid"],
                                "publickey_ver": data["publickey_ver"],
                                "encrypt_random_key": data["encrypt_random_key"],
                                "encrypt_chat_msg": data["encrypt_chat_msg"],
                                "decrypted_chat_msg": json.dumps(
                                    data["decrypted_chat_msg"]
                                ),
                                "is_external_msg": is_external_msg,
                            }

                            # 以下为解密聊天信息内容
                            for key, value in data["decrypted_chat_msg"].items():
                                if key == "msgid":
                                    pass
                                elif key == "voiceid":
                                    pass
                                elif key == "from":
                                    dic_data["from_user"] = value
                                    # 创建发送者
                                    sender = self.get_and_create_chat_sender(value)
                                    dic_data.update({"sender": sender.id})
                                elif key == "tolist":
                                    dic_data["tolist"] = json.dumps(value)
                                elif key == "roomid" and value:
                                    room = {}
                                    if is_external_msg:
                                        room = {
                                            "roomid": value,
                                        }
                                    else:
                                        # 内部群可以通过API获取群信息
                                        room = self.get_group_chat_info_by_roomid(
                                            app.company_id, value
                                        )
                                    group_chat = self.create_group_chat(room)
                                    dic_data.update({"room": group_chat.id})
                                elif key == "msgtime" or key == "time":
                                    time_stamp = value
                                    # dic_data[key] = self.timestamp2datetime(time_stamp)
                                    dic_data.update(
                                        {key: self.timestamp2datetime(time_stamp)}
                                    )
                                else:
                                    dic_data.update({key: value})

                            self.sudo().create(dic_data)
                        _logger.info(
                            _(
                                "Automatic task: End download session content record for [%s]"
                            )
                            % app.company_id.name
                        )
                    else:
                        _logger.info(
                            _(
                                "Automatic task: End download session content record for [%s],There are no records to download."
                            )
                            % app.company_id.name
                        )
                else:
                    _logger.warning(
                        _(
                            "Request error, error code:%s, error description:%s, suggestion:%s"
                        )
                        % (
                            response["code"],
                            response["description"],
                            response["suggestion"],
                        )
                    )
            except ApiException as e:
                _logger.exception(
                    _(
                        "Automatic task: Exception in downloading session content record for [%s],Exception:%s"
                    )
                    % (app.company_id.name, str(e))
                )
            except Exception as e:
                _logger.exception(
                    _(
                        "Automatic task: Exception in downloading session content record for [%s],Exception:%s"
                    )
                    % (app.company_id.name, str(e))
                )

    def cron_format_content(self):
        """
        任务自动格式化消息
        暂时支持消息类型: text / link / image 
        超过3天未格式化的数据,pass掉
        切换企业日志类型的消息,pass掉
        """
        _logger.info(
            _("Automatic task: Start formatting session content archive record.")
        )
        chats = self.search([("formatted", "=", False), ("action", "!=", "switch")])

        for chat in chats:
            chat.format_content()

        _logger.info(
            _("Automatic task: End formatting session content archive record.")
        )

    # ------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------
    def format_content(self):
        """
        格式化消息内容
        暂时支持消息类型: 见 FORMATTED_MESSAGE_TYPE 定义
        """
        formatted = False
        company = self.company_id
        if not company:
            company = self.env.company

        if company.msgaudit_app_id is False:
            raise UserError(
                _(
                    "Please bind the session content archiving application on the settings page."
                )
            )

        content = self[self._fields[self.msgtype].name]

        allow_formatting = False

        if content[0] == "{" and self.msgtype in FORMATTED_MESSAGE_TYPE:
            # 是json格式的内容
            allow_formatting = True
        elif self.msgtype == "image":
            # 检查图片是否可以打开
            tree = etree.HTML(self.image)
            image_str = tree.xpath("//img/@src")[0]
            if self.env["wecom.msgaudit.tools"].verify_img(image_str):
                # 图片正常,不允许格式化
                allow_formatting = False
            else:
                # 图片异常,允许格式化
                allow_formatting = True

        if allow_formatting:
            # msg_content = self[self._fields[self.msgtype].name]

            if self.msgtype == "text":
                # 文本消息
                format_result = self.env["wecom.msgaudit.tools"].format_text_message(
                    self
                )
                formatted = format_result["formatted"]
                content = format_result["content"]
            elif self.msgtype == "link":
                # 链接消息
                format_result = self.env["wecom.msgaudit.tools"].format_link_message(
                    self
                )
                formatted = format_result["formatted"]
                content = format_result["content"]
            elif self.msgtype == "image":
                # 图片消息
                format_result = self.env["wecom.msgaudit.tools"].format_image_message(
                    self
                )
                formatted = format_result["formatted"]
                content = format_result["content"]

            elif self.msgtype == "mixed":
                # 混合消息
                format_result = self.env["wecom.msgaudit.tools"].format_mixed_message(
                    self
                )
                formatted = format_result["formatted"]
                content = format_result["content"]
            else:
                pass

            self.write(
                {self._fields[self.msgtype].name: content, "formatted": formatted,}
            )

