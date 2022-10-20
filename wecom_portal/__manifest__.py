# -*- coding: utf-8 -*-
{
    "name": "WeCom Portal",
    "author": "RStudio",
    "website": "https://gitee.com/rainbowstudio/wecom",
    "sequence": 605,
    "installable": True,
    "application": True,
    "auto_install": False,
    "category": "WeCom Suites/Settings",
    "version": "15.0.0.1",
    "summary": """
        WeCom Portal
        """,
    "description": """


        """,
    "depends": ["portal", "wecom_contacts"],
    "external_dependencies": {"python": [],},
    "data": [
        "data/wecom_apps_data.xml",
        "views/portal_templates.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {"web.assets_qweb": ["wecom_portal/static/src/xml/*.xml",],},
	 "qweb": ["static/src/xml/*.xml",],
    "license": "LGPL-3",
}
