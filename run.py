# # QCuserlist.py

# from app import create_app, db
# from app.models import User, System, SystemUser, WorkstationUser, SystemRole
# from config import Config
# from datetime import date, timedelta
# import click  # 导入 click 库，用于在命令行打印信息

# # 创建 app 实例，这是 Flask CLI 发现和使用的核心
# app = create_app()

# # 将 shell 上下文处理器注册到这个 app 实例上
# @app.shell_context_processor
# def make_shell_context():
#     return {'db': db, 'User': User, 'System': System, 'SystemUser': SystemUser, 
#             'WorkstationUser': WorkstationUser, 'SystemRole': SystemRole}

# # 将 init-db 命令注册到这个 app 实例上
# @app.cli.command('init-db')
# def init_db_command():
#     """创建数据库表并填充示例数据。"""
    
#     # 确保数据库操作在应用上下文中执行
#     with app.app_context():
#         db.create_all()

#         # Create roles if they don't exist
#         if not SystemRole.query.first():
#             for role_name in Config.WORKSTATION_ROLES:
#                 db.session.add(SystemRole(name=role_name))
#             db.session.commit()
#             click.echo('Created default system roles.') # 使用 click.echo 替代 print

#         # Create users if they don't exist
#         if not User.query.filter_by(username='admin').first():
#             admin_user = User(username='admin', chinese_name='系统管理员', role='admin', group='综合组')
#             admin_user.set_password('adminpass')
#             user1 = User(username='zhangsan', chinese_name='张三', role='user', group='仪器组')
#             user1.set_password('userpass')
#             user2 = User(username='lisi', chinese_name='李四', role='user', group='理化组')
#             user2.set_password('userpass')
#             user3 = User(username='wangwu', chinese_name='王五', role='user', group='微生物组')
#             user3.set_password('userpass')
#             db.session.add_all([admin_user, user1, user2, user3])
#             db.session.commit()
#             click.echo('Initialized the database and created default users.')

#         # Create systems if they don't exist
#         if not System.query.first():
#             today = date.today()
#             # ... (你的系统创建代码保持不变) ...
#             sys1 = System(name='C130H气体渗透测试仪', system_number='002-CS-54', check_frequency_days=90, 
#                           next_check_date=today + timedelta(days=10), last_check_date=today - timedelta(days=80))
#             sys2 = System(name='OpenLab CDS 2.8', system_number='002-CS-78', check_frequency_days=180, 
#                           next_check_date=today + timedelta(days=30), last_check_date=today - timedelta(days=150))
#             sys3 = System(name='离子色谱仪', system_number='002-CS-81', check_frequency_days=90, 
#                           next_check_date=today + timedelta(days=120), last_check_date=None)
#             sys4 = System(name='百万分之天平', system_number='001-EQ-12', check_frequency_days=365, 
#                           next_check_date=today - timedelta(days=5), last_check_date=today - timedelta(days=370))
#             db.session.add_all([sys1, sys2, sys3, sys4])
#             db.session.commit()

#             # Link users to systems
#             admin = User.query.filter_by(username='admin').first()
#             user1 = User.query.filter_by(username='zhangsan').first()
#             user2 = User.query.filter_by(username='lisi').first()
#             role_admin = SystemRole.query.filter_by(name='系统管理员').first()
#             role_op = SystemRole.query.filter_by(name='操作员').first()
            
#             db.session.add(SystemUser(system_id=sys1.id, user_id=user1.id, system_role='分析员'))
#             db.session.add(WorkstationUser(system_id=sys2.id, user_id=admin.id, role_id=role_admin.id))
#             db.session.add(WorkstationUser(system_id=sys2.id, user_id=user1.id, role_id=role_op.id))
#             db.session.add(WorkstationUser(system_id=sys3.id, user_id=user2.id, role_id=role_op.id))
#             db.session.commit()
#             click.echo('Created sample systems and user links.')
        
#         click.echo("Database initialization complete.")

# # 移除 if __name__ == '__main__': app.run(...)
# # 这一整块代码。因为我们将使用 `flask run` 命令来启动应用。