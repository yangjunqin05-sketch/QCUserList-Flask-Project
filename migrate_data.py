import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import create_app, db
from app.models import (
    Group, SystemRole, User, SystemAccount, System, CheckHistory, 
    Script, Job, UserRequest, DisableRequest, RoleChangeRequest, 
    MenjinDeletionRequest, PartialDisableRequest, MenjinPrivilegeDeletionRequest,
    PendingSystem, SystemUser, WorkstationUser
)

# --- 配置 ---
# 旧的 SQLite 数据库连接字符串
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
OLD_DB_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'app.db')

# 新的 MySQL 数据库连接字符串 (确保与 config.py 中的一致)
NEW_DB_URI = 'mysql+pymysql://qc_user:123456@localhost/qc_system'

# --- 创建引擎和会话 ---
old_engine = create_engine(OLD_DB_URI)
new_engine = create_engine(NEW_DB_URI)

OldSession = sessionmaker(bind=old_engine)
NewSession = sessionmaker(bind=new_engine)

old_session = OldSession()
new_session = NewSession()

def migrate_model(model_class):
    """通用模型迁移函数"""
    print(f"开始迁移模型: {model_class.__name__}...")
    
    # 从旧数据库读取所有记录
    records = old_session.query(model_class).all()
    
    for record in records:
        # 创建一个新对象用于新数据库
        # 使用 __dict__ 复制所有列属性
        data = record.__dict__
        data.pop('_sa_instance_state', None) # 移除SQLAlchemy的内部状态
        
        new_record = model_class(**data)
        new_session.add(new_record)
    
    try:
        new_session.commit()
        print(f"✓ 成功迁移 {len(records)} 条 {model_class.__name__} 记录。\n")
    except Exception as e:
        new_session.rollback()
        print(f"✗ 迁移 {model_class.__name__} 时发生错误: {e}\n")
        # 遇到错误时停止执行
        raise

if __name__ == '__main__':
    print("--- 开始数据迁移 ---")
    print("警告：请确保新数据库中的表结构已通过 'flask db upgrade' 创建完成。")

    # 迁移顺序至关重要！
    # 必须先迁移没有外键或被引用的表。
    models_to_migrate = [
        # 1. 基础数据
        Group,
        SystemRole,
        # 2. 依赖基础数据的表
        User,
        SystemAccount,
        System,
        Script,
        PendingSystem,
        # 3. 依赖上面表的表 (包含外键)
        CheckHistory,
        Job,
        UserRequest,
        DisableRequest,
        RoleChangeRequest,
        MenjinDeletionRequest,
        PartialDisableRequest,
        MenjinPrivilegeDeletionRequest,
        SystemUser,
        WorkstationUser
    ]

    try:
        for model in models_to_migrate:
            migrate_model(model)
        print("🎉 所有数据迁移成功！")
    except Exception as e:
        print(f"\n迁移过程中断。错误信息: {e}")
    finally:
        old_session.close()
        new_session.close()