# -*- coding: utf-8 -*-

{
    "name": "Human Resources Management Information System",
    "author": "RStudio",
    "sequence": 608,
    "installable": True,
    "application": True,
    "auto_install": False,
    "category": "WeCom/WeCom",
    "website": "https://gitee.com/rainbowstudio/wecom",
    "version": "15.0.0.1",
    "summary": """
        
        """,
    "description": """

        """,
    "depends": ["hr", "wecom_contacts_sync",],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "data/hr_data.xml",
        "wizard/employee_bind_wecom_views.xml",
        "wizard/user_bind_wecom_views.xml",
        "views/ir_ui_menu_views.xml",
        "views/res_config_settings_views.xml",
        "views/hr_department_view.xml",
        "views/hr_employee_view.xml",
        "views/hr_employee_category_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # SCSSS
            # JS
            "hrmis/static/src/js/download_deps.js",
            "hrmis/static/src/js/download_staffs.js",
            "hrmis/static/src/js/download_tags.js",
        ],
        "web.assets_qweb": ["hrmis/static/src/xml/*.xml",],
    },
    "external_dependencies": {"python": [],},
    "license": "LGPL-3",
}