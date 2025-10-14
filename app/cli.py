# app/cli.py

from app import db
from app.models import User, System, Group, Script, Job, SystemRole
from config import Config
import click
from datetime import date, timedelta

def register(app):
    @app.cli.command('init-db')
    def init_db_command():
        """创建数据库表并填充示例数据。"""
        with app.app_context():
            db.create_all()

            # 检查并创建分组
            if not Group.query.first():
                groups = [Group(name='仪器组'), Group(name='理化组'), Group(name='微生物组'), Group(name='综合组'), Group(name='软件系统'), Group(name='物理测试')]
                db.session.add_all(groups)
                db.session.commit()
                click.echo('Created default groups.')

            # 检查并创建系统角色
            if not SystemRole.query.first():
                for role_name in Config.WORKSTATION_ROLES:
                    db.session.add(SystemRole(name=role_name))
                db.session.commit()
                click.echo('Created default system roles.')

            # 检查并创建用户
            if not User.query.filter_by(username='admin').first():
                admin_user = User(username='admin', chinese_name='系统管理员', role='admin', group_id=Group.query.filter_by(name='综合组').first().id)
                admin_user.set_password('adminpass')
                user1 = User(username='zhangsan', chinese_name='张三', role='user', group_id=Group.query.filter_by(name='仪器组').first().id)
                user1.set_password('userpass')
                db.session.add_all([admin_user, user1])
                db.session.commit()
                click.echo('Created default users.')
            
            # 检查并创建脚本
            if not Script.query.first():
                script1 = Script(name='Get-GPO-List', description='获取本机应用的组策略列表', content='Get-GPResultantSetOfPolicy -ReportType Xml | Out-String')
                script2 = Script(name='Get-System-Info', description='获取操作系统和硬件基本信息', content='Get-ComputerInfo | Select-Object OsName, CsManufacturer, CsModel, RamSizeGB | Format-List | Out-String')
                db.session.add_all([script1, script2])
                db.session.commit()
                click.echo('Created sample scripts.')

            # 检查并创建系统
            if not System.query.first():
                today = date.today()
                sys1 = System(name='C130H气体渗透测试仪', system_number='002-CS-54', check_frequency_days=90, next_check_date=today + timedelta(days=10), group_id=Group.query.filter_by(name='物理测试').first().id, computer_name='PHY-TEST-PC01', ip_address='192.168.1.50')
                sys2 = System(name='OpenLab CDS 2.8', system_number='002-CS-78', check_frequency_days=180, next_check_date=today + timedelta(days=30), group_id=Group.query.filter_by(name='软件系统').first().id, is_domain_joined=True, computer_name='CHEMSTATION-05', ip_address='10.0.0.15')
                db.session.add_all([sys1, sys2])
                db.session.commit()
                click.echo('Created sample systems.')
            
            click.echo("Database initialization complete.")