# app/__init__.py (最终禁用重构版)
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
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)

    with app.app_context():
        from app.routes import bp as main_bp
        app.register_blueprint(main_bp)
        from menjin import bp as menjin_bp
        app.register_blueprint(menjin_bp, url_prefix='/menjin')
        
        from app.models import (UserRequest, DisableRequest, RoleChangeRequest, 
                                MenjinDeletionRequest, PartialDisableRequest)
        @app.context_processor
        def inject_pending_requests_count():
            if current_user.is_authenticated and current_user.role == 'admin':
                try:
                    add_count = UserRequest.query.filter_by(status='pending').count()
                    disable_count = DisableRequest.query.filter_by(status='pending').count()
                    role_change_count = RoleChangeRequest.query.filter_by(status='pending').count()
                    menjin_del_count = MenjinDeletionRequest.query.filter_by(status='pending').count()
                    partial_disable_count = PartialDisableRequest.query.filter_by(status='pending').count()
                    
                    total_count = add_count + disable_count + role_change_count + menjin_del_count + partial_disable_count
                    return dict(pending_requests_count=total_count)
                except Exception:
                    return dict(pending_requests_count=0)
            return dict(pending_requests_count=0)

    from app.cli import register as register_cli
    register_cli(app)
    return app