# -*- coding: utf-8 -*-

import ast
import base64
import datetime
import dateutil
import email
import email.policy
import hashlib
import hmac
import lxml
import logging
import pytz
import re
import socket
import time
import threading

from collections import namedtuple
from email.message import EmailMessage
from email import message_from_string, policy
from lxml import etree
from werkzeug import urls
from xmlrpc import client as xmlrpclib

from odoo import _, api, exceptions, fields, models, tools, registry, SUPERUSER_ID
from odoo.exceptions import MissingError
from odoo.osv import expression

from odoo.tools import ustr
from odoo.tools.misc import clean_context, split_every

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

     - ``mail_create_nosubscribe``: 在创建或消息发布时，不要向记录线程订阅uid
     - ``mail_create_nolog``: 在创建时，不要记录自动的'<Document>created'消息
     - ``mail_notrack``: 在创建和写入时，不要执行值跟踪创建消息
     - ``tracking_disable``: 在创建和写入时，不执行邮件线程功能（自动订阅、跟踪、发布…）
     - ``mail_notify_force_send``: 如果要发送的电子邮件通知少于50个，请直接发送，而不是使用队列；默认情况下为True
    """

    _inherit = "mail.thread"

    is_wecom_message = fields.Boolean(
        "WeCom Message",
    )

    msgtype = fields.Selection(
        [
            ("text", "Text message"),
            ("image", "Picture message"),
            ("voice", "Voice messages"),
            ("video", "Video message"),
            ("file", "File message"),
            ("textcard", "Text card message"),
            ("news", "Graphic message"),
            ("mpnews", "Graphic message(mpnews)"),
            ("markdown", "Markdown message"),
            ("miniprogram", "Mini Program Notification Message"),
            ("taskcard", "Task card message"),
            ("template_card", "Template card message"),
            ("template_card", "Template card message"),
        ],
        string="Message type",
        required=True,
        default="text",
    )

    message_to_user = fields.Char(
        string="To Users",
        help="Message recipients (users)",
    )
    message_to_party = fields.Char(
        string="To Departments",
        help="Message recipients (departments)",
    )
    message_to_tag = fields.Char(
        string="To Tags",
        help="Message recipients (tags)",
    )

    # content
    media_id = fields.Many2one(
        string="Media file id",
        comodel_name="wecom.material",
        help="Media file ID, which can be obtained by calling the upload temporary material interface",
    )
    body_json = fields.Text(
        "Text Body",
        translate=True,
    )
    body_markdown = fields.Text(
        "Markdown Body",
        translate=True,
    )
    body_html = fields.Html("Html Body", translate=True, sanitize=False)

    # options
    safe = fields.Selection(
        [
            ("0", "Shareable"),
            ("1", "Cannot share and content shows watermark"),
            ("2", "Only share within the company "),
        ],
        string="Secret message",
        required=True,
        default="1",
        help="Indicates whether it is a confidential message, 0 indicates that it can be shared externally, 1 indicates that it cannot be shared and the content displays watermark, 2 indicates that it can only be shared within the enterprise, and the default is 0; Note that only messages of mpnews type support the safe value of 2, and other message types do not",
    )

    enable_id_trans = fields.Boolean(
        string="Turn on id translation",
        help="Indicates whether to enable ID translation, 0 indicates no, 1 indicates yes, and 0 is the default",
        default=False,
    )
    enable_duplicate_check = fields.Boolean(
        string="Turn on duplicate message checking",
        help="Indicates whether to enable duplicate message checking. 0 indicates no, 1 indicates yes. The default is 0",
        default=False,
    )
    duplicate_check_interval = fields.Integer(
        string="Time interval for repeated message checking",
        help="Indicates whether the message check is repeated. The default is 1800s and the maximum is no more than 4 hours",
        default="1800",
    )

    # ------------------------------------------------------
    # 增加、查询、修改、删除
    # CRUD
    # ------------------------------------------------------

    # ------------------------------------------------------
    # 模型/CRUD助手
    # MODELS / CRUD HELPERS
    # ------------------------------------------------------

    # ------------------------------------------------------
    # 包装和工具
    # WRAPPERS AND TOOLS
    # ------------------------------------------------------

    # ------------------------------------------------------
    # 追踪/记录
    # TRACKING / LOG
    # ------------------------------------------------------

    # ------------------------------------------------------
    # 邮件网关
    # MAIL GATEWAY
    # ------------------------------------------------------
    def _message_parse_extract_payload_postprocess(self, message, payload_dict):
        """
        在从电子邮件中提取的正文和附件中执行一些清理/后处理。请注意，此处理特定于邮件模块，不应包含安全性或通用html清理。
        实际上，工具中的html_清理方法应该涵盖这些方面。
        """
        body, body_html, body_json, body_markdown, attachments = (
            payload_dict["body"],
            payload_dict["body_html"],
            payload_dict["body_json"],
            payload_dict["body_markdown"],
            payload_dict["attachments"],
        )
        if not body.strip():
            return {
                "body": body,
                "body_html": body_html,
                "body_json": body_json,
                "body_markdown": body_markdown,
                "attachments": attachments,
            }
        try:
            root = lxml.html.fromstring(body)
        except ValueError:
            # In case the email client sent XHTML, fromstring will fail because 'Unicode strings
            # with encoding declaration are not supported'.
            root = lxml.html.fromstring(body.encode("utf-8"))

        postprocessed = False
        to_remove = []
        for node in root.iter():
            if "o_mail_notification" in (
                node.get("class") or ""
            ) or "o_mail_notification" in (node.get("summary") or ""):
                postprocessed = True
                if node.getparent() is not None:
                    to_remove.append(node)
            if node.tag == "img" and node.get("src", "").startswith("cid:"):
                cid = node.get("src").split(":", 1)[1]
                related_attachment = [
                    attach
                    for attach in attachments
                    if attach[2] and attach[2].get("cid") == cid
                ]
                if related_attachment:
                    node.set("data-filename", related_attachment[0][0])
                    postprocessed = True

        for node in to_remove:
            node.getparent().remove(node)
        if postprocessed:
            body = etree.tostring(root, pretty_print=False, encoding="unicode")
        return {
            "body": body,
            "body_html": body_html,
            "body_json": body_json,
            "body_markdown": body_markdown,
            "attachments": attachments,
        }

    def _message_parse_extract_payload(self, message, save_original=False):
        """
        从邮件中提取正文作为HTML和附件
        """
        attachments = []
        body = ""
        body_html = ""
        body_json = ""
        body_markdown = ""
        if save_original:
            attachments.append(
                self._Attachment("original_email.eml", message.as_string(), {})
            )

        # 请小心，内容类型可能包含棘手的内容，如以下示例中所示，因此请使用startswith()测试MIME类型
        #
        # Content-Type: multipart/related;
        #   boundary="_004_3f1e4da175f349248b8d43cdeb9866f1AMSPR06MB343eurprd06pro_";
        #   type="text/html"
        if message.get_content_maintype() == "text":
            encoding = message.get_content_charset()
            body = message.get_content()
            body = tools.ustr(body, encoding, errors="replace")
            body_html = message.get_content()
            body_html = tools.ustr(body_html, encoding, errors="replace")
            body_json = message.get_content()
            body_json = tools.ustr(body_json, encoding, errors="replace")
            body_markdown = message.get_content()
            body_markdown = tools.ustr(body_markdown, encoding, errors="replace")
            if message.get_content_type() == "text/plain":
                # text/plain -> <pre/>
                body = tools.append_content_to_html("", body, preserve=True)
                body_html = tools.append_content_to_html("", body_html, preserve=True)
                body_json = tools.append_content_to_html("", body_json, preserve=True)
                body_markdown = tools.append_content_to_html(
                    "", body_markdown, preserve=True
                )
        else:
            alternative = False
            mixed = False
            html = ""
            for part in message.walk():
                if part.get_content_type() == "multipart/alternative":
                    alternative = True
                if part.get_content_type() == "multipart/mixed":
                    mixed = True
                if part.get_content_maintype() == "multipart":
                    continue  # skip container

                filename = part.get_filename()  # I may not properly handle all charsets
                encoding = part.get_content_charset()  # None if attachment

                # 0) 内联附件 -> 附件，元组中有第三部分与 cid / 附件匹 配
                if filename and part.get("content-id"):
                    inner_cid = part.get("content-id").strip("><")
                    attachments.append(
                        self._Attachment(
                            filename, part.get_content(), {"cid": inner_cid}
                        )
                    )
                    continue
                # 1) 显式附件 -> 附件
                if filename or part.get("content-disposition", "").strip().startswith(
                    "attachment"
                ):
                    attachments.append(
                        self._Attachment(
                            filename or "attachment", part.get_content(), {}
                        )
                    )
                    continue
                # 2) text/plain -> <pre/>
                if part.get_content_type() == "text/plain" and (
                    not alternative or not body
                ):
                    body = tools.append_content_to_html(
                        body,
                        tools.ustr(part.get_content(), encoding, errors="replace"),
                        preserve=True,
                    )
                    body_html = tools.append_content_to_html(
                        body_html,
                        tools.ustr(part.get_content(), encoding, errors="replace"),
                        preserve=True,
                    )
                    body_json = tools.append_content_to_html(
                        body_json,
                        tools.ustr(part.get_content(), encoding, errors="replace"),
                        preserve=True,
                    )
                    body_markdown = tools.append_content_to_html(
                        body_markdown,
                        tools.ustr(part.get_content(), encoding, errors="replace"),
                        preserve=True,
                    )
                # 3) text/html -> raw
                elif part.get_content_type() == "text/html":
                    # mutlipart/alternative have one text and a html part, keep only the second
                    # mixed allows several html parts, append html content
                    append_content = not alternative or (html and mixed)
                    html = tools.ustr(part.get_content(), encoding, errors="replace")
                    if not append_content:
                        body = html
                        body_html = body_html
                        body_json = body_json
                        body_markdown = body_markdown
                    else:
                        body = tools.append_content_to_html(body, html, plaintext=False)
                        body_html = tools.append_content_to_html(
                            body_html, html, plaintext=False
                        )
                        body_json = tools.append_content_to_html(
                            body_json, html, plaintext=False
                        )
                        body_markdown = tools.append_content_to_html(
                            body_markdown, html, plaintext=False
                        )
                    # 我们在这里只 strip_classes，其他一切都将在mail.message的html字段中完成
                    body = tools.html_sanitize(
                        body, sanitize_tags=False, strip_classes=True
                    )
                    body_html = tools.html_sanitize(
                        body_html, sanitize_tags=False, strip_classes=True
                    )
                    body_json = tools.html_sanitize(
                        body_json, sanitize_tags=False, strip_classes=True
                    )
                    body_markdown = tools.html_sanitize(
                        body_markdown, sanitize_tags=False, strip_classes=True
                    )
                # 4) Anything else -> attachment
                else:
                    attachments.append(
                        self._Attachment(
                            filename or "attachment", part.get_content(), {}
                        )
                    )

        return self._message_parse_extract_payload_postprocess(
            message,
            {
                "body": body,
                "body_html": body_html,
                "body_json": body_json,
                "body_markdown": body_markdown,
                "attachments": attachments,
            },
        )

    @api.model
    def message_parse(self, message, save_original=False):
        """
        解析表示RFC-2822电子邮件的 email.message.message，并返回包含消息详细信息的通用dict。

        :param message: email to parse
        :type message: email.message.Message
        :param bool save_original: whether the returned dict should include
            an ``original`` attachment containing the source of the message
        :rtype: dict
        :return: A dict with the following structure, where each field may not
            be present if missing in original message::

            { 'message_id': msg_id,
              'subject': subject,
              'email_from': from,
              'to': to + delivered-to,
              'cc': cc,
              'recipients': delivered-to + to + cc + resent-to + resent-cc,
              'partner_ids': partners found based on recipients emails,
              'body': unified_body,
              'references': references,
              'in_reply_to': in-reply-to,
              'parent_id': parent mail.message based on in_reply_to or references,
              'is_internal': answer to an internal message (note),
              'date': date,
              'attachments': [('file1', 'bytes'),
                              ('file2', 'bytes')}
        """
        if not isinstance(message, EmailMessage):
            raise ValueError(_("Message should be a valid EmailMessage instance"))
        msg_dict = {"message_type": "email"}

        message_id = message.get("Message-Id")
        if not message_id:
            # 非常不寻常的情况，就是我们在这里应该容错
            message_id = "<%s@localhost>" % time.time()
            _logger.debug(
                "Parsing Message without message-id, generating a random one: %s",
                message_id,
            )
        msg_dict["message_id"] = message_id.strip()

        if message.get("Subject"):
            msg_dict["subject"] = tools.decode_message_header(message, "Subject")

        email_from = tools.decode_message_header(message, "From")
        email_cc = tools.decode_message_header(message, "cc")
        email_from_list = tools.email_split_and_format(email_from)
        email_cc_list = tools.email_split_and_format(email_cc)
        msg_dict["email_from"] = email_from_list[0] if email_from_list else email_from
        msg_dict["from"] = msg_dict["email_from"]  # compatibility for message_new
        msg_dict["cc"] = ",".join(email_cc_list) if email_cc_list else email_cc
        # Delivered-To is a safe bet in most modern MTAs, but we have to fallback on To + Cc values
        # for all the odd MTAs out there, as there is no standard header for the envelope's `rcpt_to` value.
        msg_dict["recipients"] = ",".join(
            set(
                formatted_email
                for address in [
                    tools.decode_message_header(message, "Delivered-To"),
                    tools.decode_message_header(message, "To"),
                    tools.decode_message_header(message, "Cc"),
                    tools.decode_message_header(message, "Resent-To"),
                    tools.decode_message_header(message, "Resent-Cc"),
                ]
                if address
                for formatted_email in tools.email_split_and_format(address)
            )
        )
        msg_dict["to"] = ",".join(
            set(
                formatted_email
                for address in [
                    tools.decode_message_header(message, "Delivered-To"),
                    tools.decode_message_header(message, "To"),
                ]
                if address
                for formatted_email in tools.email_split_and_format(address)
            )
        )
        partner_ids = [
            x.id
            for x in self._mail_find_partner_from_emails(
                tools.email_split(msg_dict["recipients"]), records=self
            )
            if x
        ]
        msg_dict["partner_ids"] = partner_ids
        # compute references to find if email_message is a reply to an existing thread
        msg_dict["references"] = tools.decode_message_header(message, "References")
        msg_dict["in_reply_to"] = tools.decode_message_header(
            message, "In-Reply-To"
        ).strip()

        if message.get("Date"):
            try:
                date_hdr = tools.decode_message_header(message, "Date")
                parsed_date = dateutil.parser.parse(date_hdr, fuzzy=True)
                if parsed_date.utcoffset() is None:
                    # naive datetime, so we arbitrarily decide to make it
                    # UTC, there's no better choice. Should not happen,
                    # as RFC2822 requires timezone offset in Date headers.
                    stored_date = parsed_date.replace(tzinfo=pytz.utc)
                else:
                    stored_date = parsed_date.astimezone(tz=pytz.utc)
            except Exception:
                _logger.info(
                    "Failed to parse Date header %r in incoming mail "
                    "with message-id %r, assuming current date/time.",
                    message.get("Date"),
                    message_id,
                )
                stored_date = datetime.datetime.now()
            msg_dict["date"] = stored_date.strftime(
                tools.DEFAULT_SERVER_DATETIME_FORMAT
            )

        parent_ids = False
        if msg_dict["in_reply_to"]:
            parent_ids = self.env["mail.message"].search(
                [("message_id", "=", msg_dict["in_reply_to"])], limit=1
            )
        if msg_dict["references"] and not parent_ids:
            references_msg_id_list = tools.mail_header_msgid_re.findall(
                msg_dict["references"]
            )
            parent_ids = self.env["mail.message"].search(
                [("message_id", "in", [x.strip() for x in references_msg_id_list])],
                limit=1,
            )
        if parent_ids:
            msg_dict["parent_id"] = parent_ids.id
            msg_dict["is_internal"] = (
                parent_ids.subtype_id and parent_ids.subtype_id.internal or False
            )

        msg_dict.update(
            self._message_parse_extract_payload(message, save_original=save_original)
        )
        msg_dict.update(self._message_parse_extract_bounce(message, msg_dict))
        return msg_dict

    # ------------------------------------------------------
    # 收件人管理工具
    # RECIPIENTS MANAGEMENT TOOLS
    # ------------------------------------------------------

    # ------------------------------------------------------
    # 消息发布API
    # MESSAGE POST API
    # ------------------------------------------------------

    @api.returns("mail.message", lambda value: value.id)
    def message_post(
        self,
        *,
        body="",
        subject=None,
        message_type="notification",
        email_from=None,
        author_id=None,
        parent_id=False,
        subtype_xmlid=None,
        subtype_id=False,
        partner_ids=None,
        channel_ids=None,
        attachments=None,
        attachment_ids=None,
        add_sign=True,
        record_name=False,
        # 企业微信字段 start
        msgtype=None,
        is_wecom_message=None,
        message_to_user=None,
        message_to_party=None,
        message_to_tag=None,
        media_id=None,
        body_html=None,
        body_json=None,
        body_markdown=None,
        safe=None,
        enable_id_trans=None,
        enable_duplicate_check=None,
        duplicate_check_interval=None,
        # 企业微信字段 end
        **kwargs,
    ):
        """
        在现有线程中发布新消息，并返回新的mail.message ID。
        :param str body: 邮件正文，通常是原始HTML，将被清理消毒
        :param str subject: 消息的主题
        :param str message_type: 请参阅mail_message.message_type字段。 可以是user_notification以外的任何内容，保留给message_notify
        :param int parent_id: 处理线程队列
        :param int subtype_id: 消息的subtype_id，主要用于关注者机制
        :param list(int) partner_ids: partner_ids通知
        :param list(int) channel_ids: channel_ids通知
        :param list(tuple(str,str), tuple(str,str, dict) or int) attachments : 以``(name,content)``或 ``(name,content, info)`` 形式的附件元组列表，其中content不是base64编码的
        :param list id attachment_ids: 链接到此消息的现有附件列表
            - 只能由聊天设定
            - 附加到mail.compose.message（0）的附件对象将被附加到相关文档。
        额外的关键字参数将用作新mail.message记录的默认列值。
        :return int: ID of newly created mail.message
        """
        self.ensure_one()  # 应始终记录在记录上，如果没有记录，请使用message_notify
        # 从通知附加值中拆分消息附加值
        msg_kwargs = dict(
            (key, val)
            for key, val in kwargs.items()
            if key in self.env["mail.message"]._fields
        )
        notif_kwargs = dict(
            (key, val) for key, val in kwargs.items() if key not in msg_kwargs
        )

        if (
            self._name == "mail.thread"
            or not self.id
            or message_type == "user_notification"
        ):
            raise ValueError(
                "message_post should only be call to post message on record. Use message_notify instead"
            )

        if "model" in msg_kwargs or "res_id" in msg_kwargs:
            raise ValueError(
                "message_post doesn't support model and res_id parameters anymore. Please call message_post on record."
            )
        if "subtype" in kwargs:
            raise ValueError(
                "message_post doesn't support subtype parameter anymore. Please give a valid subtype_id or subtype_xmlid value instead."
            )

        self = self._fallback_lang()  # 立即将lang添加到上下文中，因为在以后的各种流程中它将很有用。

        # 显式访问权限检查，因为display_name计算为sudo。
        self.check_access_rights("read")
        self.check_access_rule("read")
        record_name = record_name or self.display_name

        partner_ids = set(partner_ids or [])
        channel_ids = set(channel_ids or [])

        if any(not isinstance(pc_id, int) for pc_id in partner_ids | channel_ids):
            raise ValueError(
                "message_post partner_ids and channel_ids must be integer list, not commands"
            )

        # 查找邮件的作者
        author_id, email_from = self._message_compute_author(
            author_id, email_from, raise_exception=True
        )

        if subtype_xmlid:
            subtype_id = self.env["ir.model.data"].xmlid_to_res_id(subtype_xmlid)
        if not subtype_id:
            subtype_id = self.env["ir.model.data"].xmlid_to_res_id("mail_mt_note")

        # 根据要求自动订阅收件人
        if self._context.get("mail_post_autofollow") and partner_ids:
            self.message_subscribe(list(partner_ids))

        MailMessage_sudo = self.env["mail.message"].sudo()
        if self._mail_flat_thread and not parent_id:
            parent_message = MailMessage_sudo.search(
                [
                    ("res_id", "=", self.id),
                    ("model", "=", self._name),
                    ("message_type", "!=", "user_notification"),
                ],
                order="id ASC",
                limit=1,
            )
            # parent_message在sudo中搜索性能，仅用于id。
            # 请注意，使用sudo我们将使消息与内部子类型匹配。
            parent_id = parent_message.id if parent_message else False
        elif parent_id:
            old_parent_id = parent_id
            parent_message = MailMessage_sudo.search(
                [("id", "=", parent_id), ("parent_id", "!=", False)], limit=1
            )
            # avoid loops when finding ancestors
            processed_list = []
            if parent_message:
                new_parent_id = parent_message.parent_id and parent_message.parent_id.id
                while new_parent_id and new_parent_id not in processed_list:
                    processed_list.append(new_parent_id)
                    parent_message = parent_message.parent_id
                parent_id = parent_message.id

        values = dict(msg_kwargs)
        values.update(
            {
                "author_id": author_id,
                "email_from": email_from,
                "model": self._name,
                "res_id": self.id,
                "body": body,
                "subject": subject or False,
                "message_type": message_type,
                "parent_id": parent_id,
                "subtype_id": subtype_id,
                "partner_ids": partner_ids,
                "channel_ids": channel_ids,
                "add_sign": add_sign,
                "record_name": record_name,
                # 以下为企业微信消息字段
                "msgtype": msgtype,
                "is_wecom_message": is_wecom_message,
                "message_to_user": message_to_user,
                "message_to_party": message_to_party,
                "message_to_tag": message_to_tag,
                "media_id": media_id,
                "body_html": body_html,
                "body_json": body_json,
                "body_markdown": body_markdown,
                "safe": safe,
                "enable_id_trans": enable_id_trans,
                "enable_duplicate_check": enable_duplicate_check,
                "duplicate_check_interval": duplicate_check_interval,
            }
        )
        attachments = attachments or []
        attachment_ids = attachment_ids or []
        attachement_values = self._message_post_process_attachments(
            attachments, attachment_ids, values
        )
        values.update(attachement_values)  # attachement_ids, [body]

        new_message = self._message_create(values)

        # 如有必要，设置主附件字段
        self._message_set_main_attachment_id(values["attachment_ids"])

        if (
            values["author_id"]
            and values["message_type"] != "notification"
            and not self._context.get("mail_create_nosubscribe")
        ):
            if (
                self.env["res.partner"].browse(values["author_id"]).active
            ):  # 我们不想将odoobot / inactive添加为关注者
                self._message_subscribe([values["author_id"]])

        self._message_post_after_hook(new_message, values)
        self._notify_thread(new_message, values, **notif_kwargs)
        return new_message

    # ------------------------------------------------------
    # 消息发布工具
    # MESSAGE POST TOOLS
    # ------------------------------------------------------
    def message_post_with_template(
        self, template_id, email_layout_xmlid=None, auto_commit=False, **kwargs
    ):
        """
        使用模板发送邮件的辅助方法
        :param template_id : 要呈现以创建消息正文的模板的ID
        :param **kwargs : 创建mail.compose.message woaerd的参数（继承自mail.message）
        """

        # 获取合成模式，或根据自身中的记录数强制使用
        if not kwargs.get("composition_mode"):
            kwargs["composition_mode"] = (
                "comment" if len(self.ids) == 1 else "mass_mail"
            )
        if not kwargs.get("message_type"):
            kwargs["message_type"] = "notification"

        if not kwargs.get("is_wecom_message"):
            kwargs["is_wecom_message"] = False
        else:
            kwargs["is_wecom_message"] = kwargs.get("is_wecom_message")
        res_id = kwargs.get("res_id", self.ids and self.ids[0] or 0)
        res_ids = kwargs.get("res_id") and [kwargs["res_id"]] or self.ids

        # Create the composer
        composer = (
            self.env["mail.compose.message"]
            .with_context(
                active_id=res_id,
                active_ids=res_ids,
                active_model=kwargs.get("model", self._name),
                default_composition_mode=kwargs["composition_mode"],
                default_model=kwargs.get("model", self._name),
                default_res_id=res_id,
                default_template_id=template_id,
                custom_layout=email_layout_xmlid,
            )
            .create(kwargs)
        )
        # 仅当模板处于单一电子邮件模式时，才模拟onchange（如窗体视图中的触发器）
        if template_id:
            update_values = composer.onchange_template_id(
                template_id, kwargs["composition_mode"], self._name, res_id
            )["value"]

            composer.write(update_values)

        return composer.with_context(
            is_wecom_message=kwargs["is_wecom_message"]
        ).send_mail(auto_commit=auto_commit)

    def message_notify(
        self,
        *,
        partner_ids=False,
        parent_id=False,
        model=False,
        res_id=False,
        author_id=None,
        email_from=None,
        body="",
        subject=False,
        # 企业微信字段 start
        msgtype=None,
        is_wecom_message=None,
        message_to_user=None,
        message_to_party=None,
        message_to_tag=None,
        media_id=None,
        body_html=None,
        body_json=None,
        body_markdown=None,
        safe=None,
        enable_id_trans=None,
        enable_duplicate_check=None,
        duplicate_check_interval=1800,
        # 企业微信字段 end
        **kwargs,
    ):
        """
        允许通知合作伙伴有关不应在文档上显示的消息的快捷方式。 像其他通知一样，它会根据用户配置将通知推送到收件箱或通过电子邮件发送。
        """
        if self:
            self.ensure_one()
        # split message additional values from notify additional values
        msg_kwargs = dict(
            (key, val)
            for key, val in kwargs.items()
            if key in self.env["mail.message"]._fields
        )
        notif_kwargs = dict(
            (key, val) for key, val in kwargs.items() if key not in msg_kwargs
        )

        author_id, email_from = self._message_compute_author(
            author_id, email_from, raise_exception=True
        )

        if not partner_ids:
            _logger.warning("Message notify called without recipient_ids, skipping")
            return self.env["mail.message"]

        if not (
            model and res_id
        ):  # both value should be set or none should be set (record)
            model = False
            res_id = False

        MailThread = self.env["mail.thread"]
        values = {
            "parent_id": parent_id,
            "model": self._name if self else False,
            "res_id": self.id if self else False,
            "message_type": "user_notification",
            "subject": subject,
            "body": body,
            "author_id": author_id,
            "email_from": email_from,
            "partner_ids": partner_ids,
            "subtype_id": self.env["ir.model.data"].xmlid_to_res_id("mail.mt_note"),
            "is_internal": True,
            "record_name": False,
            "reply_to": MailThread._notify_get_reply_to(
                default=email_from, records=None
            )[False],
            "message_id": tools.generate_tracking_message_id("message-notify"),
            "msgtype": msgtype,
            "is_wecom_message": is_wecom_message,
            "message_to_user": message_to_user,
            "message_to_party": message_to_party,
            "message_to_tag": message_to_tag,
            "media_id": media_id,
            "body_html": body_html,
            "body_json": body_json,
            "body_markdown": body_markdown,
            "safe": safe,
            "enable_id_trans": enable_id_trans,
            "enable_duplicate_check": enable_duplicate_check,
            "duplicate_check_interval": duplicate_check_interval,
        }
        values.update(msg_kwargs)
        new_message = MailThread._message_create(values)
        MailThread._notify_thread(new_message, values, **notif_kwargs)
        return new_message

    def _message_log(
        self,
        *,
        body="",
        author_id=None,
        email_from=None,
        subject=False,
        message_type="notification",
        # 企业微信字段 start
        msgtype=None,
        is_wecom_message=None,
        message_to_user=None,
        message_to_party=None,
        message_to_tag=None,
        media_id=None,
        body_html=None,
        body_json=None,
        body_markdown=None,
        safe=None,
        enable_id_trans=None,
        enable_duplicate_check=None,
        duplicate_check_interval=1800,
        # 企业微信字段 end
        **kwargs,
    ):
        """
        允许在文档上发布注释的快捷方式。 它不执行任何通知，并预先计算一些值以使短代码尽可能优化。 该方法是私有的，因为它不检查访问权限，并且以sudo的身份执行消息创建，以加快日志处理速度。 应该在已经授予访问权限的方法中调用此方法，以避免特权升级。
        """
        self.ensure_one()
        author_id, email_from = self._message_compute_author(
            author_id, email_from, raise_exception=False
        )

        message_values = {
            "subject": subject,
            "body": body,
            "author_id": author_id,
            "email_from": email_from,
            "message_type": message_type,
            "model": kwargs.get("model", self._name),
            "res_id": self.ids[0] if self.ids else False,
            "subtype_id": self.env["ir.model.data"].xmlid_to_res_id("mail.mt_note"),
            "is_internal": True,
            "record_name": False,
            "reply_to": self.env["mail.thread"]._notify_get_reply_to(
                default=email_from, records=None
            )[False],
            "message_id": tools.generate_tracking_message_id(
                "message-notify"
            ),  # 为什么？ 这只是一个通知
            "msgtype": msgtype,
            "is_wecom_message": is_wecom_message,
            "message_to_user": message_to_user,
            "message_to_party": message_to_party,
            "message_to_tag": message_to_tag,
            "media_id": media_id,
            "body_html": body_html,
            "body_json": body_json,
            "body_markdown": body_markdown,
            "safe": safe,
            "enable_id_trans": enable_id_trans,
            "enable_duplicate_check": enable_duplicate_check,
            "duplicate_check_interval": duplicate_check_interval,
        }
        message_values.update(kwargs)
        return self.sudo()._message_create(message_values)

    def _message_log_batch(
        self,
        bodies,
        author_id=None,
        email_from=None,
        subject=False,
        message_type="notification",
        # 企业微信字段 start
        msgtype=None,
        is_wecom_message=None,
        message_to_user=None,
        message_to_party=None,
        message_to_tag=None,
        media_id=None,
        body_html="",
        body_json="",
        body_markdown="",
        safe=None,
        enable_id_trans=False,
        enable_duplicate_check=False,
        duplicate_check_interval=1800,
        # 企业微信字段 end
    ):
        """
        快捷方式允许在一批文档上发布注释。 它实现了与_message_log相同的目的，该目的通过批量完成以加快快速注释日志的速度。

        :param bodies: dict {record_id: body}
        """
        author_id, email_from = self._message_compute_author(
            author_id, email_from, raise_exception=False
        )

        base_message_values = {
            "subject": subject,
            "author_id": author_id,
            "email_from": email_from,
            "message_type": message_type,
            "model": self._name,
            "subtype_id": self.env["ir.model.data"].xmlid_to_res_id("mail.mt_note"),
            "is_internal": True,
            "record_name": False,
            "reply_to": self.env["mail.thread"]._notify_get_reply_to(
                default=email_from, records=None
            )[False],
            "message_id": tools.generate_tracking_message_id(
                "message-notify"
            ),  # why? this is all but a notify
            "msgtype": msgtype,
            "is_wecom_message": is_wecom_message,
            "message_to_user": message_to_user,
            "message_to_party": message_to_party,
            "message_to_tag": message_to_tag,
            "media_id": media_id,
            "body_html": body_html,
            "body_json": body_json,
            "body_markdown": body_markdown,
            "safe": safe,
            "enable_id_trans": enable_id_trans,
            "enable_duplicate_check": enable_duplicate_check,
            "duplicate_check_interval": duplicate_check_interval,
        }
        values_list = [
            dict(base_message_values, res_id=record.id, body=bodies.get(record.id, ""))
            for record in self
        ]
        return self.sudo()._message_create(values_list)

    def _message_compute_author(
        self, author_id=None, email_from=None, raise_exception=True
    ):
        """
        计算消息的作者信息的工具方法。目的是确保发送电子邮件时，作者/当前用户/电子邮件地址之间的最大一致性。
        """
        if author_id is None:
            if email_from:
                author = self._mail_find_partner_from_emails([email_from])[0]
            else:
                author = self.env.user.partner_id
                email_from = author.email_formatted
            author_id = author.id

        if email_from is None:
            if author_id:
                author = self.env["res.partner"].browse(author_id)
                email_from = author.email_formatted

        # 没有作者电子邮件的超级用户模式->可能是公共用户；无论如何，我们不想崩溃
        if not email_from and not self.env.su and raise_exception:
            raise exceptions.UserError(
                _("Unable to log message, please configure the sender's email address.")
            )

        return author_id, email_from

    # ------------------------------------------------------
    # 通知API
    # NOTIFICATION API
    # ------------------------------------------------------
    def _notify_thread(self, message, msg_vals=False, notify_by_email=True, **kwargs):
        """
        主要通知方法。 此方法主要做两件事

        * 调用``_notify_compute_recipients``来计算接收者以基于消息记录或消息创建值（如果给定的话）进行通知（以优化性能（如果我们已经计算出数据的话））；
        * 通过调用实现的各种通知方法来执行通知过程；

        可以重写此方法以拦截和延迟通知机制，例如mail.channel审核。

        :param message: mail.message记录通知；
        :param msg_vals: 用于创建消息的值的字典。 如果给定了它，则在实际上不需要通知的一些简单情况下，使用它代替访问``self``来减少查询数量；

        Kwarg允许传递给子通知方法的各种参数。 有关其他参数的更多详细信息，请参见那些方法。
        用于电子邮件样式通知的参数
        """
        print("_notify_thread--------------", message)
        msg_vals = msg_vals if msg_vals else {}
        rdata = self._notify_compute_recipients(message, msg_vals)
        if not rdata:
            return False

        message_values = {}
        if rdata["channels"]:
            message_values["channel_ids"] = [
                (6, 0, [r["id"] for r in rdata["channels"]])
            ]

        self._notify_record_by_inbox(message, rdata, msg_vals=msg_vals, **kwargs)
        if notify_by_email:
            self._notify_record_by_email(message, rdata, msg_vals=msg_vals, **kwargs)

        return rdata

    def _notify_record_by_wecom(
        self, message, recipients_data, msg_vals=False, **kwargs
    ):
        """
        通知方式：企业微信。 做两件事
          * 为用户创建企业微信通知；
          * 创建频道/消息链接（mail.message的channel_ids字段）；
          * 发送总线通知；

        TDE/XDO TODO:直接标记rdata，例如使用r ['notif'] ='ocn_client' 和 r ['needaction'] = False并正确覆盖notify_recipients
        """

    # ------------------------------------------------------
    # 关注者API
    # FOLLOWERS API
    # ------------------------------------------------------

    # ------------------------------------------------------
    # 控制器
    # CONTROLLERS
    # ------------------------------------------------------