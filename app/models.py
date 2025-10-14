# app/models.py

from datetime import date, datetime, timedelta
from app import db, login
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import json

# --- 平台用户模型 (Platform User) ---
# 这个模型只用于登录本平台的用户账户管理。
@login.user_loader
def load_user(id):
    return User.query.filter_by(id=int(id), is_active=True).first()

class User(UserMixin, db.Model):
    __tablename__ = 'platform_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    chinese_name = db.Column(db.String(64), index=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='user', nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # --- 核心修正：加回这个外键字段 ---
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    # ---------------------------------

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Platform User {self.username}>'



# --- 新增：系统账户模型 (System Account) ---
# 这个模型用于记录所有存在于目标计算机/工作站上的账户信息。
class SystemAccount(db.Model):
    __tablename__ = 'system_accounts'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    chinese_name = db.Column(db.String(64), index=True, nullable=False)

    # 反向关系，方便查询一个账户在哪些系统中有权限
    system_access = db.relationship('SystemUser', backref='account', lazy='dynamic', cascade="all, delete-orphan")
    workstation_access = db.relationship('WorkstationUser', backref='account', lazy='dynamic', cascade="all, delete-orphan")
    
    def __repr__(self):
        return f'<System Account {self.username}>'


# --- 关联表模型 (修改外键以关联到 SystemAccount) ---
class SystemUser(db.Model):
    __tablename__ = 'system_user_link'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.Integer, db.ForeignKey('system.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('system_accounts.id'), nullable=False)
    system_role = db.Column(db.String(64))
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

class WorkstationUser(db.Model):
    __tablename__ = 'workstation_user_link'
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.Integer, db.ForeignKey('system.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('system_accounts.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('system_role.id'), nullable=False)
    role = db.relationship('SystemRole')
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)


# --- 申请模型 (修改关联) ---
class UserRequest(db.Model):
    # 这个模型用于用户提交的“新增系统用户”的申请
    __tablename__ = 'user_requests'
    id = db.Column(db.Integer, primary_key=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('platform_users.id'), nullable=False)
    username = db.Column(db.String(64), nullable=False)
    chinese_name = db.Column(db.String(64), nullable=False)
    computer_role = db.Column(db.String(100), nullable=True)
    workstation_role = db.Column(db.String(100), nullable=True)
    target_systems = db.Column(db.Text, nullable=False)
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending', index=True)
    requested_by = db.relationship('User', foreign_keys=[requested_by_id])

class DisableRequest(db.Model):
    __tablename__ = 'disable_requests' # <-- 表名变更
    id = db.Column(db.Integer, primary_key=True)
    account_to_disable_id = db.Column(db.Integer, db.ForeignKey('system_accounts.id'), nullable=False) # <-- 字段名变更
    requested_by_id = db.Column(db.Integer, db.ForeignKey('platform_users.id'), nullable=False)
    request_date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(20), default='pending')
    account_to_disable = db.relationship('SystemAccount', foreign_keys=[account_to_disable_id]) # <-- 关系名变更
    requested_by = db.relationship('User', foreign_keys=[requested_by_id])


# --- 其他模型 (保持不变或微调) ---
class Group(db.Model):
    # ... (无变化)
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    users = db.relationship('User', backref='group', lazy='dynamic')
    systems = db.relationship('System', backref='group', lazy='dynamic')

# app/models.py

