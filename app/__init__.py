# app/__init__.py (最终修正版)

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from config import Config

db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'routes.login'
login.login_message = '请先登录以访问此页面。'
login.login_message_category = 'info'

def create_app(config_class=Config):
    """
    应用工厂函数
    """
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)

    with app.app_context():
        # 1. 导入并注册主应用的蓝图
        from app.routes import bp as main_bp
        app.register_blueprint(main_bp)

        # 2. 导入并注册门禁系统的蓝图
        from menjin import bp as menjin_bp
        app.register_blueprint(menjin_bp, url_prefix='/menjin')
        
        # 3. 定义上下文处理器 (核心修正区域)
        
        # 关键修正 1: 在这里导入所有需要计数的模型
        from app.models import UserRequest, DisableRequest, RoleChangeRequest, MenjinDeletionRequest

        @app.context_processor
        def inject_pending_requests_count():
            if current_user.is_authenticated and current_user.role == 'admin':
                try:
                    add_count = UserRequest.query.filter_by(status='pending').count()
                    del_count = DeletionRequest.query.filter_by(status='pending').count()
                    role_change_count = RoleChangeRequest.query.filter_by(status='pending').count()
                    
                    # 关键修正 2: 添加对门禁删除申请的计数
                    menjin_del_count = MenjinDeletionRequest.query.filter_by(status='pending').count()
                    
                    # 关键修正 3: 将门禁申请数加入总数
                    total_count = add_count + del_count + role_change_count + menjin_del_count
                    
                    return dict(pending_requests_count=total_count)
                except Exception:
                    # 这个异常捕获可以在调试时暂时注释掉，以便看到更详细的错误
                    return dict(pending_requests_count=0)
            return dict(pending_requests_count=0)

    # 4. 注册命令行命令
    from app.cli import register as register_cli
    register_cli(app)
    
    return app