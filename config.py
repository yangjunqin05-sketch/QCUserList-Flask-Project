import os
from datetime import timedelta # <-- 1. 引入 timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key-that-you-should-change'
    
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 预定义的工作站角色清单 (用于数据库初始化)
    WORKSTATION_ROLES = ['系统管理员', '部门管理员', '组长', '操作员', '审计员']
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=10)