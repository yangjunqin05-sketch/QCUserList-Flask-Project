# menjin/__init__.py

from flask import Blueprint

# 1. 创建一个名为 'menjin' 的蓝图
bp = Blueprint('menjin', __name__, template_folder='templates')

# 2. 从当前文件夹下的 routes.py 文件中导入路由函数
#    这行代码必须在 Blueprint 定义之后
from . import routes