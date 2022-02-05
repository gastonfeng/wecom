# -*- coding: utf-8 -*-


import requests
import logging
import pandas as pd

pd.set_option("max_colwidth", 4096)

from lxml import etree
import requests
from odoo import api, fields, models, SUPERUSER_ID, _

_logger = logging.getLogger(__name__)


class WecomServerApiError(models.Model):
    _name = "wecom.service_api_error"
    _description = "Wecom Server API Error"
    _order = "sequence"

    name = fields.Char(
        "Error description",
        required=True,
        readonly=True,
    )
    code = fields.Integer(
        "Error code",
        required=True,
        readonly=True,
    )

    method = fields.Char(
        "Treatment method",
        readonly=True,
    )

    sequence = fields.Integer(default=0)

    def get_error_by_code(self, code):
        res = self.search(
            [("code", "=", code)],
            limit=1,
        )
        return {
            "code": res.code,
            "name": res.name,
            "method": res.method,
        }

    def cron_pull_global_error_code(self):
        self.pull()

    @api.model
    def pull(self):
        """
        使用爬虫爬取 全局错误码
        URL的一般格式为： protocol://hostname[:port]/path/[;parameters][?query]#fragment
        """
        try:
            _logger.info(_("Start pulling the global error code of WeCom."))
            url = "https://open.work.weixin.qq.com/api/doc/90000/90139/90313"
            page_text = requests.get(url=url).text
            tree = etree.HTML(page_text)

            lis = tree.xpath("//div[@id='js_doc_preview_content']/ul/li")

            methods = []
            for li in lis:
                li_str = etree.tostring(li, encoding="utf-8").decode()
                h5 = self.getMiddleStr(li_str, "<li>", "</h5>") + "</h5>"
                code = self.getMiddleStr(h5, 'id="h5--', '"><a name=')

                method_str = li_str.replace(h5, "")
                method = self.getMiddleStr(method_str, "<li>", "</li>")

                if "-" in code:
                    multiple_codes = code.split("-", 1)
                    for multiple_code in multiple_codes:
                        multiple_dic = {}
                        multiple_dic["code"] = multiple_code
                        multiple_dic["method"] = method

                        methods.append(multiple_dic)
                else:
                    dic = {}
                    dic["code"] = code
                    dic["method"] = method

                    methods.append(dic)

            table = tree.xpath("//div[@id='js_doc_preview_content']/table")
            table = etree.tostring(
                table[0], encoding="utf-8"
            ).decode()  # 将第一个表格转成string格式
            table = table.replace("<th>错误码</th>", "<th>code</th>")
            table = table.replace("<th>错误说明</th>", "<th>name</th>")
            table = table.replace("<th>排查方法</th>", "<th>method</th>")

            df = pd.read_html(table, encoding="utf-8", header=0)[0]  # pandas读取table
            error_results = list(df.T.to_dict().values())  # 转换成列表嵌套字典的格式

            errors = []
            for index, error in enumerate(error_results):
                del error["Unnamed: 3"]
                error["sequence"] = index
                if error["method"] == "查看帮助":
                    error["method"] = self.replaceMethod(str(error["code"]), methods)
                errors.append(error)

            # 写入到odoo
            for error in errors:
                res = self.search(
                    [("code", "=", error["code"])],
                    limit=1,
                )
                if not res:
                    self.sudo().create(
                        {
                            "code": error["code"],
                            "name": error["name"],
                            "method": error["method"],
                            "sequence": error["sequence"],
                        }
                    )
                else:
                    res.sudo().write(
                        {
                            "name": error["name"],
                            "method": error["method"],
                            "sequence": error["sequence"],
                        }
                    )
            _logger.info(_("Successfully pulled the WeCom global error code!"))
            return True
        except Exception as e:
            _logger.warning(
                _("Failed to pull WeCom global error code, reason:%s") % str(e)
            )
            return False

    def replaceMethod(self, code, methods):
        """ """
        df = pd.DataFrame(methods)
        method = df["method"][df["code"] == code].to_string(
            index=False
        )  # 取 包含指定code 值的 "method"列

        # method = df["method"][df["code"].isin([code])].to_string(
        #     index=False
        # )  # 取 包含指定code 值的 "method"列

        return method

    def getMiddleStr(self, content, startStr, endStr):
        startIndex = content.index(startStr)
        if startIndex >= 0:
            startIndex += len(startStr)
        endIndex = content.index(endStr)
        return content[startIndex:endIndex]