class System(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    system_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    # --- 常规信息 ---
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    computer_name = db.Column(db.String(100), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    is_domain_joined = db.Column(db.Boolean, default=False)
    is_workstation_domain_joined = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, nullable=True)
    warning_days = db.Column(db.Integer, default=7, nullable=False)
    
    # --- 常规核查字段 ---
    check_frequency_days = db.Column(db.Integer, default=90)
    last_check_date = db.Column(db.Date, nullable=True)
    next_check_date = db.Column(db.Date, nullable=True)
    
    # --- QA 核查专用字段 ---
    needs_qa_check = db.Column(db.Boolean, default=True, nullable=False, index=True)
    qa_last_check_date = db.Column(db.Date, nullable=True)
    qa_check_frequency_days = db.Column(db.Integer, nullable=True)
    qa_next_check_date = db.Column(db.Date, nullable=True)
    
    # --- 备份与还原字段 ---
    backup_method = db.Column(db.String(50), nullable=True)
    backup_frequency = db.Column(db.String(50), nullable=True)
    is_restore_verified = db.Column(db.Boolean, default=False)
    last_restore_verification_date = db.Column(db.Date, nullable=True)
    restore_verification_cycle = db.Column(db.Integer, nullable=True)
    
    # --- 关系 (Relationships) ---
    history = db.relationship('CheckHistory', backref='system', lazy='dynamic', cascade="all, delete-orphan")
    system_users = db.relationship('SystemUser', backref='system', lazy='dynamic', cascade="all, delete-orphan")
    workstation_users = db.relationship('WorkstationUser', backref='system', lazy='dynamic', cascade="all, delete-orphan")
    
    # --- 方法 (Methods) ---
    def get_next_verification_date(self):
        if self.is_restore_verified and self.last_restore_verification_date and self.restore_verification_cycle:
            try:
                return self.last_restore_verification_date + timedelta(days=int(365.25 * self.restore_verification_cycle))
            except (ValueError, TypeError):
                return None
        return None

    def is_due(self):
        if not self.next_check_date: return False
        return (self.next_check_date - date.today()).days <= self.warning_days

    def is_overdue(self):
        if not self.next_check_date: return False
        return (self.next_check_date - date.today()).days < 0
        
    def is_qa_due(self):
        if not self.qa_next_check_date: return False
        return (self.qa_next_check_date - date.today()).days <= self.warning_days

    def is_qa_overdue(self):
        if not self.qa_next_check_date: return False
        return (self.qa_next_check_date - date.today()).days < 0
class RoleChangeRequest(db.Model):
    __tablename__ = 'role_change_requests'
    id = db.Column(db.Integer, primary_key=True)
    
    # 申请的发起人 (平台用户)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('platform_users.id'), nullable=False)
    
    # 申请的目标
    system_id = db.Column(db.Integer, db.ForeignKey('system.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('system_accounts.id'), nullable=False)
    user_type = db.Column(db.String(20), nullable=False) # 'computer' or 'workstation'
    
    # 申请的内容
    current_role = db.Column(db.String(100), nullable=False)
    new_role = db.Column(db.String(100), nullable=False)
    
    # 申请的状态
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending', index=True) # pending, completed, rejected

    # 关系
    requested_by = db.relationship('User', backref='role_change_requests')
    system = db.relationship('System', backref='role_change_requests')
    account = db.relationship('SystemAccount', backref='role_change_requests')



class CheckHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.Integer, db.ForeignKey('system.id'), nullable=False)
    check_date = db.Column(db.Date, nullable=False, default=date.today)
    checked_by = db.Column(db.String(64))
    notes = db.Column(db.String(200))

class SystemRole(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Script(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    system_id = db.Column(db.Integer, db.ForeignKey('system.id'), nullable=False)
    script_id = db.Column(db.Integer, db.ForeignKey('script.id'), nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('platform_users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    output = db.Column(db.Text, nullable=True)
    system = db.relationship('System')
    script = db.relationship('Script')
    requester = db.relationship('User')

class MenjinDeletionRequest(db.Model):
    __tablename__ = 'menjin_deletion_requests'
    id = db.Column(db.Integer, primary_key=True)
    
    # 申请的发起人 (平台用户)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('platform_users.id'), nullable=False)
    
    # 申请的目标 (门禁用户)
    consumer_no = db.Column(db.String(64), nullable=False, index=True)
    consumer_name = db.Column(db.String(64), nullable=False)
    
    # 申请的状态
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending', index=True) # pending, completed, failed

    # 关系
    requested_by = db.relationship('User', backref='menjin_deletion_requests')

    def __repr__(self):
        return f'<MenjinDeletionRequest for {self.consumer_name}>'
    
    # ... (文件顶部的其他模型保持不变) ...



# --- 新增：部分删除申请模型 ---
class PartialDisableRequest(db.Model):
    __tablename__ = 'partial_disable_requests' # <-- 表名变更
    id = db.Column(db.Integer, primary_key=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('platform_users.id'), nullable=False)
    chinese_name = db.Column(db.String(64), nullable=False)
    system_user_links = db.Column(db.Text, nullable=True)
    workstation_user_links = db.Column(db.Text, nullable=True)
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending', index=True)
    requested_by = db.relationship('User', backref='partial_disable_requests') # <-- 关系名变更

    def get_system_links(self):
        return json.loads(self.system_user_links) if self.system_user_links else []
    def get_workstation_links(self):
        return json.loads(self.workstation_user_links) if self.workstation_user_links else []