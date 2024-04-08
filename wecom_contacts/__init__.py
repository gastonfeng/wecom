# -*- coding: utf-8 -*-


# from . import controllers
from . import models

# from . import wizard
from odoo import api, SUPERUSER_ID, _
from odoo.exceptions import UserError


def post_init_hook(env):
    env.registry.clear_cache()
